"""Pipeline orchestration: a lesson recording in, a practice-ready lesson out.

    extract audio -> track pitch -> find Sa -> cut into notes
                  -> label sung / spoken -> transcribe only the spoken parts
                  -> diarize into guru and student -> repair the vocabulary

The ordering matters and is the whole design. Pitch analysis runs *first* and
speech recognition runs *last*, on only the stretches pitch analysis called
speech. That inversion — music understanding gating speech recognition rather
than the other way round — is what separates this from `transcriber/`, where
Whisper leads and everything else annotates what it found.

Heavy dependencies stay lazy: importing this module costs nothing until
:func:`transcribe_lesson` actually runs.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable

from transcriber import audio as _audio

from . import lexicon, raga as _raga, segmentation, swara as _swara, translit
from .pitch import PitchTrack, track_pitch
from .segmentation import DRONE, SUNG, Region
from .swara import Note, TonicEstimate

ProgressCb = Callable[[str, float], None]

# What a segment is doing in the lesson. Kept separate from who is doing it,
# because "the student sings" and "the guru sings" are different events and a
# practice sheet needs to tell them apart.
INSTRUCTION = "instruction"
DEMONSTRATION = "demonstration"
ATTEMPT = "attempt"

GURU = "Guru"
STUDENT = "Student"


@dataclass
class LessonSegment:
    start: float
    end: float
    kind: str                       # instruction | demonstration | attempt | drone
    speaker: str = ""
    text: str = ""                  # spoken words, after vocabulary repair
    roman: str = ""                 # romanized companion for Devanagari text
    language: str = ""              # hi | en | mixed
    sargam: str = ""                # sung phrase in swara notation
    notes: list[Note] = field(default_factory=list)
    raw_text: str = ""              # what Whisper said before repair
    corrections: list[lexicon.Correction] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def is_sung(self) -> bool:
        return self.kind in (DEMONSTRATION, ATTEMPT)

    def to_dict(self) -> dict:
        data = {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "kind": self.kind,
            "speaker": self.speaker,
        }
        if self.is_sung:
            data["sargam"] = self.sargam
            data["notes"] = [n.to_dict() for n in self.notes]
        else:
            data["text"] = self.text
            data["language"] = self.language
            if self.roman:
                data["roman"] = self.roman
        if self.raw_text and self.raw_text != self.text:
            data["raw_text"] = self.raw_text
        if self.corrections:
            data["corrections"] = [c.to_dict() for c in self.corrections]
        return data


@dataclass
class LessonResult:
    segments: list[LessonSegment]
    tonic: TonicEstimate
    scale: _raga.ScaleGuess
    regions: list[Region]
    mentions: dict[str, list[str]]
    speakers: list[str]
    language: str
    source: str
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def sung_seconds(self) -> float:
        return sum(s.duration for s in self.segments if s.is_sung)

    @property
    def spoken_seconds(self) -> float:
        return sum(s.duration for s in self.segments if not s.is_sung)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "language": self.language,
            "tonic": self.tonic.to_dict(),
            "scale": self.scale.to_dict(),
            "mentioned": self.mentions,
            "speakers": self.speakers,
            "sung_seconds": round(self.sung_seconds, 1),
            "spoken_seconds": round(self.spoken_seconds, 1),
            "timings": {k: round(v, 3) for k, v in self.timings.items()},
            "segments": [s.to_dict() for s in self.segments],
        }


def _noop(_stage: str, _frac: float) -> None:
    pass


@contextmanager
def _timed(timings: dict[str, float], key: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        timings[key] = time.perf_counter() - start


def transcribe_lesson(
    src_path: str,
    *,
    whisper_model: str = "small",
    language: str | None = None,
    tonic: float | None = None,
    diarize_speakers: bool = True,
    num_speakers: int | None = None,
    diarization_backend: str = "cluster",
    hf_token: str | None = None,
    guru_speaker: str | None = None,
    extra_terms: list[str] | None = None,
    fix_vocabulary: bool = True,
    keep_sung_text: bool = False,
    sung_threshold: float = 0.50,
    progress: ProgressCb | None = None,
) -> LessonResult:
    """Run the whole pipeline on *src_path*.

    *tonic* overrides Sa detection (in Hz) — worth using, since you know your
    own Sa and the detector only guesses. *keep_sung_text* keeps whatever
    Whisper produced over singing, which is normally hallucination but is
    occasionally a bandish lyric worth reading.
    """
    progress = progress or _noop
    hf_token = hf_token or os.environ.get("HF_TOKEN")
    timings: dict[str, float] = {}

    progress("Extracting audio", 0.03)
    with _timed(timings, "extract"):
        wav_path = _audio.extract_audio(src_path)

    try:
        progress("Tracking pitch", 0.10)
        with _timed(timings, "pitch"):
            samples, sample_rate = _audio.load_waveform(wav_path)
            track = track_pitch(samples, sample_rate)

        progress("Finding Sa", 0.25)
        with _timed(timings, "tonic"):
            tonic_estimate = _resolve_tonic(track, tonic)

        progress("Reading the swaras", 0.30)
        with _timed(timings, "notes"):
            notes = _swara.segment_notes(track, tonic_estimate.hz) if tonic_estimate.hz else []
            regions = segmentation.classify_regions(
                track, notes, tonic_estimate.hz, sung_threshold=sung_threshold
            )

        progress("Transcribing the talking", 0.40)
        with _timed(timings, "transcribe"):
            speech_segments, detected_language = _run_whisper(
                wav_path, regions, whisper_model, language, extra_terms
            )

        turns = []
        if diarize_speakers:
            progress("Telling the voices apart", 0.75)
            with _timed(timings, "diarize"):
                turns = _run_diarization(
                    wav_path, diarization_backend, num_speakers, hf_token
                )

        progress("Assembling the lesson", 0.90)
        segments = _build_segments(
            speech_segments, regions, notes, turns, keep_sung_text
        )
        _assign_roles(segments, turns, guru_speaker)
        if fix_vocabulary:
            _repair_vocabulary(segments)
        _attach_romanization(segments)

        mentions = lexicon.find_mentions(
            " ".join(s.text for s in segments if s.text)
        )
        scale = _raga.identify_scale(
            _swara.swara_weights([n for s in segments if s.is_sung for n in s.notes])
        )
        speakers = _ordered_speakers(segments)
        timings["total"] = sum(v for k, v in timings.items() if k != "total")
        progress("Done", 1.0)

        return LessonResult(
            segments=segments,
            tonic=tonic_estimate,
            scale=scale,
            regions=regions,
            mentions=mentions,
            speakers=speakers,
            language=detected_language,
            source=src_path,
            timings=timings,
        )
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Stages
# --------------------------------------------------------------------------- #
def _resolve_tonic(track: PitchTrack, override: float | None) -> TonicEstimate:
    """Use the caller's Sa if given, else detect it from a first pass of notes."""
    if override:
        return TonicEstimate(float(override), 1.0, _swara.describe_hz(float(override)))
    # Segmentation does not depend on the tonic, only labelling does, so a
    # throwaway pass against a fixed reference gives the histogram its notes.
    preliminary = _swara.segment_notes(track, _swara._HIST_REF_HZ)
    return _swara.detect_tonic(track, preliminary)


