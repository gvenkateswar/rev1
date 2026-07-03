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

# ---------------------------------------------------------------------------
# Track ordering — the ▲▼ buttons on each card set the render order
# (top card renders first). A new folder resets to alphabetical; files
# already ordered keep their positions when the folder is rescanned.
# ---------------------------------------------------------------------------

order_sig = tuple(sorted(names_by_path))
if st.session_state.get("track_order_sig") != order_sig:
    kept = [p for p in st.session_state.get("track_order", []) if p in names_by_path]
    added = sorted(
        (p for p in names_by_path if p not in kept),
        key=lambda p: names_by_path[p].lower(),
    )
    st.session_state.track_order = kept + added
    st.session_state.track_order_sig = order_sig
ordered_paths = st.session_state.track_order


def move_track(path: str, delta: int) -> None:
    order = st.session_state.track_order
    i = order.index(path)
    j = i + delta
    if 0 <= j < len(order):
        order[i], order[j] = order[j], order[i]

# ---------------------------------------------------------------------------
# Effective BPM helpers
# ---------------------------------------------------------------------------


def bpm_key(path: str) -> str:
    return f"bpm::{path}"


def scale_bpm(key: str, factor: float) -> None:
    value = st.session_state.get(key)
    if value:
        st.session_state[key] = round(value * factor, 1)


# Seed each track's BPM input once: filename override beats detection, and
# detections that landed an octave off the folder's median (librosa hearing
# half/double time) are auto-folded to the right octave. Filename BPMs and
# anything the user has already edited are never second-guessed.
seed_bpms = {p: (i["filename_bpm"] or i["detected_bpm"]) for p, i in analyses.items()}
folder_median = engine.suggest_output_bpm(list(seed_bpms.values()))
for path, info in analyses.items():
    key = bpm_key(path)
    if key not in st.session_state:
        seed = seed_bpms[path]
        if seed and folder_median and not info["filename_bpm"]:
            folded, mult = engine.fold_bpm_to_reference(seed, folder_median)
            if mult != 1.0:
                st.session_state[f"autofix::{path}"] = (seed, folded, mult)
                seed = folded
        st.session_state[key] = seed


def effective_bpm(path: str) -> float | None:
    return st.session_state.get(bpm_key(path))


def is_included(path: str) -> bool:
    return st.session_state.get(f"inc::{path}", True)


# ---------------------------------------------------------------------------
# Global controls (rendered before the table so stretch % reflects them live)
# ---------------------------------------------------------------------------

st.subheader("1 · Tracks — order, audition, set BPMs")
st.caption("Reorder with the ▲▼ buttons on each card — the mix renders top to bottom.")

# Order tools: audio-similarity recommendation, shuffle, and anchors.
oc_rec, oc_shuf, oc_first, oc_last = st.columns(
    [1.6, 1.1, 1.3, 1.3], vertical_alignment="center"
)
with oc_first:
    anchor_first = st.checkbox(
        "Anchor first track",
        key="anchor_first",
        help="Keep the current first card in place when recommending or shuffling.",
    )
with oc_last:
    anchor_last = st.checkbox(
        "Anchor last track",
        key="anchor_last",
        help="Keep the current last card in place when recommending or shuffling.",
    )
with oc_rec:
    if st.button(
        "✨ Recommend order",
        help="Orders the tracks so neighbours sound least alike (timbre "
        "fingerprint from analysis) — avoids two similar tracks back to back.",
    ):
        fingerprints = [analyses[p].get("fingerprint") for p in ordered_paths]
        if any(f is None for f in fingerprints):
            st.toast("Similarity data missing for some tracks — rescan the folder.")
        else:
            perm = engine.order_for_max_variety(
                fingerprints, fix_first=anchor_first, fix_last=anchor_last
            )
            st.session_state.track_order = [ordered_paths[i] for i in perm]
            ordered_paths = st.session_state.track_order
