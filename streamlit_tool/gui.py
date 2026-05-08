#!/usr/bin/env python3
"""
Streamlit GUI for Video Shorts Generator.

Run with:
    streamlit run gui.py
"""

import os
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np
import streamlit as st

from shorts_generator import (
    analyze_video,
    auto_fontsize,
    caption_clip,
    export_clip,
    find_caption_font,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Video Shorts Generator",
    page_icon="🎬",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem 0 0.5rem 0;
    }
    .main-header h1 {
        font-size: 2.2rem;
        font-weight: 700;
    }
    .main-header p {
        color: #888;
        font-size: 1.05rem;
    }
    .segment-card {
        background: #1e1e2e;
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        border-left: 4px solid #7c3aed;
    }
    .segment-rank {
        font-size: 1.5rem;
        font-weight: 700;
        color: #7c3aed;
    }
    .segment-time {
        font-size: 1.1rem;
        font-weight: 600;
    }
    .segment-score {
        font-size: 0.95rem;
        color: #a78bfa;
    }
    .tag {
        display: inline-block;
        background: #7c3aed33;
        color: #c4b5fd;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.82rem;
        margin-right: 6px;
        margin-top: 4px;
    }
    .transcript-preview {
        color: #aaa;
        font-style: italic;
        margin-top: 0.5rem;
        font-size: 0.92rem;
    }
    .metric-box {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .metric-box h3 {
        margin: 0;
        font-size: 1.6rem;
        color: #7c3aed;
    }
    .metric-box p {
        margin: 0;
        color: #999;
        font-size: 0.85rem;
    }
    div[data-testid="stProgress"] > div > div > div {
        background-color: #7c3aed;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def score_color(score: float) -> str:
    if score >= 0.7:
        return "#22c55e"
    if score >= 0.5:
        return "#eab308"
    return "#ef4444"


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown("""
<div class="main-header">
    <h1>Video Shorts Generator</h1>
    <p>Upload a video and find the best moments to turn into shorts — powered by audio analysis &amp; Whisper AI</p>
</div>
""", unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# Sidebar — settings
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Settings")

    top_n = st.slider(
        "Number of clips to find",
        min_value=1, max_value=20, value=5,
    )

    col1, col2 = st.columns(2)
    with col1:
        min_dur = st.number_input(
            "Min duration (s)", min_value=5, max_value=120, value=15, step=5,
        )
    with col2:
        max_dur = st.number_input(
            "Max duration (s)", min_value=10, max_value=180, value=60, step=5,
        )

    st.divider()
    st.subheader("Content type")
    instrumental = st.checkbox(
        "Instrumental track (skip speech analysis)",
        value=False,
        help=(
            "For music videos without vocals — or where you don't want "
            "vocal sections to outrank instrumental breaks. Skips Whisper "
            "entirely, saving ~3 min per video, and rebalances scoring "
            "onto pure audio features (energy, dynamics, brightness)."
        ),
    )

    whisper_model = st.selectbox(
        "Whisper model",
        options=["tiny", "base", "small", "medium", "large"],
        index=1,
        help="Larger models are more accurate but slower.",
        disabled=instrumental,
    )

    st.divider()
    st.subheader("Export format")
    vertical = st.checkbox(
        "Vertical output (9:16 for Shorts)",
        value=True,
        help="Crop and scale exports to 1080x1920.",
    )
    smart_crop = st.checkbox(
        "Smart crop (track faces)",
        value=True,
        disabled=not vertical,
        help=(
            "Sample frames from each clip, detect the largest face, and "
            "center the 9:16 crop on it. Falls back to center crop when "
            "no face is found. Uses OpenCV's built-in Haar cascade."
        ),
    )

    st.divider()
    st.subheader("Captions")
    enable_captions = st.checkbox(
        "Burn captions into clips",
        value=False,
        help=(
            "Add bold white text with a black stroke to each clip. "
            "Type the caption per-clip in the Export section below. "
            "Style: bold sans-serif, centered, lower third."
        ),
    )
    if enable_captions:
        caption_position = st.radio(
            "Caption position",
            options=["Lower third", "Upper third"],
            index=0,
            help=(
                "Lower third (y=1500) works when the subject's face is "
                "in the upper half. Flip to upper third (y=560) if the "
                "subject is in the lower half."
            ),
            horizontal=True,
        )
        caption_y_center = 1500 if caption_position == "Lower third" else 560

        caption_fontsize_mode = st.radio(
            "Font size",
            options=["Auto (by line length)", "Manual"],
            index=0,
            horizontal=True,
        )
        if caption_fontsize_mode == "Manual":
            caption_fontsize = st.slider(
                "Font size (px)", min_value=48, max_value=120, value=78,
            )
        else:
            caption_fontsize = 0  # 0 = auto in caption_clip()

        _font = find_caption_font()
        if _font:
            st.caption(f"Font: `{os.path.basename(_font)}`")
        else:
            st.warning(
                "No bold font found. Install Poppins-Bold or Arial Bold "
                "and restart. Captions will be skipped if no font is available."
            )

    st.divider()
    if instrumental:
        st.caption("Scoring weights (instrumental)")
        st.markdown("""
        | Signal | Weight |
        |--------|--------|
        | Energy | 45% |
        | Dynamics | 30% |
        | Brightness | 15% |
        | Silence penalty | -10% |
        """)
    else:
        st.caption("Scoring weights (default)")
        st.markdown("""
        | Signal | Weight |
        |--------|--------|
        | Energy | 25% |
        | Speech density | 20% |
        | Dynamics | 15% |
        | Speech rate | 15% |
        | Emphasis | 10% |
        | Brightness | 5% |
        | Silence penalty | -10% |
        """)

# ---------------------------------------------------------------------------
# File upload
# ---------------------------------------------------------------------------

uploaded_file = st.file_uploader(
    "Upload a video file",
    type=["mp4", "mkv", "mov", "avi", "webm", "flv", "wmv", "m4v"],
    help="Supports most common video formats.",
)

# Also allow local file path as an alternative
with st.expander("Or enter a local file path"):
    local_path = st.text_input(
        "Path to video file",
        placeholder="/path/to/your/video.mp4",
    )

# ---------------------------------------------------------------------------
# Determine video path
# ---------------------------------------------------------------------------

video_path = None
tmp_upload_dir = None

if uploaded_file is not None:
    tmp_upload_dir = tempfile.mkdtemp(prefix="shorts_gui_upload_")
    video_path = os.path.join(tmp_upload_dir, uploaded_file.name)
    with open(video_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.success(f"Uploaded: **{uploaded_file.name}** ({uploaded_file.size / 1_000_000:.1f} MB)")
elif local_path and os.path.isfile(local_path):
    video_path = local_path
    st.success(f"Using local file: **{Path(local_path).name}**")
elif local_path:
    if local_path.strip():
        st.error(f"File not found: {local_path}")

# ---------------------------------------------------------------------------
# Analyze button
# ---------------------------------------------------------------------------

if video_path:
    if st.button("Analyze Video", type="primary", use_container_width=True):
        # Progress bar and status text
        progress_bar = st.progress(0)
        status_text = st.empty()

        def on_progress(step, total, message):
            progress_bar.progress(step / total)
            status_text.markdown(f"**Step {step}/{total}:** {message}")

        try:
            top_segments, whisper_result, analysis = analyze_video(
                video_path=video_path,
                top_n=top_n,
                min_duration=float(min_dur),
                max_duration=float(max_dur),
                whisper_model=whisper_model,
                instrumental=instrumental,
                on_progress=on_progress,
            )

            progress_bar.progress(1.0)
            status_text.markdown("**Done!**")

            # Store in session state so results persist across reruns.
            # Also store the export-time flags so an export-only rerun
            # doesn't need to re-analyse.
            st.session_state["results"] = {
                "top_segments": top_segments,
                "whisper_result": whisper_result,
                "analysis": analysis,
                "video_path": video_path,
            }

        except FileNotFoundError:
            st.error(
                "**ffmpeg not found.** Install it first:\n"
                "- Ubuntu/Debian: `sudo apt install ffmpeg`\n"
                "- macOS: `brew install ffmpeg`\n"
                "- Windows: `choco install ffmpeg`"
            )
        except Exception as e:
            st.error(f"Analysis failed: {e}")

# ---------------------------------------------------------------------------
# Display results
# ---------------------------------------------------------------------------

if "results" in st.session_state:
    results = st.session_state["results"]
    top_segments = results["top_segments"]
    whisper_result = results["whisper_result"]
    analysis = results["analysis"]
    result_video_path = results["video_path"]

    st.divider()

    # --- Metrics row ---
    m1, m2, m3, m4 = st.columns(4)
    total_dur = analysis["total_duration"]
    with m1:
        st.metric("Video Length", f"{int(total_dur // 60)}m {int(total_dur % 60)}s")
    with m2:
        if analysis.get("instrumental"):
            st.metric("Mode", "Instrumental")
        else:
            st.metric("Speech Segments", analysis["n_speech_segments"])
    with m3:
        st.metric("Silence Ratio", f"{analysis['silence_ratio']:.0%}")
    with m4:
        st.metric("Candidates Evaluated", f"{analysis['n_candidates_evaluated']:,}")

    st.divider()

    # --- Energy waveform ---
    st.subheader("Audio Energy Profile")
    energy = analysis["energy"]
    time_axis = np.arange(len(energy)) * 0.5  # 0.5s hop

    chart_data = {"Time (s)": time_axis, "Energy": energy}
    st.line_chart(chart_data, x="Time (s)", y="Energy", color="#7c3aed")

    # Mark segment positions on a note
    if top_segments:
        markers = ", ".join(
            f"**#{i+1}** {fmt_time(s.start)}-{fmt_time(s.end)}"
            for i, s in enumerate(top_segments)
        )
        st.caption(f"Suggested clips: {markers}")

    st.divider()

    # --- Segment cards ---
    st.subheader(f"Top {len(top_segments)} Shorts Candidates")

    for i, seg in enumerate(top_segments):
        with st.container():
            col_rank, col_info = st.columns([1, 6])

            with col_rank:
                st.markdown(
                    f'<div class="segment-rank">#{i + 1}</div>',
                    unsafe_allow_html=True,
                )
                pct = int(seg.score * 100)
                st.markdown(
                    f'<div style="text-align:center;color:{score_color(seg.score)};'
                    f'font-weight:700;font-size:1.3rem;">{pct}%</div>',
                    unsafe_allow_html=True,
                )

            with col_info:
                st.markdown(
                    f"**{fmt_time(seg.start)} &rarr; {fmt_time(seg.end)}** "
                    f"&nbsp;&middot;&nbsp; {seg.duration:.0f}s"
                )

                # Score breakdown — hide speech column in instrumental mode.
                if analysis.get("instrumental"):
                    sb1, sb2 = st.columns(2)
                    sb1.caption(f"Energy: {seg.energy_score:.2f}")
                    sb2.caption(f"Dynamics: {seg.dynamics_score:.2f}")
                else:
                    sb1, sb2, sb3 = st.columns(3)
                    sb1.caption(f"Energy: {seg.energy_score:.2f}")
                    sb2.caption(f"Speech: {seg.speech_score:.2f}")
                    sb3.caption(f"Dynamics: {seg.dynamics_score:.2f}")

                # Reason tags
                if seg.reasons:
                    tags_html = " ".join(
                        f'<span class="tag">{r}</span>' for r in seg.reasons
                    )
                    st.markdown(tags_html, unsafe_allow_html=True)

                # Transcript — only relevant when we actually transcribed.
                if seg.transcript and not analysis.get("instrumental"):
                    preview = seg.transcript[:250]
                    if len(seg.transcript) > 250:
                        preview += "..."
                    with st.expander("Show transcript"):
                        st.write(seg.transcript)
                    st.caption(f'"{preview}"')

            st.divider()

    # --- Export section ---
    st.subheader("Export Clips")

    # Note current export settings from sidebar so the user sees what they'll get.
    fmt_note = "9:16 vertical (1080x1920)" if vertical else "original aspect"
    crop_note = ""
    if vertical:
        crop_note = " with face-tracking crop" if smart_crop else " with center crop"
    caption_note = ""
    if enable_captions:
        caption_note = " + captions"
    st.caption(
        f"Export format: **{fmt_note}{crop_note}{caption_note}**. "
        f"Change in the sidebar."
    )

    export_col1, export_col2 = st.columns(2)

    with export_col1:
        selected_indices = st.multiselect(
            "Select clips to export",
            options=list(range(len(top_segments))),
            default=list(range(len(top_segments))),
            format_func=lambda i: (
                f"#{i+1} — {fmt_time(top_segments[i].start)}"
                f" to {fmt_time(top_segments[i].end)}"
                f" ({top_segments[i].duration:.0f}s)"
            ),
        )

    with export_col2:
        st.write("")  # spacer
        st.write("")
        export_button = st.button(
            "Export Selected Clips",
            type="primary",
            disabled=len(selected_indices) == 0,
        )

    # Per-clip caption inputs (shown when captions are enabled).
    clip_captions: dict[int, str] = {}
    if enable_captions and selected_indices:
        st.markdown("**Captions** — type the text for each clip. "
                    "Use separate lines for multi-line captions.")
        for idx in selected_indices:
            seg = top_segments[idx]
            clip_captions[idx] = st.text_area(
                f"Clip #{idx+1} ({fmt_time(seg.start)}–{fmt_time(seg.end)})",
                value="",
                height=80,
                key=f"caption_{idx}",
                placeholder="e.g.\nOLDER THAN\nTHE BLUES",
            )

    if export_button and selected_indices:
        export_dir = tempfile.mkdtemp(prefix="shorts_export_")
        export_progress = st.progress(0)
        export_status = st.empty()
        exported_paths = []
        total_steps = len(selected_indices)

        for j, idx in enumerate(selected_indices):
            seg = top_segments[idx]

            # Step 1: cut + crop
            export_status.markdown(
                f"Cutting clip **#{idx+1}** ({fmt_time(seg.start)}–{fmt_time(seg.end)}) ..."
            )
            cut_path = export_clip(
                result_video_path, seg, export_dir, idx,
                vertical=vertical,
                smart_crop=smart_crop,
            )

            # Step 2: caption burn (if text provided)
            caption_text = clip_captions.get(idx, "").strip()
            if enable_captions and caption_text:
                export_status.markdown(
                    f"Burning caption onto clip **#{idx+1}** ..."
                )
                caption_lines = [l for l in caption_text.splitlines() if l.strip()]
                captioned_path = cut_path.replace(".mp4", "_captioned.mp4")
                caption_clip(
                    input_path=cut_path,
                    output_path=captioned_path,
                    lines=caption_lines,
                    fontsize=caption_fontsize if enable_captions else 0,
                    y_center=caption_y_center if enable_captions else 1500,
                    face_aware=True,
                )
                exported_paths.append(captioned_path)
            else:
                exported_paths.append(cut_path)

            export_progress.progress((j + 1) / total_steps)

        export_progress.progress(1.0)
        export_status.markdown("**Export complete.**")
        st.success(f"Exported {len(exported_paths)} clips!")

        # Create a zip for download
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in exported_paths:
                zf.write(p, os.path.basename(p))
        zip_buffer.seek(0)

        st.download_button(
            label="Download All Clips (.zip)",
            data=zip_buffer,
            file_name="shorts_clips.zip",
            mime="application/zip",
            use_container_width=True,
        )

        # Also show individual download buttons
        for p in exported_paths:
            with open(p, "rb") as f:
                st.download_button(
                    label=f"Download {os.path.basename(p)}",
                    data=f.read(),
                    file_name=os.path.basename(p),
                    mime="video/mp4",
                )

    # --- JSON export ---
    with st.expander("Export results as JSON"):
        import json
        json_output = {
            "video": result_video_path,
            "duration": analysis["total_duration"],
            "instrumental": analysis.get("instrumental", False),
            "shorts": [
                {
                    "rank": i + 1,
                    "start": round(seg.start, 1),
                    "end": round(seg.end, 1),
                    "duration": round(seg.duration, 1),
                    "score": round(seg.score, 3),
                    "energy_score": round(seg.energy_score, 3),
                    "speech_score": round(seg.speech_score, 3),
                    "dynamics_score": round(seg.dynamics_score, 3),
                    "reasons": seg.reasons,
                    "transcript": seg.transcript,
                }
                for i, seg in enumerate(top_segments)
            ],
        }
        st.json(json_output)
        st.download_button(
            label="Download JSON",
            data=json.dumps(json_output, indent=2),
            file_name="shorts_analysis.json",
            mime="application/json",
        )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown("---")
st.caption(
    "Video Shorts Generator | Audio analysis powered by Whisper AI | "
    "CLI available: `python shorts_generator.py --help`"
)
