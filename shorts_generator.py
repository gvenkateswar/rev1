#!/usr/bin/env python3
"""
Video Shorts Generator
======================
Analyzes a video's audio track to find the best segments for short-form content.

Scoring is based on:
  - Audio energy (loud/exciting moments)
  - Speech density (how much talking is happening)
  - Speech rate (faster speech = more engagement)
  - Energy dynamics (variance indicates exciting moments)
  - Whisper-detected emphasis (exclamation marks, questions)

Usage:
    python shorts_generator.py input_video.mp4
    python shorts_generator.py input_video.mp4 --top 5 --min-duration 20 --max-duration 60
    python shorts_generator.py input_video.mp4 --export-clips --output-dir ./clips
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    start: float          # seconds
    end: float            # seconds
    score: float = 0.0
    energy_score: float = 0.0
    speech_score: float = 0.0
    dynamics_score: float = 0.0
    transcript: str = ""
    reasons: list = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def fmt_time(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def __str__(self) -> str:
        return (
            f"[{self.fmt_time(self.start)} - {self.fmt_time(self.end)}] "
            f"({self.duration:.0f}s)  score={self.score:.2f}"
        )


# ---------------------------------------------------------------------------
# Audio extraction
# ---------------------------------------------------------------------------

def check_ffmpeg():
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, check=True,
        )
    except FileNotFoundError:
        print("Error: ffmpeg is not installed. Install it first:")
        print("  Ubuntu/Debian: sudo apt install ffmpeg")
        print("  macOS:         brew install ffmpeg")
        print("  Windows:       choco install ffmpeg")
        sys.exit(1)


def extract_audio(video_path: str, tmp_dir: str) -> str:
    """Extract audio from video as 16 kHz mono WAV (what Whisper expects)."""
    audio_path = os.path.join(tmp_dir, "audio.wav")
    print(f"  Extracting audio from {Path(video_path).name} ...")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path,
            "-vn",                  # no video
            "-acodec", "pcm_s16le", # 16-bit PCM
            "-ar", "16000",         # 16 kHz
            "-ac", "1",             # mono
            audio_path,
        ],
        capture_output=True, check=True,
    )
    return audio_path


def get_video_duration(video_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            video_path,
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


# ---------------------------------------------------------------------------
# Audio analysis (numpy / scipy / librosa)
# ---------------------------------------------------------------------------

def load_audio_np(audio_path: str) -> tuple:
    """Load WAV as numpy array. Returns (samples, sample_rate)."""
    import scipy.io.wavfile as wav
    sr, data = wav.read(audio_path)
    # Normalize to float [-1, 1]
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    return data, sr


def compute_energy_profile(samples: np.ndarray, sr: int,
                           hop_seconds: float = 0.5) -> np.ndarray:
    """Compute RMS energy in windows. Returns array of RMS values."""
    hop = int(sr * hop_seconds)
    n_frames = len(samples) // hop
    energy = np.zeros(n_frames)
    for i in range(n_frames):
        frame = samples[i * hop : (i + 1) * hop]
        energy[i] = np.sqrt(np.mean(frame ** 2))
    return energy


def detect_silence(energy: np.ndarray, threshold_ratio: float = 0.05) -> np.ndarray:
    """Returns boolean array where True = silence."""
    threshold = np.max(energy) * threshold_ratio
    return energy < threshold


def compute_spectral_centroid(samples: np.ndarray, sr: int,
                              hop_seconds: float = 0.5) -> np.ndarray:
    """Simple spectral centroid — higher = brighter/more energetic."""
    hop = int(sr * hop_seconds)
    n_frames = len(samples) // hop
    centroids = np.zeros(n_frames)
    for i in range(n_frames):
        frame = samples[i * hop : (i + 1) * hop]
        spectrum = np.abs(np.fft.rfft(frame))
        freqs = np.fft.rfftfreq(len(frame), 1.0 / sr)
        if spectrum.sum() > 0:
            centroids[i] = np.sum(freqs * spectrum) / np.sum(spectrum)
    return centroids


# ---------------------------------------------------------------------------
# Whisper transcription
# ---------------------------------------------------------------------------

def transcribe_audio(audio_path: str, model_name: str = "base") -> dict:
    """Run Whisper and return segment-level transcription."""
    print(f"  Transcribing with Whisper ({model_name} model) ...")
    import whisper

    model = whisper.load_model(model_name)
    result = model.transcribe(
        audio_path,
        language=None,       # auto-detect
        verbose=False,
        word_timestamps=True,
    )
    return result


def build_speech_timeline(whisper_result: dict, total_duration: float,
                          resolution: float = 0.5) -> dict:
    """
    From Whisper output, build per-timeslot speech features:
      - speech_density: fraction of time with speech
      - word_rate: words per second
      - emphasis: count of !, ?, CAPS per window
    """
    n_slots = int(total_duration / resolution) + 1
    word_count = np.zeros(n_slots)
    speech_mask = np.zeros(n_slots)
    emphasis = np.zeros(n_slots)

    for seg in whisper_result.get("segments", []):
        words = seg.get("words", [])
        if not words:
            # Fall back to segment-level timing
            s_start = seg["start"]
            s_end = seg["end"]
            text = seg.get("text", "")
            i_start = int(s_start / resolution)
            i_end = int(s_end / resolution)
            for i in range(max(0, i_start), min(n_slots, i_end + 1)):
                speech_mask[i] = 1.0
            n_words = len(text.split())
            dur = max(s_end - s_start, 0.1)
            for i in range(max(0, i_start), min(n_slots, i_end + 1)):
                word_count[i] = n_words / dur * resolution
                if "!" in text or "?" in text:
                    emphasis[i] += 1
                if text.upper() == text and len(text) > 3:
                    emphasis[i] += 1
            continue

        for w in words:
            w_start = w.get("start", 0)
            w_end = w.get("end", w_start + 0.1)
            w_text = w.get("word", "")
            i_start = int(w_start / resolution)
            i_end = int(w_end / resolution)
            for i in range(max(0, i_start), min(n_slots, i_end + 1)):
                speech_mask[i] = 1.0
                word_count[i] += 1
            if "!" in w_text or "?" in w_text:
                idx = int(w_start / resolution)
                if 0 <= idx < n_slots:
                    emphasis[idx] += 1

    return {
        "speech_mask": speech_mask,
        "word_count": word_count,
        "emphasis": emphasis,
        "resolution": resolution,
    }


def get_transcript_for_range(whisper_result: dict,
                             start: float, end: float) -> str:
    """Extract transcript text for a time range."""
    parts = []
    for seg in whisper_result.get("segments", []):
        seg_start = seg["start"]
        seg_end = seg["end"]
        # Overlap check
        if seg_start < end and seg_end > start:
            parts.append(seg.get("text", "").strip())
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Segment scoring
# ---------------------------------------------------------------------------

def score_segments(
    energy: np.ndarray,
    centroid: np.ndarray,
    silence: np.ndarray,
    speech_timeline: dict,
    total_duration: float,
    hop_seconds: float = 0.5,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
    step_seconds: float = 5.0,
) -> list:
    """
    Slide windows over the audio and score each one.
    Returns list of Segment objects sorted by score descending.
    """
    segments = []

    # Normalise energy for scoring
    energy_norm = energy / (np.max(energy) + 1e-10)
    centroid_norm = centroid / (np.max(centroid) + 1e-10)

    speech_mask = speech_timeline["speech_mask"]
    word_count = speech_timeline["word_count"]
    emphasis_arr = speech_timeline["emphasis"]
    res = speech_timeline["resolution"]

    # Try multiple window sizes
    for duration in np.arange(min_duration, max_duration + 1, 5):
        for start in np.arange(0, total_duration - duration, step_seconds):
            end = start + duration

            # Energy slice
            e_start = int(start / hop_seconds)
            e_end = int(end / hop_seconds)
            e_slice = energy_norm[e_start:e_end]
            c_slice = centroid_norm[e_start:e_end]
            s_slice = silence[e_start:e_end]

            if len(e_slice) == 0:
                continue

            # Speech slice
            sp_start = int(start / res)
            sp_end = int(end / res)
            sp_mask = speech_mask[sp_start:sp_end]
            sp_words = word_count[sp_start:sp_end]
            sp_emphasis = emphasis_arr[sp_start:sp_end]

            # ---- Score components ----

            # 1. Energy: mean RMS (louder = more exciting)
            energy_mean = float(np.mean(e_slice))

            # 2. Energy dynamics: std of energy (varied = interesting)
            energy_std = float(np.std(e_slice))

            # 3. Speech density: fraction of time with speech
            speech_density = float(np.mean(sp_mask)) if len(sp_mask) > 0 else 0

            # 4. Word rate: words per second
            word_rate = float(np.sum(sp_words)) / max(duration, 1)
            word_rate_norm = min(word_rate / 4.0, 1.0)  # ~4 wps is fast

            # 5. Emphasis (questions, exclamations)
            emph_score = min(float(np.sum(sp_emphasis)) / 5.0, 1.0)

            # 6. Spectral brightness
            brightness = float(np.mean(c_slice))

            # 7. Silence penalty: too much silence is bad
            silence_frac = float(np.mean(s_slice))
            silence_penalty = max(0, silence_frac - 0.3)  # penalise >30% silence

            # 8. Prefer segments that don't start/end in mid-speech
            # (mild bonus if starts near silence)
            edge_bonus = 0.0
            if e_start < len(silence) and silence[e_start]:
                edge_bonus += 0.05
            if e_end - 1 < len(silence) and silence[min(e_end - 1, len(silence) - 1)]:
                edge_bonus += 0.05

            # Weighted composite score
            score = (
                0.25 * energy_mean
                + 0.15 * energy_std
                + 0.20 * speech_density
                + 0.15 * word_rate_norm
                + 0.10 * emph_score
                + 0.05 * brightness
                - 0.10 * silence_penalty
                + edge_bonus
            )

            reasons = []
            if energy_mean > 0.6:
                reasons.append("high energy")
            if energy_std > 0.15:
                reasons.append("dynamic audio")
            if speech_density > 0.7:
                reasons.append("dense speech")
            if word_rate_norm > 0.6:
                reasons.append("fast-paced speech")
            if emph_score > 0.3:
                reasons.append("emphatic speech (!/?) ")
            if brightness > 0.6:
                reasons.append("bright audio")

            seg = Segment(
                start=start,
                end=end,
                score=score,
                energy_score=energy_mean,
                speech_score=speech_density,
                dynamics_score=energy_std,
                reasons=reasons,
            )
            segments.append(seg)

    segments.sort(key=lambda s: s.score, reverse=True)
    return segments


def select_top_non_overlapping(segments: list, top_n: int,
                               min_gap: float = 5.0) -> list:
    """Greedily pick top-scoring segments that don't overlap."""
    selected = []
    for seg in segments:
        overlaps = False
        for chosen in selected:
            # Check overlap with a min_gap buffer
            if seg.start < chosen.end + min_gap and seg.end > chosen.start - min_gap:
                overlaps = True
                break
        if not overlaps:
            selected.append(seg)
        if len(selected) >= top_n:
            break
    # Re-sort by start time for display
    selected.sort(key=lambda s: s.start)
    return selected