with oc_shuf:
    if st.button("🎲 Shuffle", help="Randomize the order (respects the anchors)."):
        import random

        lo = 1 if anchor_first else 0
        hi = len(ordered_paths) - 1 if anchor_last else len(ordered_paths)
        middle = ordered_paths[lo:hi]
        random.shuffle(middle)
        st.session_state.track_order = (
            ordered_paths[:lo] + middle + ordered_paths[hi:]
        )
        ordered_paths = st.session_state.track_order

suggested = engine.suggest_output_bpm(
    [effective_bpm(p) for p in ordered_paths if is_included(p)]
)

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

for idx, path in enumerate(ordered_paths):
    info = analyses[path]
    name = names_by_path[path]
    with st.container(border=True):
        top_inc, top_up, top_dn, top_l, top_r = st.columns(
            [0.55, 0.3, 0.3, 3.85, 1], vertical_alignment="center"
        )
        with top_inc:
            included = st.checkbox(
                "Mix",
                value=True,
                key=f"inc::{path}",
                help="Uncheck to leave this track out of the rendered mix.",
            )
        with top_up:
            st.button(
                "▲",
                key=f"up::{path}",
                on_click=move_track,
                args=(path, -1),
                disabled=idx == 0,
                help="Move this track up (earlier in the mix)",
            )
        with top_dn:
            st.button(
                "▼",
                key=f"dn::{path}",
                on_click=move_track,
                args=(path, 1),
                disabled=idx == len(ordered_paths) - 1,
                help="Move this track down (later in the mix)",
            )
        with top_l:
            badges = []
            if info["filename_bpm"]:
                badges.append(":blue-badge[BPM from filename]")
            autofix = st.session_state.get(f"autofix::{path}")
            if autofix:
                orig, folded, mult = autofix
                label = "×2" if mult > 1 else "÷2"
                badges.append(
                    f":violet-badge[auto {label}: detected {orig:g} looked "
                    f"{'half' if mult > 1 else 'double'}-time]"
                )
            if info["detected_bpm"] is None:
                badges.append(":red-badge[⚠ detection failed — set BPM manually]")
            if not included:
                badges.append(":gray-badge[not in mix]")
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
                if included:
                    missing_bpm.append(name)
        with c_audio:
            st.audio(path)

# ---------------------------------------------------------------------------
# Transition preview & manual alignment
# ---------------------------------------------------------------------------

included_paths = [p for p in ordered_paths if is_included(p)]


@st.cache_data(show_spinner=False)
def preview_cached(
    out_path: str, out_mtime: float, out_bpm: float,
    in_path: str, in_mtime: float, in_bpm: float,
    output_bpm_v: float, fade_v: float, offset_v: float,
) -> dict:
    def spec(path, mtime, bpm):
        info = analyze_cached(path, mtime)
        return {"path": path, "name": Path(path).name, "bpm": bpm, **info}

    return engine.render_transition_preview(
        spec(out_path, out_mtime, out_bpm),
        spec(in_path, in_mtime, in_bpm),
        output_bpm=output_bpm_v,
        fade_seconds=fade_v,
        manual_offset_s=offset_v,
    )


def preview_wav_bytes(preview: dict) -> bytes:
    import io

    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, preview["audio"], preview["sample_rate"], format="WAV",
             subtype="PCM_16")
    return buf.getvalue()


OUTGOING_COLOR = "#2bb3a3"   # teal, like a Logic audio region
INCOMING_COLOR = "#c95c9e"   # pink


def preview_total_seconds(preview: dict) -> float:
    return float(preview["fade_start"] + len(preview["in_env"]) / preview["env_rate"])


