// Minimal VST3 host smoke test for Drift (Linux stand-in for auval).
//
// Loads the built .so, instantiates the component + controller, checks that
// the three parameters (Drift, Warmth, Decay) are exposed, then renders two
// seconds of audio with a note-on and asserts the output is non-silent and
// finite, and that the tail decays after the envelope's decay time.

#include <dlfcn.h>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivstcomponent.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "pluginterfaces/vst/ivstevents.h"
#include "pluginterfaces/vst/ivstmessage.h"
#include "pluginterfaces/vst/ivstprocesscontext.h"

using namespace Steinberg;

// The SDK requires one translation unit to define the interface IIDs.
DEF_CLASS_IID (FUnknown)
DEF_CLASS_IID (IPluginFactory)
DEF_CLASS_IID (Vst::IComponent)
DEF_CLASS_IID (Vst::IAudioProcessor)
DEF_CLASS_IID (Vst::IEditController)
DEF_CLASS_IID (Vst::IEventList)
DEF_CLASS_IID (Vst::IConnectionPoint)

#define CHECK(cond, msg)                                          \
    do {                                                          \
        if (!(cond)) { fprintf (stderr, "FAIL: %s\n", msg); return 1; } \
        printf ("ok: %s\n", msg);                                 \
    } while (0)

static std::string toUtf8 (const Vst::TChar* s)
{
    std::string out;
    for (int i = 0; s[i] != 0 && i < 128; ++i)
        out += (char) s[i];
    return out;
}

// Minimal IEventList with a single note-on at sample 0.
struct NoteOnList : Vst::IEventList
{
    Vst::Event event {};
    bool used = false;

    NoteOnList()
    {
        event.type = Vst::Event::kNoteOnEvent;
        event.noteOn.channel = 0;
        event.noteOn.pitch = 60;
        event.noteOn.velocity = 0.9f;
        event.noteOn.noteId = -1;
    }

    int32 PLUGIN_API getEventCount() override { return used ? 0 : 1; }
    tresult PLUGIN_API getEvent (int32 index, Vst::Event& e) override
    {
        if (used || index != 0) return kResultFalse;
        e = event;
        return kResultTrue;
    }
    tresult PLUGIN_API addEvent (Vst::Event&) override { return kResultFalse; }

    tresult PLUGIN_API queryInterface (const TUID iid, void** obj) override
    {
        if (FUnknownPrivate::iidEqual (iid, Vst::IEventList::iid)
            || FUnknownPrivate::iidEqual (iid, FUnknown::iid))
        {
            *obj = this;
            return kResultOk;
        }
        *obj = nullptr;
        return kNoInterface;
    }
    uint32 PLUGIN_API addRef() override { return 1; }
    uint32 PLUGIN_API release() override { return 1; }
};

struct EmptyEventList : Vst::IEventList
{
    int32 PLUGIN_API getEventCount() override { return 0; }
    tresult PLUGIN_API getEvent (int32, Vst::Event&) override { return kResultFalse; }
    tresult PLUGIN_API addEvent (Vst::Event&) override { return kResultFalse; }
    tresult PLUGIN_API queryInterface (const TUID iid, void** obj) override
    {
        if (FUnknownPrivate::iidEqual (iid, Vst::IEventList::iid)
            || FUnknownPrivate::iidEqual (iid, FUnknown::iid))
        {
            *obj = this;
            return kResultOk;
        }
        *obj = nullptr;
        return kNoInterface;
    }
    uint32 PLUGIN_API addRef() override { return 1; }
    uint32 PLUGIN_API release() override { return 1; }
};

