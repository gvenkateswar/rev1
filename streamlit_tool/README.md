# streamlit_tool — patched Video Shorts Generator

Drop-in replacement for the files in `~/Downloads/rev1-claude-video-shorts-generator-Okw78/`, with three changes:

## What's new

1. **Instrumental mode (sidebar checkbox).** Skips Whisper transcription entirely and rebalances scoring onto pure audio features (energy, dynamics, brightness). For instrumental tracks this stops vocal-heavy sections from winning over instrumental breaks. Also saves ~3 min of analysis time per video.

2. **Vertical 9:16 export with face tracking (sidebar checkboxes).** When **Vertical output** is on, exports are forced to 1080×1920. When **Smart crop** is also on, each clip is scanned for faces — largest face per sampled frame, median center across the clip — and the crop is centered on the performer. Falls back to center-crop when no face is found.

3. **Fast ffmpeg seek on export.** The old command used `-i input -ss X`, which makes ffmpeg decode the 4K file from 0:00 up to the clip start *every time*. The patched command uses input-seek + output-seek (`-ss X-2 -i input -ss 2 -t D`), which jumps to the keyframe just before the target and then fine-seeks to the exact frame. Expect roughly a 5–10× speedup on 4K exports.

## Install (on your Mac)

Your existing Python 3.9 env has some conflicts from an earlier `pip install mediapipe` that failed partway through. Clean those up first, then install the new requirements:

```sh
# Clean up the partial install from earlier
pip uninstall -y opencv-contrib-python mediapipe jax jaxlib ml-dtypes opt-einsum

# Install the patched requirements (pins numpy<2, adds opencv-python-headless)
cd ~/Downloads/rev1-claude-video-shorts-generator-Okw78    # or wherever you put the files
pip install -r requirements.txt

# Verify OpenCV + face cascade are available
python -c "import cv2; c = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'); print('cv2', cv2.__version__, 'cascade-ok:', not c.empty())"
```

## Run

```sh
streamlit run gui.py
```

Then in the sidebar:

- For your instrumental track: tick **Instrumental track (skip speech analysis)**.
- For Shorts-ready output: leave **Vertical output (9:16)** and **Smart crop (track faces)** on.

## CLI usage (same tool, no browser)

```sh
python shorts_generator.py haveli-video-final.m4v --instrumental --export-clips --vertical
python shorts_generator.py video.mp4 --no-smart-crop --vertical       # center-crop only
python shorts_generator.py video.mp4 --instrumental --top 4 --min-duration 25 --max-duration 35
```

## Why Haar cascade, not MediaPipe

MediaPipe's BlazeFace is more accurate, but it pulls in `jax>=0.4.30`, which uses `match` statements (Python 3.10+) and refuses to install on Python 3.9. OpenCV's built-in Haar cascade ships with `opencv-python-headless`, needs no extra download, and is plenty for front-facing performer shots. If you later move to Python 3.10+ and want a better detector, swap `_detect_face_center_x()` in `shorts_generator.py` for a MediaPipe call — the function signature (returns median center-X) stays the same.

## Known limitations

- **Haar cascade misses profile shots and heavily stylized lighting.** When it fails on a clip, smart-crop falls back to center-crop automatically — you won't get a broken export, just a less-optimal crop.
- **Static crop per clip.** The crop X is fixed for the whole 30s based on median face position. If the performer walks across the frame mid-clip, you'd want a dynamic crop (ffmpeg `sendcmd`/`zoompan`). Ask if you need this; it's another ~30 lines.
- **Analysis is NOT cached across Streamlit restarts.** If you quit and re-launch `streamlit run gui.py`, you'll need to click Analyze again. Session state persists *within* a session, so flipping vertical/smart-crop and re-exporting does NOT re-run Whisper — only the ffmpeg cuts.
