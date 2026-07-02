"""Track Stitcher — combine a folder of ambient tracks into one continuous,
beat-matched, crossfaded mix exported as a single WAV.

UI only; all DSP lives in audio_engine.py. Run with:  streamlit run app.py
"""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

import streamlit as st

CONFIG_PATH = Path.home() / ".track_stitcher_config.json"

st.set_page_config(page_title="Track Stitcher", page_icon="🎛️", layout="wide")

# Import dependencies after set_page_config so a missing package shows a
# readable in-app error (with the fix) instead of a raw traceback.
try:
    from streamlit_sortables import sort_items
    import audio_engine as engine
except ModuleNotFoundError as exc:
    st.error(
        f"Missing Python dependency: **`{exc.name}`**.\n\n"
        "**Fix:** install the requirements into the same Python environment "
        "that runs Streamlit, then restart the app:\n\n"
        "```sh\npython3 -m pip install -r requirements.txt\n"
        "python3 -m streamlit run app.py\n```"
    )
    st.stop()
st.title("🎛️ Track Stitcher")
st.caption(
    "Combine a folder of ambient tracks into one continuous, beat-matched, "
    "crossfaded mix — exported as a single 24-bit / 48 kHz WAV."
)

# ---------------------------------------------------------------------------
# Startup check: pyrubberband needs the rubberband CLI
# ---------------------------------------------------------------------------

if not engine.rubberband_available():
    st.error(
        "The `rubberband` command-line tool is required for pitch-preserving "
        "time-stretching but was not found on your PATH.\n\n"
        "**Fix:** `brew install rubberband`, then restart this app."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Config persistence (last-used folder)
# ---------------------------------------------------------------------------


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg))
    except Exception:
        pass  # persistence is a convenience, never fatal


# ---------------------------------------------------------------------------
# Cached analysis — keyed on (path, mtime) so each file is analyzed exactly
# once; no widget interaction (reordering, playback, BPM edits) re-triggers it.
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def analyze_cached(path: str, mtime: float) -> dict:
    return engine.analyze_track(path)


# ---------------------------------------------------------------------------
# Folder input
# ---------------------------------------------------------------------------


def browse_for_folder() -> str | None:
    """Open a native folder picker via tkinter in a subprocess.

    Runs out-of-process because tkinter cannot share Streamlit's main thread.
    Returns the chosen path, or None if cancelled/unavailable.
    """
    code = (
        "import tkinter as tk\n"
        "from tkinter import filedialog\n"
        "root = tk.Tk(); root.withdraw()\n"
        "root.attributes('-topmost', True)\n"
        "print(filedialog.askdirectory() or '')\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=300
        )
        chosen = result.stdout.strip()
        return chosen or None
    except Exception:
        return None


if "folder_path" not in st.session_state:
    st.session_state.folder_path = load_config().get("last_folder", "")

SUPPORTED = ", ".join(sorted(engine.AUDIO_EXTENSIONS))

col_path, col_browse = st.columns([5, 1], vertical_alignment="bottom")
with col_path:
    folder = st.text_input(
        "Folder of audio tracks",
        key="folder_path",
        placeholder="/Users/you/Music/ambient-session",
        help=f"Scans for {SUPPORTED} (non-recursive).",
    )
with col_browse:
    if st.button("Browse…", use_container_width=True):
        chosen = browse_for_folder()
        if chosen:
            st.session_state.folder_path = chosen
            folder = chosen
            st.rerun()
        else:
            st.toast("Folder picker unavailable — paste the path instead.")

if not folder.strip():
    st.info("Paste a folder path above to get started.")
    st.stop()

try:
    files = engine.scan_folder(folder.strip())
except NotADirectoryError:
    st.warning(f"`{folder}` is not a valid folder — check the path.")
    st.stop()

if not files:
    st.warning(f"That folder has no supported audio files ({SUPPORTED}).")
    st.stop()

folder_path = Path(folder.strip()).expanduser()
cfg = load_config()
if cfg.get("last_folder") != str(folder_path):
    save_config({**cfg, "last_folder": str(folder_path)})

