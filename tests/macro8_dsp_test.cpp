/*
 * Standalone MODULAR-SYNTH Macro8 DSP and snapshot regression test.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * From repository root:
 *   c++ -std=c++17 -O2 -Wall -Wextra -Werror -pthread \
 *       tests/macro8_dsp_test.cpp -o /tmp/macro8_dsp_test
 *   /tmp/macro8_dsp_test
 *
 * Pure DSP: no Rack, DAW, audio hardware, UI or external libraries.
 */
#include "../plugins/ModularSynth/src/Macro8.hpp"

#include <cmath>
#include <cstdio>
#include <limits>

using modular_synth::dsp::Macro8Smoother;
using modular_synth::dsp::Macro8SnapshotBank;
using modular_synth::dsp::macro8Finite;

static bool expect(bool condition, const char* message) {
    if (!condition)
        std::fprintf(stderr, "FAIL Macro8: %s\n", message);
    return condition;
}

int main() {
    bool good = true;
    constexpr float sampleTime = 1.0f / 48000.0f;
    float zero[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    float one[8] = {1, 1, 1, 1, 1, 1, 1, 1};
    float distinct[8] = {0, 0.125f, 0.25f, 0.375f, 0.5f, 0.625f, 0.75f, 1.0f};

    Macro8Smoother smooth;
    smooth.process(sampleTime, 5.0f, distinct);
    for (int i = 0; i < 8; ++i)
        good &= expect(std::fabs(smooth.current[i] - distinct[i]) < 1.0e-7f,
                       "initial state must match the saved/live values without startup glide");

    good &= expect(std::fabs(Macro8Smoother::voltage(0.0f, false) - 0.0f) < 1.0e-7f,
                   "unipolar minimum incorrect");
    good &= expect(std::fabs(Macro8Smoother::voltage(1.0f, false) - 10.0f) < 1.0e-7f,
                   "unipolar maximum incorrect");
    good &= expect(std::fabs(Macro8Smoother::voltage(0.0f, true) + 5.0f) < 1.0e-7f,
                   "bipolar minimum incorrect");
    good &= expect(std::fabs(Macro8Smoother::voltage(0.5f, true)) < 1.0e-7f,
                   "bipolar midpoint incorrect");
    good &= expect(std::fabs(Macro8Smoother::voltage(1.0f, true) - 5.0f) < 1.0e-7f,
                   "bipolar maximum incorrect");

    smooth.reset();
    smooth.process(sampleTime, 0.0f, zero);
    float previous = smooth.current[0];
    for (int i = 0; i < 48000; ++i) {
        smooth.process(sampleTime, 1.0f, one);
        good &= expect(macro8Finite(smooth.current[0]), "morphing output must remain finite");
        good &= expect(smooth.current[0] >= previous &&
                       smooth.current[0] <= 1.0f, "morph must be monotonic without overshoot");
        previous = smooth.current[0];
    }
    good &= expect(smooth.current[0] > 0.998f,
                   "one-second morph must reach approximately 99.9 percent");
    smooth.process(sampleTime, 0.0f, zero);
    good &= expect(smooth.current[0] == 0.0f,
                   "zero transition time must jump immediately");

    // A float accumulator stalls near the destination at high sample rates.
    // Double-precision state must meet the same 99.9% settling guarantee
    // at 48k, 96k and 192k with an identical five-second morph time.
    for (int rate : {48000, 96000, 192000}) {
        smooth.reset();
        smooth.process(1.0f / rate, 0.0f, zero);
        for (int sample = 0; sample < rate * 5; ++sample)
            smooth.process(1.0f / rate, 5.0f, one);
        good &= expect(std::fabs(smooth.current[0] - 0.999) < 0.0003,
                       "five-second morph must settle consistently across sample rates");
        for (int sample = 0; sample < rate * 5; ++sample)
            smooth.process(1.0f / rate, 5.0f, one);
        good &= expect(smooth.current[0] > 0.99999,
                       "continued morph must not stall at a float precision floor");
    }

    good &= expect(!macro8Finite(std::numeric_limits<float>::quiet_NaN()) &&
                   !macro8Finite(std::numeric_limits<float>::infinity()) &&
                   !macro8Finite(std::numeric_limits<double>::infinity()),
                   "IEEE-754 finite guards must survive aggressive fast-math");

    Macro8SnapshotBank bank;
    float readback[8] = {};
    for (int slot = 0; slot < 4; ++slot) {
        float values[8];
        for (int i = 0; i < 8; ++i)
            values[i] = (slot + i) / 10.0f;
        good &= expect(bank.store(slot, values), "snapshot capture must succeed");
        good &= expect(bank.has(slot), "stored slot must be marked valid");
        good &= expect(bank.load(slot, readback), "snapshot load must succeed");
        for (int i = 0; i < 8; ++i)
            good &= expect(std::fabs(readback[i] - values[i]) < 1.0e-7f,
                           "snapshot values must round-trip exactly");
    }

    good &= expect(!bank.store(-1, zero), "negative slot must be rejected");
    good &= expect(!bank.store(4, zero), "slot past D must be rejected");
    good &= expect(!bank.load(4, readback), "invalid slot load must be rejected");

    float bad[8] = {-10.0f, 4.0f, std::numeric_limits<float>::quiet_NaN(),
                    std::numeric_limits<float>::infinity(), -0.1f, 0.3f, 0.9f, 3.0f};
    good &= expect(bank.store(0, bad), "recapture A must succeed");
    good &= expect(bank.load(0, readback), "recaptured A must load");
    good &= expect(bank.mayExist(0), "published snapshot validity must persist");

    // Simulate a short writer window. The audio callback must not confuse
    // an odd generation with a missing slot and discard selected snapshot A.
    const auto version = bank.slots[0].generation.load(std::memory_order_relaxed);
    bank.slots[0].generation.store(version | 1u, std::memory_order_release);
    good &= expect(!bank.load(0, readback) && bank.mayExist(0),
                   "transient snapshot write must remain distinguishable from empty slot");
    bank.slots[0].generation.store((version | 1u) + 1u, std::memory_order_release);
    good &= expect(bank.load(0, readback), "snapshot read must recover after writer completes");

    good &= expect(readback[0] == 0.0f && readback[1] == 1.0f &&
                   readback[2] == 0.0f && readback[3] == 0.0f &&
                   readback[7] == 1.0f, "saved values must be finite and clamped");

    smooth.reset();
    smooth.process(sampleTime, 0.0f, one);
    float invalid[8] = {std::numeric_limits<float>::quiet_NaN(),
                        -1.0f, 2.0f, 0.3f, 0.5f, 0.6f, 0.7f, 0.8f};
    smooth.process(sampleTime, 0.0f, invalid);
    good &= expect(smooth.current[0] == 0.0f && smooth.current[1] == 0.0f &&
                   smooth.current[2] == 1.0f, "invalid and out-of-range CV targets must clamp");
    const float stable = smooth.current[3];
    smooth.process(std::numeric_limits<float>::quiet_NaN(), 1.0f, one);
    good &= expect(smooth.current[3] == stable,
                   "invalid sample interval must not move the smoothing state");

    bank.clear();
    for (int slot = 0; slot < 4; ++slot)
        good &= expect(!bank.has(slot) && !bank.load(slot, readback),
                       "clear must invalidate all snapshots");

    if (good)
        std::puts("PASS: Macro8 DSP, 4-slot snapshots, voltage modes and morphing");
    return good ? 0 : 1;
}
