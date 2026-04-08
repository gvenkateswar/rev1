# Video Shorts Generator

Analyzes a video's audio track to automatically find the best segments to cut into short-form content (YouTube Shorts, TikTok, Reels, etc.).

## How It Works

The tool uses multiple audio signals to score every possible clip window:

| Signal | Weight | What it detects |
|--------|--------|-----------------|
| **Audio energy** | 25% | Loud, exciting moments |
| **Speech density** | 20% | Segments packed with talking |
| **Energy dynamics** | 15% | Varied audio = interesting moments |
| **Speech rate** | 15% | Fast-paced speech = high engagement |
| **Emphasis** | 10% | Exclamations (!), questions (?) |
| **Spectral brightness** | 5% | Bright, crisp audio |
| **Silence penalty** | -10% | Penalizes dead air |

It also uses [OpenAI Whisper](https://github.com/openai/whisper) to transcribe speech, giving you a preview of what's said in each suggested clip.

## Requirements

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/) installed and on your PATH

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Basic (find top 5 clips)
```bash
python shorts_generator.py my_video.mp4
```

### Custom options
```bash
python shorts_generator.py my_video.mp4 \
  --top 10 \
  --min-duration 20 \
  --max-duration 45 \
  --whisper-model small
```

### Export clips as separate video files
```bash
python shorts_generator.py my_video.mp4 --export-clips --output-dir ./my_shorts
```

### JSON output (for piping into other tools)
```bash
python shorts_generator.py my_video.mp4 --json
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--top N` | 5 | Number of clips to suggest |
| `--min-duration` | 15 | Minimum clip length (seconds) |
| `--max-duration` | 60 | Maximum clip length (seconds) |
| `--whisper-model` | base | Whisper model: `tiny`, `base`, `small`, `medium`, `large` |
| `--export-clips` | off | Export suggested clips as separate `.mp4` files |
| `--output-dir` | `./shorts_output` | Where to save exported clips |
| `--json` | off | Output results as JSON |

## Example Output

```
============================================================
  TOP 5 SHORTS CANDIDATES
============================================================

  #1  [3:20 - 4:05] (45s)  score=0.78
       Why: high energy, dynamic audio, dense speech
       Speech: "This is the part where everything changed..."

  #2  [8:10 - 8:55] (45s)  score=0.72
       Why: fast-paced speech, emphatic speech (!/?)
       Speech: "Wait, are you serious?! That's incredible!..."

  #3  [12:00 - 12:40] (40s)  score=0.68
       Why: high energy, dense speech
       Speech: "Let me show you exactly how this works..."
```

## Tips

- Use `--whisper-model small` or `medium` for better transcription accuracy (slower but worth it for longer videos).
- For YouTube Shorts / TikTok, use `--max-duration 60`. For Instagram Reels, `--max-duration 90`.
- The `--json` flag is useful for building automation pipelines around this tool.
