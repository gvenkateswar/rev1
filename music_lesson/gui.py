"""Streamlit GUI for the music-lesson transcriber. Run locally with:

    streamlit run music_lesson/gui.py

Everything runs on your machine — the recordings of your lessons never leave it.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

import streamlit as st

# `streamlit run music_lesson/gui.py` executes this file as a top-level script
# (no package context), so relative imports would fail. Fall back to absolute
# imports after putting the repo root on sys.path.
try:
    from .core import ATTEMPT, transcribe_lesson
    from .output import render, to_practice_sheet
    from .output import format_timings
    from .raga import all_raga_names
    from .runtime import environment_summary
    from .swara import parse_tonic
    from .transcribe import SOUTH_ASIAN_LANGUAGES
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from music_lesson.core import ATTEMPT, transcribe_lesson
    from music_lesson.output import render, to_practice_sheet
    from music_lesson.output import format_timings
    from music_lesson.raga import all_raga_names
    from music_lesson.runtime import environment_summary
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

    if st.button("Transcribe lesson", type="primary", disabled=source is None):
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
