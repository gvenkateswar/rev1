"""Command-line front-end.

    python -m transcriber audio.wav [options]      # transcribe
    python -m transcriber speakers <subcommand>    # manage the speaker store

The ``speakers`` word is intercepted before argument parsing so the plain
transcribe form keeps working unchanged.
"""
from __future__ import annotations

import argparse
import sys
import time

from .core import transcribe_file
from .output import render, to_summary


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
    p.add_argument("-f", "--format", default="txt",
                   choices=["txt", "json", "srt", "vtt"],
                   help="Output format (default: txt).")
    p.add_argument("--model", default="base",
                   help="Whisper model size: tiny/base/small/medium/large "
                        "(default: base).")
    p.add_argument("--language", default=None,
                   help="Force one language (ISO code) for the whole file. "
                        "Default: auto-detect, allowing mid-file switches.")
    p.add_argument("--no-multilingual", action="store_true",
                   help="Decode the whole file in one auto-detected language "
                        "instead of allowing the language to change mid-file.")
    p.add_argument("--diarization", default="cluster",
                   choices=["cluster", "pyannote"],
                   help="Speaker backend: 'cluster' (offline, no token) or "
                        "'pyannote' (best, needs HF token). Default: cluster.")
    p.add_argument("--speakers", type=int, default=None,
                   help="Number of speakers if known (default: auto-detect).")
    p.add_argument("--hf-token", default=None,
                   help="Hugging Face token for the pyannote backend "
                        "(or set HF_TOKEN).")
    p.add_argument("--no-identify", action="store_true",
                   help="Skip matching voices against the saved speaker store.")
    p.add_argument("--speaker-db", default=None,
                   help="Path to the speaker store "
                        "(default: ~/.transcriber/speakers.db).")
    p.add_argument("--match-threshold", type=float, default=None,
                   help="Minimum voice similarity to accept a match, 0..1 "
                        "(default: 0.72). Lower = more matches, more mistakes.")
    p.add_argument("--match-margin", type=float, default=None,
                   help="How far the best match must beat the runner-up "
                        "(default: 0.05).")
    p.add_argument("--name-speaker", action="append", default=[],
                   metavar="LABEL=NAME",
                   help="Name a speaker from this recording and remember their "
                        "voice for future files, e.g. --name-speaker "
                        "'Speaker 1=Priya'. Repeatable.")
    p.add_argument("--no-emotion", action="store_true",
                   help="Skip emotion detection (faster).")
    p.add_argument("--emotion-audio-weight", type=float, default=0.5,
                   help="Weight of voice tone vs. text, 0..1 (default: 0.5).")
    p.add_argument("--emotion-source", default="both",
                   choices=["both", "audio", "text"],
                   help="Which emotion signal(s) to use (default: both).")
    p.add_argument("--debug-emotion", action="store_true",
                   help="Print each segment's raw per-channel emotion model "
                        "output (audio vs. text) to stderr, to diagnose "
                        "which channel is firing.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = transcribe_file(
            args.input,
            whisper_model=args.model,
            language=args.language,
            multilingual=not args.no_multilingual,
            # Naming a speaker needs their voiceprint, which only the
            # identification stage extracts -- so --name-speaker implies it
            # even under --no-identify. With nothing enrolled yet, matching is
            # a no-op anyway, so this cannot mislabel anyone.
            identify_speakers=not args.no_identify or bool(args.name_speaker),
            speaker_db=args.speaker_db,
            match_threshold=args.match_threshold,
            match_margin=args.match_margin,
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

    if args.debug_emotion:
        sys.stderr.write("\n--- emotion debug (raw model outputs) ---\n")
        for seg in result.segments:
            sys.stderr.write(
                f"[{seg.start:6.1f}s] {seg.speaker}: fused={seg.emotion} "
                f"| audio_raw={seg.audio_raw} | text_raw={seg.text_raw}\n"
            )
        sys.stderr.write("--- end emotion debug ---\n\n")

    summary = to_summary(result)
    if summary:
        sys.stderr.write(summary + "\n")

    if args.name_speaker:
        try:
            _enroll_named(result, args.name_speaker, args.speaker_db)
        except (ValueError, KeyError, RuntimeError) as exc:
            sys.stderr.write(f"\nError naming speakers: {exc}\n")
            return 1

    if result.timings:
        parts = " ".join(
            f"{k}={v:.1f}s" for k, v in result.timings.items() if k != "total"
        )
        sys.stderr.write(
            f"Timing: {parts}  (total {result.timings.get('total', 0):.1f}s)\n"
        )

    text = render(result, args.format, show_emotion=not args.no_emotion)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
        sys.stderr.write(f"Wrote {args.format} to {args.output}\n")
    else:
        sys.stdout.write(text)
    return 0


# --------------------------------------------------------------------------- #
# Enrollment
# --------------------------------------------------------------------------- #
def _parse_assignment(raw: str) -> tuple[str, str]:
    """Split a 'LABEL=NAME' argument."""
    if "=" not in raw:
        raise ValueError(
            f"--name-speaker expects LABEL=NAME, got {raw!r} "
            "(e.g. --name-speaker 'Speaker 1=Priya')"
        )
    label, name = raw.split("=", 1)
    label, name = label.strip(), name.strip()
    if not label or not name:
        raise ValueError(f"--name-speaker needs both a label and a name: {raw!r}")
    return label, name


def _enroll_named(result, assignments: list[str], db_path: str | None) -> None:
    """Store voiceprints for speakers the user named on the command line."""
    from .identify import DEFAULT_MIN_ENROLL_SECONDS
    from .speakerdb import SpeakerStore

    pairs = [_parse_assignment(a) for a in assignments]
    with SpeakerStore(db_path) as store:
        for label, name in pairs:
            print_ = result.voiceprints.get(label)
            if print_ is None:
                known = ", ".join(sorted(result.voiceprints)) or "none"
                raise KeyError(
                    f"No speaker labelled {label!r} in this transcript "
                    f"(available: {known})"
                )
            if not print_.enrollable:
                # Storing a voiceprint built from a few seconds of speech would
                # degrade every future match, so refuse rather than accept it.
                sys.stderr.write(
                    f"Skipped {label} -> {name}: only "
                    f"{print_.speech_seconds:.1f}s of speech, need "
                    f"{DEFAULT_MIN_ENROLL_SECONDS:.0f}s to enroll reliably.\n"
                )
                continue
            speaker = store.enroll(
                name, print_.vector,
                source=result.source, duration=print_.speech_seconds,
            )
            sys.stderr.write(
                f"Remembered {name} ({speaker.sample_count} "
                f"voiceprint{'s' if speaker.sample_count != 1 else ''} on file).\n"
            )


def _enroll_from_audio(name: str, path: str, db_path: str | None) -> int:
    """Enroll a speaker from a clip that contains only their voice."""
    import os

    from . import audio as _audio
    from .diarize import Turn
    from .identify import DEFAULT_MIN_ENROLL_SECONDS, extract_voiceprints
    from .speakerdb import SpeakerStore

    wav_path = _audio.extract_audio(path)
    try:
        duration = _audio.audio_duration(wav_path)
        # One turn spanning the file: the caller asserts it is a single voice.
        prints = extract_voiceprints(wav_path, [Turn(0.0, duration, name)])
        if not prints:
            sys.stderr.write(
                f"Error: no usable speech found in {path}. "
                "Enrollment needs a clip of one person talking.\n"
            )
            return 1
        print_ = prints[0]
        if print_.speech_seconds < DEFAULT_MIN_ENROLL_SECONDS:
            sys.stderr.write(
                f"Error: {path} has only {print_.speech_seconds:.1f}s of speech; "
                f"need at least {DEFAULT_MIN_ENROLL_SECONDS:.0f}s.\n"
            )
            return 1
        with SpeakerStore(db_path) as store:
            speaker = store.enroll(
                name, print_.vector, source=path,
                duration=print_.speech_seconds,
            )
        sys.stderr.write(
            f"Enrolled {speaker.name} from {path} "
            f"({speaker.sample_count} voiceprint(s) on file).\n"
        )
        return 0
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# `speakers` sub-CLI
# --------------------------------------------------------------------------- #
def build_speakers_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="transcriber speakers",
        description="Manage remembered speakers and their voiceprints.",
    )
    p.add_argument("--speaker-db", default=None,
                   help="Path to the speaker store "
                        "(default: ~/.transcriber/speakers.db).")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List remembered speakers.")

    enroll = sub.add_parser(
        "enroll", help="Remember a voice from a clip of one person speaking.")
    enroll.add_argument("name")
    enroll.add_argument("audio", help="Audio/video of just this person.")

    rename = sub.add_parser("rename", help="Rename a remembered speaker.")
    rename.add_argument("old_name")
    rename.add_argument("new_name")

    forget = sub.add_parser(
        "forget", help="Delete a speaker and every voiceprint of theirs.")
    forget.add_argument("name")
    return p


