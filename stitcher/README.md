# Video Stitcher

Stitch a folder of video clips into a single video with smooth,
professional transitions — the kind you'd actually see in music videos
and title sequences, nothing corny — plus an optional randomized Ken
Burns (slow zoom/pan) move on each clip.

## Quick start (Streamlit GUI)

```sh
# 1. Install deps (requires Python 3.9+, ffmpeg 4.3+ on PATH)
cd stitcher
pip install -r requirements.txt

# 2. Run the GUI
streamlit run gui.py
```

Then in the browser:

1. Paste a **folder path** and click **Scan folder** — every video in it
   is listed with a thumbnail, duration, and resolution.
2. Curate the sequence:
   - **Include** checkboxes deselect clips without removing them.
   - **⬆ / ⬇** arrows reorder clips by hand.
   - **Anchor as FIRST / LAST** pins a clip to an end — anchors survive
     shuffles and recommendations.
   - **🔀 Shuffle order** randomizes the middle.
   - **✨ Recommend order** samples frames from each clip and measures
     color palette, brightness, and motion, then builds a paced order:
     near-duplicate clips (slight variations of the same shot) are
     spread as far apart as possible — never adjacent — and the fastest
     third of clips is interspersed evenly between the calmer ones, with
     a calm clip opening the sequence.
   - **Speed** per clip (0.5x-2x) slows down or speeds up individual
     clips; audio stays pitch-correct.
   - **🐢 Slow down fast clips** measures each clip's motion and applies
     a slight slow-down (0.75x-0.9x, scaled by how frantic the clip is
     relative to the group) to the ones that move much faster than the
     rest; **↺ Reset speeds** puts everything back to 1x.
3. Pick an output resolution — 4K landscape (3840x2160, the default),
   4K vertical, 1440p, 1080p landscape/vertical, square 4K/1080, or 720p
   — then a transition style and duration, optionally enable **Ken Burns**
   (per-clip opt-out checkboxes appear in the list), and note that
   **Mute all audio** is ON by default — untick it to keep clip audio,
   which is then crossfaded through every transition.
4. Click **⚡ Render Quick Preview** for a fast, small (max 640px) render
   to check the sequence — it uses the *same* random transition picks and
   Ken Burns moves as the full render, so what you preview is what you
   get. Then **Render Stitched Video** for the full resolution, and
   download. Two progress bars track the render: overall, and within the
   current step (per-clip prep and the final stitch each report live
   percentage from ffmpeg).

## Transitions

A deliberately small, curated set:

| Style | What it looks like |
|-------|--------------------|
| Blend (crossfade) | Classic dissolve between shots |
| Fade to black | Dip to black — the music-video staple |
| Fade to white | Dip to white — brighter, dreamier |
| Film dissolve | Grainy per-pixel dissolve, filmic |
| Smooth wipe | Soft-edged directional wipe |
| Random mix (curated) | Varies per cut, weighted toward blends and dips to black (no white flashes) |
| Hard cut | No transition, straight concat |

When Random mix is selected, a multiselect lets you choose exactly which
of the styles above the mix may draw from (fade-to-white is off by
default; CLI: `--mix-include`). The weighting still applies within your
selection.

## Ken Burns effect

When enabled, each clip gets its own randomized move: push in or pull
out (6–14% zoom on *subtle*, 12–24% on *medium*) with a gentle drifting
pan between random anchor points. Rendering supersamples the frame at 2x
before the `zoompan` crop so the motion stays smooth instead of
stair-stepping.

## Audio

**Muted by default** (one master checkbox in the sidebar) — ideal when
you'll lay a music bed over the result. Untick it to keep clip audio:
tracks are normalized to 48 kHz stereo, clips with no audio get silence,
and every cut is audio-crossfaded to match the video transition.

## CLI usage (no browser)

```sh
cd stitcher
python stitcher.py clip1.mp4 clip2.mp4 clip3.mp4 -o out.mp4
python stitcher.py *.mp4 -o out.mp4 --transition "Fade to black" --duration 1.0
python stitcher.py *.mp4 -o out.mp4 --ken-burns --keep-audio --size 1080x1920
python stitcher.py *.mp4 -o out.mp4 --size 3840x2160   # 4K (any WxH works)
python stitcher.py *.mp4 -o out.mp4 --speed 0.9        # 0.9x on every clip
python stitcher.py *.mp4 -o out.mp4 --seed 42   # reproducible randomness
```

Output is muted by default; pass `--keep-audio` to keep it.

## How it works

Two ffmpeg passes:

1. **Normalize** — every clip is scaled/padded to the target resolution,
   conformed to a constant frame rate and square pixels, and optionally
   given its Ken Burns move. Audio (if kept) is conformed to 48 kHz
   stereo, injecting silence where a clip has none.
2. **Stitch** — one `xfade` chain joins the video (plus an `acrossfade`
   chain for audio), with offsets computed from the normalized durations.
   Transition length is auto-clamped so the shortest clip survives.

The normalize pass is what makes `xfade` reliable: it requires identical
size, rate, and pixel format on both sides of every cut.

## File layout

```
stitcher/
  gui.py             # Streamlit GUI (folder scan, ordering, anchors, render)
  stitcher.py        # Core two-pass ffmpeg engine + CLI
  analyze.py         # Frame sampling, visual features, recommended order
  requirements.txt   # streamlit, numpy, opencv-headless (+ ffmpeg on PATH)
```
