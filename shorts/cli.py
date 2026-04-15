"""Command-line entry point.

Typical use:

    # URL -> 5 ranked 30s clips, cut as 9:16 Shorts-ready files
    python -m shorts https://youtu.be/XXXX --vertical

    # Analyze only, print timestamps (no cutting); feed into your own editor
    python -m shorts https://youtu.be/XXXX --list-only

    # Skip download, use an already-local file
    python -m shorts /path/to/video.mp4 --local
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import audio as audio_mod
from . import download as dl
from . import rank as rank_mod
from . import video as video_mod
from .cut import cut_all


def _format_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="shorts",
        description="Find and cut the best 30s shorts out of a long music video.",
    )
    p.add_argument("source", help="YouTube URL, or local file path with --local")
    p.add_argument("--local", action="store_true", help="treat `source` as a local file, skip download")
    p.add_argument("-n", "--n-clips", type=int, default=5, help="number of clips to produce (default: 5)")
    p.add_argument("-l", "--length", type=float, default=30.0, help="clip length in seconds (default: 30)")
    p.add_argument("--vertical", action="store_true", help="center-crop output to 9:16 for Shorts")
    p.add_argument("--list-only", action="store_true", help="print timestamps, do not cut clips")
    p.add_argument("--work-dir", default="work", help="directory for downloads/proxies/clips (default: work/)")
    p.add_argument("--audio-weight", type=float, default=0.65)
    p.add_argument("--video-weight", type=float, default=0.35)
    args = p.parse_args(argv)

    work_dir = Path(args.work_dir).resolve()
    downloads = work_dir / "downloads"
    proxies = work_dir / "proxies"
    clips_dir = work_dir / "clips"

    # 1. Get the source video.
    if args.local:
        source = Path(args.source).resolve()
        if not source.exists():
            print(f"error: file not found: {source}", file=sys.stderr)
            return 2
    else:
        print(f"[1/5] downloading {args.source} ...")
        source = dl.download_video(args.source, downloads)
        print(f"      -> {source}")

    # 2. Proxy + audio extraction in one pass of ffmpeg each.
    print("[2/5] building proxy + extracting audio ...")
    proxy = dl.make_proxy(source, proxies)
    wav = dl.extract_audio(source, proxies)

    # 3. Analyze.
    print("[3/5] analyzing audio ...")
    a = audio_mod.analyze_audio(wav)
    print(f"      duration={a.duration:.1f}s, {len(a.beats)} beats detected")

    print("[4/5] analyzing video ...")
    v = video_mod.analyze_video(proxy, a.duration)
    print(f"      {len(v.scene_start_times)} scenes detected")

    # 4. Rank.
    clips = rank_mod.rank_clips(
        a, v,
        n_clips=args.n_clips,
        clip_len=args.length,
        audio_weight=args.audio_weight,
        video_weight=args.video_weight,
    )

    if not clips:
        print("no clips found -- source may be too short.", file=sys.stderr)
        return 1

    print("[5/5] top candidates:")
    print(f"      {'#':<3}{'start':<10}{'end':<10}{'score':<8}reason")
    for i, c in enumerate(clips, 1):
        print(f"      {i:<3}{_format_ts(c.start):<10}{_format_ts(c.end):<10}{c.score:<8.3f}{c.reason}")

    # 5. Cut (unless list-only) + write manifest.
    manifest = {
        "source": str(source),
        "duration": a.duration,
        "n_clips": len(clips),
        "vertical": args.vertical,
        "clips": [asdict(c) for c in clips],
    }

    if args.list_only:
        manifest_path = work_dir / f"{source.stem}.manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        print(f"      manifest: {manifest_path}")
        return 0

    print("      cutting clips ...")
    out_paths = cut_all(source, clips, clips_dir, vertical=args.vertical)
    manifest["outputs"] = [str(p) for p in out_paths]
    manifest_path = clips_dir / f"{source.stem}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    for p in out_paths:
        print(f"      -> {p}")
    print(f"      manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
