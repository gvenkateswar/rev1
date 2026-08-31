"""Streamlit GUI for the transcriber.  Run locally with:

    streamlit run transcriber/gui.py

It opens in your browser but runs entirely on your machine — nothing is
uploaded anywhere.
"""
from __future__ import annotations

import html
import os
import sys
import tempfile
import traceback

import streamlit as st

# `streamlit run transcriber/gui.py` executes this file as a top-level script
# (no package context), so relative imports would fail. Fall back to absolute
# imports after putting the repo root on sys.path.
#
# Either path runs transcriber/__init__.py, which sets the OpenMP flag before
# torch or ctranslate2 can load. Keep that import ahead of anything heavier.
try:
    from .runtime import environment_warnings
    from .core import transcribe_file
    from .emotion import _EMOJI
    from .identify import DEFAULT_MIN_ENROLL_SECONDS
    from .output import LOW_CONFIDENCE, render, renderings
    from .speakerdb import SpeakerStore, default_db_path
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from transcriber.runtime import environment_warnings
    from transcriber.core import transcribe_file
    from transcriber.emotion import _EMOJI
    from transcriber.identify import DEFAULT_MIN_ENROLL_SECONDS
    from transcriber.output import LOW_CONFIDENCE, render, renderings
    from transcriber.speakerdb import SpeakerStore, default_db_path

# Stable colors per speaker slot (cycled if there are more speakers).
_SPEAKER_COLORS = [
    "#2563eb", "#dc2626", "#059669", "#d97706",
    "#7c3aed", "#0891b2", "#db2777", "#65a30d",
]


def _speaker_color(speakers: list[str], name: str) -> str:
    idx = speakers.index(name) if name in speakers else 0
    return _SPEAKER_COLORS[idx % len(_SPEAKER_COLORS)]


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def main() -> None:
    st.set_page_config(page_title="Speaker & Emotion Transcriber", page_icon="🎙️",
                       layout="wide")
    st.title("🎙️ Speaker & Emotion Transcriber")
    st.caption(
        "Transcribe audio/video, tell speakers apart, and read each segment's "
        "emotion — fused from voice tone *and* what was said."
    )

    # Also to stderr: when the environment is bad enough to crash the process
    # (a mismatched interpreter segfaults before or during model loading), the
    # browser never renders, and the terminal is the only place left to look.
    for note in environment_warnings():
        st.warning(note)
        sys.stderr.write(f"Note: {note}\n")

    with st.sidebar:
        st.header("Settings")
        model = st.selectbox(
            "Whisper model",
            ["tiny", "base", "small", "medium", "large-v3", "distil-large-v3"],
            index=1,
            help="Bigger = more accurate but slower. For anything other than "
                 "English, use 'small' or better: the tiny and base models "
                 "have high error rates on non-English speech and drift into "
                 "English on their own.",
        )
        language = st.text_input("Language (blank = auto-detect)", value="")
        multilingual = st.checkbox(
            "Allow the language to change mid-recording", value=True,
            disabled=bool(language),
            help="Re-detects the language every 30s, so a bilingual "
                 "conversation transcribes correctly throughout. Ignored when "
                 "a language is pinned above.",
        )
        transliterate = st.checkbox(
            "Transliterate non-Latin scripts", value=True,
            help="Spells non-Latin speech in the Latin alphabet as well, so "
                 "you can follow along without reading the script.",
        )
        translate = st.checkbox(
            "Translate non-English speech", value=True,
            help="Adds an English translation. This is a second Whisper pass "
                 "over the non-English stretches only, so it roughly doubles "
                 "the time spent on those parts.",
        )

        st.subheader("Speakers")
        backend = st.radio(
            "Diarization backend", ["cluster", "pyannote"],
            captions=["Offline, no token needed", "Best quality, needs HF token"],
        )
        hf_token = ""
        if backend == "pyannote":
            hf_token = st.text_input(
                "Hugging Face token", type="password",
                value=os.environ.get("HF_TOKEN", ""),
                help="Accept the license at hf.co/pyannote/speaker-diarization-3.1",
            )
        known = st.checkbox("I know the number of speakers")
        num_speakers = st.number_input("Speakers", 1, 12, 2) if known else None

        identify = st.checkbox(
            "Recognise speakers I've named before", value=True,
            help="Matches each voice against your saved speakers and tags "
                 "them automatically.",
        )
        threshold = st.slider(
            "Recognition strictness", 0.50, 0.95, 0.72, 0.01,
            disabled=not identify,
            help="Higher = fewer mistaken identities but more voices left "
                 "unnamed. 0.72 is a good default.",
        )
        _render_speaker_manager()

        st.subheader("Emotion")
        detect_emotion = st.checkbox("Detect emotion", value=True)
        source = st.radio(
            "Emotion source", ["both", "audio", "text"], index=0,
            captions=["Voice tone + words (recommended)", "Voice tone only",
                      "Transcript only"],
            disabled=not detect_emotion,
        )
        audio_weight = st.slider(
            "Tone vs. words", 0.0, 1.0, 0.5, 0.05,
            help="0 = trust the words, 1 = trust the voice. 0.5 weighs both.",
            disabled=not detect_emotion or source != "both",
        )

    uploaded = st.file_uploader(
        "Upload audio or video",
        type=["wav", "mp3", "m4a", "flac", "ogg", "mp4", "mov", "mkv", "webm"],
    )
    local_path = st.text_input("…or paste a path to a local file", value="")

    if st.button("Transcribe", type="primary", disabled=not (uploaded or local_path)):
        src = _resolve_source(uploaded, local_path)
        if src is None:
            st.error("Please upload a file or enter a valid local path.")
            return
        _run(src, model, language, multilingual, transliterate, translate,
             backend, hf_token, num_speakers, identify, threshold,
             detect_emotion, source, audio_weight)

    # Rendered outside the button so it survives the rerun that naming causes.
    if st.session_state.get("result") is not None:
        result = st.session_state["result"]
        _render_summary(result)
        _render_naming(result)
        _render_transcript(result, st.session_state.get("detect_emotion", True))
        _render_downloads(result, st.session_state.get("detect_emotion", True))


