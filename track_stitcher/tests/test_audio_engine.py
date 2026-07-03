"""Engine tests: analysis, stretching (pitch preservation), crossfade
anchoring, loudness, and the full render pipeline. Run with:  pytest tests/
"""

import math
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audio_engine as engine

SR = 48000


def pulsed_tone(bpm: float, seconds: float, freq: float = 440.0, sr: int = SR,
                fade_tail: float = 0.0) -> np.ndarray:
    """A sine carrier with a percussive amplitude pulse on every beat, so
    librosa can detect the tempo. Optionally decays to silence at the end."""
    n = int(seconds * sr)
    t = np.arange(n) / sr
    carrier = np.sin(2 * np.pi * freq * t)
    beat_period = 60.0 / bpm
    phase = (t % beat_period) / beat_period
    env = 0.15 + 0.85 * np.exp(-phase * 12.0)  # sharp attack, quick decay
    y = 0.5 * carrier * env
    if fade_tail > 0:
        k = int(fade_tail * sr)
        y[-k:] *= np.linspace(1.0, 0.0, k) ** 2
    return y.astype(np.float32)


@pytest.fixture(scope="module")
def track_folder(tmp_path_factory):
    """Three stereo test tracks at different BPMs, one with BPM in filename,
    one mono, plus a non-audio file that must be ignored."""
    folder = tmp_path_factory.mktemp("tracks")
    y1 = pulsed_tone(72, 30, freq=330, fade_tail=10)
    sf.write(folder / "a_raga_72bpm.wav", np.stack([y1, y1], axis=1), SR)
    y2 = pulsed_tone(80, 30, freq=440, fade_tail=10)
    sf.write(folder / "b_middle.wav", np.stack([y2, y2], axis=1), SR)
    y3 = pulsed_tone(90, 30, freq=550, fade_tail=10)
    sf.write(folder / "c_mono.wav", y3, SR)  # mono on purpose
    (folder / "notes.txt").write_text("not audio")
    return folder


# ---------------------------------------------------------------------------
# Scanning & filename parsing
# ---------------------------------------------------------------------------

def test_scan_folder_filters_and_sorts(track_folder):
    files = engine.scan_folder(track_folder)
    assert [f.name for f in files] == ["a_raga_72bpm.wav", "b_middle.wav", "c_mono.wav"]


def test_scan_folder_includes_m4a(tmp_path):
    (tmp_path / "song.m4a").write_bytes(b"")
    (tmp_path / "notes.txt").write_text("not audio")
    assert [f.name for f in engine.scan_folder(tmp_path)] == ["song.m4a"]


def test_scan_folder_skips_own_rendered_mixes(tmp_path):
    (tmp_path / "track.wav").write_bytes(b"")
    (tmp_path / "stitched_mix_20260702.wav").write_bytes(b"")
    assert [f.name for f in engine.scan_folder(tmp_path)] == ["track.wav"]


def have_m4a_decoder() -> bool:
    """True if this machine can decode AAC: CoreAudio (macOS) or ffmpeg."""
    import platform
    return platform.system() == "Darwin" or shutil.which("ffmpeg") is not None


@pytest.mark.skipif(not have_m4a_decoder(), reason="no m4a decoder available")
def test_m4a_analyze_and_render(track_folder, tmp_path):
    # Build an m4a from one of the wav fixtures.
    m4a = track_folder / "delta_80bpm.m4a"
    if shutil.which("ffmpeg"):
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(track_folder / "b_middle.wav"),
             "-c:a", "aac", "-b:a", "192k", str(m4a)],
            check=True, capture_output=True,
        )
    else:  # macOS without ffmpeg: use the built-in encoder
        subprocess.run(
            ["afconvert", "-f", "m4af", "-d", "aac",
             str(track_folder / "b_middle.wav"), str(m4a)],
            check=True, capture_output=True,
        )
    try:
        info = engine.analyze_track(m4a)
        assert "error" not in info
        assert info["duration"] == pytest.approx(30.0, abs=0.3)
        assert info["filename_bpm"] == 80.0

        specs = make_specs(track_folder, ["a_raga_72bpm.wav"])
        specs.append({
            "path": str(m4a), "name": m4a.name, "bpm": 80.0,
            "rms_env": info["rms_env"], "rms_hop": info["rms_hop"],
            "rms_sr": info["rms_sr"],
        })
        result = engine.render_mix(specs, output_bpm=80.0, crossfade_seconds=8.0,
                                   output_path=tmp_path / "with_m4a.wav")
        assert (tmp_path / "with_m4a.wav").exists()
        assert result["duration"] > 40
    finally:
        m4a.unlink()


