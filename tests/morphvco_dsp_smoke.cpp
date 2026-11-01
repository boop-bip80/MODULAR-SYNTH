/*
 * Standalone smoke test for MODULAR-SYNTH Morph VCO DSP.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * From repository root:
 *   c++ -std=c++17 -O2 -Wall -Wextra -Werror tests/morphvco_dsp_smoke.cpp -o /tmp/morphvco_dsp_smoke
 *   /tmp/morphvco_dsp_smoke
 *
 * This test requires no Rack, audio device, GUI, or third-party libraries.
 */
#include "../plugins/ModularSynth/src/MorphVCO.hpp"

#include <cmath>
#include <cstdio>
#include <initializer_list>
#include <limits>

using modular_synth::dsp::MorphOscillator;

static bool check(bool passed, const char* message) {
    if (!passed)
        std::fprintf(stderr, "FAIL: %s\n", message);
    return passed;
}

int main() {
    bool okay = true;
    constexpr double sampleRate = 48000.0;

    // One second of A4 at 48 kHz. The sine must produce 440 cycles
    // regardless of morph position and pulse width.
    MorphOscillator oscillator;
    float previous = 0.0f;
    int risingCrossings = 0;
    for (int i = 0; i < 48000; ++i) {
        const auto frame = oscillator.process(440.0, sampleRate, 0.0f, 0.5f);
        okay &= check(std::isfinite(frame.sine) && std::isfinite(frame.morph),
                      "sine render must be finite");
        if (i > 0 && previous < 0.0f && frame.sine >= 0.0f)
            ++risingCrossings;
        previous = frame.sine;
    }
    okay &= check(risingCrossings >= 438 && risingCrossings <= 440,
                  "1-second A4 frequency outside tolerance");
    okay &= check(oscillator.phase >= 0.0 && oscillator.phase < 1.0,
                  "phase must remain normalized");

    // All waveform corners and pulse width extremes must stay finite.
    for (float shape : {0.0f, 0.25f, 0.5f, 0.75f, 1.0f}) {
        for (float pulseWidth : {0.05f, 0.5f, 0.95f}) {
            oscillator.reset();
            for (int i = 0; i < 4096; ++i) {
                const auto frame = oscillator.process(9000.0, sampleRate, shape, pulseWidth);
                if (!std::isfinite(frame.sine) || !std::isfinite(frame.morph)) {
                    okay &= check(false, "high-frequency morph/PWM render non-finite");
                    break;
                }
            }
        }
    }

    // Wave shape must transition continuously across the sine/saw and
    // saw/pulse boundaries. Two identically phased voices must agree
    // when separated by an infinitesimal morph change.
    MorphOscillator a, b;
    for (int i = 0; i < 1024; ++i) {
        a.process(330.0, sampleRate, 0.5f, 0.5f);
        b.process(330.0, sampleRate, 0.5f, 0.5f);
    }
    const auto left = a.process(330.0, sampleRate, 0.499999f, 0.5f);
    const auto right = b.process(330.0, sampleRate, 0.500001f, 0.5f);
    okay &= check(std::fabs(left.morph - right.morph) < 0.001f,
                  "wave morph must be continuous at saw boundary");
    okay &= check(std::fabs(left.sine - right.sine) < 0.00001f,
                  "sine phase must not depend on morph position");

    // Verify polyBLEP does correct both sides of a discontinuity.
    okay &= check(std::fabs(MorphOscillator::polyBlep(0.0, 0.125) + 1.0) < 1.0e-12,
                  "polyBLEP leading-edge correction missing");
    okay &= check(MorphOscillator::polyBlep(0.99, 0.125) > 0.0,
                  "polyBLEP trailing-edge correction missing");
    okay &= check(MorphOscillator::polyBlep(0.5, 0.125) == 0.0,
                  "polyBLEP must be zero away from edges");

    // Invalid host inputs must not propagate NaNs into the signal.
    const auto invalid = oscillator.process(std::numeric_limits<double>::quiet_NaN(),
                                            sampleRate, 0.5f, 0.5f);
    okay &= check(invalid.sine == 0.0f && invalid.morph == 0.0f,
                  "invalid frequency must output silence");
    oscillator.reset();
    okay &= check(oscillator.phase == 0.0 && !oscillator.initialized,
                  "reset must clear oscillator state");

    if (okay)
        std::puts("PASS: Morph VCO standalone DSP smoke");
    return okay ? 0 : 1;
}