# ---------------------------------------------------------------------------
# Analyze all tracks (cached) and build per-file info
# ---------------------------------------------------------------------------

analyses: dict[str, dict] = {}
unreadable: list[str] = []
with st.spinner("Analyzing tracks (first run only — results are cached)…"):
    for f in files:
        info = analyze_cached(str(f), f.stat().st_mtime)
        if "error" in info:
            unreadable.append(f"{f.name}: {info['error']}")
        else:
            analyses[str(f)] = info

for msg in unreadable:
    st.error(f"Skipping unreadable file — {msg}")
if not analyses:
    st.stop()

names_by_path = {p: Path(p).name for p in analyses}
paths_by_name = {n: p for p, n in names_by_path.items()}

# ---------------------------------------------------------------------------
# Track ordering (drag-and-drop) — the displayed order IS the render order
# ---------------------------------------------------------------------------

st.subheader("1 · Order your tracks")
st.caption("Drag to reorder — the mix is rendered top to bottom.")

alphabetical = sorted(names_by_path.values(), key=str.lower)
# Key the sortable on the file set so a new folder resets the ordering.
order_key = "sortable_" + str(hash(tuple(alphabetical)))
ordered_names = sort_items(alphabetical, direction="vertical", key=order_key)
ordered_paths = [paths_by_name[n] for n in ordered_names]

# ---------------------------------------------------------------------------
# Effective BPM helpers
# ---------------------------------------------------------------------------


def bpm_key(path: str) -> str:
    return f"bpm::{path}"


def scale_bpm(key: str, factor: float) -> None:
    value = st.session_state.get(key)
    if value:
        st.session_state[key] = round(value * factor, 1)


# Seed each track's BPM input once: filename override beats detection.
for path, info in analyses.items():
    key = bpm_key(path)
    if key not in st.session_state:
        st.session_state[key] = info["filename_bpm"] or info["detected_bpm"]


def effective_bpm(path: str) -> float | None:
    return st.session_state.get(bpm_key(path))


# ---------------------------------------------------------------------------
# Global controls (rendered before the table so stretch % reflects them live)
# ---------------------------------------------------------------------------

st.subheader("2 · Review, audition, and set BPMs")

suggested = engine.suggest_output_bpm([effective_bpm(p) for p in ordered_paths])

gc1, gc2, gc3 = st.columns([1.2, 1, 2], vertical_alignment="bottom")
with gc1:
    if "output_bpm" not in st.session_state:
        st.session_state.output_bpm = float(suggested) if suggested else 90.0
    output_bpm = st.number_input(
        "Output BPM (suggested: median of your tracks)",
        min_value=20.0,
        max_value=300.0,
        step=1.0,
        key="output_bpm",
    )
    if suggested and st.button(f"Reset to suggestion ({suggested})"):
        st.session_state.output_bpm = float(suggested)
        st.rerun()
    st.caption("Median of your tracks — minimizes total stretching.")
with gc2:
    crossfade_s = st.number_input(
        "Crossfade length (seconds)",
        min_value=5.0,
        max_value=60.0,
        value=20.0,
        step=1.0,
        help="Applied to every transition (per-transition overrides are a "
        "planned v2 feature).",
    )
with gc3:
    default_name = f"stitched_mix_{datetime.date.today():%Y%m%d}.wav"
    output_name = st.text_input(
        "Output filename (written into the source folder)", value=default_name
    )

st.caption(
    "Stretch % color code — normal within ±8%, :orange[amber beyond ±8%], "
    ":red[red beyond ±15%]. Large stretches degrade sustained/ambient textures: "
    "rubberband has to fabricate or discard more of the waveform, which smears "
    "pads and long tails."
)

# ---------------------------------------------------------------------------
# Track table
# ---------------------------------------------------------------------------


def stretch_badge(pct: float) -> str:
    label = f"{pct:+.1f}%"
    if abs(pct) > 15:
        return f":red[**{label}**]"
    if abs(pct) > 8:
        return f":orange[**{label}**]"
    return f"**{label}**"


missing_bpm: list[str] = []

