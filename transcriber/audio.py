"""Audio I/O helpers: ffmpeg extraction and waveform loading.

Whisper, the diarizer, and the speech-emotion model all want the same thing:
16 kHz mono PCM. We normalize to that once, up front, and everything else
slices into the resulting WAV.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile

import numpy as np

SAMPLE_RATE = 16_000


def check_ffmpeg() -> None:
    """Raise a friendly error if ffmpeg is not on PATH."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg is not installed or not on PATH. Install it first:\n"
            "  Ubuntu/Debian: sudo apt install ffmpeg\n"
            "  macOS:         brew install ffmpeg\n"
            "  Windows:       choco install ffmpeg"
        )


def extract_audio(
    src_path: str, out_path: str | None = None, filters: str | None = None
) -> str:
    """Decode any audio/video file to 16 kHz mono WAV and return its path.

    If *out_path* is None a temp file is created (caller owns cleanup).
    *filters* is an optional ffmpeg audio-filter chain (``-af``), e.g. a
    denoiser for a hissy phone recording.
    """
    check_ffmpeg()
    if out_path is None:
        fd = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        fd.close()
        out_path = fd.name

    cmd = [
        "ffmpeg", "-y", "-i", str(src_path),
        "-ac", "1",                 # mono
        "-ar", str(SAMPLE_RATE),    # 16 kHz
        "-vn",                      # drop any video stream
        "-acodec", "pcm_s16le",
    ]
    if filters:
        cmd += ["-af", filters]
    cmd.append(str(out_path))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (exit {proc.returncode}) extracting audio from "
            f"{src_path}:\n{proc.stderr[-800:]}"
        )
    return out_path


def load_waveform(wav_path: str) -> tuple[np.ndarray, int]:
    """Load a WAV as float32 mono in [-1, 1]. Returns (samples, sample_rate)."""
    import soundfile as sf

    data, sr = sf.read(wav_path, dtype="float32", always_2d=False)
    if data.ndim > 1:                     # stereo -> mono
        data = data.mean(axis=1)
    return data.astype(np.float32), sr


def slice_waveform(
    samples: np.ndarray, sr: int, start: float, end: float
) -> np.ndarray:
    """Return the sample slice covering [start, end] seconds (clamped)."""
    a = max(0, int(round(start * sr)))
    b = min(len(samples), int(round(end * sr)))
    if b <= a:
        return np.zeros(1, dtype=np.float32)
    return samples[a:b]


def audio_duration(wav_path: str) -> float:
    """Duration of a WAV in seconds."""
    import soundfile as sf

    info = sf.info(wav_path)
    return float(info.frames) / float(info.samplerate)
