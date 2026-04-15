"""Download source video and extract a low-res proxy for visual analysis.

We keep the original 4K file for the final cut, but analyze visuals on a
downscaled proxy -- scene detection and motion on 4K is needlessly slow.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def download_video(url: str, out_dir: Path) -> Path:
    """Download a YouTube video at the best available quality.

    Returns the path to the downloaded file. Skips download if already present
    (keyed by yt-dlp's `%(id)s`).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(out_dir / "%(id)s.%(ext)s")

    # --merge-output-format mp4 keeps us in mp4 land so ffmpeg cuts are clean.
    # --no-overwrites + -c makes this idempotent across runs.
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=2160]+bestaudio/best",
        "--merge-output-format", "mp4",
        "--no-overwrites",
        "-c",
        "-o", output_template,
        "--print", "after_move:filepath",
        url,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    path_line = next(
        (line for line in reversed(result.stdout.splitlines()) if line.strip()),
        "",
    )
    path = Path(path_line.strip())
    if not path.exists():
        raise RuntimeError(f"yt-dlp did not report a usable file path: {result.stdout}")
    return path


def make_proxy(source: Path, out_dir: Path, height: int = 360, fps: int = 5) -> Path:
    """Create a small proxy video for visual analysis.

    360p @ 5fps is more than enough to detect scenes and motion, and is ~100x
    faster to process than a 4K source.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    proxy_path = out_dir / f"{source.stem}.proxy.mp4"
    if proxy_path.exists():
        return proxy_path

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(source),
        "-vf", f"scale=-2:{height},fps={fps}",
        "-an",  # no audio in proxy
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        str(proxy_path),
    ]
    subprocess.run(cmd, check=True)
    return proxy_path


def extract_audio(source: Path, out_dir: Path, sr: int = 22050) -> Path:
    """Extract mono audio for librosa analysis. 22.05kHz mono is plenty."""
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / f"{source.stem}.audio.wav"
    if wav_path.exists():
        return wav_path

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(source),
        "-ac", "1", "-ar", str(sr),
        "-vn",
        str(wav_path),
    ]
    subprocess.run(cmd, check=True)
    return wav_path
