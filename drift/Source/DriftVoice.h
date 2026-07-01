#pragma once

#include <juce_audio_utils/juce_audio_utils.h>

//==============================================================================
/** The one sound type Drift produces; any MIDI note/channel plays it. */
struct DriftSound : public juce::SynthesiserSound
{
    bool appliesToNote (int) override    { return true; }
    bool appliesToChannel (int) override { return true; }
};

//==============================================================================
/** Slow random pitch-drift LFO.

    Glides smoothly (smoothstep) between random targets at a slow rate that is
    itself randomised per voice, so the four voices never drift in lockstep.
    Output is in [-1, 1] and is scaled to cents by the caller.
*/
class DriftLfo
{
public:
    void prepare (double sampleRate, juce::Random& rng)
    {
        rate = 0.07 + rng.nextDouble() * 0.23;     // 0.07 - 0.3 Hz
        phaseInc = rate / sampleRate;
        current = rng.nextFloat() * 2.0f - 1.0f;
        target  = rng.nextFloat() * 2.0f - 1.0f;
        phase = 0.0;
    }

    float getNextSample (juce::Random& rng)
    {
        phase += phaseInc;
        if (phase >= 1.0)
        {
            phase -= 1.0;
            current = target;
            target = rng.nextFloat() * 2.0f - 1.0f;
        }

        auto t = (float) phase;
        auto s = t * t * (3.0f - 2.0f * t);        // smoothstep
        return current + (target - current) * s;
    }

private:
    double rate = 0.15, phase = 0.0, phaseInc = 0.0;
    float current = 0.0f, target = 0.0f;
};

//==============================================================================
/** One synth voice: triangle oscillator -> one-pole lowpass -> AD envelope,
    with the drift LFO modulating oscillator pitch by up to +/-15 cents.
*/
class DriftVoice : public juce::SynthesiserVoice
{
public:
    explicit DriftVoice (juce::int64 seed) : rng (seed) {}

    bool canPlaySound (juce::SynthesiserSound* sound) override
    {
        return dynamic_cast<DriftSound*> (sound) != nullptr;
    }

    void setCurrentPlaybackSampleRate (double newRate) override
    {
        juce::SynthesiserVoice::setCurrentPlaybackSampleRate (newRate);

        if (newRate > 0.0)
            lfo.prepare (newRate, rng);
    }

    /** Called by the processor once per block with the current parameter values. */
    void setParameters (float driftCents, float cutoffHz, float decaySeconds)
    {
        driftDepthCents = driftCents;

        auto sr = getSampleRate();
        if (sr <= 0.0)
            return;

        filterCoeff = 1.0f - std::exp ((float) (-juce::MathConstants<double>::twoPi
                                                * cutoffHz / sr));

        // Time for the exponential decay to fall to -60 dB.
        decayMult = (float) std::pow (0.001, 1.0 / (juce::jmax (0.001f, decaySeconds) * sr));
    }

    void startNote (int midiNoteNumber, float velocity,
                    juce::SynthesiserSound*, int) override
    {
        baseFrequency = juce::MidiMessage::getMidiNoteInHertz (midiNoteNumber);
        level = velocity * 0.35f;

        phase = 0.0;
        envValue = 0.0f;
        envStage = Stage::attack;
        attackInc = (float) (1.0 / (attackSeconds * getSampleRate()));
    }

    void stopNote (float, bool allowTailOff) override
    {
        // AD envelope: the note decays on its own, so note-off with tail-off is
        // a no-op. A stolen voice must stop immediately.
        if (! allowTailOff)
        {
            envStage = Stage::idle;
            envValue = 0.0f;
            clearCurrentNote();
        }
    }

    void pitchWheelMoved (int) override {}
    void controllerMoved (int, int) override {}

    void renderNextBlock (juce::AudioBuffer<float>& outputBuffer,
                          int startSample, int numSamples) override
    {
        if (envStage == Stage::idle)
            return;

        auto sr = getSampleRate();

        for (int i = 0; i < numSamples; ++i)
        {
            // Per-voice slow random pitch drift, in cents.
            auto cents = driftDepthCents * lfo.getNextSample (rng);
            auto freq = baseFrequency * std::exp2 ((double) cents / 1200.0);

            phase += freq / sr;
            if (phase >= 1.0)
                phase -= 1.0;

            // Triangle from phase: rises 0..0.5, falls 0.5..1.
            auto p = (float) phase;
            auto tri = p < 0.5f ? 4.0f * p - 1.0f : 3.0f - 4.0f * p;

            // One-pole lowpass ("Warmth").
            filterState += filterCoeff * (tri - filterState);

            // AD envelope.
            if (envStage == Stage::attack)
            {
                envValue += attackInc;
                if (envValue >= 1.0f)
                {
                    envValue = 1.0f;
                    envStage = Stage::decay;
                }
            }
            else
            {
                envValue *= decayMult;
                if (envValue < 0.0001f)
                {
                    envStage = Stage::idle;
                    clearCurrentNote();
                    break;
                }
            }

            auto sample = filterState * envValue * level;

            for (int ch = outputBuffer.getNumChannels(); --ch >= 0;)
                outputBuffer.addSample (ch, startSample + i, sample);
        }
    }

private:
    enum class Stage { idle, attack, decay };

    juce::Random rng;
    DriftLfo lfo;

    double baseFrequency = 440.0, phase = 0.0;
    float level = 0.0f;

    static constexpr double attackSeconds = 0.004;
    Stage envStage = Stage::idle;
    float envValue = 0.0f, attackInc = 0.0f, decayMult = 0.999f;

    float driftDepthCents = 6.0f;
    float filterCoeff = 1.0f, filterState = 0.0f;
};
