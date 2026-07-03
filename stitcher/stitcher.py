#!/usr/bin/env python3
"""
Video Stitcher — join multiple clips into one video with professional
transitions and an optional randomized Ken Burns (slow zoom/pan) effect.

Design notes
------------
Stitching happens in two ffmpeg passes:

1. **Normalize** — every clip is re-encoded to the same resolution, frame
   rate, SAR, and pixel format (and, if audio is kept, the same 48 kHz
   stereo layout, injecting silence for clips with no audio track). The
   optional Ken Burns move is applied here with `zoompan` over a 2x
   supersampled frame so sub-pixel pans stay smooth.
2. **Stitch** — one `xfade` (+ `acrossfade` for audio) chain joins the
   normalized clips. Normalization is what makes this pass reliable:
   `xfade` requires identical size/rate/format on both inputs.

Transitions are deliberately limited to a small curated set that reads as
professional (the kind of cuts you see in music videos and title
sequences) — no stars, hearts, or checkerboards.

CLI usage:
    python stitcher.py a.mp4 b.mp4 c.mp4 -o out.mp4
    python stitcher.py *.mp4 -o out.mp4 --transition fadeblack --duration 1.0
    python stitcher.py *.mp4 -o out.mp4 --ken-burns --keep-audio
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Curated transitions
# ---------------------------------------------------------------------------

# Display name -> list of xfade transition names to draw from (one is picked
# per cut; most styles map to a single name, "Smooth wipe" alternates
# direction so back-to-back wipes don't all travel the same way).
TRANSITION_STYLES: dict[str, list[str]] = {
    "Blend (crossfade)": ["fade"],
    "Fade to black": ["fadeblack"],
    "Fade to white": ["fadewhite"],
    "Film dissolve": ["dissolve"],
    "Smooth wipe": ["smoothleft", "smoothright"],
    "Hard cut (no transition)": [],
}

# The random mix leans on the two workhorses (crossfade / dip-to-black) and
# sprinkles in dissolves and wipes. Fade-to-white is excluded on purpose —
# repeated white flashes read as strobing.
RANDOM_MIX = (
    ["fade"] * 35
    + ["fadeblack"] * 30
    + ["dissolve"] * 20
    + ["smoothleft"] * 8
    + ["smoothright"] * 7
)
RANDOM_STYLE = "Random mix (curated)"

KEN_BURNS_INTENSITY = {
    # (min max-zoom, max max-zoom) — how far in the move travels.
    "subtle": (1.06, 1.14),
    "medium": (1.12, 1.24),
}

SIZE_PRESETS = {
    "1080p landscape (16:9)": (1920, 1080),
    "1080p vertical (9:16)": (1080, 1920),
    "Square (1:1)": (1080, 1080),
    "720p landscape (16:9)": (1280, 720),
}


@dataclass
class ClipInfo:
    path: str
    duration: float
    width: int
    height: int
    has_audio: bool


@dataclass
class StitchResult:
    output_path: str
    duration: float
    transitions_used: list[str]
    warnings: list[str] = field(default_factory=list)


ProgressFn = Callable[[int, int, str], None]


# ---------------------------------------------------------------------------
# ffmpeg helpers
# ---------------------------------------------------------------------------

def _require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise FileNotFoundError(
                f"{tool} not found on PATH. Install ffmpeg 4.3+ "
                "(Ubuntu: `sudo apt install ffmpeg`, macOS: `brew install ffmpeg`)."
            )


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-12:])
        raise RuntimeError(f"ffmpeg failed ({' '.join(cmd[:3])} ...):\n{tail}")


def probe_clip(path: str) -> ClipInfo:
    """Read duration / resolution / audio presence with ffprobe."""
    _require_ffmpeg()
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", path,
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe could not read {path}:\n{proc.stderr.strip()}")
    data = json.loads(proc.stdout)

    video = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    if video is None:
        raise ValueError(f"No video stream in {path}")
    has_audio = any(
        s.get("codec_type") == "audio" for s in data.get("streams", [])
    )

    duration = float(
        video.get("duration") or data.get("format", {}).get("duration") or 0
    )
    if duration <= 0:
        raise ValueError(f"Could not determine duration of {path}")

    return ClipInfo(
        path=path,
        duration=duration,
        width=int(video["width"]),
        height=int(video["height"]),
        has_audio=has_audio,
    )


# ---------------------------------------------------------------------------
# Ken Burns
# ---------------------------------------------------------------------------

def _ken_burns_filter(
    duration: float,
    width: int,
    height: int,
    fps: int,
    rng: random.Random,
    intensity: str = "subtle",
) -> str:
    """Build a randomized zoompan move (zoom in or out + gentle pan).

    The frame is first scaled to *cover* 2x the output size, then zoompan
    crops a moving window out of it. The 2x supersample keeps the pan from
    stair-stepping (zoompan rounds the crop origin to integers).
    """
    zoom_lo, zoom_hi = KEN_BURNS_INTENSITY[intensity]
    zmax = rng.uniform(zoom_lo, zoom_hi)
    if rng.random() < 0.5:
        z0, z1 = 1.0, zmax          # push in
    else:
        z0, z1 = zmax, 1.0          # pull out

    # Pan anchors as fractions of the available slack; drift a little from
    # start to end so the move never feels static.
    def anchor() -> float:
        return rng.uniform(0.15, 0.85)

    fx0, fy0 = anchor(), anchor()
    fx1 = min(max(fx0 + rng.uniform(-0.35, 0.35), 0.0), 1.0)
    fy1 = min(max(fy0 + rng.uniform(-0.35, 0.35), 0.0), 1.0)

    dur = max(duration, 0.1)
    prog = f"min(it/{dur:.3f},1)"   # 0 -> 1 across the clip
    z_expr = f"{z0:.4f}+({z1:.4f}-{z0:.4f})*{prog}"
    x_expr = f"(iw-iw/zoom)*({fx0:.4f}+({fx1:.4f}-{fx0:.4f})*{prog})"
    y_expr = f"(ih-ih/zoom)*({fy0:.4f}+({fy1:.4f}-{fy0:.4f})*{prog})"

    big_w, big_h = width * 2, height * 2
    return (
        f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase,"
        f"crop={big_w}:{big_h},setsar=1,fps={fps},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}'"
        f":d=1:s={width}x{height}:fps={fps}"
    )


# ---------------------------------------------------------------------------
# Pass 1 — normalize
# ---------------------------------------------------------------------------

def _normalize_clip(
    clip: ClipInfo,
    dst: str,
    width: int,
    height: int,
    fps: int,
    mute: bool,
    ken_burns: bool,
    intensity: str,
    rng: random.Random,
    final: bool = False,
) -> None:
    """Re-encode one clip to the common format (optionally with Ken Burns).

    `final=True` uses delivery encode settings (for the single-clip case
    where normalization output is the finished file).
    """
    if ken_burns:
        vf = _ken_burns_filter(clip.duration, width, height, fps, rng, intensity)
    else:
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
        )
    vf += ",format=yuv420p"

    cmd = ["ffmpeg", "-y", "-i", clip.path]

    silent_source = not mute and not clip.has_audio
    if silent_source:
        cmd += [
            "-f", "lavfi", "-t", f"{clip.duration:.3f}",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        ]

    cmd += ["-vf", vf, "-map", "0:v:0"]

    if mute:
        cmd += ["-an"]
    else:
        if silent_source:
            cmd += ["-map", "1:a:0"]
        else:
            cmd += ["-map", "0:a:0", "-af", "aresample=async=1:first_pts=0,apad"]
        cmd += ["-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "192k"]
        cmd += ["-shortest"]

    if final:
        cmd += ["-c:v", "libx264", "-crf", "18", "-preset", "medium",
                "-movflags", "+faststart"]
    else:
        # Intermediates get re-encoded in the stitch pass — keep them near
        # lossless so generational loss stays invisible.
        cmd += ["-c:v", "libx264", "-crf", "16", "-preset", "veryfast"]

    cmd += [dst]
    _run(cmd)


# ---------------------------------------------------------------------------
# Pass 2 — stitch with xfade / acrossfade
# ---------------------------------------------------------------------------

def _stitch_normalized(
    clips: list[ClipInfo],
    transitions: list[str],
    fade_dur: float,
    mute: bool,
    out_path: str,
) -> None:
    n = len(clips)
    cmd = ["ffmpeg", "-y"]
    for c in clips:
        cmd += ["-i", c.path]

    parts: list[str] = []

    if fade_dur <= 0 or not transitions:
        # Hard cuts: plain concat.
        streams = "".join(
            f"[{i}:v]" + ("" if mute else f"[{i}:a]") for i in range(n)
        )
        parts.append(
            f"{streams}concat=n={n}:v=1:a={0 if mute else 1}[vout]"
            + ("" if mute else "[aout]")
        )
    else:
        # Video chain: [0][1]xfade[v1]; [v1][2]xfade[v2]; ...
        prev = "[0:v]"
        offset = 0.0
        for i in range(1, n):
            offset += clips[i - 1].duration - fade_dur
            label = "[vout]" if i == n - 1 else f"[vx{i}]"
            parts.append(
                f"{prev}[{i}:v]xfade=transition={transitions[i - 1]}"
                f":duration={fade_dur:.3f}:offset={max(offset, 0):.3f}{label}"
            )
            prev = label

        if not mute:
            prev_a = "[0:a]"
            for i in range(1, n):
                label = "[aout]" if i == n - 1 else f"[ax{i}]"
                parts.append(
                    f"{prev_a}[{i}:a]acrossfade=d={fade_dur:.3f}"
                    f":c1=tri:c2=tri{label}"
                )
                prev_a = label

    cmd += ["-filter_complex", ";".join(parts), "-map", "[vout]"]
    if mute:
        cmd += ["-an"]
    else:
        cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]
    cmd += [
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        out_path,
    ]
    _run(cmd)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def stitch_videos(
    paths: list[str],
    output_path: str,
    *,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    transition_style: str = RANDOM_STYLE,
    transition_duration: float = 0.75,
    mute: bool = True,
    ken_burns: bool = False,
    ken_burns_intensity: str = "subtle",
    ken_burns_per_clip: Optional[list[bool]] = None,
    seed: Optional[int] = None,
    on_progress: Optional[ProgressFn] = None,
) -> StitchResult:
    """Stitch `paths` into `output_path`. Returns a StitchResult.

    - `transition_style`: a key of TRANSITION_STYLES or RANDOM_STYLE.
    - `mute`: True (default) drops all audio from the output.
    - `ken_burns`: apply a randomized slow zoom/pan to each clip;
      `ken_burns_per_clip` (same length as paths) can opt clips out.
    - `seed`: fix the RNG for reproducible Ken Burns moves / random mixes.
    """
    _require_ffmpeg()
    if not paths:
        raise ValueError("No input videos given")

    rng = random.Random(seed)
    warnings: list[str] = []
    progress = on_progress or (lambda *a: None)
    total_steps = len(paths) + 1

    clips = [probe_clip(p) for p in paths]

    if ken_burns_per_clip is None:
        ken_burns_per_clip = [ken_burns] * len(paths)

    # Pick the xfade name for every cut.
    if transition_style == RANDOM_STYLE:
        pool: list[str] = list(RANDOM_MIX)
    elif transition_style in TRANSITION_STYLES:
        pool = list(TRANSITION_STYLES[transition_style])
    else:
        raise ValueError(f"Unknown transition style: {transition_style}")
    transitions = [rng.choice(pool) for _ in range(len(clips) - 1)] if pool else []

    # A transition eats fade_dur off both neighbours — clamp so the
    # shortest clip survives its two overlaps.
    fade_dur = transition_duration if transitions else 0.0
    if transitions:
        max_fade = max(min(c.duration for c in clips) / 2 - 0.05, 0.0)
        if fade_dur > max_fade:
            warnings.append(
                f"Transition duration clamped from {fade_dur:.2f}s to "
                f"{max_fade:.2f}s to fit the shortest clip."
            )
            fade_dur = max_fade

    if not mute:
        silent = [os.path.basename(c.path) for c in clips if not c.has_audio]
        if silent:
            warnings.append(
                "No audio track in: " + ", ".join(silent) + " — silence inserted."
            )

    work_dir = tempfile.mkdtemp(prefix="stitcher_")
    try:
        single = len(clips) == 1
        normalized: list[ClipInfo] = []
        for i, clip in enumerate(clips):
            progress(
                i + 1, total_steps,
                f"Preparing clip {i + 1}/{len(clips)}: "
                f"{os.path.basename(clip.path)}",
            )
            dst = output_path if single else os.path.join(work_dir, f"norm_{i:03d}.mp4")
            _normalize_clip(
                clip, dst, width, height, fps,
                mute=mute,
                ken_burns=ken_burns and ken_burns_per_clip[i],
                intensity=ken_burns_intensity,
                rng=rng,
                final=single,
            )
            normalized.append(probe_clip(dst))

        if not single:
            progress(total_steps, total_steps,
                     f"Stitching {len(clips)} clips with transitions...")
            _stitch_normalized(normalized, transitions, fade_dur, mute, output_path)

        result = probe_clip(output_path)
        return StitchResult(
            output_path=output_path,
            duration=result.duration,
            transitions_used=transitions,
            warnings=warnings,
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    styles = list(TRANSITION_STYLES) + [RANDOM_STYLE]
    parser = argparse.ArgumentParser(
        description="Stitch videos together with professional transitions.",
    )
    parser.add_argument("inputs", nargs="+", help="Input video files, in order")
    parser.add_argument("-o", "--output", default="stitched.mp4")
    parser.add_argument(
        "--transition", default=RANDOM_STYLE, choices=styles,
        help=f"Transition style (default: '{RANDOM_STYLE}')",
    )
    parser.add_argument(
        "--duration", type=float, default=0.75,
        help="Transition duration in seconds (default: 0.75)",
    )
    parser.add_argument(
        "--size", default="1920x1080",
        help="Output resolution WxH (default: 1920x1080)",
    )
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--keep-audio", action="store_true",
        help="Keep audio (crossfaded). Output is MUTED by default.",
    )
    parser.add_argument(
        "--ken-burns", action="store_true",
        help="Apply a randomized slow zoom/pan to every clip.",
    )
    parser.add_argument(
        "--ken-burns-intensity", default="subtle",
        choices=list(KEN_BURNS_INTENSITY),
    )
    parser.add_argument("--seed", type=int, default=None,
                        help="RNG seed for reproducible renders.")
    args = parser.parse_args(argv)

    try:
        width, height = (int(v) for v in args.size.lower().split("x"))
    except ValueError:
        parser.error(f"--size must look like 1920x1080, got {args.size!r}")

    def on_progress(step: int, total: int, message: str) -> None:
        print(f"[{step}/{total}] {message}", flush=True)

    result = stitch_videos(
        args.inputs,
        args.output,
        width=width,
        height=height,
        fps=args.fps,
        transition_style=args.transition,
        transition_duration=args.duration,
        mute=not args.keep_audio,
        ken_burns=args.ken_burns,
        ken_burns_intensity=args.ken_burns_intensity,
        seed=args.seed,
        on_progress=on_progress,
    )
    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)
    if result.transitions_used:
        print("transitions:", ", ".join(result.transitions_used))
    print(f"done: {result.output_path} ({result.duration:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
