#!/usr/bin/env python3
"""
Video Shorts Generator
======================
Analyzes a video's audio track to find the best segments for short-form content.

Scoring (vocal mode, default):
  - Audio energy (loud/exciting moments)
  - Speech density (how much talking is happening)
  - Speech rate (faster speech = more engagement)
  - Energy dynamics (variance indicates exciting moments)
  - Whisper-detected emphasis (exclamation marks, questions)

Scoring (instrumental mode, --instrumental):
  - Audio energy only (loudness)
  - Energy dynamics (variation = a build/drop structure)
  - Spectral brightness
  - Silence penalty
  Speech-based features are ignored and Whisper is skipped entirely.

Export:
  - Default output is the same aspect ratio as the source
  - --vertical forces 9:16 output (1080x1920) with center crop
  - --smart-crop (with --vertical) tracks the largest detected face
    across the clip and centers the crop on it; falls back to center
    crop when no face is found

Usage:
    python shorts_generator.py input_video.mp4
    python shorts_generator.py input_video.mp4 --instrumental --export-clips --vertical --smart-crop
    python shorts_generator.py input_video.mp4 --top 5 --min-duration 20 --max-duration 60
"""

from __future__ import annotations  # PEP 604 / PEP 585 types work on 3.9

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


def build_empty_speech_timeline(total_duration: float,
                                resolution: float = 0.5) -> dict:
    """All-zero speech timeline for instrumental tracks (no Whisper needed)."""
    n_slots = int(total_duration / resolution) + 1
    return {
        "speech_mask": np.zeros(n_slots),
        "word_count": np.zeros(n_slots),
        "emphasis": np.zeros(n_slots),
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
    instrumental: bool = False,
) -> list:
    """
    Slide windows over the audio and score each one.
    Returns list of Segment objects sorted by score descending.

    When instrumental=True, speech-derived signals are ignored and the scoring
    is rebalanced onto pure audio features (energy, dynamics, brightness).
    This is the right mode for music videos without vocals, or where you
    don't want vocal sections to win over instrumental breaks.
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

            # Speech slice (zeros in instrumental mode)
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

            if instrumental:
                # Rebalanced onto pure-audio features. Weights sum to ~0.9
                # (without the bonuses), matching the default mode's scale
                # so the displayed % values are comparable.
                score = (
                    0.45 * energy_mean
                    + 0.30 * energy_std
                    + 0.15 * brightness
                    - 0.10 * silence_penalty
                    + edge_bonus
                )
                reasons = []
                if energy_mean > 0.6:
                    reasons.append("high energy")
                if energy_std > 0.15:
                    reasons.append("dynamic audio")
                if brightness > 0.6:
                    reasons.append("bright audio")
                if silence_frac < 0.1:
                    reasons.append("no dead air")
            else:
                # Default (vocal-aware) weighting
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
# Face detection for smart 9:16 crop
# ---------------------------------------------------------------------------

def _detect_face_center_x(video_path: str, start: float, end: float,
                          sample_interval: float = 1.0) -> float | None:
    """Sample frames within [start, end], detect the largest face in each,
    and return the median of their center-X coordinates in source pixels.

    Returns None if OpenCV isn't available, no faces are found, or the video
    can't be opened. Callers should fall back to center-crop on None.

    Uses OpenCV's Haar cascade (ships with opencv-python/-headless). Less
    accurate than MediaPipe BlazeFace, but good enough for performer-centric
    music videos and requires no extra install.
    """
    try:
        import cv2
    except ImportError:
        return None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    try:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        face_cascade = cv2.CascadeClassifier(cascade_path)
        if face_cascade.empty():
            return None

        face_centers_x: list[float] = []
        t = start
        while t < end:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if not ok:
                break

            # Downscale for fast detection — Haar on 4K is pointlessly slow.
            h, w = frame.shape[:2]
            scale = 480.0 / max(h, w) if max(h, w) > 480 else 1.0
            if scale != 1.0:
                small = cv2.resize(frame, None, fx=scale, fy=scale)
            else:
                small = frame
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

            faces = face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30),
            )
            if len(faces) > 0:
                # Biggest face wins — usually the performer, not the crowd.
                fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                center_x_small = fx + fw / 2.0
                face_centers_x.append(center_x_small / scale)

            t += sample_interval

        if not face_centers_x:
            return None
        return float(np.median(face_centers_x))
    finally:
        cap.release()


def _get_video_dimensions(video_path: str) -> tuple[int | None, int | None]:
    """Return (width, height) of the source video in pixels, or (None, None)
    if OpenCV isn't available or the file can't be opened."""
    try:
        import cv2
    except ImportError:
        return None, None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None, None
    try:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if w <= 0 or h <= 0:
            return None, None
        return w, h
    finally:
        cap.release()


# ---------------------------------------------------------------------------
# Clip export
# ---------------------------------------------------------------------------

def export_clip(video_path: str, segment: Segment,
                output_dir: str, index: int,
                vertical: bool = False,
                smart_crop: bool = True) -> str:
    """Cut a clip from the video using ffmpeg.

    Uses two-step seek (fast input-seek + precise output-seek) to avoid
    decoding the whole file up to the start time. This is dramatically
    faster on large 4K sources than the old `-i input -ss start` form,
    which decodes from 0:00 every time.

    When vertical=True, output is forced to 1080x1920 (9:16). With
    smart_crop=True we detect the largest face across the clip and center
    the crop on it; otherwise it's a center-crop.
    """
    os.makedirs(output_dir, exist_ok=True)
    name = Path(video_path).stem
    suffix = "_vertical" if vertical else ""
    out_path = os.path.join(
        output_dir,
        f"{name}_short_{index + 1}_{int(segment.start)}s-{int(segment.end)}s{suffix}.mp4"
    )

    # --- Fast two-step seek ---
    # Seek to 2s before the target on input (keyframe-snapped, cheap),
    # then 2s of precise output-seek to land on the exact frame.
    input_seek = max(0.0, segment.start - 2.0)
    fine_seek = segment.start - input_seek
    clip_duration = segment.end - segment.start

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{input_seek:.3f}",
        "-i", video_path,
        "-ss", f"{fine_seek:.3f}",
        "-t", f"{clip_duration:.3f}",
    ]

    if vertical:
        # Compute the crop rectangle in Python (using integer pixel values)
        # rather than as an ffmpeg expression. ffmpeg's filtergraph parser
        # treats commas as filter separators, so expressions like
        # min(iw,ih*9/16) inside a filter argument are ambiguous and
        # routinely break on the command line. Integer literals avoid
        # that whole class of bug.
        src_w, src_h = _get_video_dimensions(video_path)

        if src_w and src_h:
            # 9:16 crop window width in source pixels. If the source is
            # already taller-than-9:16, take the full width.
            crop_w = min(src_w, int(round(src_h * 9 / 16)))

            center_x = src_w // 2  # fallback: frame center
            if smart_crop:
                face_cx = _detect_face_center_x(
                    video_path, segment.start, segment.end,
                )
                if face_cx is not None:
                    center_x = int(round(face_cx))

            # Clamp so the crop rectangle stays fully inside the frame.
            crop_x = max(0, min(src_w - crop_w, center_x - crop_w // 2))

            vf = (
                f"crop={crop_w}:{src_h}:{crop_x}:0,"
                f"scale=1080:1920:force_original_aspect_ratio=decrease,"
                f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
            )
            cmd += ["-vf", vf]
        # If we couldn't read dimensions, skip the vertical filter and
        # fall through to a plain cut — better to produce a landscape
        # clip than to fail the whole export.

    cmd += [
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-avoid_negative_ts", "make_zero",
        out_path,
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True, text=True)
    except subprocess.CalledProcessError as e:
        # Surface the actual ffmpeg error instead of a bare CalledProcessError.
        stderr_tail = (e.stderr or "").strip().splitlines()[-10:]
        raise RuntimeError(
            f"ffmpeg failed (exit {e.returncode}) while cutting clip {index + 1}.\n"
            f"command: {' '.join(e.cmd)}\n"
            f"stderr (last 10 lines):\n  " + "\n  ".join(stderr_tail)
        ) from None
    return out_path


# ---------------------------------------------------------------------------
# Caption burn
# ---------------------------------------------------------------------------

_FONT_CANDIDATES = [
    # User-installed (macOS)
    os.path.expanduser("~/Library/Fonts/Poppins-Bold.ttf"),
    "/Library/Fonts/Poppins-Bold.ttf",
    # macOS system
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Futura Bold.ttf",
    # Linux
    "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    # Windows
    "C:/Windows/Fonts/arialbd.ttf",
]


def find_caption_font() -> str:
    """Find a bold sans-serif font suitable for captions. Returns an empty
    string if nothing is found (caller should warn or skip captions)."""
    for f in _FONT_CANDIDATES:
        if os.path.isfile(f):
            return f
    return ""


def auto_fontsize(lines: list[str]) -> int:
    """Pick a fontsize for a 1080-wide canvas based on the longest line."""
    max_chars = max((len(line) for line in lines), default=10)
    if max_chars <= 16:
        return 92
    elif max_chars <= 19:
        return 78
    return 74


def _escape_drawtext(s: str) -> str:
    """Escape characters that are special inside ffmpeg's drawtext filter."""
    for ch, repl in [("\\", "\\\\\\\\"), (":", "\\\\:"),
                     ("'", "'\\\\\\''"), ("%", "\\\\%")]:
        s = s.replace(ch, repl)
    return s