def _run_whisper(
    wav_path: str,
    regions: list[Region],
    model_name: str,
    language: str | None,
    extra_terms: list[str] | None,
):
    from .transcribe import transcribe_speech

    spans = segmentation.speech_spans(regions)
    return transcribe_speech(
        wav_path,
        model_name=model_name,
        language=language,
        initial_prompt=lexicon.whisper_prompt(extra_terms),
        clip_spans=spans or None,
    )


def _run_diarization(
    wav_path: str, backend: str, num_speakers: int | None, hf_token: str | None
):
    from transcriber.diarize import diarize

    try:
        return diarize(
            wav_path, backend=backend, num_speakers=num_speakers, hf_token=hf_token
        )
    except RuntimeError:
        # Diarization is optional garnish: a lesson transcript without speaker
        # labels is still a lesson transcript.
        return []


def _build_segments(
    speech_segments,
    regions: list[Region],
    notes: list[Note],
    turns,
    keep_sung_text: bool,
) -> list[LessonSegment]:
    """Interleave transcribed speech with sung stretches, in time order."""
    segments: list[LessonSegment] = []

    for seg in speech_segments:
        region = segmentation.region_at(regions, seg.start, seg.end)
        sung = region is not None and region.kind in (SUNG, DRONE)
        if sung and not keep_sung_text:
            continue          # Whisper talking over music: almost always invented
        segments.append(
            LessonSegment(
                start=seg.start, end=seg.end, kind=INSTRUCTION,
                text=seg.text, raw_text=seg.text,
                language=_segment_language(seg),
            )
        )

    for region in regions:
        if region.kind != SUNG:
            continue
        # Require a note to sit almost entirely inside the region. A note that
        # merely straddles the boundary belongs to the speech on the other
        # side of it, and one stray syllable at the front of a sargam line is
        # the difference between a phrase you can read back and one you cannot.
        region_notes = [
            n for n in notes
            if n.overlap_seconds(region.start, region.end) >= 0.9 * n.duration
        ]
        region_notes = _strip_edge_blips(region_notes)
        if not region_notes:
            continue
        segments.append(
            LessonSegment(
                start=region_notes[0].start, end=region_notes[-1].end,
                kind=DEMONSTRATION,
                sargam=_swara.sargam_line(region_notes), notes=region_notes,
            )
        )

    segments.sort(key=lambda s: s.start)
    return [s for s in segments if s.text or s.notes]