int main (int argc, char** argv)
{
    if (argc < 2)
    {
        fprintf (stderr, "usage: %s <path-to-Drift.so>\n", argv[0]);
        return 2;
    }

    void* lib = dlopen (argv[1], RTLD_NOW);
    CHECK (lib != nullptr, "dlopen plugin module");

    using EntryFn = bool (*) (void*);
    using FactoryFn = IPluginFactory* (*)();

    auto entry = (EntryFn) dlsym (lib, "ModuleEntry");
    auto getFactory = (FactoryFn) dlsym (lib, "GetPluginFactory");
    CHECK (entry && getFactory, "ModuleEntry / GetPluginFactory exported");
    CHECK (entry (lib), "ModuleEntry succeeds");

    IPluginFactory* factory = getFactory();
    CHECK (factory != nullptr, "factory obtained");

    PFactoryInfo facInfo {};
    factory->getFactoryInfo (&facInfo);
    printf ("   vendor: %s\n", facInfo.vendor);

    // Find the audio component class.
    PClassInfo audioClass {};
    bool found = false;
    for (int32 i = 0; i < factory->countClasses(); ++i)
    {
        PClassInfo ci {};
        factory->getClassInfo (i, &ci);
        printf ("   class: %s (%s)\n", ci.name, ci.category);
        if (strcmp (ci.category, kVstAudioEffectClass) == 0)
        {
            audioClass = ci;
            found = true;
        }
    }
    CHECK (found, "audio component class present");
    CHECK (strcmp (audioClass.name, "Drift") == 0, "plugin is named Drift");

    Vst::IComponent* component = nullptr;
    CHECK (factory->createInstance (audioClass.cid, Vst::IComponent::iid,
                                    (void**) &component) == kResultOk
               && component != nullptr,
           "IComponent created");
    CHECK (component->initialize (nullptr) == kResultOk, "component initialised");

    // JUCE plugins implement IEditController on the same object.
    Vst::IEditController* controller = nullptr;
    if (component->queryInterface (Vst::IEditController::iid, (void**) &controller) != kResultOk)
    {
        TUID controllerCid;
        CHECK (component->getControllerClassId (controllerCid) == kResultOk,
               "controller class id available");
        CHECK (factory->createInstance (controllerCid, Vst::IEditController::iid,
                                        (void**) &controller) == kResultOk,
               "IEditController created");
        controller->initialize (nullptr);
    }
    CHECK (controller != nullptr, "edit controller obtained");

    // Connect component and controller as a host would, so the controller
    // learns about the processor's parameters.
    Vst::IConnectionPoint* compCP = nullptr;
    Vst::IConnectionPoint* ctrlCP = nullptr;
    component->queryInterface (Vst::IConnectionPoint::iid, (void**) &compCP);
    controller->queryInterface (Vst::IConnectionPoint::iid, (void**) &ctrlCP);
    if (compCP != nullptr && ctrlCP != nullptr)
    {
        compCP->connect (ctrlCP);
        ctrlCP->connect (compCP);
    }

    bool hasDrift = false, hasWarmth = false, hasDecay = false;
    for (int32 i = 0; i < controller->getParameterCount(); ++i)
    {
        Vst::ParameterInfo pi {};
        controller->getParameterInfo (i, pi);
        auto name = toUtf8 (pi.title);
        if (i < 4)  // the rest is JUCE's MIDI-CC parameter map
            printf ("   param %d: %s\n", i, name.c_str());
        hasDrift  |= name == "Drift";
        hasWarmth |= name == "Warmth";
        hasDecay  |= name == "Decay";
    }
    CHECK (hasDrift && hasWarmth && hasDecay, "Drift/Warmth/Decay parameters exposed");

    Vst::IAudioProcessor* processor = nullptr;
    CHECK (component->queryInterface (Vst::IAudioProcessor::iid, (void**) &processor)
               == kResultOk,
           "IAudioProcessor obtained");

    constexpr double sampleRate = 48000.0;
    constexpr int32 blockSize = 512;

    CHECK (component->getBusCount (Vst::kAudio, Vst::kOutput) == 1, "one audio output bus");
    CHECK (component->getBusCount (Vst::kEvent, Vst::kInput) == 1, "one MIDI event input bus");
    component->activateBus (Vst::kAudio, Vst::kOutput, 0, true);
    component->activateBus (Vst::kEvent, Vst::kInput, 0, true);

    Vst::ProcessSetup setup { Vst::kRealtime, Vst::kSample32, blockSize, sampleRate };
    CHECK (processor->setupProcessing (setup) == kResultOk, "setupProcessing");
    CHECK (component->setActive (true) == kResultOk, "setActive");
    processor->setProcessing (true);

    std::vector<float> left (blockSize), right (blockSize);
    float* channels[2] = { left.data(), right.data() };

    Vst::AudioBusBuffers outBus;
    outBus.numChannels = 2;
    outBus.silenceFlags = 0;
    outBus.channelBuffers32 = channels;

    Vst::ProcessContext ctx {};
    ctx.state = Vst::ProcessContext::kPlaying;
    ctx.sampleRate = sampleRate;

    NoteOnList noteOn;
    EmptyEventList noEvents;

    // Render 2 s; note-on in the first block only. Measure early vs late RMS.
    const int totalBlocks = (int) (2.0 * sampleRate / blockSize);
    double earlyPeak = 0.0, latePeak = 0.0;
    bool allFinite = true;

    for (int b = 0; b < totalBlocks; ++b)
    {
        Vst::ProcessData data;
        data.processMode = Vst::kRealtime;
        data.symbolicSampleSize = Vst::kSample32;
        data.numSamples = blockSize;
        data.numInputs = 0;
        data.numOutputs = 1;
        data.inputs = nullptr;
        data.outputs = &outBus;
        data.inputParameterChanges = nullptr;
        data.outputParameterChanges = nullptr;
        data.inputEvents = (b == 0) ? (Vst::IEventList*) &noteOn
                                    : (Vst::IEventList*) &noEvents;
        data.outputEvents = nullptr;
        data.processContext = &ctx;

        if (processor->process (data) != kResultOk)
        {
            fprintf (stderr, "FAIL: process() returned error at block %d\n", b);
            return 1;
        }
        if (b == 0) noteOn.used = true;

        for (int i = 0; i < blockSize; ++i)
        {
            float v = std::fabs (left[i]);
            if (! std::isfinite (left[i]) || ! std::isfinite (right[i]))
                allFinite = false;
            if (b < totalBlocks / 4)      earlyPeak = std::max (earlyPeak, (double) v);
            else if (b > 3 * totalBlocks / 4) latePeak = std::max (latePeak, (double) v);
        }
        ctx.projectTimeSamples += blockSize;
    }

    printf ("   early peak: %.4f, late peak: %.4f\n", earlyPeak, latePeak);
    CHECK (allFinite, "output is finite (no NaN/inf)");
    CHECK (earlyPeak > 0.01, "note produces audible output");
    CHECK (latePeak < earlyPeak * 0.25, "AD envelope decays (default 1 s decay)");

    processor->setProcessing (false);
    component->setActive (false);
    processor->release();
    controller->release();
    component->terminate();
    component->release();
    factory->release();

    printf ("\nVST3 SMOKE TEST PASSED\n");
    return 0;
}
