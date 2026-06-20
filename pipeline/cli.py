"""Command-line entry point for the video asset pipeline.

Each pipeline stage runs as its own subcommand. Only Stage 1
(``shotlist``) is implemented so far.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from .config import ConfigError, load_config
from .shotlist import ShotlistError, generate_shotlist, write_shotlist


def cmd_shotlist(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    script_path: Path = args.script
    if not script_path.is_file():
        print(f"Script file not found: {script_path}", file=sys.stderr)
        return 1

    script_text = script_path.read_text(encoding="utf-8")
    word_count = len(script_text.split())
    if word_count == 0:
        print(f"Script file is empty: {script_path}", file=sys.stderr)
        return 1

    output_path: Path = args.output or script_path.with_suffix(".shotlist.json")

    print("Stage 1 — Shotlist generator")
    print(f"  Script : {script_path}  ({word_count} words)")
    print(f"  Model  : {config.shotlist_model}")
    print(f"  Output : {output_path}")
    print("Calling the Anthropic API to segment the script...")

    try:
        shotlist = generate_shotlist(config, script_text, script_path.name)
    except ShotlistError as exc:
        print(f"\nShotlist generation failed: {exc}", file=sys.stderr)
        return 1

    write_shotlist(shotlist, output_path)

    segments = shotlist["segments"]
    total_sec = sum(s["duration_estimate_sec"] for s in segments)
    print(f"\nDone — {len(segments)} segments, ~{total_sec / 60:.1f} min estimated runtime.")
    print(f"  Title: {shotlist['video_title']}")
    print()
    for s in segments:
        print(
            f"  {s['id']}  {s['visual_type']:<13}"
            f" {s['duration_estimate_sec']:>6.1f}s  {s['visual_query']}"
        )
    print()
    print(f"Wrote shotlist to {output_path}")
    print(
        "Review and edit the segments before running later stages — "
        "you are the curator."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Historical video asset pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    shotlist = subparsers.add_parser(
        "shotlist",
        help="Stage 1: break a script into a visual shotlist.",
        description="Stage 1: break a plain-text script into a visual shotlist.",
    )
    shotlist.add_argument(
        "script",
        type=Path,
        help="Path to the plain-text essay/script file.",
    )
    shotlist.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: <script>.shotlist.json).",
    )
    shotlist.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.json (default: config.json in the project root).",
    )
    shotlist.set_defaults(func=cmd_shotlist)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