def _render_speaker_manager() -> None:
    """Sidebar list of remembered speakers, with a delete control."""
    with st.expander("Remembered speakers"):
        try:
            with SpeakerStore() as store:
                speakers = store.all_speakers()
        except Exception as exc:
            st.warning(f"Could not open the speaker store: {exc}")
            return

        if not speakers:
            st.caption(
                "None yet. Transcribe a file, then name the speakers below — "
                "they'll be recognised automatically next time."
            )
            return

        for s in speakers:
            col_name, col_del = st.columns([3, 1])
            col_name.write(f"**{s.name}**  \n<small>{s.sample_count} "
                           f"voiceprint(s)</small>", unsafe_allow_html=True)
            if col_del.button("Forget", key=f"forget_{s.id}"):
                with SpeakerStore() as store:
                    store.forget(s.name)
                st.rerun()
        st.caption(f"Stored locally at `{default_db_path()}`.")


def _resolve_source(uploaded, local_path: str) -> str | None:
    if uploaded is not None:
        suffix = os.path.splitext(uploaded.name)[1] or ".bin"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.write(uploaded.getbuffer())
        tmp.close()
        return tmp.name
    if local_path and os.path.exists(local_path):
        return local_path
    return None


def _run(src, model, language, multilingual, transliterate, translate,
         backend, hf_token, num_speakers,
         identify, threshold, detect_emotion, source, audio_weight) -> None:
    bar = st.progress(0.0, text="Starting…")

    def progress(stage: str, frac: float) -> None:
        bar.progress(min(1.0, frac), text=stage)

    try:
        result = transcribe_file(
            src,
            whisper_model=model,
            language=language or None,
            multilingual=multilingual,
            transliterate=transliterate,
            translate=translate,
            identify_speakers=identify,
            match_threshold=threshold,
            diarization_backend=backend,
            num_speakers=num_speakers,
            hf_token=hf_token or None,
            detect_emotion=detect_emotion,
            audio_weight=audio_weight,
            use_audio_emotion=source in ("both", "audio"),
            use_text_emotion=source in ("both", "text"),
            progress=progress,
        )
    except Exception as exc:  # surface any backend/runtime error to the user
        bar.empty()
        # Streamlit collapses single newlines, and these messages are
        # multi-line on purpose; two trailing spaces make markdown keep them.
        st.error("Failed: " + str(exc).replace("\n", "  \n"))
        # The browser only ever shows str(exc). The chained cause -- which is
        # where a dependency failure actually names itself -- is only in the
        # traceback, so put that where the terminal can see it.
        traceback.print_exc()
        return

    bar.empty()
    st.session_state["result"] = result
    st.session_state["detect_emotion"] = detect_emotion


def _render_summary(result) -> None:
    langs = ", ".join(result.languages) if result.languages else result.language
    st.success(
        f"Done in {result.timings.get('total', 0):.1f}s — "
        f"{len(result.segments)} segments, "
        f"{len(result.speakers)} speaker(s), language: {langs}"
    )
    if result.identified:
        st.info(
            "Recognised from your saved speakers: "
            + ", ".join(f"**{n}**" for n in sorted(set(result.identified.values())))
        )
    if result.is_multilingual:
        breakdown = " · ".join(
            f"{lang} {secs:.0f}s" for lang, secs in result.languages.items()
        )
        st.caption(f"Multiple languages detected — {breakdown}")
    if result.timings:
        cols = st.columns(len(result.timings))
        for col, (stage, secs) in zip(cols, result.timings.items()):
            col.metric(stage.title(), f"{secs:.1f}s")
        st.caption(
            "First run loads models; later runs reuse them and are much faster."
        )


