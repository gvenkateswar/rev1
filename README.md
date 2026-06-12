# Video & Audio Tools

This repo holds three independent tools:

1. **Video Shorts Generator** (below) — find the best 30s clips in a long video.
2. **[Speaker & Emotion Transcriber](transcriber/README.md)** — transcribe
   audio/video, tell speakers apart, and tag each segment with an emotion fused
   from voice tone *and* the words. CLI + local Streamlit GUI. See
   [`transcriber/`](transcriber/).
3. **[World History Atlas](historical-map/README.md)** — interactive world map
   with a timeline slider (1000–2025); political boundaries crossfade in real
   time as you scrub through history. Static site, no build step. See
   [`historical-map/`](historical-map/).

---

# Video Shorts Generator

Find the best 30-second clips in a long music video and export them as
vertical Shorts with face-tracking crop and burned-in captions.

## Quick start (Streamlit GUI)

```sh
# 1. Install deps (requires Python 3.9+, ffmpeg on PATH)
cd streamlit_tool
pip install -r requirements.txt

# 2. Run the GUI
streamlit run gui.py
```

Then in the browser:
- Point it at a local video file (or upload one <200 MB)
- Check **Instrumental track** if there are no vocals
- Check **Vertical output** + **Smart crop** for 9:16 Shorts
- Check **Burn captions** and type per-clip text in the Export section
- Click **Analyze Video**, then **Export Selected Clips**

## What it does

1. Extracts audio and analyzes loudness, dynamics, and spectral brightness.
2. Optionally transcribes speech with Whisper (skip for instrumental tracks).
3. Scores every candidate window and picks the top N non-overlapping segments.
4. Cuts clips from the source with fast two-step ffmpeg seek.
5. Optionally crops to 9:16 centered on the largest detected face (Haar cascade).
6. Optionally burns bold white-on-black captions with face-aware repositioning
   (caption flips between lower and upper third if the face enters the text zone).

## CLI usage (no browser)

```sh
cd streamlit_tool
python shorts_generator.py /path/to/video.mp4 --instrumental --vertical --export-clips
python shorts_generator.py video.mp4 --top 4 --min-duration 25 --max-duration 35
```

## Dependency notes

numpy, pandas, and opencv are pinned to versions compatible with torch 2.2.x
(which Whisper pulls in on Python 3.9). See `streamlit_tool/requirements.txt`
for the exact caps and the rationale.

## File layout

```
streamlit_tool/
  gui.py                 # Streamlit GUI
  shorts_generator.py    # Analysis + scoring + export + captions
  requirements.txt       # Pinned deps (numpy<2, pandas<2.2, opencv<4.11)

shorts/                  # Alternate CLI-only tool (different scoring approach)
  cli.py, audio.py, video.py, rank.py, cut.py, download.py
```
