#include "PluginProcessor.h"

//==============================================================================
DriftAudioProcessor::DriftAudioProcessor()
    : AudioProcessor (BusesProperties().withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      apvts (*this, nullptr, "Parameters", createParameterLayout())
{
    driftParam  = apvts.getRawParameterValue ("drift");
    warmthParam = apvts.getRawParameterValue ("warmth");
    decayParam  = apvts.getRawParameterValue ("decay");

    for (int i = 0; i < numVoices; ++i)
        synth.addVoice (new DriftVoice ((juce::int64) (i + 1) * 7919));

    synth.addSound (new DriftSound());
}

juce::AudioProcessorValueTreeState::ParameterLayout DriftAudioProcessor::createParameterLayout()
{
    juce::AudioProcessorValueTreeState::ParameterLayout layout;

    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { "drift", 1 }, "Drift",
        juce::NormalisableRange<float> (0.0f, 15.0f, 0.01f), 6.0f,
        juce::AudioParameterFloatAttributes().withLabel ("ct")));

    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { "warmth", 1 }, "Warmth",
        juce::NormalisableRange<float> (0.0f, 1.0f, 0.001f), 0.5f));

    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { "decay", 1 }, "Decay",
        juce::NormalisableRange<float> (0.05f, 8.0f, 0.001f, 0.4f), 1.0f,
        juce::AudioParameterFloatAttributes().withLabel ("s")));

    return layout;
}

//==============================================================================
void DriftAudioProcessor::prepareToPlay (double sampleRate, int)
{
    synth.setCurrentPlaybackSampleRate (sampleRate);
}

bool DriftAudioProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    auto out = layouts.getMainOutputChannelSet();
    return out == juce::AudioChannelSet::mono() || out == juce::AudioChannelSet::stereo();
}

double DriftAudioProcessor::getTailLengthSeconds() const
{
    return decayParam != nullptr ? (double) decayParam->load() : 8.0;
}

void DriftAudioProcessor::processBlock (juce::AudioBuffer<float>& buffer,
                                        juce::MidiBuffer& midiMessages)
{
    juce::ScopedNoDenormals noDenormals;
    buffer.clear();

    auto drift  = driftParam->load();
    auto warmth = warmthParam->load();
    auto decay  = decayParam->load();

    // Warmth 0 -> bright (18 kHz open), 1 -> dark (~500 Hz).
    auto cutoffHz = 500.0f * std::pow (36.0f, 1.0f - warmth);

    for (int i = 0; i < synth.getNumVoices(); ++i)
        if (auto* voice = dynamic_cast<DriftVoice*> (synth.getVoice (i)))
            voice->setParameters (drift, cutoffHz, decay);

    synth.renderNextBlock (buffer, midiMessages, 0, buffer.getNumSamples());
}

//==============================================================================
juce::AudioProcessorEditor* DriftAudioProcessor::createEditor()
{
    return new juce::GenericAudioProcessorEditor (*this);
}

//==============================================================================
void DriftAudioProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    if (auto xml = apvts.copyState().createXml())
        copyXmlToBinary (*xml, destData);
}

void DriftAudioProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    if (auto xml = getXmlFromBinary (data, sizeInBytes))
        if (xml->hasTagName (apvts.state.getType()))
            apvts.replaceState (juce::ValueTree::fromXml (*xml));
}

//==============================================================================
juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new DriftAudioProcessor();
}
