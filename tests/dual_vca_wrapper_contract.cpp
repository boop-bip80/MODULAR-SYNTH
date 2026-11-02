/*
 * DualVCA Rack wrapper process tests against a HEADLESS test-only Rack shim.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Not a real Rack ABI, Cardinal plugin, GUI, audio-device or DAW test.
 */
#ifndef HEADLESS
#error "This file tests only the HEADLESS shim wrapper"
#endif
#include "../plugins/ModularSynth/src/DualVCA.cpp"

#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <new>
#include <thread>

static std::atomic<std::size_t> allocations{0};
void* operator new(std::size_t bytes) {
    if (void* p = std::malloc(bytes ? bytes : 1)) {
        allocations.fetch_add(1, std::memory_order_relaxed);
        return p;
    }
    throw std::bad_alloc();
}
void* operator new[](std::size_t bytes) {
    if (void* p = std::malloc(bytes ? bytes : 1)) {
        allocations.fetch_add(1, std::memory_order_relaxed);
        return p;
    }
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }

static void require(bool okay, const char* reason) {
    if (!okay) {
        std::fprintf(stderr, "FAIL DualVCA wrapper: %s\n", reason);
        std::exit(1);
    }
}

static void checkOutputs(ModularSynthDualVCA& module, int aCount,
                         int bCount) {
    require(module.outputs[ModularSynthDualVCA::AUDIO_A_OUTPUT].getChannels() == aCount,
            "A output tracks its independent channel count");
    require(module.outputs[ModularSynthDualVCA::AUDIO_B_OUTPUT].getChannels() == bCount,
            "B output tracks its independent channel count");
    const int sumCount = std::max(aCount, bCount);
    require(module.outputs[ModularSynthDualVCA::SUM_OUTPUT].getChannels() == sumCount,
            "SUM output carries the maximum side channel count");
    for (int c = 0; c < sumCount; ++c) {
        const float sum = module.outputs[ModularSynthDualVCA::SUM_OUTPUT].getVoltage(c);
        require(modular_synth::dsp::DualVCA::finite(sum),
                "every SUM voltage is finite");
        require(sum >= -10.0f && sum <= 10.0f,
                "SUM voltage stays within +/-10V");
    }
}

int main() {
    rack::ProcessArgs args;
    args.sampleRate = 48000.0;
    ModularSynthDualVCA module;
    require(module.params.size() == ModularSynthDualVCA::NUM_PARAMS, "parameter count");
    require(module.inputs.size() == ModularSynthDualVCA::NUM_INPUTS, "input count");
    require(module.outputs.size() == ModularSynthDualVCA::NUM_OUTPUTS, "output count");
    module.params[ModularSynthDualVCA::LEVEL_A_PARAM].setValue(0.5f);
    module.params[ModularSynthDualVCA::LEVEL_B_PARAM].setValue(0.25f);

    // 8 voices on side A, only 1 on side B. SUM must preserve the tail
    // rather than truncating it to the minimum of two independent sides.
    module.inputs[ModularSynthDualVCA::AUDIO_A_INPUT].setChannels(8);
    for (int c = 0; c < 8; ++c)
        module.inputs[ModularSynthDualVCA::AUDIO_A_INPUT].setVoltage(4.0f, c);
    module.inputs[ModularSynthDualVCA::AUDIO_B_INPUT].setChannels(1);
    module.inputs[ModularSynthDualVCA::AUDIO_B_INPUT].setVoltage(-4.0f, 0);
    module.process(args);
    checkOutputs(module, 8, 1);
    require(std::abs(module.outputs[ModularSynthDualVCA::AUDIO_A_OUTPUT].getVoltage(7)
                     - 2.0f) < 1e-6f,
            "A eighth voice has actual audio at default disconnected CV");
    require(std::abs(module.outputs[ModularSynthDualVCA::AUDIO_B_OUTPUT].getVoltage(0)
                     + 1.0f) < 1e-6f,
            "B mono lane processes independent level");

    // CV alone can create polyphonic channels. Mono audio is normalled
    // across every poly CV lane by Rack Input::getNormalPolyVoltage().
    module.inputs[ModularSynthDualVCA::CV_B_INPUT].setChannels(16);
    for (int c = 0; c < 16; ++c)
        module.inputs[ModularSynthDualVCA::CV_B_INPUT].setVoltage(c * (10.0f / 15), c);
    module.process(args);
    checkOutputs(module, 8, 16);
    require(module.voicesB[15].gain() > 0.0, "16th B lane receives CV");
    module.inputs[ModularSynthDualVCA::CV_B_INPUT].setVoltage(
        std::numeric_limits<float>::quiet_NaN(), 15);
    module.process(args);
    checkOutputs(module, 8, 16);
    require(module.outputs[ModularSynthDualVCA::AUDIO_B_OUTPUT].getVoltage(15) <= 0.0f,
            "invalid B CV cannot invert its negative source");

    module.inputs[ModularSynthDualVCA::CV_B_INPUT].setChannels(0);
    module.inputs[ModularSynthDualVCA::AUDIO_A_INPUT].setChannels(1);
    module.process(args);
    checkOutputs(module, 1, 1);
    require(module.voicesA[7].gain() == 0.0,
            "retired A polyphonic lane clears smoothing state");
    require(module.voicesB[15].gain() == 0.0,
            "retired B polyphonic lane clears smoothing state");

    // onReset() is allowed on an external host thread and never touches
    // process-owned voices directly.
    rack::Module& rackModule = module;
    const rack::ResetEvent event{};
    rackModule.onReset(event);
    require(module.pendingReset.load(std::memory_order_acquire),
            "reset request is atomic and deferred");
    require(module.voicesA[0].gain() > 0.0,
            "UI reset leaves process-owned voice untouched until audio tick");
    module.process(args);
    require(!module.pendingReset.load(std::memory_order_acquire),
            "audio process consumes reset request");

    const auto before = allocations.load(std::memory_order_relaxed);
    for (int i = 0; i < 8192; ++i)
        module.process(args);
    require(allocations.load(std::memory_order_relaxed) == before,
            "8192 process ticks allocate no heap memory");

    std::atomic<bool> start{false}, done{false};
    std::thread ui([&] {
        while (!start.load(std::memory_order_acquire))
            std::this_thread::yield();
        for (int i = 0; i < 10000; ++i)
            rackModule.onReset(event);
        done.store(true, std::memory_order_release);
    });
    start.store(true, std::memory_order_release);
    int frames = 0;
    do {
        module.process(args);
        checkOutputs(module, 1, 1);
        ++frames;
    } while (!done.load(std::memory_order_acquire) || frames < 10000);
    ui.join();
    std::puts("PASS DualVCA HEADLESS shim wrapper: 1/8/16 lanes, independent gains, retirement, allocation-free audio and concurrent reset requests");
}
