cmake_minimum_required(VERSION 3.22)

project(Drift VERSION 1.0.0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Use a local JUCE checkout if present (drift/JUCE), otherwise fetch it.
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/JUCE/CMakeLists.txt")
    add_subdirectory(JUCE)
else()
    include(FetchContent)
    FetchContent_Declare(JUCE
        GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
        GIT_TAG        8.0.8
        GIT_SHALLOW    TRUE)
    FetchContent_MakeAvailable(JUCE)
endif()

# AU only exists on macOS; JUCE errors on unsupported formats elsewhere.
set(DRIFT_FORMATS VST3)
if(APPLE)
    list(APPEND DRIFT_FORMATS AU)
endif()

juce_add_plugin(Drift
    PRODUCT_NAME "Drift"
    COMPANY_NAME "Drift Audio"
    BUNDLE_ID com.driftaudio.drift
    PLUGIN_MANUFACTURER_CODE Drfa
    PLUGIN_CODE Drft
    FORMATS ${DRIFT_FORMATS}
    IS_SYNTH TRUE
    NEEDS_MIDI_INPUT TRUE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    AU_MAIN_TYPE kAudioUnitType_MusicDevice
    VST3_CATEGORIES Instrument Synth
    COPY_PLUGIN_AFTER_BUILD FALSE)

target_sources(Drift PRIVATE
    Source/PluginProcessor.cpp)

target_compile_definitions(Drift PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0)

target_link_libraries(Drift
    PRIVATE
        juce::juce_audio_utils
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_lto_flags
        juce::juce_recommended_warning_flags)
