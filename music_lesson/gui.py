"""Streamlit GUI for the music-lesson transcriber. Run locally with:

    streamlit run music_lesson/gui.py

Everything runs on your machine — the recordings of your lessons never leave it.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

import numpy as np
import streamlit as st

# `streamlit run music_lesson/gui.py` executes this file as a top-level script
# (no package context), so relative imports would fail. Fall back to absolute
# imports after putting the repo root on sys.path.
try:
    from .core import ATTEMPT, transcribe_lesson
    from .output import render, to_practice_sheet
    from .output import format_timings
    from .raga import all_raga_names
    from .runtime import build_info, environment_summary
    from .swara import parse_tonic
    from .transcribe import SOUTH_ASIAN_LANGUAGES
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from music_lesson.core import ATTEMPT, transcribe_lesson
    from music_lesson.output import render, to_practice_sheet
    from music_lesson.output import format_timings
    from music_lesson.raga import all_raga_names
    from music_lesson.runtime import build_info, environment_summary
    from music_lesson.swara import parse_tonic
    from music_lesson.transcribe import SOUTH_ASIAN_LANGUAGES

_SPEAKER_COLORS = ["#b45309", "#1d4ed8", "#059669", "#7c3aed", "#db2777"]


def _speaker_color(speakers: list[str], name: str) -> str:
    index = speakers.index(name) if name in speakers else 0
    return _SPEAKER_COLORS[index % len(_SPEAKER_COLORS)]


def _fmt_ts(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:d}:{secs:02d}"


def _sidebar() -> dict:
    with st.sidebar:
        st.header("Settings")

        st.subheader("Your Sa")
        tonic_text = st.text_input(
            "Tonic", value="",
            placeholder="e.g. C#3, D3, or 138.6",
            help="Leave blank to detect it. Setting it is more reliable than "
                 "any detector — you know what your tanpura is tuned to.",
        )

        st.subheader("Speech")
        model = st.selectbox(
            "Whisper model", ["tiny", "base", "small", "medium", "large-v3"],
            index=2,
            help="'small' is the floor for Hindi. 'medium' is noticeably "
                 "better on code-switching if you can wait.",
        )
        language_names = st.multiselect(
            "Languages in the recording",
            list(SOUTH_ASIAN_LANGUAGES),
            default=["Hindi", "English"],
            help="The allow-list for per-window language detection. A window "
                 "detected outside it (or written in another script) is "
                 "re-decoded as the first non-English pick — that is what "
                 "keeps Hindi in Devanagari instead of Nastaliq or worse. "
                 "For a Carnatic lesson pick Telugu/Tamil/Kannada + English. "
                 "Picking exactly one language forces it everywhere.",
        )
        beam_size = st.select_slider(
            "Decoding beam width", options=[1, 2, 3, 5], value=5,
            help="Drop to 1 for roughly 1.5-2x faster decoding at some "
                 "accuracy cost. Worth it on a first pass through a long "
                 "lesson.",
        )
        fix_vocabulary = st.checkbox(
            "Repair Hindustani vocabulary", value=True,
            help="Turns 'tea total' back into 'teentaal'. Every repair is "
                 "listed in the JSON export.",
        )
        extra_terms = st.text_input(
            "Extra vocabulary (comma separated)", value="",
            placeholder="Bageshri, Panditji, Gwalior",
            help="Primes the decoder with names it would otherwise mangle.",
        )

        st.subheader("Music")
        raga_hints = st.multiselect(
            "Raags you expect in this lesson", all_raga_names(),
            help="Type to search. Primes the transcription with the names and "
                 "scores each pick against the sung notes — 'I know this was "
                 "Kirwani' beats any detector, and a pick that does NOT fit "
                 "usually means the tonic is off.",
        )
        notation = st.radio(
            "Sargam notation",
            ["Bhatkhande  (S R\u0332 G\u0332 M\u2019 \u1e60 \u1e62)",
             "ASCII  (S r g M S' .S)"],
            horizontal=True,
            help="Bhatkhande matches your handwritten-notes conventions: "
                 "komal underlined, octave dots, M\u2019 for teevra Ma.",
        )
        sung_threshold = st.slider(
            "Singing sensitivity", 0.30, 0.75, 0.50, 0.05,
            help="Lower catches quiet humming; higher stops slow, deliberate "
                 "speech from being read as a demonstration.",
        )
        denoise = st.checkbox(
            "Denoise first", value=False,
            help="Mild high-pass + spectral denoiser before analysis. Try on "
                 "hissy phone recordings; heavy processing can smear meend "
                 "and gamak, so compare with and without.",
        )
        keep_sung_text = st.checkbox(
            "Keep Whisper's words over singing", value=False,
            help="Usually hallucination — turn on to catch bandish lyrics.",
        )

        st.subheader("Voices")
        diarize = st.checkbox("Tell guru and student apart", value=True)
        num_speakers = st.number_input(
            "How many voices (0 = auto)", min_value=0, max_value=8, value=0,
            disabled=not diarize,
        )

        st.divider()
        summary = environment_summary()
        if "Rosetta" in summary:
            st.warning(summary)
        else:
            st.caption(summary)
        st.caption(build_info())

    return {
        "tonic_text": tonic_text.strip(),
        "raga_hints": raga_hints,
        "notation": "ascii" if notation.startswith("ASCII") else "bhatkhande",
        "model": model,
        "languages": [SOUTH_ASIAN_LANGUAGES[n] for n in language_names],
        "beam_size": beam_size,
        "fix_vocabulary": fix_vocabulary,
        "extra_terms": [t.strip() for t in extra_terms.split(",") if t.strip()],
        "sung_threshold": sung_threshold,
        "denoise": denoise,
        "keep_sung_text": keep_sung_text,
        "diarize": diarize,
        "num_speakers": int(num_speakers) or None,
    }


def _load_preview(path: str):
    """Envelope + duration for the waveform view, cached per file.

    Decodes the file once (seconds, not minutes) so the person can see where
    the lesson's sections are and audition settings on a slice instead of
    committing an hour to a full pass.
    """
    key = f"preview::{path}::{os.path.getmtime(path)}"
    if st.session_state.get("preview_key") == key:
        return st.session_state["preview"]

    from transcriber import audio as _audio

    wav = _audio.extract_audio(path)
    try:
        samples, rate = _audio.load_waveform(wav)
    finally:
        try:
            os.unlink(wav)
        except OSError:
            pass
    duration = len(samples) / rate
    # ~1500 columns of peak amplitude: enough to see structure, cheap to draw.
    columns = max(1, len(samples) // 1500)
    trimmed = samples[: (len(samples) // columns) * columns]
    envelope = np.abs(trimmed).reshape(-1, columns).max(axis=1)
    preview = {"duration": duration, "envelope": envelope}
    st.session_state["preview_key"] = key
    st.session_state["preview"] = preview
    return preview


def _section_picker(source: str, settings: dict) -> tuple[float, float] | None:
    """Waveform + range slider; returns (start, end) or None for the whole file."""
    with st.expander("Preview & pick a section", expanded=False):
        st.audio(source)
        try:
            with st.spinner("Decoding waveform…"):
                preview = _load_preview(source)
        except Exception as exc:
            st.warning(f"Could not decode a preview: {exc}")
            return None
        duration = preview["duration"]
        envelope = preview["envelope"]
        st.area_chart(
            {
                "minutes": np.linspace(0, duration / 60, len(envelope)),
                "level": envelope,
            },
            x="minutes", y="level", height=120,
        )
        start, end = st.slider(
            "Section (seconds)", 0.0, float(round(duration, 1)),
            (0.0, float(round(duration, 1))), step=1.0,
            help="Drag the ends in to transcribe just that slice — the fast "
                 "way to audition settings (Sa, singing sensitivity, model) "
                 "before a full run. Timestamps in the output stay true to "
                 "the full recording.",
        )
        st.caption(
            f"Selected {_fmt_ts(start)} – {_fmt_ts(end)} "
            f"({_fmt_ts(end - start)} of {_fmt_ts(duration)})"
        )
        chosen = (
            (float(start), float(end))
            if start > 0.0 or end < duration - 0.5 else None
        )
        if st.button("Analyze pitch of selection  ·  fast, no speech model"):
            st.session_state["analysis_request"] = chosen or (0.0, duration)
        request = st.session_state.get("analysis_request")
        if request is not None:
            _render_pitch_analysis(source, request, settings)
        return chosen
    return None


def _build_pitch_chart(
    contour_df, region_df, grid_df, x_domain, y_domain,
    notes_df=None, glide_df=None, height=None,
):
    """Layered vega spec: bands, swara grid, labels, pitch dots, note bars.

    The note bars are the point of the whole view: green bars are what became
    sargam, grey bars are pitch the tracker held but the classifier did not
    count as singing, and gold links are meends — so "why is this phrase
    missing from my transcript" has a visual answer.

    Interaction follows the piano-roll convention rather than the map
    convention: the wheel zooms TIME only (drag pans, double-click resets),
    and vertical detail comes from the caller's *height* plus a cropped
    *y_domain* — zooming both axes at once just made everything drift, and a
    chart whose pixel height never grows cannot gain vertical detail however
    hard the scale zooms.

    Kept free of streamlit calls so the spec can be compiled in tests — an
    earlier version crashed at runtime on an altair v6 rule that no import
    check could catch.
    """
    import altair as alt
    import pandas as pd

    grid_df = grid_df.copy()
    grid_df["width"] = grid_df["kind"].map(
        {"sa": 1.6, "pa": 1.1, "komal": 0.4, "shuddha": 0.55}
    )
    x_scale = alt.Scale(domain=list(x_domain), nice=False)
    y_scale = alt.Scale(domain=list(y_domain))
    y_axis = alt.Axis(title=None, labels=False, ticks=False, grid=False)

    bands = alt.Chart(region_df).mark_rect().encode(
        x=alt.X("start:Q", scale=x_scale, title="seconds (recording time)"),
        x2="end:Q",
        color=alt.Color(
            "kind:N",
            scale=alt.Scale(
                domain=["sung", "spoken", "drone", "silent"],
                range=["#2e7d32", "#78909c", "#b8860b", "#bdbdbd"],
            ),
            legend=alt.Legend(title=None, orient="top"),
        ),
        opacity=alt.Opacity(
            "kind:N",
            scale=alt.Scale(domain=["sung", "spoken", "drone", "silent"],
                            range=[0.22, 0.07, 0.18, 0.05]),
            legend=None,
        ),
    )
    solid = alt.Chart(grid_df[grid_df["kind"] != "komal"]).mark_rule(
        opacity=0.6,
    ).encode(
        y=alt.Y("semi:Q", scale=y_scale, axis=y_axis),
        strokeWidth=alt.StrokeWidth("width:Q", scale=None, legend=None),
    )
    komal = alt.Chart(grid_df[grid_df["kind"] == "komal"]).mark_rule(
        opacity=0.5, strokeDash=[3, 4], strokeWidth=0.4,
    ).encode(y=alt.Y("semi:Q", scale=y_scale, axis=y_axis))
    labels = alt.Chart(grid_df).mark_text(
        align="left", dx=3, fontSize=11, color="#555555",
    ).encode(y=alt.Y("semi:Q", scale=y_scale, axis=y_axis),
             text="swara:N", x=alt.value(2))
    contour = alt.Chart(contour_df).mark_circle(
        size=5, opacity=0.6, clip=True,
    ).encode(
        x=alt.X("t:Q", scale=x_scale),
        y=alt.Y("semi:Q", scale=y_scale, axis=y_axis),
        color=alt.value("#1a5b8f"),
    )

    layers = [bands, solid, komal, labels, contour]

    if glide_df is not None and len(glide_df):
        layers.append(
            alt.Chart(glide_df).mark_line(
                strokeWidth=2.2, opacity=0.9, color="#b8860b", clip=True,
            ).encode(
                x=alt.X("t:Q", scale=x_scale),
                y=alt.Y("semi:Q", scale=y_scale, axis=y_axis),
                detail="gid:N",
            )
        )
    if notes_df is None:
        notes_df = pd.DataFrame(
            columns=["start", "end", "lo", "hi", "swara", "status",
                     "duration", "cents_off"]
        )
    layers.append(
        alt.Chart(notes_df).mark_rect(cornerRadius=2, clip=True).encode(
            x=alt.X("start:Q", scale=x_scale),
            x2="end:Q",
            y=alt.Y("lo:Q", scale=y_scale, axis=y_axis),
            y2="hi:Q",
            color=alt.Color(
                "status:N",
                scale=alt.Scale(domain=["in the sargam", "detected, not sung"],
                                range=["#1b5e20", "#8d8d8d"]),
                legend=alt.Legend(title=None, orient="top"),
            ),
            opacity=alt.Opacity(
                "status:N",
                scale=alt.Scale(domain=["in the sargam", "detected, not sung"],
                                range=[0.85, 0.45]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("swara:N", title="swara"),
                alt.Tooltip("duration:Q", title="held (s)", format=".2f"),
                alt.Tooltip("cents_off:Q", title="cents off", format="+.0f"),
                alt.Tooltip("status:N", title="status"),
            ],
        )
    )

    rows = int(y_domain[1] - y_domain[0]) + 1
    zoom_time = alt.selection_interval(bind="scales", encodings=["x"])
    return alt.layer(*layers).properties(
        height=height or max(340, rows * 15)
    ).add_params(zoom_time)


def _render_pitch_analysis(
    source: str, clip: tuple[float, float], settings: dict
) -> None:
    """The sonic X-ray: pitch contour on the swara grid, regions shaded.

    Runs only the NumPy side of the pipeline — seconds, not minutes — so it is
    the tool for seeing what the tracker hears *before* spending a Whisper run
    on it: whether the taans register as singing, whether the tracker is
    following the voice or the harmonium, where Sa sits.
    """
    import pandas as pd

    from music_lesson.pitch import hz_to_cents, track_pitch
    from music_lesson.segmentation import classify_regions
    from music_lesson.swara import (
        _HIST_REF_HZ, detect_tonic, parse_tonic, sargam_line, segment_notes,
        swara_label,
    )
    from transcriber import audio as _audio

    start, end = clip
    key = (
        f"analysis::{source}::{os.path.getmtime(source)}::{start:.1f}"
        f"::{end:.1f}::{settings['tonic_text']}::{settings['sung_threshold']}"
    )
    if st.session_state.get("analysis_key") != key:
        with st.spinner("Analyzing pitch…"):
            wav = _audio.extract_audio(source, start=start, duration=end - start)
            try:
                samples, rate = _audio.load_waveform(wav)
            finally:
                try:
                    os.unlink(wav)
                except OSError:
                    pass
            track = track_pitch(samples, rate)
            if settings["tonic_text"]:
                try:
                    tonic = parse_tonic(settings["tonic_text"])
                except ValueError:
                    tonic = 0.0
            else:
                tonic = 0.0
            if not tonic:
                tonic = detect_tonic(
                    track, segment_notes(track, _HIST_REF_HZ)
                ).hz
            notes = segment_notes(track, tonic) if tonic else []
            regions = classify_regions(
                track, notes, tonic, sung_threshold=settings["sung_threshold"]
            )
            st.session_state["analysis_key"] = key
            st.session_state["analysis"] = (track, tonic, notes, regions)
    track, tonic, notes, regions = st.session_state["analysis"]

    if not tonic or not track.voiced.any():
        st.warning("No pitched material found in this selection.")
        return

    cents = hz_to_cents(track.f0, tonic)
    voiced = ~np.isnan(cents)
    times = track.times[voiced] + start
    semis = cents[voiced] / 100.0
    if len(times) > 4000:                    # keep the chart responsive
        step = int(np.ceil(len(times) / 4000))
        times, semis = times[::step], semis[::step]

    full_lo = max(int(np.floor(np.percentile(semis, 2))) - 1, -17)
    full_hi = min(int(np.ceil(np.percentile(semis, 98))) + 1, 26)

    # Piano-roll controls (think a DAW's midi editor): the wheel zooms time
    # only, so vertical detail comes from these two — taller rows, and
    # cropping away the octaves you are not looking at.
    size_col, range_col = st.columns([1, 2])
    with size_col:
        row_px = st.slider("Row height (px)", 10, 44, 18, 2,
                           key="chart_row_px")
    with range_col:
        lo, hi = st.slider(
            "Swara range shown (semitones from Sa)",
            full_lo, full_hi, (full_lo, full_hi), 1,
            key="chart_y_range",
            help="Crop to the octaves in play — the drone octave rarely "
                 "needs the same space as the melody.",
        )
    if hi <= lo:
        hi = lo + 1

    grid = pd.DataFrame([
        {
            "semi": r,
            "swara": swara_label(((r % 12) + 12) % 12, r // 12),
            "kind": "sa" if r % 12 == 0 else
                    "pa" if ((r % 12) + 12) % 12 == 7 else
                    "komal" if ((r % 12) + 12) % 12 in (1, 3, 6, 8, 10) else "shuddha",
        }
        for r in range(lo, hi + 1)
    ])
    region_df = pd.DataFrame([
        {"start": r.start + start, "end": r.end + start, "kind": r.kind}
        for r in regions
    ])
    contour_df = pd.DataFrame({"t": times, "semi": semis})

    from music_lesson.swara import detect_glides

    def in_sung(note):
        return any(
            r.kind == "sung" and r.overlap(note.start, note.end) > 0.5 * note.duration
            for r in regions
        )

    notes_df = pd.DataFrame([
        {
            "start": n.start + start, "end": n.end + start,
            "lo": n.cents / 100.0 - 0.22, "hi": n.cents / 100.0 + 0.22,
            "swara": n.label(), "duration": n.duration,
            "cents_off": n.deviation,
            "status": "in the sargam" if in_sung(n) else "detected, not sung",
        }
        for n in notes
    ])
    glide_rows = []
    for gid, g in enumerate(detect_glides(track, tonic, notes)):
        a, b = notes[g.index], notes[g.index + 1]
        glide_rows.append({"gid": gid, "t": a.end + start, "semi": a.cents / 100.0})
        glide_rows.append({"gid": gid, "t": b.start + start, "semi": b.cents / 100.0})
    glide_df = pd.DataFrame(glide_rows)

    chart = _build_pitch_chart(
        contour_df, region_df, grid, (start, end), (lo, hi), notes_df, glide_df,
        height=(hi - lo + 1) * row_px,
    )
    st.altair_chart(chart, use_container_width=True)

    sung = sum(r.duration for r in regions if r.kind == "sung")
    spoken = sum(r.duration for r in regions if r.kind == "spoken")
    from music_lesson.swara import describe_hz
    st.caption(
        f"Sa = {describe_hz(tonic)} · {_fmt_ts(sung)} sung / "
        f"{_fmt_ts(spoken)} spoken in this selection · wheel zooms time, drag "
        f"pans, double-click resets; use the sliders for vertical size · dots = tracked pitch, green bars = "
        f"notes in the sargam, grey bars = held pitch not counted as singing "
        f"(hover any bar for its swara), gold links = meend. If the dots ride "
        f"the harmonium instead of the voice, the sargam will too."
    )
    sung_notes = [n for n in notes if any(
        r.kind == "sung" and r.overlap(n.start, n.end) > 0.5 * n.duration
        for r in regions
    )]
    if sung_notes:
        st.code(sargam_line(sung_notes, max_notes=80), language=None)


def _pick_input() -> str | None:
    tab_path, tab_upload = st.tabs(["Local file path", "Upload"])
    with tab_path:
        path = st.text_input(
            "Path to the recording",
            placeholder="/Users/you/lessons/2024-03-12-yaman.m4a",
            help="Best for long lessons — no upload size limit, no copy.",
        )
        if path and os.path.exists(path):
            return path
        if path:
            st.error(f"No file at {path}")
    with tab_upload:
        upload = st.file_uploader(
            "Audio or video", type=["mp3", "m4a", "wav", "aac", "flac",
                                    "ogg", "mp4", "mov", "mkv"],
        )
        if upload is not None:
            suffix = os.path.splitext(upload.name)[1] or ".m4a"
            handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            handle.write(upload.getbuffer())
            handle.close()
            return handle.name
    return None


def _show_summary(result) -> None:
    timing = format_timings(result.timings)
    if timing:
        st.caption(timing.capitalize())
    for notice in result.notices:
        st.info(notice)

    left, middle, right = st.columns(3)
    left.metric("Sa (tonic)", result.tonic.western, f"{result.tonic.hz:.1f} Hz")
    middle.metric("Sung", _fmt_ts(result.sung_seconds))
    right.metric("Spoken", _fmt_ts(result.spoken_seconds))

    st.markdown(f"**Scale:** {result.scale.summary()}")
    if result.mentions.get("ragas"):
        st.markdown(f"**Raags named out loud:** {', '.join(result.mentions['ragas'])}")
    if result.mentions.get("talas"):
        st.markdown(f"**Taals named:** {', '.join(result.mentions['talas'])}")
    if result.tonic.confidence < 0.25 and result.sung_seconds > 0:
        st.warning(
            "Sa was hard to pin down, and the sargam is only as good as the "
            "tonic. Type your Sa in the sidebar and re-run."
        )


def _show_transcript(result) -> None:
    for segment in result.segments:
        color = _speaker_color(result.speakers, segment.speaker)
        who = segment.speaker or ""
        stamp = _fmt_ts(segment.start)
        if segment.is_sung:
            label = "sings back" if segment.kind == ATTEMPT else "sings"
            st.markdown(
                f"<div style='margin-bottom:0.55rem'>"
                f"<span style='color:#6b7280'>{stamp}</span> "
                f"<b style='color:{color}'>{who}</b> "
                f"<i style='color:#6b7280'>{label}</i><br>"
                f"<code style='font-size:1.05rem;letter-spacing:0.08em'>"
                f"{segment.sargam}</code></div>",
                unsafe_allow_html=True,
            )
        else:
            roman = (
                f"<br><span style='color:#6b7280;font-size:0.9rem'>{segment.roman}</span>"
                if segment.roman else ""
            )
            st.markdown(
                f"<div style='margin-bottom:0.55rem'>"
                f"<span style='color:#6b7280'>{stamp}</span> "
                f"<b style='color:{color}'>{who}</b>: {segment.text}{roman}</div>",
                unsafe_allow_html=True,
            )


def main() -> None:
    st.set_page_config(page_title="Music Lesson Transcriber", page_icon="🎼",
                       layout="wide")
    st.title("🎼 Hindustani lesson transcriber")
    st.caption(
        "Separates the singing from the talking, writes the singing as sargam "
        "against your Sa, and transcribes the Hindi/English explanation around "
        "it. Runs entirely on your machine."
    )

    settings = _sidebar()
    source = _pick_input()
    clip = _section_picker(source, settings) if source else None

    label = (
        f"Transcribe {_fmt_ts(clip[1] - clip[0])} section" if clip
        else "Transcribe lesson"
    )
    if st.button(label, type="primary", disabled=source is None):
        tonic = None
        if settings["tonic_text"]:
            try:
                tonic = parse_tonic(settings["tonic_text"])
            except ValueError as exc:
                st.error(str(exc))
                return

        bar = st.progress(0.0, text="Starting…")
        started = time.monotonic()

        def progress(stage: str, frac: float) -> None:
            minutes, seconds = divmod(int(time.monotonic() - started), 60)
            bar.progress(
                min(frac, 1.0), text=f"{stage}  ·  {minutes:d}:{seconds:02d} elapsed"
            )

        try:
            result = transcribe_lesson(
                source,
                whisper_model=settings["model"],
                languages=settings["languages"],
                tonic=tonic,
                diarize_speakers=settings["diarize"],
                num_speakers=settings["num_speakers"],
                extra_terms=settings["extra_terms"],
                fix_vocabulary=settings["fix_vocabulary"],
                keep_sung_text=settings["keep_sung_text"],
                denoise=settings["denoise"],
                clip=clip,
                sung_threshold=settings["sung_threshold"],
                beam_size=settings["beam_size"],
                notation=settings["notation"],
                raga_hints=settings["raga_hints"],
                progress=progress,
            )
        except (RuntimeError, FileNotFoundError, ValueError) as exc:
            bar.empty()
            st.error(str(exc))
            return
        bar.empty()
        st.session_state["result"] = result

    result = st.session_state.get("result")
    if result is None:
        return

    _show_summary(result)
    sheet_tab, transcript_tab, download_tab = st.tabs(
        ["Practice sheet", "Transcript", "Download"]
    )
    with sheet_tab:
        st.markdown(to_practice_sheet(result))
    with transcript_tab:
        _show_transcript(result)
    with download_tab:
        stem = os.path.splitext(os.path.basename(result.source))[0]
        for fmt, label, mime in [
            ("md", "Practice sheet (.md)", "text/markdown"),
            ("txt", "Transcript (.txt)", "text/plain"),
            ("srt", "Subtitles (.srt)", "text/plain"),
            ("json", "Everything (.json)", "application/json"),
        ]:
            st.download_button(
                label, data=render(result, fmt),
                file_name=f"{stem}.{fmt}", mime=mime, key=f"dl_{fmt}",
            )


if __name__ == "__main__":
    main()