def _detect_face_y_on_clip(
    clip_path: str, sample_interval: float = 2.0,
) -> tuple[list[tuple[float, float | None]], float]:
    """Sample frames of an already-cut clip, detect the largest face's
    Y center per sample.

    Returns (samples, duration) where samples is
    [(offset_sec, face_center_y_or_None), ...] with Y in clip pixel coords.
    """
    try:
        import cv2
    except ImportError:
        return [], 0.0

    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        return [], 0.0

    try:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        face_cascade = cv2.CascadeClassifier(cascade_path)
        if face_cascade.empty():
            return [], 0.0

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        samples: list[tuple[float, float | None]] = []
        t = 0.0
        while t < duration:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ok, frame = cap.read()
            if not ok:
                break
            h, w = frame.shape[:2]
            scale = 480.0 / max(h, w) if max(h, w) > 480 else 1.0
            small = cv2.resize(frame, None, fx=scale, fy=scale) if scale != 1.0 else frame
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30),
            )
            if len(faces) > 0:
                fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                samples.append((t, (fy + fh / 2.0) / scale))
            else:
                samples.append((t, None))
            t += sample_interval
        return samples, duration
    finally:
        cap.release()


def _compute_caption_segments(
    face_samples: list[tuple[float, float | None]],
    clip_duration: float,
    default_y_center: int = 0,
) -> list[tuple[float, float, int]]:
    """Given per-second face Y samples, return time segments with the
    y_center the caption should use.

    Starting position is auto-detected from the first face sample:
      - Face in upper half of 1920-tall frame → caption at lower third (1500)
      - Face in lower half → caption at upper third (560)
      - No face found → use default_y_center, or lower third if 0

    If the face moves into the caption zone mid-clip, the caption flips
    to the opposite third for that portion.

    Returns [(start, end, y_center), ...].
    """
    LOWER_Y = 1500
    UPPER_Y = 560
    FRAME_MID = 960  # midpoint of 1920
    CAPTION_HALF_H = 150

    # Auto-detect starting position from early face samples.
    if default_y_center == 0:
        first_face_y = next(
            (y for _, y in face_samples if y is not None), None,
        )
        if first_face_y is not None:
            default_y_center = LOWER_Y if first_face_y < FRAME_MID else UPPER_Y
        else:
            default_y_center = LOWER_Y

    if not face_samples:
        return [(0.0, clip_duration, default_y_center)]

    def in_zone(face_y: float, y_center: int) -> bool:
        return abs(face_y - y_center) < CAPTION_HALF_H

    current_y = default_y_center
    segments: list[tuple[float, float, int]] = []
    seg_start = 0.0

    for t, face_y in face_samples:
        if face_y is None:
            continue
        if in_zone(face_y, current_y):
            alt_y = UPPER_Y if current_y == LOWER_Y else LOWER_Y
            if not in_zone(face_y, alt_y):
                if t > seg_start:
                    segments.append((seg_start, t, current_y))
                current_y = alt_y
                seg_start = t

    segments.append((seg_start, clip_duration, current_y))

    # Merge tiny segments (<2s) to avoid flicker.
    merged: list[tuple[float, float, int]] = []
    for seg in segments:
        if merged and seg[2] == merged[-1][2]:
            merged[-1] = (merged[-1][0], seg[1], seg[2])
        elif seg[1] - seg[0] < 2.0 and merged:
            merged[-1] = (merged[-1][0], seg[1], merged[-1][2])
        else:
            merged.append(seg)

    return merged if merged else [(0.0, clip_duration, default_y_center)]


