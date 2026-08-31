"""Command-line front-end:  python -m music_lesson lesson.m4a [options]"""
from __future__ import annotations

import argparse
import sys

from .core import transcribe_lesson
from .output import render
from .swara import parse_tonic


def _progress(stage: str, frac: float) -> None:
    bar = "#" * int(frac * 30)
    sys.stderr.write(f"\r[{bar:<30}] {frac:5.0%}  {stage:<26}")
    sys.stderr.flush()
    if frac >= 1.0:
        sys.stderr.write("\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="music_lesson",
        description="Transcribe a Hindustani classical music lesson: separate "
                    "singing from talking, write the singing as sargam, and "
                    "transcribe the code-switched Hindi/English explanation.",
    )
    p.add_argument("input", help="Path to an audio or video recording.")
    p.add_argument("-o", "--output", help="Write result here (default: stdout).")
    p.add_argument("-f", "--format", default="md",
                   choices=["md", "txt", "json", "srt"],
                   help="md = practice sheet (default), txt = transcript, "
                        "json = everything, srt = subtitles.")

    music = p.add_argument_group("music")
    music.add_argument("--tonic", default=None,
                       help="Your Sa, as a note or a frequency: 'C#3', 'D3', "
                            "'138.6'. Default: detect it. Setting it is more "
                            "reliable than any detector — you know your Sa.")
    music.add_argument("--sung-threshold", type=float, default=0.50,
                       help="How readily a stretch counts as singing, 0..1 "
                            "(default: 0.50). Raise it if slow, deliberate "
                            "speech is being read as demonstration.")
    music.add_argument("--keep-sung-text", action="store_true",
                       help="Keep Whisper's output over singing. Off by "
                            "default because it is nearly always invented — "
                            "turn it on to catch bandish lyrics.")

    speech = p.add_argument_group("speech")
    speech.add_argument("--model", default="small",
                        help="Whisper size: tiny/base/small/medium/large-v3 "
                             "(default: small — 'base' mangles Hindi).")
    speech.add_argument("--language", default=None,
                        help="Force a language (hi/en). Default: detect per "
                             "window, which is what code-switching needs.")
    speech.add_argument("--term", action="append", dest="terms", default=[],
                        metavar="WORD",
                        help="Extra vocabulary to prime the decoder with — a "
                             "raag name, your guru's name. Repeatable.")
    speech.add_argument("--no-vocabulary-fix", action="store_true",
                        help="Skip the Hindustani vocabulary repair pass.")

    speakers = p.add_argument_group("speakers")
    speakers.add_argument("--no-speakers", action="store_true",
                          help="Skip diarization (faster; no Guru/Student labels).")
    speakers.add_argument("--speakers", type=int, default=None,
                          help="Number of voices, if you know it.")
    speakers.add_argument("--diarization", default="cluster",
                          choices=["cluster", "pyannote"],
                          help="Speaker backend (default: cluster, offline).")
    speakers.add_argument("--guru", default=None, metavar="LABEL",
                          help="Which raw speaker label is the guru, e.g. "
                               "'Speaker 2'. Default: whoever talks most.")
    speakers.add_argument("--hf-token", default=None,
                          help="Hugging Face token for pyannote (or HF_TOKEN).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    tonic = None
    if args.tonic:
        try:
            tonic = parse_tonic(args.tonic)
        except ValueError as exc:
            sys.stderr.write(f"Error: {exc}\n")
            return 2

    try:
        result = transcribe_lesson(
            args.input,
            whisper_model=args.model,
            language=args.language,
            tonic=tonic,
            diarize_speakers=not args.no_speakers,
            num_speakers=args.speakers,
            diarization_backend=args.diarization,
            hf_token=args.hf_token,
            guru_speaker=args.guru,
            extra_terms=args.terms,
            fix_vocabulary=not args.no_vocabulary_fix,
            keep_sung_text=args.keep_sung_text,
            sung_threshold=args.sung_threshold,
            progress=_progress,
        )
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        sys.stderr.write(f"\nError: {exc}\n")
        return 1

    if result.tonic.confidence < 0.25 and result.sung_seconds > 0:
        sys.stderr.write(
            f"Note: Sa was hard to pin down (confidence "
            f"{result.tonic.confidence:.0%}); the sargam is only as good as "
            f"the tonic. Re-run with --tonic if it looks wrong.\n"
        )

    if result.timings:
        parts = " ".join(
            f"{k}={v:.1f}s" for k, v in result.timings.items() if k != "total"
        )
        sys.stderr.write(
            f"Timing: {parts}  (total {result.timings.get('total', 0):.1f}s)\n"
        )

    text = render(result, args.format)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
        sys.stderr.write(f"Wrote {args.format} to {args.output}\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