def preview_chart(preview: dict, window: tuple) -> None:
    """Two stacked DAW-style waveform panels (filled, mirrored around zero)
    on a shared time axis — outgoing on top, incoming below — with tick marks
    at each track's detected beats, so beat alignment is visible while
    nudging. Envelopes have the crossfade gains applied, so the equal-power
    taper shows in the shape. *window* is the (start, end) zoom range in
    preview seconds; envelopes are sliced and adaptively downsampled so
    zooming in reveals more detail.
    """
    import altair as alt
    import numpy as np
    import pandas as pd

    er = preview["env_rate"]
    t0, t1 = float(window[0]), float(window[1])
    x_scale = alt.Scale(domain=[t0, t1], nice=False)
    fade0 = preview["fade_start"]
    fade1 = fade0 + preview["fade_seconds"]
    band_df = pd.DataFrame(
        [{"x1": max(t0, fade0), "x2": min(t1, fade1)}]
        if fade1 > t0 and fade0 < t1 else {"x1": [], "x2": []}
    )

    def wave_df(env, offset):
        peak = float(np.max(env)) if len(env) else 0.0
        i0 = max(0, int((t0 - offset) * er))
        i1 = min(len(env), max(i0, int(np.ceil((t1 - offset) * er))))
        seg = np.asarray(env[i0:i1], dtype=float)
        if not len(seg) or peak <= 0:
            return pd.DataFrame({"t": [], "hi": [], "lo": []})
        step = max(1, int(np.ceil(len(seg) / 2200)))  # cap points per panel
        if step > 1:
            pad = (-len(seg)) % step
            if pad:
                seg = np.concatenate([seg, np.zeros(pad)])
            seg = seg.reshape(-1, step).max(axis=1)
        t = offset + (i0 + np.arange(len(seg)) * step + step / 2) / er
        return pd.DataFrame({"t": t, "hi": seg / peak, "lo": -seg / peak})

    def panel(env, offset, beats, color, label, last):
        axis = alt.Axis(grid=False) if last else None

        def x(field):
            return alt.X(field, scale=x_scale, axis=axis,
                         title="seconds" if last else None)

        y = alt.Y("hi:Q", title=label,
                  axis=alt.Axis(labels=False, ticks=False, grid=False),
                  scale=alt.Scale(domain=[-1.05, 1.05]))
        layers = []
        if len(band_df):
            layers.append(
                alt.Chart(band_df).mark_rect(color="#808080", opacity=0.18)
                .encode(x=x("x1:Q"), x2="x2:Q")
            )
        visible_beats = [b for b in np.asarray(beats, dtype=float) if t0 <= b <= t1]
        if visible_beats:
            layers.append(
                alt.Chart(pd.DataFrame({"t": visible_beats}))
                .mark_rule(color="#808080", strokeWidth=1, opacity=0.6)
                .encode(x=x("t:Q"))
            )
        wdf = wave_df(env, offset)
        if len(wdf):
            layers.append(
                alt.Chart(wdf).mark_area(color=color, opacity=0.95)
                .encode(x=x("t:Q"), y=y, y2="lo:Q")
            )
        else:  # silent or out-of-window segment: draw the zero line
            layers.append(
                alt.Chart(pd.DataFrame({"t": [max(t0, offset), t1], "hi": [0.0, 0.0]}))
                .mark_line(color=color, strokeWidth=1)
                .encode(x=x("t:Q"), y=y)
            )
        return alt.layer(*layers).properties(height=110)

    chart = alt.vconcat(
        panel(preview["out_env"], 0.0, preview["out_beats"],
              OUTGOING_COLOR, "outgoing", last=False),
        panel(preview["in_env"], preview["fade_start"], preview["in_beats"],
              INCOMING_COLOR, "incoming", last=True),
        spacing=4,
    ).configure_view(strokeOpacity=0)
    st.altair_chart(chart, use_container_width=True)
    st.caption(
        f":gray[Gray band = the crossfade ({preview['fade_seconds']:.1f} s "
        f"equal-power); vertical ticks = each track's detected beats (every "
        f"beat, not just downbeats). Ticks lining up vertically across the "
        f"two panels = a tight transition.]"
    )


st.subheader("2 · Transitions — preview & manual alignment")

if len(included_paths) < 2:
    st.caption("With fewer than two tracks in the mix there are no transitions.")