for path in ordered_paths:
    info = analyses[path]
    name = names_by_path[path]
    with st.container(border=True):
        top_l, top_r = st.columns([5, 1])
        with top_l:
            badges = []
            if info["filename_bpm"]:
                badges.append(":blue-badge[BPM from filename]")
            if info["detected_bpm"] is None:
                badges.append(":red-badge[⚠ detection failed — set BPM manually]")
            st.markdown(f"**{name}** " + " ".join(badges))
            detected = (
                f"detected: {info['detected_bpm']:g} BPM"
                if info["detected_bpm"] is not None
                else "detected: —"
            )
            st.caption(f":gray[{detected}]")
        with top_r:
            st.markdown(f"Duration: **{engine.format_duration(info['duration'])}**")

        c_bpm, c_x2, c_half, c_stretch, c_audio = st.columns(
            [1.6, 0.5, 0.5, 1.2, 3.5], vertical_alignment="center"
        )
        with c_bpm:
            st.number_input(
                "BPM",
                min_value=20.0,
                max_value=300.0,
                step=0.1,
                format="%.1f",
                key=bpm_key(path),
                label_visibility="collapsed",
                placeholder="BPM required",
            )
        with c_x2:
            st.button(
                "×2",
                key=f"x2::{path}",
                on_click=scale_bpm,
                args=(bpm_key(path), 2.0),
                help="Double the BPM (fixes half-time detection)",
            )
        with c_half:
            st.button(
                "÷2",
                key=f"half::{path}",
                on_click=scale_bpm,
                args=(bpm_key(path), 0.5),
                help="Halve the BPM (fixes double-time detection)",
            )
        with c_stretch:
            bpm = effective_bpm(path)
            if bpm:
                pct = (output_bpm / bpm - 1.0) * 100.0
                st.markdown(
                    f"stretch: {stretch_badge(pct)}",
                    help="Tempo change at the selected output BPM. Large "
                    "stretches (amber >8%, red >15%) degrade sustained "
                    "ambient textures.",
                )
            else:
                st.markdown(":red[no BPM]")
                missing_bpm.append(name)
        with c_audio:
            st.audio(path)

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

st.subheader("3 · Render")

if missing_bpm:
    st.warning(
        "Set a manual BPM for these tracks before rendering: "
        + ", ".join(f"**{n}**" for n in missing_bpm)
    )

output_name = output_name.strip() or default_name
if not output_name.lower().endswith(".wav"):
    output_name += ".wav"
output_path = folder_path / output_name

if st.button(
    "🎚️ Render mix",
    type="primary",
    disabled=bool(missing_bpm),
    help="Set a BPM on every track first." if missing_bpm else None,
):
    progress_bar = st.progress(0.0, text="Starting render…")

    def on_progress(frac: float, msg: str) -> None:
        progress_bar.progress(frac, text=msg)

    track_specs = [
        {
            "path": path,
            "name": names_by_path[path],
            "bpm": float(effective_bpm(path)),
            "rms_env": analyses[path]["rms_env"],
            "rms_hop": analyses[path]["rms_hop"],
            "rms_sr": analyses[path]["rms_sr"],
            "beats": analyses[path].get("beats", []),
        }
        for path in ordered_paths
    ]

    try:
        result = engine.render_mix(
            tracks=track_specs,
            output_bpm=float(output_bpm),
            crossfade_seconds=float(crossfade_s),
            output_path=output_path,
        )
    except engine.RenderError as exc:
        progress_bar.empty()
        st.error(
            f"Render failed at stage **{exc.stage}** on track "
            f"**{exc.track_name}**:\n\n`{exc.original}`"
        )
    else:
        progress_bar.progress(1.0, text="Done!")
        st.success(
            f"Mix rendered to `{result['output_path']}` — "
            f"{engine.format_duration(result['duration'])} long, "
            f"{result['integrated_lufs']:.1f} LUFS integrated, "
            f"true peak {result['true_peak_dbtp']:.2f} dBTP."
        )
        st.audio(result["output_path"])
        with st.expander("Render log"):
            for line in result["log"]:
                st.text(line)