def speakers_main(argv: list[str]) -> int:
    from .speakerdb import SpeakerStore, default_db_path

    args = build_speakers_parser().parse_args(argv)
    try:
        if args.command == "enroll":
            return _enroll_from_audio(args.name, args.audio, args.speaker_db)

        with SpeakerStore(args.speaker_db) as store:
            if args.command == "list":
                speakers = store.all_speakers()
                if not speakers:
                    path = args.speaker_db or default_db_path()
                    print(f"No speakers remembered yet ({path}).")
                    print("Name one with: python -m transcriber FILE "
                          "--name-speaker 'Speaker 1=Alice'")
                    return 0
                print(f"{'NAME':<24} {'VOICEPRINTS':>11}   LAST UPDATED")
                for s in speakers:
                    when = time.strftime(
                        "%Y-%m-%d %H:%M", time.localtime(s.updated_at))
                    print(f"{s.name:<24} {s.sample_count:>11}   {when}")
                return 0

            if args.command == "rename":
                store.rename(args.old_name, args.new_name)
                print(f"Renamed {args.old_name!r} -> {args.new_name!r}")
                return 0

            if args.command == "forget":
                store.forget(args.name)
                print(f"Forgot {args.name!r} and deleted their voiceprints.")
                return 0
    except (ValueError, KeyError, RuntimeError, FileNotFoundError) as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1
    return 1


def dispatch(argv: list[str] | None = None) -> int:
    """Route to the speakers sub-CLI or the transcribe CLI."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "speakers":
        return speakers_main(argv[1:])
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(dispatch())
