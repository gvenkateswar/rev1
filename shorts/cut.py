"""Cut candidate clips out of the source video with ffmpeg.

We always re-encode (rather than stream-copy) because stream-copy snaps to
keyframes, which for music videos is often 2-4 seconds off the requested start
and can leave the first frame black. Re-encoding 30s of 4K is still fast.

Optionally reframes to 9:16 for vertical Shorts via a simple center-crop.
A smarter salient-region crop (face/subject tracking) would be a future
improvement -- center-crop is the right default for music videos where the
subject is usually in the middle of the frame.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .rank import Clip


def cut_clip(
    source: Path,
    clip: Clip,
    out_path: Path,
    vertical: bool = False,
    crf: int = 18,
) -> None:
    """Cut a single clip from source to out_path, optionally 9:16."""
    # -ss BEFORE -i for fast seek, then -ss 0 after for precision. Putting -ss
    # only before -i is fast but imprecise; only after is precise but slow on
    # 4K sources. The two-step form gives both.
    input_seek = max(0.0, clip.start - 2.0)
    fine_seek = clip.start - input_seek

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{input_seek:.3f}",
        "-i", str(source),
        "-ss", f"{fine_seek:.3f}",
        "-t", f"{clip.end - clip.start:.3f}",
    ]

    if vertical:
        # Center-crop to 9:16, scale to 1080x1920. Using `min(iw, ih*9/16)`
        # handles both landscape and already-vertical sources safely.
        vf = "crop='min(iw,ih*9/16)':ih,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
        cmd += ["-vf", vf]

    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def cut_all(
    source: Path,
    clips: list[Clip],
    out_dir: Path,
    vertical: bool = False,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, clip in enumerate(clips, 1):
        suffix = "_vertical" if vertical else ""
        out_path = out_dir / f"short_{i:02d}_{int(clip.start):05d}s{suffix}.mp4"
        cut_clip(source, clip, out_path, vertical=vertical)
        paths.append(out_path)
    return paths