def test_scan_folder_invalid():
    with pytest.raises(NotADirectoryError):
        engine.scan_folder("/definitely/not/a/folder")


@pytest.mark.parametrize("name,expected", [
    ("raga_72bpm.wav", 72.0),
    ("song 72 bpm final.flac", 72.0),
    ("piece-115BPM.aiff", 115.0),
    ("track_98.5bpm.wav", 98.5),
    ("drone_72-bpm.wav", 72.0),
    ("no_tempo_here.wav", None),
    ("500bpm_out_of_range.wav", None),
    ("2024_recording.wav", None),
])
def test_parse_filename_bpm(name, expected):
    assert engine.parse_filename_bpm(name) == expected


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def test_analyze_track(track_folder):
    info = engine.analyze_track(track_folder / "b_middle.wav")
    assert "error" not in info
    assert info["duration"] == pytest.approx(30.0, abs=0.1)
    # librosa may report half/double time; accept the family.
    assert info["detected_bpm"] is not None
    assert min(abs(info["detected_bpm"] * m - 80) for m in (0.5, 1, 2)) < 3
    assert info["filename_bpm"] is None
    assert len(info["rms_env"]) > 100


def test_analyze_filename_override(track_folder):
    info = engine.analyze_track(track_folder / "a_raga_72bpm.wav")
    assert info["filename_bpm"] == 72.0


def test_analyze_unreadable(tmp_path):
    bad = tmp_path / "corrupt.wav"
    bad.write_bytes(b"RIFFgarbage")
    assert "error" in engine.analyze_track(bad)


# ---------------------------------------------------------------------------
# Stretching — pitch must be preserved
# ---------------------------------------------------------------------------

