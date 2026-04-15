# shorts

Find and cut the best 30-second clips out of a long YouTube music video.

Built for the workflow of "I have a 30–60 minute 4K music video and I want
4–5 Shorts out of it, each on the best audio + visual moment."

## What it does

1. Downloads the source with `yt-dlp` (or uses a local file).
2. Extracts a low-res proxy for fast visual analysis and mono audio for music analysis.
3. Scores every second of the video on two axes:
   - **Audio** — loudness (RMS), onset density, and "lift" (current moment is
     loud and the preceding ~6s was quieter; catches the lead-in to drops and
     choruses).
   - **Video** — scene-cut density and frame-to-frame motion.
4. Slides a 30s window across the timeline and picks the top N non-overlapping
   windows. Each pick is snapped to the nearest scene cut or downbeat (within
   ~1.5s) so the clip doesn't start mid-phrase or mid-shot.
5. Cuts the clips out of the original 4K source with ffmpeg. Optional 9:16
   center-crop for Shorts.
6. Writes a manifest JSON so you can re-cut or override picks later without
   re-running analysis.

## Install

```
pip install -r requirements.txt
# also need these on your PATH:
#   ffmpeg   (https://ffmpeg.org)
#   yt-dlp   (https://github.com/yt-dlp/yt-dlp)
```

## Usage

```
# URL -> 5 ranked 30s Shorts-ready 9:16 clips
python -m shorts https://youtu.be/XXXX --vertical

# Don't cut, just print the best timestamps (feed into your existing editor)
python -m shorts https://youtu.be/XXXX --list-only

# Local file, 4 clips of 25s each, landscape
python -m shorts /path/to/video.mp4 --local -n 4 -l 25

# Tune the mix (default is 0.65 audio / 0.35 video)
python -m shorts URL --audio-weight 0.5 --video-weight 0.5
```

Output looks like:

```
[5/5] top candidates:
      #  start     end       score   reason
      1  1:23      1:53      0.812   high audio energy, scene cut
      2  4:05      4:35      0.774   dynamic visuals, downbeat
      3  7:48      8:18      0.730   high audio energy, dynamic visuals
      ...
```

## How the files fit together

- `shorts/download.py` — yt-dlp wrapper, proxy generation, audio extraction
- `shorts/audio.py`    — librosa-based per-second audio score + beats
- `shorts/video.py`    — PySceneDetect + OpenCV motion, per-second score
- `shorts/rank.py`     — sliding window, snap-to-beat/scene, non-max suppression
- `shorts/cut.py`      — ffmpeg clip extraction + optional 9:16 reframe
- `shorts/cli.py`      — argparse glue

## Honest limitations

- **"Best" is heuristic.** High-energy + scene-cut-dense windows are a good
  proxy for the chorus/drop, but it won't *understand* lyrics or narrative.
  Treat the output as strong candidates, not final picks — review before
  posting.
- **Vertical crop is naive.** It's a center-crop to 9:16. No face/subject
  tracking yet. Fine for most music videos where the subject is centered.
- **No lyrics alignment.** If you want to hit a specific line, override by
  editing the manifest and re-running with `--local` on the same file.

## Future improvements worth trying

- Salient-region crop for 9:16 (MediaPipe/face-detection-based reframing)
- Structural segmentation (librosa `segment_structure` / HPSS) to prefer
  distinct song sections over raw loudness
- Loudness normalization (EBU R128) on output clips
- `--from-manifest` mode to re-cut from an edited JSON without re-analyzing
