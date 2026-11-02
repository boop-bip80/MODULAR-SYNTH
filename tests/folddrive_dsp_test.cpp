/*
 * MODULAR-SYNTH FoldDrive standalone DSP contract and stress checks.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Compiles without Rack, including aggressive -ffast-math and UBSan.
 */
#include "../plugins/ModularSynth/src/FoldDrive.hpp"

#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>

using modular_synth::dsp::FoldDrive;

static void require(bool condition, const char* message) {
    if (!condition) {
        std::fprintf(stderr, "FAIL FoldDrive: %s\n", message);
        std::exit(EXIT_FAILURE);
    }
}

static void closeTo(float actual, double expected, double epsilon, const char* message) {
    require(FoldDrive::ieeeFinite(actual), "output finite");
    require(std::abs(static_cast<double>(actual) - expected) <= epsilon, message);
}

static void checkPassthroughAndFold() {
    FoldDrive voice;
    for (int i = -20; i <= 20; ++i) {
        const double in = i * 0.5;
        voice.reset();
        closeTo(voice.process(in, 48000.0, 0.95, 0.42, 0.0), in, 1e-6,
                "MIX=0 must be exact dry audio");
        voice.reset();
        closeTo(voice.process(in, 48000.0, 0.0, 0.0, 1.0), in, 1e-6,
                "DRIVE=0 with zero bias must be transparent");
    }

    voice.reset();
    const float folded = voice.process(1.5, 48000.0, 1.0, 0.0, 1.0);
    require(folded < -3.0f, "strong sine folding must invert some positive wave sections");
    voice.reset();
    const float mirrored = voice.process(-1.5, 48000.0, 1.0, 0.0, 1.0);
    closeTo(mirrored, -folded, 1e-6, "zero-bias wavefold must be odd-symmetric");

    voice.reset();
    const float positive = voice.process(2.2, 48000.0, 0.8, 0.6, 1.0);
    voice.reset();
    const float negative = voice.process(-2.2, 48000.0, 0.8, 0.6, 1.0);
    require(std::abs(positive + negative) > 0.1f,
            "BIAS must introduce audible asymmetric harmonics");
    voice.reset();
    closeTo(voice.process(0.0, 48000.0, 1.0, 0.8, 1.0), 0.0, 1e-6,
            "bias baseline subtraction must preserve silence at zero input");
}

static void checkCVSlewAndLifecycle() {
    FoldDrive voice;
    const float dry = voice.process(1.5, 48000.0, 1.0, 0.0, 0.0);
    const float firstTransition = voice.process(1.5, 48000.0, 1.0, 0.0, 1.0);
    require(std::abs(firstTransition - dry) < 0.1f,
            "sudden wet CV must slew in small sample increments");
    for (int frame = 0; frame < 3000; ++frame)
        voice.process(1.5, 48000.0, 1.0, 0.0, 1.0);
    const float settled = voice.process(1.5, 48000.0, 1.0, 0.0, 1.0);
    require(settled < -3.0f, "wet CV must settle after a bounded time");

    voice.reset();
    closeTo(voice.process(1.5, 48000.0, 1.0, 0.0, 0.0), 1.5, 1e-6,
            "retired channel must reset old wet state");
    voice.reset();
    closeTo(voice.process(1.5, 48000.0, 1.0, 0.0, 1.0), settled, 1e-5,
            "new channel must initialize at requested CV, without old slew");

    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double inf = std::numeric_limits<double>::infinity();
    voice.reset();
    closeTo(voice.process(2.0, 48000.0, nan, inf, -inf), 2.0, 1e-6,
            "invalid knobs and CV must fall back to dry-safe controls");
    closeTo(voice.process(3.0, nan, 1.0, 0.0, 1.0), 0.0, 1e-6,
            "invalid sample rate must produce silence and reset state");
    closeTo(voice.process(2.0, 48000.0, 1.0, 0.0, 0.0), 2.0, 1e-6,
            "valid first sample following invalid sample rate reinitializes");
}

static void checkHostileInputs() {
    constexpr double huge = std::numeric_limits<double>::max();
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double inf = std::numeric_limits<double>::infinity();
    const std::array<double, 15> values{{
        -huge, -inf, -1000000.0, -100.0, -10.0, -5.0, -0.01,
        0.0, 0.01, 5.0, 10.0, 100.0, 1000000.0, inf, nan
    }};
    constexpr std::array<double, 4> rates{{44100.0, 48000.0, 96000.0, 192000.0}};
    FoldDrive voice;
    std::uint32_t state = 0x51A8D5u;
    for (double rate : rates) {
        voice.reset();
        for (int i = 0; i < 70000; ++i) {
            state ^= state << 13;
            state ^= state >> 17;
            state ^= state << 5;
            const auto at = [&](unsigned divisor) -> double {
                return values[(state / divisor) % values.size()];
            };
            const float result = voice.process(at(1), rate, at(13), at(17), at(23));
            require(FoldDrive::ieeeFinite(result), "hostile input must remain finite");
            require(result >= -10.0f && result <= 10.0f,
                    "output stays within strict +/-10V including hostile automation");
        }
    }
}

int main() {
    checkPassthroughAndFold();
    checkCVSlewAndLifecycle();
    checkHostileInputs();
    std::puts("PASS FoldDrive: transparency, musical folds, asymmetry, CV slew, lifecycle, invalid controls and 280k bounded hostile samples");
}
