"""Streamlit GUI for the transcriber.  Run locally with:

    streamlit run transcriber/gui.py

It opens in your browser but runs entirely on your machine — nothing is
uploaded anywhere.
"""
from __future__ import annotations

import os
import sys
import tempfile

import streamlit as st

# `streamlit run transcriber/gui.py` executes this file as a top-level script
# (no package context), so relative imports would fail. Fall back to absolute
# imports after putting the repo root on sys.path.
try:
    from .core import transcribe_file
    from .emotion import _EMOJI
    from .output import render
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from transcriber.core import transcribe_file
    from transcriber.emotion import _EMOJI
    from transcriber.output import render

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

    with st.sidebar:
        st.header("Settings")
        model = st.selectbox(
            "Whisper model", ["tiny", "base", "small", "medium", "large"],
            index=1, help="Bigger = more accurate but slower.",
        )
        language = st.text_input("Language (blank = auto-detect)", value="")

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
        _run(src, model, language, backend, hf_token, num_speakers,
             detect_emotion, source, audio_weight)


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


def _run(src, model, language, backend, hf_token, num_speakers,
         detect_emotion, source, audio_weight) -> None:
    bar = st.progress(0.0, text="Starting…")

    def progress(stage: str, frac: float) -> None:
        bar.progress(min(1.0, frac), text=stage)

    try:
        result = transcribe_file(
            src,
            whisper_model=model,
            language=language or None,
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
        st.error(f"Failed: {exc}")
        return

    bar.empty()
    st.success(
        f"Done in {result.timings.get('total', 0):.1f}s — "
        f"{len(result.segments)} segments, "
        f"{len(result.speakers)} speaker(s), language: {result.language}"
    )
    if result.timings:
        cols = st.columns(len(result.timings))
        for col, (stage, secs) in zip(cols, result.timings.items()):
            col.metric(stage.title(), f"{secs:.1f}s")
        st.caption(
            "First run loads models; later runs reuse them and are much faster."
        )
    _render_transcript(result, detect_emotion)
    _render_downloads(result, detect_emotion)


def _render_transcript(result, detect_emotion: bool) -> None:
    st.subheader("Transcript")
    for seg in result.segments:
        color = _speaker_color(result.speakers, seg.speaker)
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
        st.markdown(
            f"<div style='border-left:4px solid {color};padding:.2em .8em;"
            f"margin:.3em 0'>"
            f"<span style='color:{color};font-weight:600'>{seg.speaker}</span>"
            f"<span style='color:#888'> · {_fmt_ts(seg.start)}</span>{emo}<br>"
            f"{seg.text}</div>",
            unsafe_allow_html=True,
        )


def _render_downloads(result, detect_emotion: bool) -> None:
    st.subheader("Download")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button("Text (.txt)", render(result, "txt", detect_emotion),
                           file_name="transcript.txt")
    with c2:
        st.download_button("JSON (.json)", render(result, "json"),
                           file_name="transcript.json")
    with c3:
        st.download_button("Subtitles (.srt)", render(result, "srt", detect_emotion),
                           file_name="transcript.srt")


if __name__ == "__main__":
    main()