def dominant_freq(y: np.ndarray, sr: int) -> float:
    mono = y.mean(axis=1)
    seg = mono[len(mono) // 4: len(mono) // 4 + sr * 4]
    windowed = seg * np.hanning(len(seg))
    spectrum = np.abs(np.fft.rfft(windowed))
    return float(np.fft.rfftfreq(len(seg), 1 / sr)[int(np.argmax(spectrum))])


def test_stretch_preserves_pitch():
    t = np.arange(10 * SR) / SR
    sine = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    audio = np.stack([sine, sine], axis=1)
    stretched, applied = engine.stretch_track(audio, rate=1.15)
    assert applied
    assert len(stretched) == pytest.approx(len(audio) / 1.15, rel=0.02)
    assert dominant_freq(stretched, SR) == pytest.approx(440.0, abs=1.0)


def test_stretch_skipped_within_tolerance():
    audio = np.zeros((SR, 2), dtype=np.float32)
    out, applied = engine.stretch_track(audio, rate=1.004)
    assert not applied and out is audio


# ---------------------------------------------------------------------------
# Loudness
# ---------------------------------------------------------------------------

def test_normalize_track():
    rng = np.random.default_rng(0)
    audio = (rng.standard_normal((SR * 10, 2)) * 0.05).astype(np.float32)
    normalized, gain_db = engine.normalize_track(audio)
    lufs = pyln.Meter(SR).integrated_loudness(normalized.astype(np.float64))
    assert lufs == pytest.approx(engine.WORKING_LUFS, abs=0.2)
    assert gain_db != 0.0


def test_blockwise_loudness_matches_pyloudnorm():
    rng = np.random.default_rng(1)
    audio = (rng.standard_normal((SR * 20, 2)) * 0.08).astype(np.float32)
    audio[SR * 5: SR * 7] *= 0.001  # a quiet stretch to exercise gating
    reference = pyln.Meter(SR).integrated_loudness(audio.astype(np.float64))
    assert engine.integrated_loudness_blockwise(audio, SR) == pytest.approx(
        reference, abs=0.1
    )


def test_true_peak_on_full_scale_sine():
    t = np.arange(SR) / SR
    sine = np.sin(2 * np.pi * 997 * t).astype(np.float32)
    audio = np.stack([sine, sine], axis=1)
    assert engine.true_peak_dbtp(audio, SR) == pytest.approx(0.0, abs=0.1)


# ---------------------------------------------------------------------------
# Crossfade anchoring
# ---------------------------------------------------------------------------

def test_decay_onset_found_on_fading_track():
    # 60 s envelope at analysis frame rate: steady, then decaying final 20 s.
    frames_per_s = engine.ANALYSIS_SR / engine.RMS_HOP_LENGTH
    steady = np.full(int(40 * frames_per_s), 0.5)
    decay = np.linspace(0.5, 0.01, int(20 * frames_per_s))
    env = np.concatenate([steady, decay])
    onset = engine.find_decay_onset_seconds(env, engine.RMS_HOP_LENGTH, engine.ANALYSIS_SR)
    assert onset is not None
    assert 35 < onset < 45  # decay starts at t=40s, within the 45 s window


def test_no_decay_on_flat_track():
    frames_per_s = engine.ANALYSIS_SR / engine.RMS_HOP_LENGTH
    env = np.full(int(60 * frames_per_s), 0.5)
    assert engine.find_decay_onset_seconds(env, engine.RMS_HOP_LENGTH,
                                           engine.ANALYSIS_SR) is None


def test_equal_power_curves_sum_of_squares():
    out, fin = engine.equal_power_curves(1000)
    assert np.allclose(out ** 2 + fin ** 2, 1.0)


# ---------------------------------------------------------------------------
# Beat-phase alignment
# ---------------------------------------------------------------------------

def test_analysis_returns_beat_grid(track_folder):
    info = engine.analyze_track(track_folder / "b_middle.wav")
    beats = np.asarray(info["beats"])
    assert len(beats) > 20
    # Pulses are every 60/80 = 0.75 s; detected beats should tick at ~0.75 s.
    assert np.median(np.diff(beats)) == pytest.approx(0.75, abs=0.03)


def test_beat_aligned_anchor_snaps_to_grid():
    period = int(0.75 * SR)
    out_beats = np.arange(100, dtype=np.float64) * period          # beats at k*0.75s
    in_first = 0.37 * SR                                           # incoming pickup
    desired = 40 * SR                                              # decay wants 40 s
    anchor, shift = engine.beat_aligned_anchor(desired, out_beats, in_first, 0, 70 * SR)
    assert shift is not None
    # Incoming first beat lands exactly on an outgoing beat…
    assert (anchor + in_first) % period == pytest.approx(0, abs=1)
    # …and the anchor moved at most half a beat from the decay position.
    assert abs(anchor - desired) <= period / 2 + 1


def test_beat_aligned_anchor_respects_bounds_and_fallback():
    out_beats = np.array([10.0 * SR])
    # No aligned position inside [lo, hi] -> unchanged, no shift reported.
    anchor, shift = engine.beat_aligned_anchor(5 * SR, out_beats, 0.0, 0, 2 * SR)
    assert (anchor, shift) == (5 * SR, None)
    # Missing grids -> unchanged.
    assert engine.beat_aligned_anchor(5, np.array([]), 1.0, 0, 10) == (5, None)
    assert engine.beat_aligned_anchor(5, out_beats, None, 0, 10) == (5, None)


def test_crossfade_lands_on_the_beat(tmp_path):
    """The make-or-break property: after a crossfade between two tracks at the
    same BPM, every audible pulse in the mix stays on one 0.75 s beat grid —
    even when the incoming track's first beat is offset from a bar boundary."""
    folder = tmp_path / "beats"
    folder.mkdir()
    a = pulsed_tone(80, 30, freq=330, fade_tail=8)
    sf.write(folder / "a.wav", np.stack([a, a], axis=1), SR)
    # b's pulses start 0.37 s in — deliberately off-grid vs. a naive anchor.
    pad = np.zeros(int(0.37 * SR), dtype=np.float32)
    b = np.concatenate([pad, pulsed_tone(80, 30, freq=550)])
    sf.write(folder / "b.wav", np.stack([b, b], axis=1), SR)

    specs = []
    for name in ["a.wav", "b.wav"]:
        info = engine.analyze_track(folder / name)
        specs.append({
            "path": str(folder / name), "name": name, "bpm": 80.0,
            "rms_env": info["rms_env"], "rms_hop": info["rms_hop"],
            "rms_sr": info["rms_sr"], "beats": info["beats"],
        })
    result = engine.render_mix(specs, output_bpm=80.0, crossfade_seconds=6.0,
                               output_path=tmp_path / "beat_mix.wav")
    assert "beat-aligned" in "\n".join(result["log"])

    import librosa
    mix, _ = sf.read(str(tmp_path / "beat_mix.wav"))
    onsets = librosa.onset.onset_detect(y=mix.mean(axis=1).astype(np.float32),
                                        sr=SR, units="time", backtrack=False)
    period = 60.0 / 80.0
    # Every onset-to-onset gap must sit on the beat grid (within 40 ms) —
    # a misaligned overlap would produce split intervals like 0.37/0.38 s.
    gaps = np.diff(onsets)
    offsets = np.minimum(gaps % period, period - gaps % period)
    assert float(np.max(offsets)) < 0.04, f"off-grid onset gaps: {gaps[offsets >= 0.04]}"


# ---------------------------------------------------------------------------
# Full render pipeline
# ---------------------------------------------------------------------------

def make_specs(track_folder, order):
    specs = []
    for name in order:
        path = track_folder / name
        info = engine.analyze_track(path)
        bpm = info["filename_bpm"] or {"b_middle.wav": 80.0, "c_mono.wav": 90.0}[name]
        specs.append({
            "path": str(path), "name": name, "bpm": bpm,
            "rms_env": info["rms_env"], "rms_hop": info["rms_hop"],
            "rms_sr": info["rms_sr"], "beats": info["beats"],
        })
    return specs


def test_render_mix_end_to_end(track_folder, tmp_path):
    specs = make_specs(track_folder, ["a_raga_72bpm.wav", "b_middle.wav", "c_mono.wav"])
    out = tmp_path / "mix.wav"
    progress_msgs = []
    result = engine.render_mix(
        specs, output_bpm=80.0, crossfade_seconds=8.0, output_path=out,
        progress=lambda frac, msg: progress_msgs.append((frac, msg)),
    )

    assert out.exists()
    info = sf.info(str(out))
    assert info.samplerate == SR and info.channels == 2 and info.subtype == "PCM_24"

    # Duration: stretched lengths minus two 8 s overlaps, minus any trimmed
    # decay tails (each tail trim is bounded by the 45 s search window).
    stretched = [30 * 80 / 72, 30.0, 30 * 80 / 90]
    upper = sum(stretched) - 2 * 8.0 + 0.1
    lower = upper - 2 * 45.0
    assert lower < result["duration"] < upper
    assert info.duration == pytest.approx(result["duration"], abs=0.01)

    # Mastering targets: ~-14 LUFS integrated unless the peak ceiling forced
    # the level down; true peak always at or under -1 dBTP.
    audio, _ = sf.read(str(out))
    measured = pyln.Meter(SR).integrated_loudness(audio)
    assert result["true_peak_dbtp"] <= engine.TRUE_PEAK_CEILING_DBTP + 0.05
    if result["true_peak_dbtp"] < engine.TRUE_PEAK_CEILING_DBTP - 0.05:
        assert measured == pytest.approx(engine.TARGET_LUFS, abs=0.3)

    # Render log covers stretch, gain, and fade anchors; progress advanced.
    log = "\n".join(result["log"])
    assert "stretched" in log and "gain" in log and "fade anchored" in log
    assert progress_msgs[-1][0] == 1.0


def test_render_order_is_respected(track_folder, tmp_path):
    order = ["c_mono.wav", "a_raga_72bpm.wav", "b_middle.wav"]
    result = engine.render_mix(
        make_specs(track_folder, order), output_bpm=80.0,
        crossfade_seconds=8.0, output_path=tmp_path / "reordered.wav",
    )
    positions = [next(i for i, line in enumerate(result["log"]) if name in line)
                 for name in order]
    assert positions == sorted(positions)


def test_render_single_track_skips_crossfade(track_folder, tmp_path):
    result = engine.render_mix(
        make_specs(track_folder, ["b_middle.wav"]), output_bpm=80.0,
        crossfade_seconds=20.0, output_path=tmp_path / "single.wav",
    )
    assert "fade" not in "\n".join(result["log"]).lower()
    assert result["duration"] == pytest.approx(30.0, abs=0.5)


def test_short_track_shortens_crossfade(track_folder, tmp_path):
    short = pulsed_tone(80, 12, freq=660)
    sf.write(track_folder / "short.wav", np.stack([short, short], axis=1), SR)
    try:
        specs = make_specs(track_folder, ["b_middle.wav"])
        info = engine.analyze_track(track_folder / "short.wav")
        specs.append({
            "path": str(track_folder / "short.wav"), "name": "short.wav",
            "bpm": 80.0, "rms_env": info["rms_env"], "rms_hop": info["rms_hop"],
            "rms_sr": info["rms_sr"],
        })
        result = engine.render_mix(specs, output_bpm=80.0, crossfade_seconds=20.0,
                                   output_path=tmp_path / "short_mix.wav")
        log = "\n".join(result["log"])
        assert "crossfade shortened" in log
        assert f"{0.4 * 12:.1f} s" in log  # 40% of the shorter track
    finally:
        (track_folder / "short.wav").unlink()


def test_render_error_names_track_and_stage(track_folder, tmp_path):
    specs = make_specs(track_folder, ["b_middle.wav"])
    specs[0]["path"] = str(track_folder / "gone.wav")
    with pytest.raises(engine.RenderError) as exc_info:
        engine.render_mix(specs, output_bpm=80.0, crossfade_seconds=8.0,
                          output_path=tmp_path / "err.wav")
    assert exc_info.value.stage == "load"
    assert exc_info.value.track_name == "b_middle.wav"


# ---------------------------------------------------------------------------
# Transition preview & manual anchor offsets
# ---------------------------------------------------------------------------

def full_specs(track_folder, names, bpms):
    specs = []
    for name, bpm in zip(names, bpms):
        path = track_folder / name
        info = engine.analyze_track(path)
        specs.append({"path": str(path), "name": name, "bpm": bpm, **info})
    return specs


def test_transition_preview_matches_render_anchor(track_folder):
    out_spec, in_spec = full_specs(
        track_folder, ["b_middle.wav", "c_mono.wav"], [80.0, 90.0])
    pv = engine.render_transition_preview(out_spec, in_spec, output_bpm=80.0,
                                          fade_seconds=8.0)
    assert pv["audio"].ndim == 2 and pv["audio"].shape[1] == 2
    # ~10 s context + 8 s fade + ~10 s incoming tail
    assert pv["audio"].shape[0] / SR == pytest.approx(28.0, abs=2.0)
    assert pv["fade_seconds"] == pytest.approx(8.0, abs=0.01)
    assert pv["fade_start"] == pytest.approx(10.0, abs=1.0)
    assert len(pv["out_env"]) > 0 and len(pv["in_env"]) > 0
    # Display envelopes are post-fade: the outgoing tail tapers to ~silence
    # and the incoming head starts near silence (equal-power crossfade).
    assert pv["out_env"][-1] < 0.05 * np.max(pv["out_env"])
    assert pv["in_env"][0] < 0.05 * np.max(pv["in_env"])
    # Beat ticks land on the preview timeline: outgoing within its panel,
    # incoming starting at fade_start.
    assert len(pv["out_beats"]) > 0 and len(pv["in_beats"]) > 0
    assert 0 <= pv["out_beats"].min() and pv["out_beats"].max() <= pv["fade_start"] + pv["fade_seconds"] + 0.1
    assert pv["in_beats"].min() >= pv["fade_start"]
    # The same anchor logic drives the full render (shared helper), and the
    # anchor sits inside the stretched outgoing track.
    assert 0 <= pv["anchor_seconds"] <= 30.0
    assert "beat-aligned" in pv["note"]


def test_transition_preview_manual_nudge_shifts_anchor(track_folder):
    out_spec, in_spec = full_specs(
        track_folder, ["b_middle.wav", "c_mono.wav"], [80.0, 90.0])
    base = engine.render_transition_preview(out_spec, in_spec, 80.0, 8.0)
    nudged = engine.render_transition_preview(out_spec, in_spec, 80.0, 8.0,
                                              manual_offset_s=-1.5)
    assert nudged["anchor_seconds"] == pytest.approx(
        base["anchor_seconds"] - 1.5, abs=0.02)
    assert "manual nudge -1.50 s" in nudged["note"]


def test_render_mix_applies_anchor_offsets(track_folder, tmp_path):
    specs = make_specs(track_folder, ["b_middle.wav", "c_mono.wav"])
    base = engine.render_mix(specs, output_bpm=80.0, crossfade_seconds=8.0,
                             output_path=tmp_path / "base.wav")
    nudged = engine.render_mix(specs, output_bpm=80.0, crossfade_seconds=8.0,
                               output_path=tmp_path / "nudged.wav",
                               anchor_offsets=[-2.0])
    assert "manual nudge -2.00 s" in "\n".join(nudged["log"])
    # Fade starts 2 s earlier -> 2 s more of the outgoing tail is trimmed.
    assert nudged["duration"] == pytest.approx(base["duration"] - 2.0, abs=0.1)


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def test_fold_bpm_to_reference():
    assert engine.fold_bpm_to_reference(36.0, 72) == (72.0, 2.0)     # half-time
    assert engine.fold_bpm_to_reference(144.0, 72) == (72.0, 0.5)    # double-time
    assert engine.fold_bpm_to_reference(160.5, 80) == (80.2, 0.5)
    assert engine.fold_bpm_to_reference(75.0, 72) == (75.0, 1.0)     # close enough
    assert engine.fold_bpm_to_reference(89.1, 80) == (89.1, 1.0)
    assert engine.fold_bpm_to_reference(None, 72) == (None, 1.0)
    assert engine.fold_bpm_to_reference(80.0, None) == (80.0, 1.0)


def test_suggest_output_bpm():
    assert engine.suggest_output_bpm([72.0, 80.0, 90.0]) == 80
    assert engine.suggest_output_bpm([72.0, None, 90.0]) == 81
    assert engine.suggest_output_bpm([None]) is None


def test_format_duration():
    assert engine.format_duration(0) == "0:00"
    assert engine.format_duration(75.4) == "1:15"
    assert engine.format_duration(600) == "10:00"