else:
    st.caption(
        "Each crossover is placed automatically (energy decay + beat "
        "alignment). Preview any transition to hear it and see both "
        "waveforms; if the algorithm didn't nail it, nudge the fade point — "
        "the nudge shifts where the fade begins in the outgoing track and is "
        "used in the final render."
    )
    for a, b in zip(included_paths[:-1], included_paths[1:]):
        na, nb = names_by_path[a], names_by_path[b]
        nudge_key = f"nudge::{a}::{b}"
        shown_key = f"preview_on::{a}::{b}"
        if nudge_key not in st.session_state:
            st.session_state[nudge_key] = 0.0
        # NOTE: the label must not change with the nudge value — a changed
        # label makes Streamlit treat the expander as a new widget and
        # collapse it on every slider move.
        with st.expander(f"{na}  →  {nb}"):
            bpm_a, bpm_b = effective_bpm(a), effective_bpm(b)
            if not bpm_a or not bpm_b:
                st.info("Set BPMs on both tracks to preview this transition.")
                continue
            col_slider, col_btn = st.columns([3, 1], vertical_alignment="bottom")
            with col_slider:
                st.slider(
                    "Nudge crossfade point (seconds)",
                    min_value=-4.0, max_value=4.0, step=0.01,
                    key=nudge_key,
                    help="0 = fully automatic. Positive starts the fade later "
                    "in the outgoing track, negative earlier. Applied after "
                    "beat alignment, so use it when the automatic placement "
                    "is wrong.",
                )
            with col_btn:
                if st.button("Preview crossover", key=f"pv_btn::{a}::{b}",
                             use_container_width=True):
                    st.session_state[shown_key] = True
            if st.session_state.get(shown_key):
                with st.spinner("Rendering preview…"):
                    preview = preview_cached(
                        a, Path(a).stat().st_mtime, float(bpm_a),
                        b, Path(b).stat().st_mtime, float(bpm_b),
                        float(output_bpm), float(crossfade_s),
                        float(st.session_state[nudge_key]),
                    )
                total = round(preview_total_seconds(preview), 1)
                zoom_key = f"zoom::{a}::{b}"
                stored = st.session_state.get(zoom_key)
                if stored is not None and not (0.0 <= stored[0] < stored[1] <= total):
                    del st.session_state[zoom_key]  # settings changed the range
                window = st.slider(
                    "Zoom (visible time window, seconds)",
                    min_value=0.0, max_value=total,
                    value=st.session_state.get(zoom_key, (0.0, total)),
                    step=0.1, key=zoom_key,
                    help="Narrow the window to inspect beat alignment "
                    "precisely — waveform detail increases as you zoom in.",
                )
                preview_chart(preview, window)
                st.caption(
                    f"Fade: {preview['fade_seconds']:.1f} s starting at "
                    f"{preview['fade_start']:.1f} s into this preview "
                    f"(anchor {engine.format_duration(preview['anchor_seconds'])} "
                    f"into the stretched track — {preview['note']})."
                )
                st.audio(preview_wav_bytes(preview))

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

st.subheader("3 · Render")

if missing_bpm:
    st.warning(
        "Set a manual BPM for these tracks before rendering: "
        + ", ".join(f"**{n}**" for n in missing_bpm)
    )
if not included_paths:
    st.warning("All tracks are deselected — include at least one to render.")
elif len(included_paths) < len(ordered_paths):
    st.caption(
        f"Rendering {len(included_paths)} of {len(ordered_paths)} tracks "
        f"({len(ordered_paths) - len(included_paths)} deselected)."
    )

output_name = output_name.strip() or default_name
if not output_name.lower().endswith(".wav"):
    output_name += ".wav"
output_path = folder_path / output_name

if st.button(
    "🎚️ Render mix",
    type="primary",
    disabled=bool(missing_bpm) or not included_paths,
    help="Set a BPM on every included track first." if missing_bpm else None,
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
        for path in included_paths
    ]

    try:
        result = engine.render_mix(
            tracks=track_specs,
            output_bpm=float(output_bpm),
            crossfade_seconds=float(crossfade_s),
            output_path=output_path,
            anchor_offsets=[
                st.session_state.get(f"nudge::{a}::{b}", 0.0)
                for a, b in zip(included_paths[:-1], included_paths[1:])
            ],
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
