/*
 * Standalone DualVCA regressions, no Rack/host required.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "plugins/ModularSynth/src/DualVCA.hpp"

#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>

using modular_synth::dsp::DualVCA;

static void require(bool okay, const char* description) {
    if (!okay) {
        std::fprintf(stderr, "FAIL DualVCA: %s\n", description);
        std::exit(1);
    }
}

static void near(double got, double expected, double tolerance,
                 const char* description) {
    require(DualVCA::finite(got) && std::abs(got - expected) <= tolerance,
            description);
}

static void testUnityAndCurves() {
    DualVCA voice;
    DualVCA::Input in;
    in.inputVoltage = 5.0;
    near(voice.process(in), 5.0, 0.000001, "unpatched CV must be unity");
    voice.reset();
    in.level = 0.5;
    near(voice.process(in), 2.5, 0.000001, "level knob caps unity gain");
    voice.reset();
    in.level = 1.0;
    in.cvConnected = true;
    in.cvVolts = 0.0;
    near(voice.process(in), 0.0, 0.000001, "connected zero CV mutes");
    voice.reset();
    in.cvVolts = -10.0;
    near(voice.process(in), 0.0, 0.000001, "negative CV cannot invert audio");
    voice.reset();
    in.cvVolts = 5.0;
    in.curve = 0.0;
    near(voice.process(in), 2.5, 0.000001, "linear CV at five volts");
    voice.reset();
    in.curve = 1.0;
    near(voice.process(in), 0.625, 0.000001, "cubic CV at five volts");
    voice.reset();
    in.cvVolts = 10.0;
    near(voice.process(in), 5.0, 0.000001, "both curves reach unity at 10V");
    voice.reset();
    in.cvVolts = 30.0;
    near(voice.process(in), 5.0, 0.000001, "overvoltage CV clamps to unity");
}

static void testSlewAndLifecycle() {
    DualVCA voice;
    DualVCA::Input in;
    in.inputVoltage = 5.0;
    in.cvConnected = true;
    in.cvVolts = 10.0;
    near(voice.process(in), 5.0, 0.000001, "new voice starts at requested CV");
    in.cvVolts = 0.0;
    const double afterOne = voice.process(in);
    require(afterOne > 4.9 && afterOne < 5.0,
            "large CV cut must be slewed over multiple samples");
    for (int sample = 0; sample < 3000; ++sample)
        voice.process(in);
    require(std::abs(voice.process(in)) < 1e-5,
            "gain envelope must settle to silence");
    voice.reset();
    in.cvVolts = 10.0;
    near(voice.process(in), 5.0, 0.000001,
         "retired/reset lane cannot reuse previous muted gain state");
    in.sampleRateHz = 0.0;
    near(voice.process(in), 0.0, 0.000001,
         "invalid sample rate returns silence and clears state");
    in.sampleRateHz = 48000.0;
    in.cvVolts = 0.0;
    near(voice.process(in), 0.0, 0.000001,
         "post-invalid-rate lane initializes at requested gain");
}

static void testHeadroomAndHostileAutomation() {
    DualVCA voice;
    DualVCA::Input in;
    in.inputVoltage = 20.0;
    near(voice.process(in), 10.0, 0.000001,
         "amplifier output caps at +10V");
    voice.reset();
    in.inputVoltage = -20.0;
    near(voice.process(in), -10.0, 0.000001,
         "amplifier output caps at -10V");
    near(DualVCA::boundedSum(7.0f, 7.0f), 10.0, 0.000001,
         "sum output must cap positive mixed audio");
    near(DualVCA::boundedSum(-7.0f, -7.0f), -10.0, 0.000001,
         "sum output must cap negative mixed audio");
    near(DualVCA::boundedSum(4.0f, -2.0f), 2.0, 0.000001,
         "sum output must preserve lawful signed mixes");

    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double inf = std::numeric_limits<double>::infinity();
    const double huge = std::numeric_limits<double>::max();
    const std::array<double, 13> hostile{{
        -huge, -inf, -1e9, -20.0, -5.0, -0.01, 0.0,
        0.01, 5.0, 20.0, 1e9, inf, nan
    }};
    std::array<DualVCA, 16> poly;
    unsigned seed = 0x8953491u;
    for (int frame = 0; frame < 60000; ++frame) {
        for (unsigned channel = 0; channel < poly.size(); ++channel) {
            seed ^= seed << 13;
            seed ^= seed >> 17;
            seed ^= seed << 5;
            DualVCA::Input sample;
            sample.inputVoltage = hostile[(seed + channel) % hostile.size()];
            sample.sampleRateHz = frame % 2 ? 44100.0 : 96000.0;
            sample.level = hostile[(seed / 3) % hostile.size()];
            sample.cvVolts = hostile[(seed / 7) % hostile.size()];
            sample.curve = hostile[(seed / 11) % hostile.size()];
            sample.cvConnected = frame % 3 != 0;
            const float result = poly[channel].process(sample);
            require(DualVCA::finite(result), "hostile poly audio remains finite");
            require(result >= -10.0f && result <= 10.0f,
                    "hostile poly output remains inside +/-10V");
        }
    }
    in.inputVoltage = 5.0;
    in.level = nan;
    in.cvConnected = false;
    voice.reset();
    near(voice.process(in), 0.0, 0.000001,
         "invalid gain knob fails closed to zero");
    in.level = 1.0;
    in.cvConnected = true;
    in.cvVolts = nan;
    voice.reset();
    near(voice.process(in), 0.0, 0.000001,
         "invalid connected CV fails closed to zero");
    in.cvVolts = inf;
    voice.reset();
    near(voice.process(in), 0.0, 0.000001,
         "infinite connected CV fails closed to zero");
}

int main() {
    testUnityAndCurves();
    testSlewAndLifecycle();
    testHeadroomAndHostileAutomation();
    std::puts("PASS DualVCA: normalled CV, level/curve, slew, reset, bounded mix and hostile 16-lane automation");
}
