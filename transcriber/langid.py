"""Spoken-language identification, with two interchangeable detectors.

Whisper's own detector is a by-product of a transcription model: it reads the
same encoder that decides what words to emit, so when it is wrong about the
language it tends to be wrong in a way that agrees with the wrong transcript.
On densely mixed speech that is exactly the failure -- the detector says
English, the decoder obligingly translates, and both look confident.

VoxLingua107 is trained for one job, identifying the spoken language, and
knows nothing about Whisper. That independence is the point: a second opinion
is only worth having if it can disagree.

Both are behind the same tiny interface, so the pipeline neither knows nor
cares which is running:

    detector.detect(chunk_at_16khz) -> (language_code, probability) | None

Returning None means "no opinion" -- unreadable audio, a chunk too short --
and callers fall back rather than treat it as a detection.
"""
from __future__ import annotations

import numpy as np

from .runtime import require

# VoxLingua107. 107 languages, trained on ~6.6k hours of YouTube audio, and
# designed to work on utterance-length input rather than a fixed 30s window.
VOXLINGUA_MODEL = "speechbrain/lang-id-voxlingua107-ecapa"

SAMPLE_RATE = 16_000


class WhisperLanguageDetector:
    """Whisper's built-in detector -- what this pipeline has always used."""

    name = "whisper"

    def __init__(self, model):
        self._model = model

    def detect(self, chunk: np.ndarray) -> tuple[str, float] | None:
        try:
            language, probability, _all = self._model.detect_language(
                audio=chunk.astype(np.float32), language_detection_segments=1
            )
        except (RuntimeError, ValueError):
            # Silence or noise can fail feature extraction. One bad chunk is
            # not a reason to abort detection for the whole recording.
            return None
        return str(language), float(probability)


class VoxLinguaDetector:
    """SpeechBrain's VoxLingua107 ECAPA classifier.

    Loaded once and reused; the checkpoint is a few hundred MB and is cached
    by huggingface_hub after the first run.
    """

    name = "speechbrain"

    def __init__(self, classifier, torch_module):
        self._classifier = classifier
        self._torch = torch_module

    @classmethod
    def load(cls) -> "VoxLinguaDetector":
        speechbrain = require(
            "speechbrain.inference.classifiers",
            purpose="needed for the 'speechbrain' language detector",
            install="pip install speechbrain",
        )
        torch = require(
            "torch",
            purpose="needed to run the language detector",
            install="pip install torch",
        )
        classifier = speechbrain.EncoderClassifier.from_hparams(
            source=VOXLINGUA_MODEL
        )
        if classifier is None:
            raise RuntimeError(
                f"speechbrain returned no classifier for {VOXLINGUA_MODEL}. "
                "Check network access to huggingface.co and try again."
            )
        return cls(classifier, torch)

    def detect(self, chunk: np.ndarray) -> tuple[str, float] | None:
        if chunk.size < SAMPLE_RATE // 2:      # under half a second
            return None
        wav = self._torch.from_numpy(
            np.ascontiguousarray(chunk, dtype=np.float32)
        ).unsqueeze(0)
        out_prob, _score, _index, text_lab = self._classifier.classify_batch(wav)
        if not text_lab:
            return None
        # classify_batch returns *log* posteriors, so exponentiate to get the
        # probability the rest of the pipeline's thresholds are written for.
        probability = float(out_prob.squeeze(0).max().exp())
        return language_code(str(text_lab[0])), probability


def language_code(label: str) -> str:
    """Reduce a VoxLingua107 label to the ISO code the pipeline speaks.

    Labels arrive as "hi: Hindi". Whisper's codes are the bare "hi", and every
    threshold, alias and span in this pipeline is written against those, so
    the two detectors have to agree on vocabulary before they can be compared.
    """
    return label.split(":", 1)[0].strip().lower()


def make_detector(name: str, whisper_model):
    """Build a detector by name. *whisper_model* is only used by "whisper"."""
    if name == "whisper":
        return WhisperLanguageDetector(whisper_model)
    if name == "speechbrain":
        return VoxLinguaDetector.load()
    raise ValueError(
        f"Unknown language detector: {name!r} (use whisper or speechbrain)"
    )
