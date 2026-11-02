/*
 * FoldDrive actual Rack wrapper against the small HEADLESS test-only shim.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 * This is not a real Rack binary/ABI or DAW plugin test.
 */
#ifndef HEADLESS
#error "Compile this test only against the HEADLESS Rack API shim"
#endif

#include "../plugins/ModularSynth/src/FoldDrive.cpp"

#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <new>
#include <thread>

// The module constructor initializes Rack's parameter/port vectors, so
// allocation counting begins only after construction and setup have ended.
static std::atomic<std::size_t> allocationCount{0};
static void* trackedAllocation(std::size_t bytes) {
    if (void* p = std::malloc(bytes == 0 ? 1 : bytes)) {
        allocationCount.fetch_add(1, std::memory_order_relaxed);
        return p;
    }
    throw std::bad_alloc();
}
void* operator new(std::size_t bytes) { return trackedAllocation(bytes); }
void* operator new[](std::size_t bytes) { return trackedAllocation(bytes); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }

static void require(bool condition, const char* reason) {
    if (!condition) {
        std::fprintf(stderr, "FAIL FoldDrive wrapper: %s\n", reason);
        std::exit(EXIT_FAILURE);
    }
}

static void assertChannels(ModularSynthFoldDrive& module, int requested) {
    require(module.outputs[ModularSynthFoldDrive::AUDIO_OUTPUT].getChannels() == requested,
            "polyphonic output channel count matches inputs/CV up to 16");
    for (int c = 0; c < requested; ++c) {
        const float voltage = module.outputs[ModularSynthFoldDrive::AUDIO_OUTPUT].getVoltage(c);
        require(modular_synth::dsp::FoldDrive::ieeeFinite(voltage),
                "all wrapper outputs finite");
        require(voltage >= -10.0f && voltage <= 10.0f,
                "all wrapper outputs bounded by +/-10V");
    }
}

int main() {
    rack::ProcessArgs args;
    args.sampleRate = 48000.0;
    ModularSynthFoldDrive module;
    require(module.params.size() == ModularSynthFoldDrive::NUM_PARAMS,
            "Rack parameter vector cardinality");
    require(module.inputs.size() == ModularSynthFoldDrive::NUM_INPUTS,
            "Rack audio/CV input vector cardinality");
    require(module.outputs.size() == ModularSynthFoldDrive::NUM_OUTPUTS,
            "Rack output vector cardinality");

    module.params[ModularSynthFoldDrive::DRIVE_PARAM].setValue(1.0f);
    module.params[ModularSynthFoldDrive::BIAS_PARAM].setValue(0.0f);
    module.params[ModularSynthFoldDrive::MIX_PARAM].setValue(1.0f);
    module.inputs[ModularSynthFoldDrive::AUDIO_INPUT].setChannels(8);
    for (int c = 0; c < 8; ++c)
        module.inputs[ModularSynthFoldDrive::AUDIO_INPUT].setVoltage(1.5f, c);
    module.process(args);
    assertChannels(module, 8);
    const float folded = module.outputs[ModularSynthFoldDrive::AUDIO_OUTPUT].getVoltage(7);
    require(folded < -3.0f, "last poly lane processes actual audio fold");

    // A mono invalid CV must be ignored for every audio lane, even if the
    // C++ compiler assumes IEEE values are finite under -ffast-math.
    module.inputs[ModularSynthFoldDrive::DRIVE_CV_INPUT].setChannels(1);
    module.inputs[ModularSynthFoldDrive::DRIVE_CV_INPUT].setVoltage(
        std::numeric_limits<float>::quiet_NaN(), 0);
    module.process(args);
    assertChannels(module, 8);

    module.inputs[ModularSynthFoldDrive::AUDIO_INPUT].setChannels(1);
    module.process(args);
    assertChannels(module, 1);
    require(!module.voices[7].initialized, "retired lane clears 3ms CV slew state");

    // CV may alone establish polyphony; a 16-lane modulation source is
    // broadcast against a mono audio signal by getNormalPolyVoltage().
    module.inputs[ModularSynthFoldDrive::DRIVE_CV_INPUT].setChannels(16);
    for (int c = 0; c < 16; ++c)
        module.inputs[ModularSynthFoldDrive::DRIVE_CV_INPUT].setVoltage(c * 0.3f, c);
    module.process(args);
    assertChannels(module, 16);
    require(module.voices[15].initialized, "re-expanded lane starts cleanly");

    module.inputs[ModularSynthFoldDrive::AUDIO_INPUT].setVoltage(
        std::numeric_limits<float>::infinity(), 0);
    module.process(args);
    assertChannels(module, 16);

    // Exercise Rack's REAL event overload. The callback may be on the UI
    // thread, so it must queue rather than write process-owned DSP state.
    rack::Module& rackModule = module;
    const rack::ResetEvent event{};
    rackModule.onReset(event);
    require(module.pendingReset.load(std::memory_order_acquire),
            "ResetEvent queues atomic audio-thread reset");
    require(module.previousChannels == 16,
            "ResetEvent callback never directly mutates audio channel lifecycle");
    for (auto& voice : module.voices)
        require(voice.initialized, "ResetEvent callback leaves audio DSP state untouched");

    // Process tick consumes the request, resets lanes, and initializes the
    // current sixteen newly alive lanes from their current CV settings.
    module.process(args);
    assertChannels(module, 16);
    require(!module.pendingReset.load(std::memory_order_acquire),
            "process() consumes pending reset");
    for (auto& voice : module.voices)
        require(voice.initialized, "process() initializes first frame after reset");

    const std::size_t before = allocationCount.load(std::memory_order_relaxed);
    for (int frame = 0; frame < 8192; ++frame)
        module.process(args);
    require(allocationCount.load(std::memory_order_relaxed) == before,
            "8192 process ticks allocate zero heap memory");

    // UI/Rack reset requests concurrently with audio processing: the only
    // shared mutable member is atomic pendingReset, so no cross-thread voice
    // mutation is permitted. Source-only stress, not a real host test.
    std::atomic<bool> start{false};
    std::atomic<bool> finished{false};
    std::thread ui([&] {
        while (!start.load(std::memory_order_acquire))
            std::this_thread::yield();
        for (int i = 0; i < 10000; ++i)
            rackModule.onReset(event);
        finished.store(true, std::memory_order_release);
    });
    start.store(true, std::memory_order_release);
    int audioFrames = 0;
    do {
        module.process(args);
        assertChannels(module, 16);
        ++audioFrames;
    } while (!finished.load(std::memory_order_acquire) || audioFrames < 10000);
    ui.join();
    module.process(args);
    assertChannels(module, 16);
    std::puts("PASS FoldDrive HEADLESS wrapper: 1/8/16 lanes, CV broadcast, 8192 allocation-free ticks and concurrent UI ResetEvent");
}
