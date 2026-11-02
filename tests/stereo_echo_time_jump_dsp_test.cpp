/*
 * MODULAR-SYNTH StereoEcho abrupt delay-time modulation regression.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Standalone C++17: quantify adjacent-sample output jumps while the delay
 * knob moves abruptly, without using Rack or any external audio files.
 * The optional header override permits comparison to an earlier DSP revision.
 */
#ifndef STEREO_ECHO_IMPL_HEADER
#define STEREO_ECHO_IMPL_HEADER "../plugins/ModularSynth/src/StereoEcho.hpp"
#endif
#include STEREO_ECHO_IMPL_HEADER

#include <algorithm>
#include <cmath>
#include <cstdio>

using modular_synth::dsp::StereoEchoDSP;

namespace {

int failures = 0;

void expect(bool valid, const char* message) {
    if (!valid) {
        ++failures;
        std::fprintf(stderr, "FAIL StereoEcho time jump: %s\n", message);
    }
}

void testAbruptTimeJumps(int rate, double jumpedDelayMs, double maxStepVolts) {
    constexpr double pi = 3.14159265358979323846;
    constexpr double toneHz = 523.25;
    constexpr double amplitude = 4.0;
    constexpr double initialDelayMs = 7.0;
    const int firstJump = rate * 3 / 5;              // 600 ms of filled history
    const int crossfadeFrames = rate / 40;            // nominal 25 ms
    const int secondJump = firstJump + 2 * crossfadeFrames;
    const int end = secondJump + crossfadeFrames + rate / 100;
    const int measureSpan = crossfadeFrames + rate / 200;

    StereoEchoDSP echo;
    float previousLeft = 0.0f;
    double peakUp = 0.0;
    double peakDown = 0.0;
    double stereoError = 0.0;
    for (int i = 0; i < end; ++i) {
        const double inputL = amplitude * std::sin(2.0 * pi * toneHz * i / rate);
        const double inputR = -0.5 * inputL;
        const double delayMs = i < firstJump || i >= secondJump
            ? initialDelayMs : jumpedDelayMs;
        const auto sample = echo.process(
            inputL, inputR, rate, delayMs, 0.0, 1.0, 0.0);
        stereoError = std::max(stereoError,
                               std::abs(sample.right + 0.5 * sample.left));
        if (i > 0 && i >= firstJump && i < firstJump + measureSpan)
            peakUp = std::max(peakUp,
                              std::abs(static_cast<double>(sample.left - previousLeft)));
        if (i > 0 && i >= secondJump && i < secondJump + measureSpan)
            peakDown = std::max(peakDown,
                                std::abs(static_cast<double>(sample.left - previousLeft)));
        previousLeft = sample.left;
    }

    std::printf("TIME_JUMP rate=%d Hz 7->%.0f->7 ms: peak_up=%.6f V "
                "peak_down=%.6f V stereo_error=%.9g V\n",
                rate, jumpedDelayMs, peakUp, peakDown, stereoError);
    expect(peakUp < maxStepVolts && peakDown < maxStepVolts,
           "abrupt delay-time changes must not skip through the ring in one sample");
    expect(stereoError < 1.0e-5,
           "left and right delays must share a coherent crossfade envelope");
}

void testDeferredJumpAndReset() {
    constexpr int rate = 48000;
    constexpr int fadeFrames = rate / 40;
    StereoEchoDSP echo;
    echo.process(0.0, 0.0, rate, 7.0, 0.5, 1.0, 0.0);
    // Start a 7 -> 200 ms fade, then revise the target to 300 ms while
    // the first fade is still active. The second target must be honored.
    echo.process(0.0, 0.0, rate, 200.0, 0.5, 1.0, 0.0);
    for (int i = 0; i < 2 * fadeFrames + 4; ++i) {
        const auto out = echo.process(
            0.0, 0.0, rate, 300.0, 0.5, 1.0, 0.0);
        expect(out.left == 0.0f && out.right == 0.0f,
               "deferred time changes may not create phantom audio");
    }
    expect(std::abs(echo.currentDelaySamples() - 14400.0) < 0.0001,
           "a changed target during a crossfade must be applied after the fade");

    // A reset must discard both read heads, any in-progress transition,
    // and the old ring history without clearing megabytes.
    echo.process(1.0, 0.0, rate, 500.0, 0.5, 1.0, 0.0);
    echo.reset();
    const auto postReset = echo.process(
        0.0, 0.0, rate, 25.0, 0.5, 1.0, 0.0);
    expect(postReset.left == 0.0f && postReset.right == 0.0f,
           "reset during a time crossfade must invalidate both read heads");
    expect(std::abs(echo.currentDelaySamples() - 1200.0) < 0.0001,
           "reset must initialize the next time target without a stale fade");
}

} // namespace

int main() {
    testAbruptTimeJumps(48000, 200.0, 0.42);
    testAbruptTimeJumps(384000, 450.0, 0.09);
    testDeferredJumpAndReset();
    if (failures) {
        std::fprintf(stderr, "StereoEcho time jump: %d failure(s)\n", failures);
        return 1;
    }
    std::puts("PASS: StereoEcho bounded stereo-coherent time-jump transitions at 48/384 kHz");
    return 0;
}
