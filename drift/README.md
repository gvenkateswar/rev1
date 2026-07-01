# Drift

A small JUCE synth plugin (AU + VST3): four voices that never quite sit still.

## Signal path

Each of the **4 polyphonic voices** is:

```
triangle oscillator ──► one-pole lowpass ──► AD envelope
        ▲
        │ pitch, ±0–15 cents
  slow random drift LFO (per voice)
```

Every voice owns its own drift LFO — a smoothed random walk with a randomised
rate (0.07–0.3 Hz) and an independent random seed, so chords shimmer instead of
chorusing in lockstep. Note-off is ignored musically (AD, percussive); voices
end when the decay reaches silence, or immediately when stolen.

## Parameters

| Parameter | Range | What it does |
|-----------|-------|--------------|
| **Drift** | 0–15 cents | Depth of the per-voice random pitch drift |
| **Warmth** | 0–1 | One-pole lowpass: 0 = open (~18 kHz), 1 = dark (~500 Hz) |
| **Decay** | 0.05–8 s | Decay time of the AD envelope (time to −60 dB) |

## Building

Requires CMake ≥ 3.22 and a C++17 compiler. A local `JUCE/` checkout is used
if present, otherwise JUCE 8.0.8 is fetched automatically via CMake
FetchContent. Any JUCE ≥ 7 works (CI-tested against 7.0.5 from the Ubuntu
`juce` source package).

```sh
cd drift
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
```

- **VST3** (all platforms): `build/Drift_artefacts/Release/VST3/Drift.vst3`
- **AU** (macOS only): `build/Drift_artefacts/Release/AU/Drift.component`

On Linux the usual JUCE dev packages are needed
(`libasound2-dev libfreetype-dev libx11-dev libxrandr-dev libxinerama-dev
libxcursor-dev libxext-dev libcurl4-openssl-dev`).

## VST3 smoke test (Linux/anywhere)

A dependency-free mini-host that loads the built VST3, checks the plugin
name, the three parameters and the bus layout, then renders two seconds of
audio from a note-on and asserts it is non-silent, finite, and decays:

```sh
cd drift
g++ -std=c++17 -O1 -o build/vst3_smoke_test tests/vst3_smoke_test.cpp \
    -I JUCE/modules/juce_audio_processors/format_types/VST3_SDK -ldl
./build/vst3_smoke_test build/Drift_artefacts/Release/VST3/Drift.vst3/Contents/x86_64-linux/Drift.so
```

## AU validation (macOS)

```sh
cd drift
./scripts/validate_au.sh
```

This builds the AU, installs it to `~/Library/Audio/Plug-Ins/Components`, and
runs `auval -strict -v aumu Drft Drfa`. Expected result:

```
AU VALIDATION SUCCEEDED.
```