def _render_naming(result) -> None:
    """Let the user name unrecognised speakers, saving their voiceprints."""
    unnamed = [
        label for label in result.speakers
        if label in result.voiceprints and label not in result.identified.values()
    ]
    if not unnamed:
        return

    with st.expander("Name these speakers so they're recognised next time",
                     expanded=True):
        with st.form("name_speakers"):
            entries: dict[str, str] = {}
            for label in unnamed:
                print_ = result.voiceprints[label]
                col_a, col_b = st.columns([1, 2])
                col_a.write(f"**{label}**")
                if print_.enrollable:
                    entries[label] = col_b.text_input(
                        f"Name for {label}", key=f"name_{label}",
                        label_visibility="collapsed", placeholder="e.g. Priya",
                    )
                else:
                    # Enrolling on a few seconds of speech produces a voiceprint
                    # that degrades every later match, so we don't offer it.
                    col_b.caption(
                        f"Only {print_.speech_seconds:.1f}s of speech — needs "
                        f"{DEFAULT_MIN_ENROLL_SECONDS:.0f}s to remember reliably."
                    )
            if st.form_submit_button("Remember these voices", type="primary"):
                _save_names(result, entries)


def _save_names(result, entries: dict[str, str]) -> None:
    saved: list[str] = []
    try:
        with SpeakerStore() as store:
            for label, name in entries.items():
                name = (name or "").strip()
                if not name:
                    continue
                store.enroll(
                    name, result.voiceprints[label].vector,
                    source=result.source,
                    duration=result.voiceprints[label].speech_seconds,
                )
                saved.append(name)
                # Relabel the transcript in place so the user sees the effect.
                for seg in result.segments:
                    if seg.speaker == label:
                        seg.speaker, seg.known_speaker = name, True
                result.identified[label] = name
                result.speakers = [
                    name if s == label else s for s in result.speakers
                ]
                result.voiceprints[name] = result.voiceprints.pop(label)
    except (ValueError, KeyError) as exc:
        st.error(f"Could not save: {exc}")
        return

    if saved:
        st.success(f"Remembered {', '.join(saved)}. They'll be tagged "
                   "automatically in future transcripts.")
        st.rerun()


def _render_transcript(result, detect_emotion: bool) -> None:
    st.subheader("Transcript")
    show_lang = result.is_multilingual
    for seg in result.segments:
        color = _speaker_color(result.speakers, seg.speaker)
        # A check mark distinguishes a name we recognised from one the user is
        # about to assign, so nobody mistakes a guess for a confirmed identity.
        known = " ✓" if seg.known_speaker else ""
        lang = ""
        if show_lang:
            lang = (f" <span style='background:#eef;color:#446;padding:0 .4em;"
                    f"border-radius:3px;font-size:0.75em'>{seg.language}</span>")
        conf = ""
        if seg.confidence < LOW_CONFIDENCE:
            conf = (f" <span style='color:#b45309;font-size:0.75em' "
                    f"title='Whisper was unsure of these words'>"
                    f"⚠ {seg.confidence:.0%}</span>")
        emo = ""
        if detect_emotion:
            emoji = _EMOJI.get(seg.emotion, "")
            detail = ""
            if seg.audio_emotion and seg.text_emotion and \
                    seg.audio_emotion != seg.text_emotion:
                detail = (f"  <span style='color:#888;font-size:0.8em'>"
                          f"(tone: {seg.audio_emotion} · words: {seg.text_emotion})"
                          f"</span>")
            emo = (f" &nbsp; {emoji} <b>{seg.emotion}</b> "
                   f"<span style='color:#888'>{seg.emotion_score:.0%}</span>{detail}")
        # Everything interpolated below is escaped: the transcript is model
        # output and the speaker names are typed by the user, and this block
        # is rendered as raw HTML.
        extra = "".join(
            f"<div style='color:#555;font-size:0.92em;margin-top:.15em'>"
            f"<span style='color:#999'>{label}</span> {html.escape(text)}</div>"
            for label, text in renderings(seg)
        )
        st.markdown(
            f"<div style='border-left:4px solid {color};padding:.2em .8em;"
            f"margin:.3em 0'>"
            f"<span style='color:{color};font-weight:600'>"
            f"{html.escape(seg.speaker)}{known}</span>"
            f"<span style='color:#888'> · {_fmt_ts(seg.start)}</span>"
            f"{lang}{conf}{emo}<br>"
            f"{html.escape(seg.text)}{extra}</div>",
            unsafe_allow_html=True,
        )


def _render_downloads(result, detect_emotion: bool) -> None:
    st.subheader("Download")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.download_button("Text (.txt)", render(result, "txt", detect_emotion),
                           file_name="transcript.txt")
    with c2:
        st.download_button("JSON (.json)", render(result, "json"),
                           file_name="transcript.json")
    with c3:
        st.download_button("Subtitles (.srt)", render(result, "srt", detect_emotion),
                           file_name="transcript.srt")
    with c4:
        st.download_button("WebVTT (.vtt)", render(result, "vtt", detect_emotion),
                           file_name="transcript.vtt")


if __name__ == "__main__":
    main()