def _strip_edge_blips(notes: list[Note], min_edge: float = 0.15) -> list[Note]:
    """Drop the very short notes at each end of a sung phrase.

    Where speech meets singing the tracker emits a sliver as the pitch settles.
    In the middle of a phrase a sliver is a real note — a fast taan is made of
    them — but at the edge it is the transition, and it turns a readable sargam
    line into one that starts on a swara nobody sang.
    """
    trimmed = list(notes)
    while trimmed and trimmed[0].duration < min_edge:
        trimmed.pop(0)
    while trimmed and trimmed[-1].duration < min_edge:
        trimmed.pop()
    return trimmed


def _segment_language(seg) -> str:
    """Whisper's language tag, corrected by the script actually written."""
    ratio = translit.devanagari_ratio(seg.text)
    if 0.15 < ratio < 0.85:
        return "mixed"
    if ratio >= 0.85:
        return "hi"
    if ratio <= 0.15 and seg.language in ("hi", "ur", "bn", "mr", "ne"):
        # Whisper heard Hindi but wrote Latin: romanized Hindi, which is
        # exactly what a code-switched lesson sounds like.
        return f"{seg.language}-roman"
    return seg.language or "en"


def _assign_roles(
    segments: list[LessonSegment], turns, guru_speaker: str | None
) -> None:
    """Label voices Guru and Student, or leave raw speaker names if unsure.

    The guru does the explaining, so the speaker with the most *spoken* time is
    the guru — singing is a bad signal, because the student sings too, which is
    the entire point of the lesson.
    """
    if not turns:
        return

    from transcriber.core import _dominant_speaker

    for segment in segments:
        segment.speaker = _dominant_speaker(segment.start, segment.end, turns)

    talk_time: dict[str, float] = {}
    for segment in segments:
        if segment.kind == INSTRUCTION and segment.speaker:
            talk_time[segment.speaker] = talk_time.get(segment.speaker, 0.0) + segment.duration
    if not talk_time:
        return

    guru = guru_speaker or max(talk_time, key=lambda name: talk_time[name])
    present = _ordered_speakers(segments)
    if guru not in present:
        return                                  # caller named a speaker we never saw

    # Only two roles are meaningful; anyone else keeps their raw label. The
    # student is counted over *all* segments, not just spoken ones — a student
    # who only ever sings back is still the student, and is in fact the common
    # case in a lesson recording.
    roles = {guru: GURU}
    others = [name for name in present if name != guru]
    if len(others) == 1:
        roles[others[0]] = STUDENT

    for segment in segments:
        segment.speaker = roles.get(segment.speaker, segment.speaker)
        if segment.kind == DEMONSTRATION and segment.speaker == STUDENT:
            segment.kind = ATTEMPT


def _repair_vocabulary(segments: list[LessonSegment]) -> None:
    for segment in segments:
        if not segment.text:
            continue
        segment.text, segment.corrections = lexicon.correct_text(segment.text)


def _attach_romanization(segments: list[LessonSegment]) -> None:
    for segment in segments:
        if segment.text and translit.is_devanagari(segment.text):
            segment.roman = translit.romanize(segment.text)


def _ordered_speakers(segments: list[LessonSegment]) -> list[str]:
    seen: list[str] = []
    for segment in segments:
        if segment.speaker and segment.speaker not in seen:
            seen.append(segment.speaker)
    return seen