def caption_clip(
    input_path: str,
    output_path: str,
    lines: list[str],
    fontsize: int = 0,
    y_center: int = 0,
    border: int = 8,
    font: str = "",
    face_aware: bool = True,
) -> str:
    """Burn multi-line caption onto a clip.

    Each entry in `lines` becomes a separate drawtext filter, stacked
    vertically and centered horizontally. Font size auto-selects from
    line length when fontsize=0. Font path auto-detects when font=''.

    Caption position is fully automatic when y_center=0 (default):
      - Detects faces in the clip
      - Places caption opposite the face (face top → caption bottom,
        face bottom → caption top)
      - If the face moves into the caption zone mid-clip, the caption
        flips to the other third for that time range

    Set y_center to 1500 (lower) or 560 (upper) to override auto-detect.

    Returns output_path on success.
    """
    import shutil as _shutil

    lines = [line.strip() for line in lines if line.strip()]
    if not lines:
        _shutil.copy2(input_path, output_path)
        return output_path

    if not font:
        font = find_caption_font()
    if fontsize <= 0:
        fontsize = auto_fontsize(lines)

    line_h = int(fontsize * 1.18)
    total_h = len(lines) * line_h

    font_safe = font.replace("\\", "\\\\").replace(":", "\\:")

    # Determine caption position segments.
    if face_aware:
        face_samples, clip_dur = _detect_face_y_on_clip(input_path)
        if clip_dur <= 0:
            clip_dur = 300.0  # safe fallback
        segments = _compute_caption_segments(face_samples, clip_dur, y_center)
    else:
        segments = [(0.0, 999999.0, y_center)]

    single_segment = len(segments) == 1

    clauses: list[str] = []
    for seg_start, seg_end, seg_y in segments:
        y_start = seg_y - total_h // 2
        for i, line in enumerate(lines):
            y = y_start + i * line_h
            enable = ""
            if not single_segment:
                enable = f":enable='between(t,{seg_start:.2f},{seg_end:.2f})'"
            clauses.append(
                f"drawtext=fontfile='{font_safe}'"
                f":text='{_escape_drawtext(line)}'"
                f":fontsize={fontsize}"
                f":fontcolor=white"
                f":borderw={border}:bordercolor=black"
                f":x=(w-text_w)/2:y={y}"
                f"{enable}"
            )

    vf = ",".join(clauses)

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(input_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True, text=True)
    except subprocess.CalledProcessError as e:
        stderr_tail = (e.stderr or "").strip().splitlines()[-10:]
        raise RuntimeError(
            f"ffmpeg caption burn failed (exit {e.returncode}).\n"
            f"stderr:\n  " + "\n  ".join(stderr_tail)
        ) from None
    return output_path