# ---------------------------------------------------------------------------
# Clip export
# ---------------------------------------------------------------------------

def export_clip(video_path: str, segment: Segment,
                output_dir: str, index: int) -> str:
    """Cut a clip from the video using ffmpeg."""
    os.makedirs(output_dir, exist_ok=True)
    name = Path(video_path).stem
    out_path = os.path.join(
        output_dir,
        f"{name}_short_{index + 1}_{int(segment.start)}s-{int(segment.end)}s.mp4"
    )
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ss", str(segment.start),
            "-to", str(segment.end),
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            "-avoid_negative_ts", "make_zero",
            out_path,
        ],
        capture_output=True, check=True,
    )
    return out_path


# ---------------------------------------------------------------------------
# High-level pipeline (used by both CLI and GUI)
# ---------------------------------------------------------------------------

def analyze_video(
    video_path: str,
    top_n: int = 5,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
    whisper_model: str = "base",
    on_progress=None,
):
    """
    Full analysis pipeline.  Returns (top_segments, whisper_result, analysis).

    on_progress(step, total, message) is an optional callback for UI updates.
    """
    def _progress(step, total, msg):
        if on_progress:
            on_progress(step, total, msg)

    check_ffmpeg()

    # 1 ── duration
    _progress(1, 5, "Reading video metadata ...")
    total_duration = get_video_duration(video_path)

    # 2 ── extract audio
    _progress(2, 5, "Extracting audio ...")
    tmp_dir = tempfile.mkdtemp(prefix="shorts_gen_")
    audio_path = extract_audio(video_path, tmp_dir)

    # 3 ── audio features
    _progress(3, 5, "Analyzing audio features ...")
    samples, sr = load_audio_np(audio_path)
    hop = 0.5
    energy = compute_energy_profile(samples, sr, hop)
    centroid = compute_spectral_centroid(samples, sr, hop)
    silence = detect_silence(energy)

    # 4 ── transcribe
    _progress(4, 5, "Transcribing speech (this may take a while) ...")
    whisper_result = transcribe_audio(audio_path, whisper_model)
    speech_timeline = build_speech_timeline(whisper_result, total_duration, hop)

    # 5 ── score
    _progress(5, 5, "Scoring candidate segments ...")
    all_segments = score_segments(
        energy, centroid, silence, speech_timeline,
        total_duration,
        hop_seconds=hop,
        min_duration=min_duration,
        max_duration=max_duration,
    )

    top_segments = select_top_non_overlapping(all_segments, top_n)

    for seg in top_segments:
        seg.transcript = get_transcript_for_range(
            whisper_result, seg.start, seg.end
        )

    # cleanup
    try:
        os.remove(audio_path)
        os.rmdir(tmp_dir)
    except OSError:
        pass

    analysis = {
        "total_duration": total_duration,
        "energy": energy,
        "silence_ratio": float(silence.mean()),
        "n_speech_segments": len(whisper_result.get("segments", [])),
        "n_candidates_evaluated": len(all_segments),
    }

    return top_segments, whisper_result, analysis


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_banner():
    print("=" * 60)
    print("  Video Shorts Generator")
    print("  Finds the best clips based on audio analysis")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze a video's audio to find the best segments for shorts."
    )
    parser.add_argument("video", help="Path to the input video file")
    parser.add_argument(
        "--top", type=int, default=5,
        help="Number of top clips to suggest (default: 5)"
    )
    parser.add_argument(
        "--min-duration", type=float, default=15,
        help="Minimum clip duration in seconds (default: 15)"
    )
    parser.add_argument(
        "--max-duration", type=float, default=60,
        help="Maximum clip duration in seconds (default: 60)"
    )
    parser.add_argument(
        "--whisper-model", default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base). Larger = more accurate but slower."
    )
    parser.add_argument(
        "--export-clips", action="store_true",
        help="Export the suggested clips as separate video files"
    )
    parser.add_argument(
        "--output-dir", default="./shorts_output",
        help="Directory to save exported clips (default: ./shorts_output)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    if not os.path.isfile(args.video):
        print(f"Error: File not found: {args.video}")
        sys.exit(1)

    print_banner()

    def cli_progress(step, total, msg):
        print(f"\n[{step}/{total}] {msg}")

    top_segments, whisper_result, analysis = analyze_video(
        video_path=args.video,
        top_n=args.top,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        whisper_model=args.whisper_model,
        on_progress=cli_progress,
    )

    total_duration = analysis["total_duration"]
    print(f"  Video duration: {int(total_duration // 60)}m {int(total_duration % 60)}s")
    print(f"  Silence ratio: {analysis['silence_ratio']:.1%}")
    print(f"  Speech segments found: {analysis['n_speech_segments']}")
    print(f"  Candidate windows evaluated: {analysis['n_candidates_evaluated']}")

    # --- Output ---
    if args.json:
        output = {
            "video": args.video,
            "duration": total_duration,
            "shorts": [
                {
                    "rank": i + 1,
                    "start": round(seg.start, 1),
                    "end": round(seg.end, 1),
                    "duration": round(seg.duration, 1),
                    "score": round(seg.score, 3),
                    "energy_score": round(seg.energy_score, 3),
                    "speech_score": round(seg.speech_score, 3),
                    "dynamics_score": round(seg.dynamics_score, 3),
                    "reasons": seg.reasons,
                    "transcript_preview": seg.transcript[:200],
                }
                for i, seg in enumerate(top_segments)
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print("\n" + "=" * 60)
        print(f"  TOP {len(top_segments)} SHORTS CANDIDATES")
        print("=" * 60)

        for i, seg in enumerate(top_segments):
            print(f"\n  #{i + 1}  {seg}")
            if seg.reasons:
                print(f"       Why: {', '.join(seg.reasons)}")
            if seg.transcript:
                preview = seg.transcript[:150]
                if len(seg.transcript) > 150:
                    preview += "..."
                print(f"       Speech: \"{preview}\"")

    # --- Export clips ---
    if args.export_clips:
        print(f"\nExporting {len(top_segments)} clips to {args.output_dir} ...")
        for i, seg in enumerate(top_segments):
            out = export_clip(args.video, seg, args.output_dir, i)
            print(f"  Exported: {out}")

    # Cleanup temp files
    try:
        os.remove(audio_path)
        os.rmdir(tmp_dir)
    except OSError:
        pass

    print("\nDone!")


if __name__ == "__main__":
    main()
