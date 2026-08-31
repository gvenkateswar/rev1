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

import difflib
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable

from . import audio as _audio
from .credentials import resolve_hf_token
from .diarize import Turn, diarize
from .language import (
    LanguageSpan, apply_aliases, describe_spans, detect_language_timeline,
    detect_one_language, language_for,
)
from .language import summarize as _summarize_languages
from .transcribe import (
    RawSegment, Word, decode_chunk, load_model, transcribe,
    transcribe_spans, translate_each,
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
    native_is_english: bool = False   # the "native" text came back as English
    detected_language: str | None = None  # what this segment's own audio says
    detected_confidence: float = 0.0      # ...and how sure the detector was
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
            "native_is_english": self.native_is_english,
            "detected_language": self.detected_language,
            "detected_confidence": round(self.detected_confidence, 4),
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
    def untranscribed_segments(self) -> int:
        """How many non-English lines came back as English instead."""
        return sum(1 for s in self.segments if s.native_is_english)

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


# Diarization on CPU can run for many minutes with nothing to show for it. The
# browser gets a progress bar; the terminal the app was launched from gets
# these, so "is it still working?" has an answer in both places. Set
# TRANSCRIBER_QUIET=1 to silence them (a library caller usually wants that).
def _log(message: str) -> None:
    if os.environ.get("TRANSCRIBER_QUIET"):
        return
    sys.stderr.write(f"transcriber: {message}\n")
    sys.stderr.flush()


@contextmanager
def _timed(timings: dict[str, float], key: str):
    _log(f"{key}: started")
    t0 = time.perf_counter()
    finished = False
    try:
        yield
        finished = True
    finally:
        elapsed = time.perf_counter() - t0
        timings[key] = elapsed
        # Say which it was: a stage that died still recorded a duration, and
        # reporting that as "done" would be a lie.
        _log(f"{key}: {'done' if finished else 'FAILED'} in {elapsed:.1f}s")


def _stage_progress(progress: ProgressCb, label: str, lo: float, hi: float) -> ProgressCb:
    """Map a stage's own 0..1 progress into its slice of the overall bar."""
    def report(detail: str, frac: float) -> None:
        frac = min(1.0, max(0.0, frac))
        progress(f"{label} — {detail}" if detail else label, lo + (hi - lo) * frac)
    return report


def transcribe_file(
    src_path: str,
    *,
    # small, not base: base does not transcribe non-English speech, it
    # returns an English translation of it (see _flag_missing_native_text).
    whisper_model: str = "small",
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
    language_aliases: dict[str, str] | None = None,
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
    language_aliases = language_aliases or {}
    hf_token, token_source = resolve_hf_token(hf_token)
    if token_source and diarization_backend == "pyannote":
        # The source, never the token: which file was used is the thing that
        # is unclear when a stale one keeps getting picked up.
        _log(f"hugging face token: {token_source}")
    timings: dict[str, float] = {}

    progress("Extracting audio", 0.05)
    with _timed(timings, "extract"):
        wav_path = _audio.extract_audio(src_path)
    try:
        # Both numbers set expectations for every stage that follows, and the
        # diarization backend is the one that decides whether this run takes
        # seconds or an hour.
        _log(
            f"{_audio.audio_duration(wav_path):.0f}s of audio | "
            f"model={whisper_model} diarization={diarization_backend}"
        )
        # Load once and share: the language probe and the decode use the same
        # model, and loading it twice would double the slowest startup cost.
        model = load_model(whisper_model)

        spans: list[LanguageSpan] = []
        if language is None and multilingual:
            progress("Detecting languages", 0.10)
            with _timed(timings, "language"):
                spans = detect_language_timeline(wav_path, model)
            for span in spans:
                span.language = apply_aliases(span.language, language_aliases)
            # The spans decide both what each stretch is labelled and how the
            # decode is chunked, so when the transcript looks wrong this is
            # the first thing worth seeing. It is one short line.
            _log("languages: " + (describe_spans(spans) or "none detected"))

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

        progress("Separating speakers", 0.50)
        with _timed(timings, "diarize"):
            turns = diarize(
                wav_path,
                backend=diarization_backend,
                num_speakers=num_speakers,
                hf_token=hf_token,
                progress=_stage_progress(
                    progress, "Separating speakers", 0.50, 0.70),
            )

        identified: dict[str, str] = {}
        unmatched: dict[str, str] = {}
        voiceprints: dict = {}
        if identify_speakers and turns:
            progress("Recognising speakers", 0.72)
            with _timed(timings, "identify"):
                identified, unmatched, voiceprints = _identify_speakers(
                    wav_path, turns, speaker_db, match_threshold, match_margin,
                )

        segments = assign_speakers(raw_segments, turns)
        _attach_languages(segments, raw_segments, spans, lang)

        # Stretches the decode produced nothing for. A span pinned to one
        # language yields no text at all where another was spoken, so the
        # words do not come back wrong -- they come back missing, and a
        # re-check of the segments cannot see them because there is no
        # segment there to check.
        if turns:
            progress("Filling gaps", 0.72)
            with _timed(timings, "gaps"):
                segments = _fill_untranscribed_gaps(
                    wav_path, segments, turns, model, lang, language_aliases)

        # Diarization has now cut the recording where the speaker changes,
        # which is also where the language usually changes. Those boundaries
        # are far finer than the 30s probes the timeline was built from, so
        # this is the first chance to catch a switch too short for it.
        if spans and multilingual and language is None:
            progress("Checking languages", 0.74)
            with _timed(timings, "relanguage"):
                _recheck_segment_languages(
                    wav_path, segments, model, language_aliases)

        if translate:
            to_translate = [s for s in segments if s.language != ENGLISH]
            if to_translate:
                progress("Translating", 0.76)
                with _timed(timings, "translate"):
                    for seg, text in zip(
                        to_translate,
                        translate_each(wav_path, to_translate, model=model),
                    ):
                        seg.english = text or None

        _reconcile_english_lines(segments)
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


# A gap shorter than this is a pause between words, not a missing sentence.
GAP_MIN_SECONDS = 1.0


def _fill_untranscribed_gaps(
    wav_path: str,
    segments: list[TranscriptSegment],
    turns: list[Turn],
    model,
    default_language: str,
    aliases: dict[str, str],
) -> list[TranscriptSegment]:
    """Decode speech that produced no segment, and return the merged list.

    Only gaps that diarization says contain a speaker are decoded. That
    matters: Whisper handed a stretch of silence invents text, confidently and
    plausibly, and a fabricated line is worse than a missing one. The
    diarization turns are the evidence that someone was talking.

    The language is detected on the gap's own audio rather than inherited,
    because a gap that the span's language produced nothing for is precisely
    where that language is likely to be wrong.
    """
    gaps = _uncovered_speech(segments, turns, GAP_MIN_SECONDS)
    if not gaps:
        return segments

    samples, sr = _audio.load_waveform(wav_path)
    found: list[TranscriptSegment] = []
    for start, end in gaps:
        chunk = _audio.slice_waveform(samples, sr, start, end)
        detected = detect_one_language(model, chunk)
        language = apply_aliases(
            detected[0] if detected else default_language, aliases)
        text = decode_chunk(chunk, model=model, language=language).strip()
        if not text:
            continue
        found.append(TranscriptSegment(
            start=start, end=end,
            speaker=_dominant_speaker(start, end, turns),
            text=text, language=language,
        ))

    if not found:
        return segments
    _log(f"gaps: recovered {len(found)} untranscribed stretch(es)")
    return sorted(segments + found, key=lambda s: s.start)


def _uncovered_speech(
    segments: list[TranscriptSegment], turns: list[Turn], min_seconds: float
) -> list[tuple[float, float]]:
    """Stretches where somebody spoke and no segment came back."""
    covered = _merge_intervals([(s.start, s.end) for s in segments])
    gaps: list[tuple[float, float]] = []
    for start, end in _merge_intervals([(t.start, t.end) for t in turns]):
        cursor = start
        for lo, hi in covered:
            if hi <= cursor:
                continue
            if lo >= end:
                break
            if lo > cursor:
                gaps.append((cursor, min(lo, end)))
            cursor = max(cursor, hi)
            if cursor >= end:
                break
        if cursor < end:
            gaps.append((cursor, end))
    return [(a, b) for a, b in gaps if b - a >= min_seconds]


def _merge_intervals(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Sorted, non-overlapping. Touching intervals merge; empty ones vanish."""
    out: list[tuple[float, float]] = []
    for start, end in sorted(s for s in spans if s[1] > s[0]):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


# Below this, a slice is too short for the detector to say anything useful.
RELANGUAGE_MIN_SECONDS = 2.0

# And below this confidence it is not worth overriding the timeline, which was
# built from far more audio than one segment carries.
RELANGUAGE_MIN_CONFIDENCE = 0.70


def _recheck_segment_languages(
    wav_path: str,
    segments: list[TranscriptSegment],
    model,
    aliases: dict[str, str] | None = None,
) -> int:
    """Re-detect each segment's language on its own audio; re-decode the
    ones that were wrong. Returns how many changed.

    The timeline probes 30 seconds at a time, which is as fine as Whisper's
    detector works -- a six-second question in another language sits inside
    one probe and cannot be seen. Those spans then pin the decode, so the
    question comes out decoded as the wrong language, which usually means it
    comes out as nothing at all.

    Detection is one encoder pass, so checking every segment is cheap; only
    the segments that actually disagree pay for a second decode.
    """
    if not segments:
        return 0

    samples, sr = _audio.load_waveform(wav_path)
    changed = 0
    for seg in segments:
        chunk = _audio.slice_waveform(samples, sr, seg.start, seg.end)
        detected = detect_one_language(model, chunk)
        if detected:
            detected = (apply_aliases(detected[0], aliases or {}), detected[1])
            # Kept even when it is too weak to act on. Re-decoding a line needs
            # strong evidence; deciding *not* to accuse the model of skipping
            # the transcript needs much less, and this is what that check
            # reads.
            seg.detected_language, seg.detected_confidence = detected
        if not _should_relanguage(seg, detected):
            continue
        language, _confidence = detected
        text = decode_chunk(chunk, model=model, language=language).strip()
        if not text:
            # The re-decode found nothing. The original text may be wrong, but
            # it is what we have, and blanking the line is not an improvement
            # on it.
            continue
        seg.text, seg.language = text, language
        changed += 1

    if changed:
        _log(f"relanguage: corrected {changed} segment(s)")
    return changed


def _should_relanguage(
    seg: TranscriptSegment, detected: tuple[str, float] | None
) -> bool:
    """Whether one segment's own audio outvotes the span it sits in."""
    if detected is None:
        return False
    language, confidence = detected
    if language == seg.language:
        return False
    if seg.end - seg.start < RELANGUAGE_MIN_SECONDS:
        return False
    return confidence >= RELANGUAGE_MIN_CONFIDENCE


# Two renderings this close together are not a transcript and a translation of
# it -- they are one English sentence printed twice. Below this the two really
# do say different things.
_SAME_TEXT_RATIO = 0.80

# Under this many letters, two short phrases collide by chance ("ok", "hello").
_MIN_COMPARABLE_CHARS = 12


def _reconcile_english_lines(segments: list[TranscriptSegment]) -> None:
    """Sort out lines whose transcript and translation say the same thing.

    That happens for two opposite reasons, and telling them apart matters:

    * The speaker used English, inside a recording labelled something else.
      The transcript is right and the label is wrong; the two renderings
      agreeing is exactly what correct English output looks like.
    * A small Whisper checkpoint returned an English translation instead of
      transcribing. Transcribe and translate share one decoder, and the tiny
      and base models conflate the tasks, so what comes out reads like a clean
      transcript while the speaker's own words are missing.

    The segment's own audio decides. Only when it does *not* say English is
    the model accused of skipping the transcript -- an accusation should need
    more evidence than staying quiet does, and a warning on a correct line is
    itself a wrong answer.

    When the audio does say English, the label is corrected and the duplicate
    translation dropped rather than printed twice.
    """
    for seg in segments:
        if seg.language == ENGLISH:
            # The same failure mirrored, and nothing else looks at these: a
            # line decoded as English gets no translation rendering, so there
            # is nothing to compare it against and it passes in silence. Its
            # own audio is the only evidence available.
            seg.native_is_english = _confidently_not_english(seg)
            continue
        if not seg.english or not _nearly_the_same(seg.text, seg.english):
            continue
        if seg.detected_language == ENGLISH:
            seg.language, seg.english = ENGLISH, None
        else:
            seg.native_is_english = True


def _confidently_not_english(seg: TranscriptSegment) -> bool:
    """Whether this line's own audio disagrees with being decoded as English.

    Held to the same bar as re-decoding. A weaker bar would mostly fire on
    short lines, which is where detection is least reliable and a warning
    least deserved.
    """
    return (
        seg.detected_language is not None
        and seg.detected_language != ENGLISH
        and seg.detected_confidence >= RELANGUAGE_MIN_CONFIDENCE
    )


def _nearly_the_same(native: str, english: str) -> bool:
    a, b = _letters(native), _letters(english)
    if min(len(a), len(b)) < _MIN_COMPARABLE_CHARS:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= _SAME_TEXT_RATIO


def _letters(text: str) -> str:
    """Lowercased letters and digits only, so punctuation cannot mask a match."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


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
