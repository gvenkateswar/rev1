"""Tests for the music-lesson transcriber.

Everything here runs on synthesized audio and needs nothing but NumPy — no
Whisper, no model downloads, no network. That is deliberate: the parts of this
pipeline that are easy to get quietly wrong (pitch tracking, tonic detection,
swara labelling, sung-versus-spoken) are exactly the parts that can be checked
against a signal whose correct answer you constructed yourself.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from music_lesson import lexicon, raga, translit                      # noqa: E402
from music_lesson.pitch import hz_to_cents, track_pitch               # noqa: E402
from music_lesson.segmentation import SPOKEN, SUNG, classify_regions  # noqa: E402
from music_lesson.swara import (                                      # noqa: E402
    _HIST_REF_HZ, classify_cents, describe_hz, detect_tonic, parse_tonic,
    sargam_line, segment_notes, swara_weights,
)

SR = 16_000
SA = 146.83          # D3, a common male vocalist's Sa


# --------------------------------------------------------------------------- #
# Synthesis helpers: build audio whose correct transcription we already know.
# --------------------------------------------------------------------------- #
def _harmonic(phase: np.ndarray, amplitude: float) -> np.ndarray:
    """A voice-like tone: fundamental plus a handful of decaying harmonics."""
    return sum(np.sin(phase * k) / k for k in range(1, 6)) * amplitude


def sing(semitones: list[int], note_s: float = 0.55, amplitude: float = 0.3,
         tonic: float = SA) -> np.ndarray:
    """Sung phrase: one steady, faintly vibrato note per semitone offset."""
    out = []
    for semitone in semitones:
        t = np.arange(int(note_s * SR)) / SR
        freq = tonic * 2 ** (semitone / 12) * (1 + 0.004 * np.sin(2 * np.pi * 5 * t))
        out.append(_harmonic(np.cumsum(2 * np.pi * freq / SR), amplitude))
    return np.concatenate(out)


def speak(duration: float, rng: np.random.Generator,
          amplitude: float = 0.3) -> np.ndarray:
    """Speech-like audio: short voiced syllables that glide, plus fricatives."""
    total = int(duration * SR)
    out = np.zeros(total)
    i = 0
    while i < total:
        span = min(int(rng.uniform(0.06, 0.18) * SR), total - i)
        roll = rng.random()
        if roll < 0.6:                                   # voiced syllable
            start_f = rng.uniform(95, 185)
            slope = rng.uniform(-160, 160)
            t = np.arange(span) / SR
            freq = np.maximum(start_f + slope * t, 70)
            out[i:i + span] = (
                _harmonic(np.cumsum(2 * np.pi * freq / SR), amplitude)
                * np.hanning(span)
            )
        elif roll < 0.85:                                # fricative
            out[i:i + span] = rng.normal(0, 0.04, span)
        i += span                                        # else: a pause
    return out


def tanpura(length: int, tonic: float = SA, amplitude: float = 0.03) -> np.ndarray:
    """A quiet drone on Sa and Pa, as it sits under a real lesson."""
    t = np.arange(length) / SR
    return amplitude * (
        np.sin(2 * np.pi * tonic * t) + 0.5 * np.sin(2 * np.pi * tonic * 1.5 * t)
    )


class PitchTrackingTests(unittest.TestCase):
    def test_steady_tone_is_tracked_to_within_a_few_cents(self):
        t = np.arange(3 * SR) / SR
        audio = _harmonic(2 * np.pi * 220.0 * t, 0.25)
        track = track_pitch(audio, SR)

        voiced = track.f0[track.voiced]
        self.assertGreater(voiced.size, 0.9 * len(track))
        error_cents = abs(float(np.median(hz_to_cents(voiced, 220.0))))
        self.assertLess(error_cents, 5.0)

    def test_glide_is_followed_not_averaged(self):
        t = np.arange(2 * SR) / SR
        freq = np.linspace(200, 300, len(t))
        audio = _harmonic(np.cumsum(2 * np.pi * freq / SR), 0.25)
        track = track_pitch(audio, SR)

        voiced = track.f0[track.voiced]
        self.assertAlmostEqual(float(voiced[5]), 200.0, delta=8.0)
        self.assertAlmostEqual(float(voiced[-5]), 300.0, delta=8.0)

    def test_noise_is_not_pitched(self):
        rng = np.random.default_rng(0)
        track = track_pitch(rng.normal(0, 0.1, 2 * SR), SR)
        self.assertLess(float(track.voiced.mean()), 0.05)

    def test_audio_shorter_than_one_frame_is_handled(self):
        track = track_pitch(np.zeros(100), SR)
        self.assertEqual(len(track), 0)


class TonicTests(unittest.TestCase):
    def _detect(self, tonic_hz: float) -> float:
        phrase = np.concatenate([
            sing([0, 2, 4, 6, 7, 6, 4, 2, 0], tonic=tonic_hz),
            np.zeros(int(0.3 * SR)),
            sing([0], note_s=1.2, tonic=tonic_hz),        # nyas: rest on Sa
        ])
        audio = phrase + tanpura(len(phrase), tonic=tonic_hz)
        track = track_pitch(audio, SR)
        estimate = detect_tonic(track, segment_notes(track, _HIST_REF_HZ))
        return estimate.hz

    def test_tonic_pitch_class_is_recovered(self):
        for true_tonic in (146.83, 196.0, 261.63):
            with self.subTest(tonic=true_tonic):
                detected = self._detect(true_tonic)
                # The octave is cosmetic; the pitch class is the answer.
                cents = abs(float(hz_to_cents(detected, true_tonic))) % 1200
                self.assertLess(min(cents, 1200 - cents), 25.0)

    def test_parse_tonic_accepts_notes_and_frequencies(self):
        self.assertAlmostEqual(parse_tonic("138.6"), 138.6, places=3)
        self.assertAlmostEqual(parse_tonic("C#3"), 138.591, places=2)
        self.assertAlmostEqual(parse_tonic("Db3"), 138.591, places=2)
        self.assertAlmostEqual(parse_tonic("A4"), 440.0, places=3)
        self.assertAlmostEqual(parse_tonic("d3"), 146.832, places=2)
        with self.assertRaises(ValueError):
            parse_tonic("banana")

    def test_describe_hz_names_the_western_note(self):
        self.assertTrue(describe_hz(440.0).startswith("A4"))
        self.assertTrue(describe_hz(146.83).startswith("D3"))

    def test_classify_cents_maps_to_swara_and_octave(self):
        self.assertEqual(classify_cents(0.0)[:2], (0, 0))
        self.assertEqual(classify_cents(700.0)[:2], (7, 0))
        self.assertEqual(classify_cents(1200.0)[:2], (0, 1))
        self.assertEqual(classify_cents(-100.0)[:2], (11, -1))
        swara, _, deviation = classify_cents(420.0)
        self.assertEqual(swara, 4)
        self.assertAlmostEqual(deviation, 20.0, places=6)


class SwaraSegmentationTests(unittest.TestCase):
    def test_a_sung_phrase_comes_back_as_the_right_sargam(self):
        audio = sing([0, 2, 4, 7, 9, 7, 4, 2, 0])
        track = track_pitch(audio + tanpura(len(audio)), SR)
        line = sargam_line(segment_notes(track, SA))
        self.assertEqual(line, "S R G P D P G R S")

    def test_komal_and_teevra_swaras_are_named(self):
        audio = sing([0, 1, 3, 6, 8, 10])            # r g M d n
        track = track_pitch(audio, SR)
        self.assertEqual(sargam_line(segment_notes(track, SA)), "S r g M d n")

    def test_octave_registers_are_marked(self):
        audio = sing([-12, 0, 12])
        track = track_pitch(audio, SR)
        self.assertEqual(sargam_line(segment_notes(track, SA)), ".S S S'")

    def test_swara_weights_total_the_sung_time(self):
        audio = sing([0, 4, 7], note_s=0.5)
        notes = segment_notes(track_pitch(audio, SR), SA)
        weights = swara_weights(notes)
        self.assertEqual(set(weights), {0, 4, 7})
        self.assertAlmostEqual(sum(weights.values()), 1.5, delta=0.3)


class SungVersusSpokenTests(unittest.TestCase):
    def test_singing_and_talking_are_separated(self):
        rng = np.random.default_rng(3)
        parts = [speak(6.0, rng), sing([0, 2, 4, 6, 7, 4, 2, 0]),
                 speak(5.0, rng), sing([7, 9, 11, 12, 11, 9, 7])]
        audio = np.concatenate(parts)
        audio = audio + tanpura(len(audio))
        boundaries = np.cumsum([0] + [len(p) / SR for p in parts])

        track = track_pitch(audio, SR)
        notes = segment_notes(track, SA)
        regions = classify_regions(track, notes, SA)

        kinds = [r.kind for r in regions]
        self.assertEqual(kinds, [SPOKEN, SUNG, SPOKEN, SUNG])
        for region, expected_start in zip(regions, boundaries):
            self.assertAlmostEqual(region.start, expected_start, delta=0.6)

    def test_pure_speech_yields_no_demonstrations(self):
        rng = np.random.default_rng(11)
        audio = speak(12.0, rng)
        track = track_pitch(audio, SR)
        regions = classify_regions(track, segment_notes(track, SA), SA)
        self.assertNotIn(SUNG, [r.kind for r in regions])


class ScaleIdentificationTests(unittest.TestCase):
    def test_pentatonic_set_is_named_exactly(self):
        weights = {0: 12.0, 2: 6.0, 4: 8.0, 7: 9.0, 9: 5.0}   # S R G P D
        guess = raga.identify_scale(weights)
        self.assertIn("Bhupali", guess.exact_ragas)

    def test_kalyan_thaat_is_recognized_with_candidates(self):
        weights = {0: 10.0, 2: 5.0, 4: 6.0, 6: 4.0, 7: 8.0, 9: 3.0, 11: 4.0}
        guess = raga.identify_scale(weights)
        self.assertEqual(guess.thaat, "Kalyan")
        self.assertIn("Yaman", guess.thaat_ragas)

    def test_too_little_singing_makes_no_claim(self):
        guess = raga.identify_scale({0: 2.0, 4: 1.0})
        self.assertIsNone(guess.thaat)
        self.assertEqual(guess.exact_ragas, ())
        self.assertIn("not enough", guess.summary())

    def test_thaat_lookup_is_case_insensitive(self):
        self.assertEqual(raga.thaat_of_raga("yaman"), "Kalyan")
        self.assertEqual(raga.thaat_of_raga("Darbari Kanada"), "Asavari")


class VocabularyTests(unittest.TestCase):
    def test_known_mishearings_are_repaired(self):
        fixed, corrections = lexicon.correct_text(
            "Aaj hum raga man karenge, tea total mein, vilambit ek tal se."
        )
        self.assertIn("Raag Yaman", fixed)
        self.assertIn("teentaal", fixed)
        self.assertIn("ektaal", fixed)
        self.assertTrue(all(c.kind for c in corrections))

    def test_ordinary_english_is_left_alone(self):
        text = "The song was sung in a band, and I don't mind the sound."
        fixed, corrections = lexicon.correct_text(text)
        self.assertEqual(fixed, text)
        self.assertEqual(corrections, [])

    def test_ambiguous_words_are_repaired_only_in_musical_context(self):
        fixed, _ = lexicon.correct_text("Take the meend and hold the sum.")
        self.assertIn("sam", fixed)
        self.assertNotIn("sum", fixed)

    def test_a_run_of_solfege_is_normalized_but_a_single_word_is_not(self):
        fixed, _ = lexicon.correct_text("So ray gah ma pa, samajhe?")
        self.assertIn("Sa Re Ga Ma Pa", fixed)

        text = "So, what did you think of the song?"
        self.assertEqual(lexicon.correct_text(text)[0], text)

    def test_mentions_pick_up_ragas_talas_and_terms(self):
        found = lexicon.find_mentions(
            "Aaj Raag Yaman, teentaal mein, alaap se shuru karte hain."
        )
        self.assertEqual(found["ragas"], ["Yaman"])
        self.assertEqual(found["talas"], ["Teentaal"])
        self.assertIn("alaap", found["terms"])

    def test_longer_raga_names_subsume_shorter_ones(self):
        found = lexicon.find_mentions("today we sing Yaman Kalyan")
        self.assertEqual(found["ragas"], ["Yaman Kalyan"])

    def test_whisper_prompt_carries_the_domain_and_the_extras(self):
        prompt = lexicon.whisper_prompt(["Bageshri", "Panditji"])
        self.assertIn("bandish", prompt)
        self.assertIn("Panditji", prompt)

    def test_glosses_exist_for_the_core_terms(self):
        for term in ("meend", "bandish", "sam", "taan", "alaap"):
            self.assertTrue(lexicon.gloss_for(term))


class TransliterationTests(unittest.TestCase):
    def test_common_music_words_romanize_the_way_people_write_them(self):
        expected = {
            "राग": "raag",
            "सरगम": "sargam",
            "बंदिश": "bandish",
            "मींड": "meend",
            "तीनताल": "teentaal",
            "गमक": "gamak",
            "कोमल": "komal",
            "विलंबित": "vilambit",
            "संगीत": "sangeet",
            "ज्ञान": "gyaan",
            "शुद्ध": "shuddh",
        }
        for devanagari, roman in expected.items():
            with self.subTest(word=devanagari):
                self.assertEqual(translit.romanize(devanagari), roman)

    def test_latin_text_passes_through_untouched(self):
        text = "sing the bandish in teentaal"
        self.assertEqual(translit.romanize(text), text)

    def test_mixed_script_keeps_the_latin_and_converts_the_rest(self):
        out = translit.romanize("Aaj हम Yaman करेंगे")
        self.assertIn("Aaj", out)
        self.assertIn("Yaman", out)
        self.assertIn("ham", out)

    def test_script_ratio_detects_code_switching(self):
        self.assertEqual(translit.devanagari_ratio("sing the bandish"), 0.0)
        self.assertEqual(translit.devanagari_ratio("राग यमन"), 1.0)
        self.assertTrue(0.1 < translit.devanagari_ratio("आज we sing") < 0.9)


class RenderingTests(unittest.TestCase):
    """The renderers run without any ML dependency, on a hand-built result."""

    def _result(self):
        from music_lesson.core import (
            ATTEMPT, DEMONSTRATION, INSTRUCTION, LessonResult, LessonSegment,
        )
        from music_lesson.swara import Note, TonicEstimate

        notes = [
            Note(10.0, 10.8, 0, 0, 0.0, 0.0, 0.9),
            Note(10.8, 11.6, 4, 0, 375.0, -25.0, 0.9),
            Note(11.6, 12.5, 7, 0, 700.0, 0.0, 0.9),
        ]
        segments = [
            LessonSegment(
                0.0, 4.0, INSTRUCTION, "Guru",
                text="Aaj Raag Yaman, alaap se shuru karte hain.",
                language="hi-roman",
            ),
            LessonSegment(10.0, 12.5, DEMONSTRATION, "Guru",
                          sargam="S G P", notes=notes),
            LessonSegment(13.0, 15.0, ATTEMPT, "Student", sargam="S G P"),
        ]
        return LessonResult(
            segments=segments,
            tonic=TonicEstimate(146.83, 0.8, "D3 (+0c)"),
            scale=raga.identify_scale({0: 12.0, 2: 6.0, 4: 8.0, 6: 5.0,
                                       7: 9.0, 9: 4.0, 11: 4.0}),
            regions=[],
            mentions=lexicon.find_mentions(segments[0].text),
            speakers=["Guru", "Student"],
            language="hi",
            source="/tmp/lesson.m4a",
            timings={"total": 12.0},
        )

    def test_every_format_renders(self):
        from music_lesson.output import render

        result = self._result()
        for fmt in ("txt", "json", "srt", "md"):
            with self.subTest(fmt=fmt):
                self.assertTrue(render(result, fmt).strip())
        with self.assertRaises(ValueError):
            render(result, "docx")

    def test_practice_sheet_leads_with_what_you_practise(self):
        from music_lesson.output import to_practice_sheet

        sheet = to_practice_sheet(self._result())
        self.assertIn("Sa (tonic)", sheet)
        self.assertIn("D3", sheet)
        self.assertIn("Demonstrations to copy", sheet)
        self.assertIn("S G P", sheet)
        self.assertIn("Call and response", sheet)      # demo followed by attempt
        self.assertIn("Yaman", sheet)                  # named out loud
        self.assertIn("alaap", sheet)                  # glossary

    def test_practice_sheet_flags_notes_held_off_equal_temperament(self):
        from music_lesson.output import to_practice_sheet

        sheet = to_practice_sheet(self._result())
        self.assertIn("-25c", sheet)                   # the flat Ga

    def test_json_round_trips(self):
        import json

        from music_lesson.output import to_json

        data = json.loads(to_json(self._result()))
        self.assertEqual(data["tonic"]["hz"], 146.83)
        self.assertEqual(len(data["segments"]), 3)
        self.assertEqual(data["segments"][1]["sargam"], "S G P")



class PipelineIntegrationTests(unittest.TestCase):
    """The whole of :func:`transcribe_lesson` with only the ML stages stubbed.

    Whisper and the diarizer are the two pieces that need a model download, so
    they are replaced by fixtures. Everything else — pitch, tonic, notes,
    region labelling, segment assembly, role assignment, vocabulary repair,
    romanization, scale identification, rendering — runs for real against
    synthesized audio built from a known phrase.
    """

    def _audio(self):
        rng = np.random.default_rng(5)
        parts = [
            speak(5.0, rng),                       # guru explains
            sing([0, 2, 4, 7, 9, 7, 4, 2, 0]),     # guru demonstrates
            speak(3.0, rng),                       # guru corrects
            sing([0, 2, 4, 7, 9, 7, 4, 2, 0]),     # student copies
        ]
        audio = np.concatenate(parts)
        return audio + tanpura(len(audio)), np.cumsum([0.0] + [len(p) / SR for p in parts])

    def _run(self, **kwargs):
        from unittest import mock

        from music_lesson import core
        from music_lesson.transcribe import SpeechResult, SpeechSegment
        from transcriber.diarize import Turn

        audio, bounds = self._audio()

        speech = [
            SpeechSegment(0.4, 4.6, "Aaj hum raga man karenge, alap se shuru.",
                          language="hi"),
            SpeechSegment(bounds[2] + 0.2, bounds[3] - 0.2,
                          "Ab tum gao, the meend from ga to pa.", language="en"),
        ]
        turns = [
            Turn(0.0, bounds[3], "Speaker 1"),
            Turn(bounds[3], bounds[4], "Speaker 2"),
        ]

        with mock.patch.object(core._audio, "extract_audio", return_value="/tmp/none.wav"), \
             mock.patch.object(core._audio, "load_waveform", return_value=(audio, SR)), \
             mock.patch.object(core, "_run_whisper", return_value=SpeechResult(
                 speech, "hi", speech_seconds=8.0, clips=2, dropped_options=[])), \
             mock.patch.object(core, "_run_diarization", return_value=turns):
            return core.transcribe_lesson("/tmp/lesson.m4a", **kwargs)

    def test_lesson_is_assembled_in_order_with_both_kinds_of_segment(self):
        from music_lesson.core import ATTEMPT, DEMONSTRATION, INSTRUCTION

        result = self._run(tonic=SA)

        kinds = [s.kind for s in result.segments]
        self.assertEqual(kinds, [INSTRUCTION, DEMONSTRATION, INSTRUCTION, ATTEMPT])
        starts = [s.start for s in result.segments]
        self.assertEqual(starts, sorted(starts))

    def test_the_guru_is_the_one_who_explains_and_the_copy_is_an_attempt(self):
        from music_lesson.core import ATTEMPT, GURU, STUDENT

        result = self._run(tonic=SA)

        self.assertEqual(result.segments[0].speaker, GURU)
        self.assertEqual(result.segments[-1].speaker, STUDENT)
        self.assertEqual(result.segments[-1].kind, ATTEMPT)

    def test_singing_becomes_sargam_and_never_becomes_words(self):
        result = self._run(tonic=SA)
        demo = result.segments[1]
        self.assertEqual(demo.sargam, "S R G P D P G R S")
        self.assertEqual(demo.text, "")

    def test_vocabulary_is_repaired_and_mentions_are_collected(self):
        result = self._run(tonic=SA)
        self.assertIn("Raag Yaman", result.segments[0].text)
        self.assertIn("alaap", result.segments[0].text)
        self.assertEqual(result.mentions["ragas"], ["Yaman"])

    def test_the_scale_is_read_off_the_singing(self):
        result = self._run(tonic=SA)
        self.assertIn("Bhupali", result.scale.exact_ragas)   # S R G P D

    def test_a_supplied_tonic_is_trusted_and_a_missing_one_is_detected(self):
        supplied = self._run(tonic=SA)
        self.assertAlmostEqual(supplied.tonic.hz, SA, places=2)
        self.assertEqual(supplied.tonic.confidence, 1.0)

        detected = self._run()
        cents = abs(float(hz_to_cents(detected.tonic.hz, SA))) % 1200
        self.assertLess(min(cents, 1200 - cents), 25.0)

    def test_the_practice_sheet_reads_like_a_lesson(self):
        from music_lesson.output import to_practice_sheet

        sheet = to_practice_sheet(self._run(tonic=SA))
        self.assertIn("Yaman", sheet)
        self.assertIn("S R G P D P G R S", sheet)
        self.assertIn("Call and response", sheet)

    def test_timings_are_recorded_for_every_stage(self):
        result = self._run(tonic=SA)
        for stage in ("extract", "pitch", "tonic", "notes", "transcribe", "total"):
            self.assertIn(stage, result.timings)




class DecodingCostTests(unittest.TestCase):
    """Whisper pads every clip to a 30s window, so clip count is the cost."""

    def _regions(self, spec):
        from music_lesson.segmentation import Region

        return [Region(start, end, kind) for start, end, kind in spec]

    def test_short_sung_interjections_are_decoded_through(self):
        from music_lesson.segmentation import speech_spans

        # talk, 4s demo, talk: one clip, not two — the gap is cheaper to
        # decode than to pay a second encoder pass for.
        spans = speech_spans(self._regions([
            (0.0, 20.0, SPOKEN), (20.0, 24.0, SUNG), (24.0, 40.0, SPOKEN),
        ]))
        self.assertEqual(len(spans), 1)
        self.assertAlmostEqual(spans[0][0], 0.0)
        self.assertAlmostEqual(spans[0][1], 40.25)

    def test_long_sung_stretches_still_split_the_clips(self):
        from music_lesson.segmentation import speech_spans

        spans = speech_spans(self._regions([
            (0.0, 20.0, SPOKEN), (20.0, 140.0, SUNG), (140.0, 160.0, SPOKEN),
        ]))
        self.assertEqual(len(spans), 2)
        self.assertLess(spans[0][1], 25.0)
        self.assertGreater(spans[1][0], 135.0)

    def test_slivers_too_short_to_hold_a_phrase_are_dropped(self):
        from music_lesson.segmentation import speech_spans

        spans = speech_spans(
            self._regions([(0.0, 0.2, SPOKEN), (0.2, 200.0, SUNG)]), pad=0.0
        )
        self.assertEqual(spans, [])

    def test_progress_tracks_decoded_audio_not_wall_clock(self):
        from music_lesson.transcribe import _speech_elapsed

        clips = [(0.0, 10.0), (100.0, 110.0)]
        self.assertAlmostEqual(_speech_elapsed(5.0, clips), 5.0)
        # Halfway through the second clip is 15s decoded, not 105s.
        self.assertAlmostEqual(_speech_elapsed(105.0, clips), 15.0)
        self.assertAlmostEqual(_speech_elapsed(50.0, clips), 10.0)
        self.assertAlmostEqual(_speech_elapsed(50.0, None), 50.0)

    def test_a_faster_whisper_too_old_to_skip_singing_says_so(self):
        from music_lesson.core import _transcription_notices
        from music_lesson.transcribe import SpeechResult

        quiet = _transcription_notices(
            SpeechResult([], "hi", 60.0, 3, dropped_options=[])
        )
        self.assertEqual(quiet, [])

        loud = _transcription_notices(
            SpeechResult([], "hi", 60.0, 1, dropped_options=["clip_timestamps"])
        )
        self.assertEqual(len(loud), 1)
        self.assertIn("pip install -U faster-whisper", loud[0])




class RuntimeGuardTests(unittest.TestCase):
    """The macOS duplicate-OpenMP escape hatch (see music_lesson/runtime.py)."""

    def _call(self, platform, env):
        from unittest import mock

        from music_lesson import runtime

        with mock.patch.object(runtime.sys, "platform", platform), \
             mock.patch.object(runtime.os, "environ", env), \
             mock.patch.object(runtime, "_applied", False):
            runtime.ensure_single_openmp()
            return env, runtime.openmp_workaround_applied()

    def test_on_macos_the_escape_hatch_is_set(self):
        env, applied = self._call("darwin", {})
        self.assertEqual(env.get("KMP_DUPLICATE_LIB_OK"), "TRUE")
        self.assertTrue(applied)

    def test_an_explicit_user_setting_is_never_overwritten(self):
        env, applied = self._call("darwin", {"KMP_DUPLICATE_LIB_OK": "FALSE"})
        self.assertEqual(env["KMP_DUPLICATE_LIB_OK"], "FALSE")
        self.assertFalse(applied)

    def test_other_platforms_are_left_alone(self):
        env, applied = self._call("linux", {})
        self.assertNotIn("KMP_DUPLICATE_LIB_OK", env)
        self.assertFalse(applied)



if __name__ == "__main__":
    unittest.main(verbosity=2)
