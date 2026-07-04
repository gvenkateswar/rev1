#!/usr/bin/env python3
"""
Streamlit GUI for the Video Stitcher.

Point it at a folder of videos, pick and order the clips (or let the
visual analysis recommend an order), choose a transition style, and
render a single stitched video.

Run with:
    streamlit run gui.py
"""

import os
import random
import tempfile
from pathlib import Path

import streamlit as st

from analyze import (
    extract_features,
    recommend_order,
    recommend_speeds,
    shuffle_order,
    thumbnail_png,
)
from stitcher import (
    DEFAULT_RANDOM_INCLUDE,
    MIXABLE_STYLES,
    RANDOM_STYLE,
    SIZE_PRESETS,
    TRANSITION_STYLES,
    probe_clip,
    stitch_videos,
)

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".flv"}

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Video Stitcher",
    page_icon="🎞️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Custom CSS (matches the Shorts Generator look)
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
    .clip-name {
        font-weight: 600;
        font-size: 1.0rem;
    }
    .clip-meta {
        color: #999;
        font-size: 0.85rem;
    }
    .anchor-tag {
        display: inline-block;
        background: #7c3aed33;
        color: #c4b5fd;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.8rem;
        margin-left: 6px;
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


def scan_folder(folder: str) -> list[str]:
    """Return video file paths in `folder`, sorted by name."""
    paths = [
        str(p) for p in sorted(Path(folder).iterdir())
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    ]
    return paths


def init_clips(paths: list[str]) -> None:
    """(Re)build session state from a list of clip paths."""
    clips = {}
    errors = []
    prog = st.progress(0.0, text="Reading clips...")
    for i, path in enumerate(paths):
        try:
            info = probe_clip(path)
        except Exception as e:
            errors.append(f"{os.path.basename(path)}: {e}")
            continue
        clips[path] = {
            "name": os.path.basename(path),
            "info": info,
            "thumb": thumbnail_png(path),
            "selected": True,
            "ken_burns": True,
            "speed": 1.0,
        }
        prog.progress((i + 1) / len(paths), text=f"Reading clips... {i + 1}/{len(paths)}")
    prog.empty()

    st.session_state.clips = clips
    st.session_state.order = list(clips.keys())
    st.session_state.anchor_first = None
    st.session_state.anchor_last = None
    st.session_state.features = {}
    st.session_state.pop("render_result", None)
    if errors:
        st.warning("Skipped unreadable files:\n\n" + "\n".join(f"- {e}" for e in errors))


def apply_anchors(order: list[str]) -> list[str]:
    """Force the anchored clips to the ends of the order."""
    order = list(order)
    first = st.session_state.get("anchor_first")
    last = st.session_state.get("anchor_last")
    if first in order:
        order.remove(first)
        order.insert(0, first)
    if last in order and last != first:
        order.remove(last)
        order.append(last)
    return order


def selected_in_order() -> list[str]:
    clips = st.session_state.clips
    return [p for p in st.session_state.order if clips[p]["selected"]]


def ensure_features(paths: list[str]) -> dict:
    """Compute (and cache) visual features for `paths`."""
    features = st.session_state.features
    missing = [p for p in paths if p not in features]
    if missing:
        prog = st.progress(0.0, text="Analyzing visuals...")
        for i, p in enumerate(missing):
            features[p] = extract_features(p)
            prog.progress(
                (i + 1) / len(missing),
                text=f"Analyzing visuals... {i + 1}/{len(missing)}",
            )
        prog.empty()
    return features


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown("""
<div class="main-header">
    <h1>Video Stitcher</h1>
    <p>Stitch a folder of clips into one video — professional transitions,
    optional Ken Burns motion, visual-flow ordering</p>
</div>
""", unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# Sidebar — settings
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Settings")

    st.subheader("Output")
    size_name = st.selectbox("Resolution", options=list(SIZE_PRESETS), index=0)
    out_w, out_h = SIZE_PRESETS[size_name]
    fps = st.selectbox("Frame rate", options=[24, 25, 30, 60], index=2)

    st.divider()
    st.subheader("Transitions")
    style_options = [RANDOM_STYLE] + list(TRANSITION_STYLES)
    transition_style = st.selectbox(
        "Style",
        options=style_options,
        index=0,
        help=(
            "A curated set of transitions you'd actually see in "
            "professional edits: crossfade blend, dip to black/white, "
            "film dissolve, smooth wipe. The random mix varies them "
            "per cut, leaning on blends and dips to black."
        ),
    )
    mix_include = None
    if transition_style == RANDOM_STYLE:
        mix_include = st.multiselect(
            "Include in random mix",
            options=MIXABLE_STYLES,
            default=DEFAULT_RANDOM_INCLUDE,
            help=(
                "Which transitions the random mix may draw from. The "
                "weighting still applies: blends and dips to black show "
                "up most, dissolves and wipes as accents. Fade-to-white "
                "is off by default (repeated white flashes read as "
                "strobing) but can be added here."
            ),
        )
        if not mix_include:
            st.warning("Pick at least one style for the random mix.")

    transition_duration = st.slider(
        "Transition duration (s)",
        min_value=0.3, max_value=2.0, value=0.75, step=0.05,
        disabled=(transition_style == "Hard cut (no transition)"),
        help="Longer feels dreamier, shorter feels snappier. "
             "Automatically shortened if a clip is too brief.",
    )

    st.divider()
    st.subheader("Ken Burns effect")
    ken_burns = st.checkbox(
        "Apply randomized Ken Burns to each clip",
        value=False,
        help=(
            "A slow, randomized zoom + pan (push in or pull out) applied "
            "to every clip. Each clip gets its own randomly chosen "
            "direction, amount, and drift. Uncheck individual clips below."
        ),
    )
    kb_intensity = st.radio(
        "Intensity",
        options=["subtle", "medium"],
        index=0,
        horizontal=True,
        disabled=not ken_burns,
        help="Subtle: 6-14% zoom. Medium: 12-24% zoom.",
    )

    st.divider()
    st.subheader("Audio")
    mute_all = st.checkbox(
        "Mute all audio (override)",
        value=True,
        help=(
            "On (default): the output has no audio track — ideal when "
            "you'll add a music bed later. Off: clip audio is kept and "
            "crossfaded through each transition; clips with no audio "
            "get silence."
        ),
    )

# ---------------------------------------------------------------------------
# Folder input
# ---------------------------------------------------------------------------

col_path, col_btn = st.columns([5, 1])
with col_path:
    folder = st.text_input(
        "Folder of videos",
        placeholder="/path/to/folder/of/clips",
        label_visibility="collapsed",
    )
with col_btn:
    scan_clicked = st.button("Scan folder", type="primary", use_container_width=True)

if scan_clicked:
    if not folder or not os.path.isdir(folder):
        st.error(f"Not a folder: `{folder or '(empty)'}`")
    else:
        paths = scan_folder(folder)
        if not paths:
            st.error(f"No video files found in `{folder}` "
                     f"(looking for {', '.join(sorted(VIDEO_EXTENSIONS))}).")
        else:
            init_clips(paths)

# ---------------------------------------------------------------------------
# Clip list — select, order, anchor
# ---------------------------------------------------------------------------

if "clips" in st.session_state and st.session_state.clips:
    clips = st.session_state.clips
    st.session_state.order = apply_anchors(st.session_state.order)
    order = st.session_state.order

    n_sel = len(selected_in_order())
    total_dur = sum(
        clips[p]["info"].duration
        / st.session_state.get(f"speed_{p}", clips[p]["speed"])
        for p in selected_in_order()
    )
    st.subheader(f"Clips — {n_sel}/{len(order)} selected, {fmt_time(total_dur)} total")

    # --- Anchors ---
    anchor_options = [None] + selected_in_order()

    def _anchor_label(p):
        return "(none)" if p is None else clips[p]["name"]

    ac1, ac2 = st.columns(2)
    with ac1:
        st.session_state.anchor_first = st.selectbox(
            "Anchor as FIRST clip",
            options=anchor_options,
            index=(anchor_options.index(st.session_state.anchor_first)
                   if st.session_state.anchor_first in anchor_options else 0),
            format_func=_anchor_label,
            help="This clip stays first through shuffles and recommendations.",
        )
    with ac2:
        last_options = [p for p in anchor_options
                        if p is None or p != st.session_state.anchor_first]
        st.session_state.anchor_last = st.selectbox(
            "Anchor as LAST clip",
            options=last_options,
            index=(last_options.index(st.session_state.anchor_last)
                   if st.session_state.anchor_last in last_options else 0),
            format_func=_anchor_label,
            help="This clip stays last through shuffles and recommendations.",
        )
    st.session_state.order = apply_anchors(st.session_state.order)
    order = st.session_state.order

    # --- Ordering buttons ---
    ob1, ob2, ob3 = st.columns([1, 1, 2])
    with ob1:
        if st.button("🔀 Shuffle order", use_container_width=True):
            sel = selected_in_order()
            shuffled = shuffle_order(
                sel,
                first=st.session_state.anchor_first,
                last=st.session_state.anchor_last,
                rng=random.Random(),
            )
            unselected = [p for p in order if not clips[p]["selected"]]
            st.session_state.order = shuffled + unselected
            st.rerun()
    with ob2:
        recommend_clicked = st.button(
            "✨ Recommend order", use_container_width=True,
            help="Analyzes color palette, brightness, and motion of "
                 "each clip, then builds a paced order.",
        )
    with ob3:
        st.caption(
            "Recommended order: near-duplicate clips (slight variations of "
            "the same shot) are spread as far apart as possible — never "
            "adjacent — and the fastest third of clips is interspersed "
            "evenly between the calmer ones, opening on a calm clip. "
            "Anchors are always respected."
        )

    if recommend_clicked:
        sel = selected_in_order()
        features = ensure_features(sel)
        recommended = recommend_order(
            sel, features,
            first=st.session_state.anchor_first,
            last=st.session_state.anchor_last,
        )
        unselected = [p for p in order if not clips[p]["selected"]]
        st.session_state.order = recommended + unselected
        st.toast("Order updated from visual analysis")
        st.rerun()

    # --- Speed suggestion buttons ---
    sb1, sb2, sb3 = st.columns([1, 1, 2])
    with sb1:
        slow_clicked = st.button(
            "🐢 Slow down fast clips", use_container_width=True,
            help="Analyzes motion and applies a slight slow-down "
                 "(0.75x-0.9x) to clips that move much faster than "
                 "the rest. Speeds you set by hand on other clips "
                 "are left alone.",
        )
    with sb2:
        if st.button("↺ Reset speeds", use_container_width=True,
                     help="Set every clip back to 1x."):
            for p in order:
                clips[p]["speed"] = 1.0
                st.session_state[f"speed_{p}"] = 1.0
            st.rerun()
    with sb3:
        st.caption(
            "Slow-down suggestions compare each clip's measured motion to "
            "the group's median: the more frantic a clip is relative to the "
            "rest, the stronger the suggested slow-down (never below 0.75x)."
        )

    if slow_clicked:
        sel = selected_in_order()
        features = ensure_features(sel)
        suggestions = recommend_speeds(sel, features)
        slowed = []
        for p, speed in suggestions.items():
            if speed != 1.0:
                clips[p]["speed"] = speed
                st.session_state[f"speed_{p}"] = speed
                slowed.append(f"{clips[p]['name']} → {speed:g}x")
        if slowed:
            st.toast("Slowed " + ", ".join(slowed))
        else:
            st.toast("No clip moves fast enough relative to the rest "
                     "to need slowing.")
        st.rerun()

    st.write("")

    # --- Clip rows ---
    anchored = {st.session_state.anchor_first, st.session_state.anchor_last}
    display_positions = {p: i for i, p in enumerate(order)}

    for pos, path in enumerate(order):
        clip = clips[path]
        info = clip["info"]
        is_first_anchor = path == st.session_state.anchor_first
        is_last_anchor = path == st.session_state.anchor_last

        cols = st.columns([0.5, 1.4, 3.2, 0.9, 1.0, 1.1, 0.6, 0.6])

        with cols[0]:
            st.markdown(
                f"<div style='font-size:1.2rem;font-weight:700;color:#7c3aed;"
                f"padding-top:0.9rem;'>{pos + 1}</div>",
                unsafe_allow_html=True,
            )
        with cols[1]:
            if clip["thumb"]:
                st.image(clip["thumb"])
        with cols[2]:
            tags = ""
            if is_first_anchor:
                tags += '<span class="anchor-tag">📌 first</span>'
            if is_last_anchor:
                tags += '<span class="anchor-tag">📌 last</span>'
            st.markdown(
                f'<div class="clip-name">{clip["name"]}{tags}</div>'
                f'<div class="clip-meta">{fmt_time(info.duration)} &middot; '
                f'{info.width}x{info.height}'
                f'{"" if info.has_audio else " &middot; no audio"}</div>',
                unsafe_allow_html=True,
            )
        with cols[3]:
            clip["selected"] = st.checkbox(
                "Include", value=clip["selected"], key=f"sel_{path}",
            )
        with cols[4]:
            clip["ken_burns"] = st.checkbox(
                "Ken Burns", value=clip["ken_burns"], key=f"kb_{path}",
                disabled=not ken_burns,
            )
        with cols[5]:
            # Seed widget state from the clips dict, not a default param:
            # a mid-script st.rerun() (order/speed buttons) wipes the state
            # of widgets that didn't render that run, and the dict is what
            # survives. Seeding via session state also lets the slow-down/
            # reset buttons write values without a default-conflict warning.
            speed_options = [0.5, 0.75, 0.8, 0.9, 0.95, 1.0,
                             1.05, 1.1, 1.2, 1.25, 1.5, 2.0]
            speed_key = f"speed_{path}"
            if speed_key not in st.session_state:
                st.session_state[speed_key] = clip["speed"]
            clip["speed"] = st.selectbox(
                "Speed",
                options=speed_options,
                key=speed_key,
                format_func=lambda v: f"{v:g}x",
                help="Playback speed for this clip. Audio stays pitch-correct.",
            )
        # Up/down move within the selected middle; anchors stay pinned.
        movable = clip["selected"] and path not in anchored
        with cols[6]:
            if st.button("⬆", key=f"up_{path}", disabled=not movable or pos == 0):
                o = st.session_state.order
                o[pos - 1], o[pos] = o[pos], o[pos - 1]
                st.session_state.order = apply_anchors(o)
                st.rerun()
        with cols[7]:
            if st.button("⬇", key=f"dn_{path}",
                         disabled=not movable or pos == len(order) - 1):
                o = st.session_state.order
                o[pos + 1], o[pos] = o[pos], o[pos + 1]
                st.session_state.order = apply_anchors(o)
                st.rerun()

    st.divider()

    # -----------------------------------------------------------------------
    # Render
    # -----------------------------------------------------------------------

    st.subheader("Render")

    sel_paths = selected_in_order()
    kb_note = ""
    if ken_burns:
        n_kb = sum(1 for p in sel_paths if clips[p]["ken_burns"])
        kb_note = f" · Ken Burns ({kb_intensity}) on {n_kb}/{len(sel_paths)} clips"
    audio_note = "muted" if mute_all else "audio crossfaded"
    n_speed = sum(1 for p in sel_paths if clips[p]["speed"] != 1.0)
    speed_note = f" · speed adjusted on {n_speed} clips" if n_speed else ""
    st.caption(
        f"**{len(sel_paths)} clips** → {size_name} @ {fps} fps · "
        f"{transition_style} ({transition_duration:.2f}s) · "
        f"{audio_note}{kb_note}{speed_note}"
    )

    mix_empty = transition_style == RANDOM_STYLE and not mix_include
    rb1, rb2 = st.columns(2)
    with rb1:
        preview_clicked = st.button(
            "⚡ Render Quick Preview",
            use_container_width=True,
            disabled=len(sel_paths) == 0 or mix_empty,
            help=(
                "A small, fast render (max 640px wide, fast encode) to "
                "check the sequence before committing to the full "
                "resolution. Uses the same random transition picks and "
                "Ken Burns moves as the full render."
            ),
        )
    with rb2:
        render_clicked = st.button(
            "Render Stitched Video",
            type="primary",
            use_container_width=True,
            disabled=len(sel_paths) == 0 or mix_empty,
        )

    def preview_size(w: int, h: int, max_dim: int = 640) -> tuple[int, int]:
        s = max_dim / max(w, h)
        return max(int(w * s) // 2 * 2, 2), max(int(h * s) // 2 * 2, 2)

    def run_render(preview: bool):
        # One seed shared by preview and final render (per clip selection /
        # session) so the random transition mix and Ken Burns moves in the
        # preview are exactly what the full render produces.
        if "render_seed" not in st.session_state:
            st.session_state.render_seed = random.randrange(2**31)

        if preview:
            w, h = preview_size(out_w, out_h)
            render_fps = min(fps, 24)
        else:
            w, h = out_w, out_h
            render_fps = fps

        out_dir = tempfile.mkdtemp(prefix="stitcher_out_")
        out_path = os.path.join(
            out_dir, "preview.mp4" if preview else "stitched.mp4",
        )

        st.caption("Overall")
        overall_bar = st.progress(0.0)
        st.caption("Current step")
        step_bar = st.progress(0.0)
        status_text = st.empty()

        def on_progress(step, total, message, frac=0.0):
            overall_bar.progress(min((step - 1 + frac) / total, 1.0))
            step_bar.progress(min(frac, 1.0))
            pct = f" — {frac * 100:.0f}%" if frac > 0 else ""
            status_text.markdown(f"**Step {step}/{total}:** {message}{pct}")

        try:
            result = stitch_videos(
                sel_paths,
                out_path,
                width=w,
                height=h,
                fps=render_fps,
                transition_style=transition_style,
                transition_duration=transition_duration,
                mute=mute_all,
                ken_burns=ken_burns,
                ken_burns_per_clip=[clips[p]["ken_burns"] for p in sel_paths],
                ken_burns_intensity=kb_intensity,
                speed_per_clip=[clips[p]["speed"] for p in sel_paths],
                random_include=mix_include,
                seed=st.session_state.render_seed,
                preview=preview,
                on_progress=on_progress,
            )
            overall_bar.progress(1.0)
            step_bar.progress(1.0)
            status_text.markdown("**Done!**")
            key = "preview_result" if preview else "render_result"
            st.session_state[key] = result
        except FileNotFoundError as e:
            st.error(
                f"**{e}**\n\n"
                "- Ubuntu/Debian: `sudo apt install ffmpeg`\n"
                "- macOS: `brew install ffmpeg`\n"
                "- Windows: `choco install ffmpeg`"
            )
        except Exception as e:
            st.error(f"Render failed: {e}")

    if preview_clicked:
        run_render(preview=True)
    elif render_clicked:
        run_render(preview=False)

    if "preview_result" in st.session_state:
        result = st.session_state.preview_result
        if os.path.isfile(result.output_path):
            pw, ph = preview_size(out_w, out_h)
            st.markdown("#### ⚡ Quick preview")
            st.caption(
                f"Preview quality ({pw}x{ph}, fast encode) — the full render "
                f"will use the same transitions and Ken Burns moves at "
                f"{out_w}x{out_h}."
            )
            for w in result.warnings:
                st.warning(w)
            st.video(result.output_path)

    if "render_result" in st.session_state:
        result = st.session_state.render_result
        if os.path.isfile(result.output_path):
            st.markdown("#### Full render")
            for w in result.warnings:
                st.warning(w)
            if result.transitions_used:
                st.caption("Transitions used: " + ", ".join(result.transitions_used))
            st.success(f"Rendered **{fmt_time(result.duration)}** video.")
            st.video(result.output_path)
            with open(result.output_path, "rb") as f:
                st.download_button(
                    label="Download stitched video (.mp4)",
                    data=f.read(),
                    file_name="stitched.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                )

else:
    st.info(
        "Point the box above at a folder of video files and click "
        "**Scan folder**. You can then deselect clips, drag their order "
        "with the arrows, pin a first/last clip, shuffle, or let the "
        "visual analysis recommend an order."
    )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown("---")
st.caption(
    "Video Stitcher | ffmpeg xfade transitions | "
    "CLI available: `python stitcher.py --help`"
)
