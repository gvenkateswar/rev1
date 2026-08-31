"""Pipeline orchestration: file in, labelled transcript out.

    extract audio -> language timeline -> Whisper -> diarize
                  -> identify speakers -> align -> fuse emotion

Two stages carry the interesting logic. :func:`assign_speakers` uses Whisper's
word-level timestamps to *split* a transcript segment when the speaker changes
mid-sentence, so a back-and-forth that Whisper merged into one segment still
comes out as separate speaker turns. The identification stage then replaces
anonymous "Speaker N" labels with real names recognised from the voiceprint
store, so the same person keeps their name across recordings.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable

from . import audio as _audio
from .diarize import Turn, diarize
from .language import LanguageSpan, detect_language_timeline, language_for
from .language import summarize as _summarize_languages
from .transcribe import (
    RawSegment, Word, load_model, transcribe, transcribe_spans,
)

ProgressCb = Callable[[str, float], None]

# Whisper's "translate" task has exactly one target: English. It was never
# trained to translate into anything else, so this is the language a segment
# is already in when there is nothing to translate it to.
ENGLISH = "en"


@dataclass
class TranscriptSegment:
    start: float
    end: float
    speaker: str
    text: str                   # what was said, in the script it was said in
    language: str = "en"
    latin: str | None = None    # Latin transliteration, None if already Latin
    english: str | None = None  # English translation, None if already English
    confidence: float = 1.0     # mean word probability, 0..1
    known_speaker: bool = False  # True when matched to an enrolled speaker
    emotion: str = "neutral"
    emotion_score: float = 0.0
    emotion_scores: dict[str, float] = field(default_factory=dict)
    audio_emotion: str | None = None
    text_emotion: str | None = None
    audio_raw: str | None = None   # raw audio-model top label+score (debug)
    text_raw: str | None = None    # raw text-model top label+score (debug)

    def to_dict(self) -> dict:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "speaker": self.speaker,
            "known_speaker": self.known_speaker,
            "text": self.text,
            "latin": self.latin,
            "english": self.english,
            "language": self.language,
            "confidence": round(self.confidence, 4),
            "emotion": self.emotion,
            "emotion_score": round(self.emotion_score, 4),
            "emotion_scores": {k: round(v, 4) for k, v in self.emotion_scores.items()},
            "audio_emotion": self.audio_emotion,
            "text_emotion": self.text_emotion,
        }


@dataclass
class TranscriptResult:
    segments: list[TranscriptSegment]
    language: str                       # dominant language of the recording
    speakers: list[str]
    source: str
    timings: dict[str, float] = field(default_factory=dict)  # stage -> seconds
    languages: dict[str, float] = field(default_factory=dict)  # lang -> seconds
    identified: dict[str, str] = field(default_factory=dict)   # label -> name
    unmatched: dict[str, str] = field(default_factory=dict)    # label -> reason
    # Final speaker label -> identify.ClusterVoiceprint, so a caller can enroll
    # a speaker straight after a run without re-diarizing the audio (which the
    # pipeline deletes on the way out). Not serialized: it is biometric data.
    voiceprints: dict = field(default_factory=dict, repr=False)

    @property
    def is_multilingual(self) -> bool:
        return len(self.languages) > 1

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "language": self.language,
            "languages": {k: round(v, 2) for k, v in self.languages.items()},
            "speakers": self.speakers,
            "identified": self.identified,
            "unmatched": self.unmatched,
            "timings": {k: round(v, 3) for k, v in self.timings.items()},
            "segments": [s.to_dict() for s in self.segments],
        }


def _noop(_stage: str, _frac: float) -> None:
    pass


@contextmanager
def _timed(timings: dict[str, float], key: str):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        timings[key] = time.perf_counter() - t0


def transcribe_file(
    src_path: str,
    *,
    whisper_model: str = "base",
    language: str | None = None,
    multilingual: bool = True,
    diarization_backend: str = "cluster",
    num_speakers: int | None = None,
    hf_token: str | None = None,
    identify_speakers: bool = True,
    speaker_db: str | None = None,
    match_threshold: float | None = None,
    match_margin: float | None = None,
    transliterate: bool = True,
    translate: bool = True,
    detect_emotion: bool = True,
    audio_weight: float = 0.5,
    use_audio_emotion: bool = True,
    use_text_emotion: bool = True,
    progress: ProgressCb | None = None,
) -> TranscriptResult:
    """Run the full pipeline on *src_path* and return a TranscriptResult.

    *multilingual* allows the language to change mid-recording. *language*
    pins one language and disables that. *identify_speakers* matches diarized
    voices against the persistent speaker store to recover real names.

    Non-English speech is kept in the script it was spoken in and carries two
    further renderings: *transliterate* spells it in the Latin alphabet, and
    *translate* runs a second Whisper pass to put it into English. Both leave
    already-English segments untouched, and translation only decodes the
    non-English stretches, so an English recording pays for neither.
    """
    progress = progress or _noop
    hf_token = hf_token or os.environ.get("HF_TOKEN")
    timings: dict[str, float] = {}

    progress("Extracting audio", 0.05)
    with _timed(timings, "extract"):
        wav_path = _audio.extract_audio(src_path)
    try:
        # Load once and share: the language probe and the decode use the same
        # model, and loading it twice would double the slowest startup cost.
        model = load_model(whisper_model)

        spans: list[LanguageSpan] = []
        if language is None and multilingual:
            progress("Detecting languages", 0.10)
            with _timed(timings, "language"):
                spans = detect_language_timeline(wav_path, model)

        progress("Transcribing", 0.15)
        with _timed(timings, "transcribe"):
            if spans:
                # We already know which language is spoken where, from
                # overlapping probes with a confirmation rule. Decoding each
                # span with that language pinned beats letting Whisper guess
                # again per 30s window, which is what lets a non-English
                # stretch come back written in English.
                raw_segments = transcribe_spans(wav_path, spans, model=model)
                lang = spans[0].language
            else:
                raw_segments, lang = transcribe(
                    wav_path,
                    model_name=whisper_model,
                    language=language,
                    multilingual=multilingual,
                    model=model,
                )

        translated: list[RawSegment] = []
        to_translate = _spans_to_translate(spans, lang, wav_path) if translate else []
        if to_translate:
            progress("Translating", 0.40)
            with _timed(timings, "translate"):
                translated = transcribe_spans(
                    wav_path, to_translate, model=model,
                    task="translate", word_timestamps=False,
                )

        progress("Separating speakers", 0.55)
        with _timed(timings, "diarize"):
            turns = diarize(
                wav_path,
                backend=diarization_backend,
                num_speakers=num_speakers,
                hf_token=hf_token,
            )

        identified: dict[str, str] = {}
        unmatched: dict[str, str] = {}
        voiceprints: dict = {}
        if identify_speakers and turns:
            progress("Recognising speakers", 0.65)
            with _timed(timings, "identify"):
                identified, unmatched, voiceprints = _identify_speakers(
                    wav_path, turns, speaker_db, match_threshold, match_margin,
                )

        segments = assign_speakers(raw_segments, turns)
        _attach_languages(segments, raw_segments, spans, lang)
        _attach_translations(segments, translated)
        if transliterate:
            _attach_transliterations(segments)
        for seg in segments:
            seg.known_speaker = seg.speaker in identified.values()

        if detect_emotion and segments:
            progress("Analyzing emotion", 0.80)
            with _timed(timings, "emotion"):
                _attach_emotions(
                    wav_path, segments, audio_weight,
                    use_audio_emotion, use_text_emotion, progress,
                )

        languages = _summarize_languages(spans) if spans else {lang: 0.0}
        # Report the language spoken for the longest, not merely the one Whisper
        # happened to detect first -- on a file that opens with a short greeting
        # in another language those differ, and the summary should say what the
        # recording is mostly in.
        dominant = next(iter(languages), lang)
        speakers = _ordered_speakers(segments)
        timings["total"] = sum(v for k, v in timings.items() if k != "total")
        progress("Done", 1.0)
        return TranscriptResult(
            segments=segments, language=dominant, speakers=speakers,
            source=src_path, timings=timings, languages=languages,
            identified=identified, unmatched=unmatched, voiceprints=voiceprints,
        )
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


def _identify_speakers(
    wav_path: str,
    turns: list[Turn],
    speaker_db: str | None,
    threshold: float | None,
    margin: float | None,
) -> tuple[dict[str, str], dict[str, str], dict]:
    """Rename turns to known speakers.

    Returns (matched, unmatched-reasons, voiceprints-by-final-label).
    """
    from .identify import (
        DEFAULT_MARGIN, DEFAULT_THRESHOLD, apply_matches,
        extract_voiceprints, match_speakers,
    )
    from .speakerdb import SpeakerStore

    prints = extract_voiceprints(wav_path, turns)
    if not prints:
        return {}, {}, {}

    with SpeakerStore(speaker_db) as store:
        known = store.all_speakers()

    matches = match_speakers(
        prints, known,
        threshold=DEFAULT_THRESHOLD if threshold is None else threshold,
        margin=DEFAULT_MARGIN if margin is None else margin,
    )
    _, mapping = apply_matches(matches, turns)
    reasons = {m.label: m.reason for m in matches if not m.matched}
    # Key by the label the transcript actually shows, so callers can enroll by
    # what they read rather than by the pre-rename diarization label.
    by_final = {mapping.get(p.label, p.label): p for p in prints}
    return mapping, reasons, by_final


def _attach_languages(
    segments: list[TranscriptSegment],
    raw_segments: list[RawSegment],
    spans: list[LanguageSpan],
    default: str,
) -> None:
    """Label each segment with its language and Whisper's confidence.

    Speaker splitting means one raw segment can become several transcript
    segments, so confidence is carried by time overlap rather than by index.
    """
    for seg in segments:
        seg.language = language_for(seg.start, seg.end, spans, default=default)
        source = _overlapping_raw(seg, raw_segments)
        if source is not None:
            seg.confidence = source.confidence


def _spans_to_translate(
    spans: list[LanguageSpan], detected: str, wav_path: str
) -> list[LanguageSpan]:
    """The stretches worth running the translation pass over.

    English stretches are skipped: Whisper translates into English, so it has
    nothing to add to speech already in it, and the pass costs a second full
    decode of whatever it is handed.
    """
    if spans:
        return [s for s in spans if s.language != ENGLISH]
    if detected == ENGLISH:
        return []
    # No timeline (a short file, or detection declined). The whole recording
    # is one span of whatever Whisper detected.
    return [
        LanguageSpan(0.0, _audio.audio_duration(wav_path), detected, 1.0)
    ]


def _attach_translations(
    segments: list[TranscriptSegment], translated: list[RawSegment]
) -> None:
    """Fill in ``english`` from a separate translate-task decode.

    The two passes segment the audio independently, so they cannot be zipped.
    Each translated segment is given to the transcript segment it overlaps
    most and the pieces are joined in time order -- a partition, so no
    sentence is attributed to two speakers at once.
    """
    if not segments or not translated:
        return

    buckets: dict[int, list[str]] = {}
    for raw in translated:
        index = _best_overlap_index(raw, segments)
        if index is not None:
            buckets.setdefault(index, []).append(raw.text.strip())

    for index, parts in buckets.items():
        text = " ".join(p for p in parts if p).strip()
        if text:
            segments[index].english = text


def _best_overlap_index(
    raw: RawSegment, segments: list[TranscriptSegment]
) -> int | None:
    best, best_overlap = None, 0.0
    for i, seg in enumerate(segments):
        overlap = min(seg.end, raw.end) - max(seg.start, raw.start)
        if overlap > best_overlap:
            best, best_overlap = i, overlap
    return best


def _attach_transliterations(segments: list[TranscriptSegment]) -> None:
    """Fill in ``latin`` for segments written in a non-Latin script.

    Imported here rather than at module scope so that uroman is only needed by
    a run that actually has a non-Latin script to romanize.
    """
    from .translit import romanize

    for seg in segments:
        seg.latin = romanize(seg.text, seg.language)


def _overlapping_raw(
    seg: TranscriptSegment, raw_segments: list[RawSegment]
) -> RawSegment | None:
    best, best_overlap = None, 0.0
    for raw in raw_segments:
        overlap = min(seg.end, raw.end) - max(seg.start, raw.start)
        if overlap > best_overlap:
            best, best_overlap = raw, overlap
    return best


# --------------------------------------------------------------------------- #
# Speaker alignment
# --------------------------------------------------------------------------- #
def assign_speakers(
    raw_segments: list[RawSegment], turns: list[Turn]
) -> list[TranscriptSegment]:
    """Attach a speaker to each segment, splitting on mid-segment speaker change.

    If a segment has word timestamps we group its words by the speaker active
    at each word and emit one TranscriptSegment per contiguous run. Without
    word timestamps (or diarization) we fall back to a whole-segment vote.
    """
    if not turns:
        return [
            TranscriptSegment(s.start, s.end, "Speaker 1", s.text)
            for s in raw_segments
        ]

    out: list[TranscriptSegment] = []
    for seg in raw_segments:
        if seg.words:
            out.extend(_split_segment_by_words(seg, turns))
        else:
            spk = _dominant_speaker(seg.start, seg.end, turns)
            out.append(TranscriptSegment(seg.start, seg.end, spk, seg.text))
    return out


def _split_segment_by_words(
    seg: RawSegment, turns: list[Turn]
) -> list[TranscriptSegment]:
    pieces: list[TranscriptSegment] = []
    cur_spk: str | None = None
    cur_words: list[Word] = []

    def flush():
        if cur_words:
            pieces.append(
                TranscriptSegment(
                    start=cur_words[0].start,
                    end=cur_words[-1].end,
                    speaker=cur_spk,
                    text="".join(w.text for w in cur_words).strip(),
                )
            )

    for w in seg.words:
        spk = _speaker_at((w.start + w.end) / 2, turns)
        if cur_spk is None or spk == cur_spk:
            cur_spk = spk
            cur_words.append(w)
        else:
            flush()
            cur_spk, cur_words = spk, [w]
    flush()

    # Coalesce tiny fragments back into neighbours to avoid 1-word flip-flops.
    return _merge_short_pieces(pieces) or [
        TranscriptSegment(
            seg.start, seg.end,
            _dominant_speaker(seg.start, seg.end, turns), seg.text,
        )
    ]


def _merge_short_pieces(
    pieces: list[TranscriptSegment], min_words: int = 2
) -> list[TranscriptSegment]:
    if len(pieces) <= 1:
        return pieces
    merged: list[TranscriptSegment] = []
    for p in pieces:
        n_words = len(p.text.split())
        if merged and n_words < min_words and merged[-1].speaker != p.speaker:
            # Absorb a stray fragment into the previous run.
            prev = merged[-1]
            prev.end = p.end
            prev.text = (prev.text + " " + p.text).strip()
        elif merged and merged[-1].speaker == p.speaker:
            prev = merged[-1]
            prev.end = p.end
            prev.text = (prev.text + " " + p.text).strip()
        else:
            merged.append(p)
    return merged


def _speaker_at(t: float, turns: list[Turn]) -> str:
    """Speaker whose turn contains time *t*; nearest turn if t is in a gap."""
    for turn in turns:
        if turn.start <= t <= turn.end:
            return turn.speaker
    nearest = min(
        turns,
        key=lambda tr: 0 if tr.start <= t <= tr.end
        else min(abs(t - tr.start), abs(t - tr.end)),
    )
    return nearest.speaker


def _dominant_speaker(start: float, end: float, turns: list[Turn]) -> str:
    """Speaker with the most temporal overlap of [start, end]."""
    overlap: dict[str, float] = {}
    for turn in turns:
        lo, hi = max(start, turn.start), min(end, turn.end)
        if hi > lo:
            overlap[turn.speaker] = overlap.get(turn.speaker, 0.0) + (hi - lo)
    if not overlap:
        return _speaker_at((start + end) / 2, turns)
    return max(overlap, key=overlap.get)


def _ordered_speakers(segments: list[TranscriptSegment]) -> list[str]:
    seen: list[str] = []
    for s in segments:
        if s.speaker not in seen:
            seen.append(s.speaker)
    return seen


# --------------------------------------------------------------------------- #
# Emotion
# --------------------------------------------------------------------------- #
def _attach_emotions(
    wav_path: str,
    segments: list[TranscriptSegment],
    audio_weight: float,
    use_audio: bool,
    use_text: bool,
    progress: ProgressCb,
) -> None:
    from .emotion import EmotionAnalyzer

    analyzer = EmotionAnalyzer(
        audio_weight=audio_weight, use_audio=use_audio, use_text=use_text
    )
    samples, sr = _audio.load_waveform(wav_path)
    items = [
        (_audio.slice_waveform(samples, sr, seg.start, seg.end), sr, seg.text)
        for seg in segments
    ]
    # One batched pass over both models instead of per-segment inference.
    # Languages gate the English-only text model per segment.
    results = analyzer.analyze_batch(
        items, languages=[seg.language for seg in segments]
    )
    for seg, res in zip(segments, results):
        seg.emotion = res.label
        seg.emotion_score = res.score
        seg.emotion_scores = res.scores
        seg.audio_emotion = res.audio_label
        seg.text_emotion = res.text_label
        seg.audio_raw = res.audio_raw
        seg.text_raw = res.text_raw
    progress("Analyzing emotion", 0.95)
