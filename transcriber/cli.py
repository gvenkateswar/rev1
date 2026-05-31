"""Command-line front-end:  python -m transcriber audio.wav [options]"""
from __future__ import annotations

import argparse
import sys

from .core import transcribe_file
from .output import render


def _progress(stage: str, frac: float) -> None:
    bar = "#" * int(frac * 30)
    sys.stderr.write(f"\r[{bar:<30}] {frac:5.0%}  {stage:<22}")
    sys.stderr.flush()
    if frac >= 1.0:
        sys.stderr.write("\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="transcriber",
        description="Transcribe audio/video with speaker diarization and "
                    "fused audio+text emotion detection.",
    )
    p.add_argument("input", help="Path to an audio or video file.")
    p.add_argument("-o", "--output", help="Write result here (default: stdout).")
    p.add_argument("-f", "--format", default="txt", choices=["txt", "json", "srt"],
                   help="Output format (default: txt).")
    p.add_argument("--model", default="base",
                   help="Whisper model size: tiny/base/small/medium/large "
                        "(default: base).")
    p.add_argument("--language", default=None,
                   help="Force a language (ISO code). Default: auto-detect.")
    p.add_argument("--diarization", default="cluster",
                   choices=["cluster", "pyannote"],
                   help="Speaker backend: 'cluster' (offline, no token) or "
                        "'pyannote' (best, needs HF token). Default: cluster.")
    p.add_argument("--speakers", type=int, default=None,
                   help="Number of speakers if known (default: auto-detect).")
    p.add_argument("--hf-token", default=None,
                   help="Hugging Face token for the pyannote backend "
                        "(or set HF_TOKEN).")
    p.add_argument("--no-emotion", action="store_true",
                   help="Skip emotion detection (faster).")
    p.add_argument("--emotion-audio-weight", type=float, default=0.5,
                   help="Weight of voice tone vs. text, 0..1 (default: 0.5).")
    p.add_argument("--emotion-source", default="both",
                   choices=["both", "audio", "text"],
                   help="Which emotion signal(s) to use (default: both).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = transcribe_file(
            args.input,
            whisper_model=args.model,
            language=args.language,
            diarization_backend=args.diarization,
            num_speakers=args.speakers,
            hf_token=args.hf_token,
            detect_emotion=not args.no_emotion,
            audio_weight=args.emotion_audio_weight,
            use_audio_emotion=args.emotion_source in ("both", "audio"),
            use_text_emotion=args.emotion_source in ("both", "text"),
            progress=_progress,
        )
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        sys.stderr.write(f"\nError: {exc}\n")
        return 1

    text = render(result, args.format, show_emotion=not args.no_emotion)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
        sys.stderr.write(f"Wrote {args.format} to {args.output}\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
