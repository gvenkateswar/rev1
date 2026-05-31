"""Emotion detection that fuses *how* something was said with *what* was said.

A loud voice is ambiguous on its own — excitement and anger sound alike — so we
score each segment two ways and combine them:

* **Audio (tone):** a wav2vec2 speech-emotion model over the raw audio slice.
* **Text (content):** a RoBERTa emotion classifier over the transcribed words.

Both produce probabilities over a shared label set; we take a weighted average.
The fused top label is the segment's emotion, and we keep the per-channel
breakdown so the UI can show *why* (e.g. "tone: angry / words: joy -> excited").
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Canonical labels both models are mapped onto.
CANONICAL = ["angry", "happy", "sad", "fear", "disgust", "surprise", "neutral"]

# Audio model: ehcalabres/wav2vec2 -> 8 labels.
_AUDIO_MAP = {
    "angry": "angry", "happy": "happy", "sad": "sad", "fearful": "fear",
    "disgust": "disgust", "surprised": "surprise", "neutral": "neutral",
    "calm": "neutral",
}
# Text model: j-hartmann/emotion-english-distilroberta-base -> 7 labels.
_TEXT_MAP = {
    "anger": "angry", "joy": "happy", "sadness": "sad", "fear": "fear",
    "disgust": "disgust", "surprise": "surprise", "neutral": "neutral",
}

_EMOJI = {
    "angry": "😠", "happy": "😀", "sad": "😢", "fear": "😨",
    "disgust": "🤢", "surprise": "😲", "neutral": "😐",
}

AUDIO_MODEL = "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"
TEXT_MODEL = "j-hartmann/emotion-english-distilroberta-base"


@dataclass
class EmotionResult:
    label: str                                   # fused top emotion
    score: float                                 # fused top probability
    scores: dict[str, float] = field(default_factory=dict)   # fused breakdown
    audio_label: str | None = None
    text_label: str | None = None

    @property
    def emoji(self) -> str:
        return _EMOJI.get(self.label, "")


class EmotionAnalyzer:
    """Lazily loads the two models and scores audio slices + text.

    Construct once and reuse across segments — model loading is the expensive
    part. ``audio_weight`` in [0,1] trades off tone vs. content (0.5 = equal).
    """

    def __init__(
        self,
        audio_weight: float = 0.5,
        use_audio: bool = True,
        use_text: bool = True,
        device: int | str | None = None,
    ):
        if not (use_audio or use_text):
            raise ValueError("Enable at least one of use_audio / use_text.")
        self.audio_weight = float(np.clip(audio_weight, 0.0, 1.0))
        self.use_audio = use_audio
        self.use_text = use_text
        self.device = device
        self._audio_pipe = None
        self._text_pipe = None

    # -- model loaders ----------------------------------------------------- #
    def _ensure_audio(self):
        if self._audio_pipe is None:
            from transformers import pipeline

            self._audio_pipe = pipeline(
                "audio-classification", model=AUDIO_MODEL,
                top_k=None, device=self._resolve_device(),
            )
        return self._audio_pipe

    def _ensure_text(self):
        if self._text_pipe is None:
            from transformers import pipeline

            self._text_pipe = pipeline(
                "text-classification", model=TEXT_MODEL,
                top_k=None, device=self._resolve_device(),
            )
        return self._text_pipe

    def _resolve_device(self):
        if self.device is not None:
            return self.device
        try:
            import torch

            return 0 if torch.cuda.is_available() else -1
        except ImportError:  # pragma: no cover
            return -1

    # -- scoring ----------------------------------------------------------- #
    def analyze(
        self, samples: np.ndarray, sr: int, text: str
    ) -> EmotionResult:
        audio_scores = self._score_audio(samples, sr) if self.use_audio else None
        text_scores = self._score_text(text) if self.use_text else None

        fused = self._fuse(audio_scores, text_scores)
        top = max(fused, key=fused.get)
        return EmotionResult(
            label=top,
            score=fused[top],
            scores=fused,
            audio_label=_argmax(audio_scores),
            text_label=_argmax(text_scores),
        )

    def _score_audio(self, samples: np.ndarray, sr: int) -> dict[str, float]:
        # The model expects 16 kHz mono float; audio.py already guarantees that.
        try:
            preds = self._ensure_audio()(
                {"array": samples.astype(np.float32), "sampling_rate": sr}
            )
        except Exception:  # pragma: no cover - very short/empty slice
            return {}
        return _remap(preds, _AUDIO_MAP)

    def _score_text(self, text: str) -> dict[str, float]:
        text = (text or "").strip()
        if not text:
            return {}
        preds = self._ensure_text()(text, truncation=True)
        if preds and isinstance(preds[0], list):  # top_k=None nests one level
            preds = preds[0]
        return _remap(preds, _TEXT_MAP)

    def _fuse(
        self, audio: dict[str, float] | None, text: dict[str, float] | None
    ) -> dict[str, float]:
        have_audio = bool(audio)
        have_text = bool(text)
        if have_audio and have_text:
            wa, wt = self.audio_weight, 1.0 - self.audio_weight
        elif have_audio:
            wa, wt = 1.0, 0.0
        elif have_text:
            wa, wt = 0.0, 1.0
        else:
            return {"neutral": 1.0}

        fused = {}
        for label in CANONICAL:
            fused[label] = wa * (audio or {}).get(label, 0.0) + \
                wt * (text or {}).get(label, 0.0)
        total = sum(fused.values()) or 1.0
        return {k: v / total for k, v in fused.items()}


def _remap(preds, mapping: dict[str, str]) -> dict[str, float]:
    """Collapse a model's raw {label: score} list onto canonical labels."""
    out: dict[str, float] = {}
    for p in preds:
        canon = mapping.get(p["label"].lower())
        if canon:
            out[canon] = out.get(canon, 0.0) + float(p["score"])
    total = sum(out.values())
    if total > 0:
        out = {k: v / total for k, v in out.items()}
    return out


def _argmax(scores: dict[str, float] | None) -> str | None:
    if not scores:
        return None
    return max(scores, key=scores.get)