# ---------------------------------------------------------------------------
# High-level pipeline (used by both CLI and GUI)
# ---------------------------------------------------------------------------

def analyze_video(
    video_path: str,
    top_n: int = 5,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
    whisper_model: str = "base",
    instrumental: bool = False,
    on_progress=None,
):
    """
    Full analysis pipeline.  Returns (top_segments, whisper_result, analysis).

    on_progress(step, total, message) is an optional callback for UI updates.

    When instrumental=True, Whisper transcription is skipped entirely
    (saves ~3 min on a long video) and scoring is rebalanced onto pure
    audio features. Use this for instrumental music videos where vocal
    sections should not be prioritized over instrumental passages.
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

    # 4 ── transcribe (or skip for instrumental)
    if instrumental:
        _progress(4, 5, "Instrumental mode — skipping speech transcription ...")
        whisper_result = {"segments": []}
        speech_timeline = build_empty_speech_timeline(total_duration, hop)
    else:
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
        instrumental=instrumental,
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
        "instrumental": instrumental,
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
        "--instrumental", action="store_true",
        help="Skip speech transcription and score purely on audio features. "
             "Use for instrumental music videos.",
    )
    parser.add_argument(
        "--export-clips", action="store_true",
        help="Export the suggested clips as separate video files"
    )
    parser.add_argument(
        "--vertical", action="store_true",
        help="Export clips as 9:16 vertical (1080x1920). Implies --export-clips.",
    )
    parser.add_argument(
        "--smart-crop", action="store_true", default=True,
        help="With --vertical, use face tracking to center the crop (default: on). "
             "Use --no-smart-crop to disable.",
    )
    parser.add_argument(
        "--no-smart-crop", dest="smart_crop", action="store_false",
        help="Disable face tracking; use plain center-crop for --vertical.",
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

    # --vertical implies export
    if args.vertical:
        args.export_clips = True

    print_banner()

    def cli_progress(step, total, msg):
        print(f"\n[{step}/{total}] {msg}")

    top_segments, whisper_result, analysis = analyze_video(
        video_path=args.video,
        top_n=args.top,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        whisper_model=args.whisper_model,
        instrumental=args.instrumental,
        on_progress=cli_progress,
    )

    total_duration = analysis["total_duration"]
    print(f"  Video duration: {int(total_duration // 60)}m {int(total_duration % 60)}s")
    print(f"  Silence ratio: {analysis['silence_ratio']:.1%}")
    if not args.instrumental:
        print(f"  Speech segments found: {analysis['n_speech_segments']}")
    else:
        print(f"  Mode: instrumental (speech analysis skipped)")
    print(f"  Candidate windows evaluated: {analysis['n_candidates_evaluated']}")

    # --- Output ---
    if args.json:
        output = {
            "video": args.video,
            "duration": total_duration,
            "instrumental": args.instrumental,
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
        mode = "9:16 vertical" if args.vertical else "original aspect"
        crop_mode = ""
        if args.vertical:
            crop_mode = " (smart face-tracking crop)" if args.smart_crop else " (center crop)"
        print(f"\nExporting {len(top_segments)} clips as {mode}{crop_mode} to {args.output_dir} ...")
        for i, seg in enumerate(top_segments):
            out = export_clip(
                args.video, seg, args.output_dir, i,
                vertical=args.vertical,
                smart_crop=args.smart_crop,
            )
            print(f"  Exported: {out}")

    print("\nDone!")


if __name__ == "__main__":
    main()
