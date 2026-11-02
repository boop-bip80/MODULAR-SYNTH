/*
 * Original MODULAR-SYNTH FM Voice standalone DSP regression.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Compiles without Rack, audio hardware, heap allocation or third-party SDKs.
 */
#include "../plugins/ModularSynth/src/FMVoice.hpp"

#include <cmath>
#include <cstdio>
#include <limits>

using modular_synth::dsp::FMVoice;

namespace {
bool check(bool okay, const char* label) {
    if (!okay)
        std::fprintf(stderr, "FAIL: %s\n", label);
    return okay;
}
}

int main() {
    bool okay = true;
    const double c4 = FMVoice::frequencyForPitch(0.0);
    okay &= check(std::abs(c4 - 261.6255653) < 1.0e-6, "C4 pitch");
    okay &= check(std::abs(FMVoice::frequencyForPitch(1.0) / c4 - 2.0) < 1.0e-10,
                  "1 V/oct pitch doubling");
    okay &= check(std::abs(FMVoice::frequencyForPitch(-1.0) / c4 - 0.5) < 1.0e-10,
                  "1 V/oct pitch halving");
    okay &= check(FMVoice::finite(FMVoice::frequencyForPitch(999.0)),
                  "extreme pitch must clamp finite");
    okay &= check(!FMVoice::finite(std::numeric_limits<double>::infinity())
                  && !FMVoice::finite(std::numeric_limits<float>::quiet_NaN()),
                  "bitwise NaN/Inf detection under fast-math");
    okay &= check(FMVoice::frequencyForPitch(
                      std::numeric_limits<double>::quiet_NaN()) == c4,
                  "invalid pitch falls back to C4");

    FMVoice dry;
    FMVoice::Input plain;
    plain.frequencyHz = 440.0;
    plain.sampleRateHz = 48000.0;
    plain.ratio = 1.0;
    plain.indexRadians = 0.0;
    for (int n = 0; n < 960; ++n) {
        const auto out = dry.process(plain);
        const double ideal = std::sin(FMVoice::kTwoPi * (n * 440.0 / 48000.0));
        okay &= check(std::abs(out.carrier - ideal) < 1.0e-5,
                      "index zero must reproduce unmodulated sine");
        okay &= check(std::abs(out.modulator - ideal) < 1.0e-5,
                      "ratio one raw modulator matches unmodulated carrier");
    }

    FMVoice modulated;
    FMVoice::Input rich = plain;
    rich.ratio = 2.0;
    rich.indexRadians = 3.0;
    double carrierDifference = 0.0;
    double modulatorEnergy = 0.0;
    for (int n = 0; n < 960; ++n) {
        const auto actual = modulated.process(rich);
        const double ideal = std::sin(FMVoice::kTwoPi * (n * 440.0 / 48000.0));
        carrierDifference += std::abs(actual.carrier - ideal);
        modulatorEnergy += actual.modulator * actual.modulator;
        okay &= check(FMVoice::finite(actual.carrier) && FMVoice::finite(actual.modulator),
                      "FM samples always finite");
        okay &= check(std::abs(actual.carrier) <= 1.00001
                      && std::abs(actual.modulator) <= 1.00001,
                      "FM sine outputs stay bounded to unit amplitude");
    }
    okay &= check(carrierDifference > 100.0,
                  "nonzero index must alter the carrier waveform");
    okay &= check(modulatorEnergy > 100.0,
                  "ratio-two modulator must produce a substantial signal");

    FMVoice smoothed;
    FMVoice::Input step = plain;
    step.indexRadians = 0.0;
    step.ratio = 1.0;
    step.feedback = 0.0;
    smoothed.process(step);
    step.indexRadians = 8.0;
    step.ratio = 16.0;
    step.feedback = 0.95;
    smoothed.process(step);
    okay &= check(smoothed.smoothedIndex > 0.0 && smoothed.smoothedIndex < 8.0,
                  "index CV step is smoothed");
    okay &= check(smoothed.smoothedRatio > 1.0 && smoothed.smoothedRatio < 16.0,
                  "ratio CV step is smoothed");
    okay &= check(smoothed.smoothedFeedback > 0.0 && smoothed.smoothedFeedback < 0.95,
                  "feedback CV step is smoothed");
    for (int n = 0; n < 5000; ++n)
        smoothed.process(step);
    okay &= check(std::abs(smoothed.smoothedIndex - 8.0) < 1.0e-10
                  && std::abs(smoothed.smoothedFeedback - 0.95) < 1.0e-10,
                  "smoothed controls converge to targets");

    const double priorPhase = smoothed.carrierPhase;
    step.sampleRateHz = 96000.0;
    smoothed.process(step);
    okay &= check(std::abs(smoothed.carrierPhase
                          - std::fmod(priorPhase + 440.0 / 96000.0, 1.0)) < 1.0e-9,
                  "sample-rate change preserves phase");
    const double phaseBeforeInvalid = smoothed.carrierPhase;
    step.sampleRateHz = std::numeric_limits<double>::infinity();
    const auto silence = smoothed.process(step);
    okay &= check(silence.carrier == 0.0f && silence.modulator == 0.0f
                  && smoothed.carrierPhase == phaseBeforeInvalid,
                  "invalid sample rate mutes without corrupting phase");

    FMVoice invalid;
    step.sampleRateHz = 48000.0;
    step.ratio = std::numeric_limits<double>::infinity();
    step.indexRadians = std::numeric_limits<double>::quiet_NaN();
    step.feedback = -100.0;
    for (int n = 0; n < 10000; ++n) {
        const auto output = invalid.process(step);
        okay &= check(FMVoice::finite(output.carrier) && FMVoice::finite(output.modulator),
                      "invalid controls must not leak NaN/Inf");
        okay &= check(invalid.carrierPhase >= 0.0 && invalid.carrierPhase < 1.0
                      && invalid.modulatorPhase >= 0.0 && invalid.modulatorPhase < 1.0,
                      "invalid controls maintain normalized phase");
    }

    FMVoice high;
    FMVoice::Input extreme = plain;
    extreme.frequencyHz = 1.0e12;
    extreme.ratio = 1.0e12;
    extreme.indexRadians = 1.0e12;
    extreme.feedback = 1.0e12;
    for (int n = 0; n < 5000; ++n) {
        const auto output = high.process(extreme);
        okay &= check(FMVoice::finite(output.carrier) && FMVoice::finite(output.modulator),
                      "extreme frequency/controls must produce finite output");
        okay &= check(high.carrierPhase < 1.0 && high.modulatorPhase < 1.0,
                      "Nyquist step cap preserves normalized phase");
    }

    FMVoice lanes[16];
    for (int n = 0; n < 777; ++n)
        for (int c = 0; c < 16; ++c) {
            FMVoice::Input voiceInput = plain;
            voiceInput.frequencyHz = 110.0 * (1.0 + c / 8.0);
            lanes[c].process(voiceInput);
        }
    okay &= check(lanes[0].carrierPhase != lanes[15].carrierPhase,
                  "polyphonic lanes have independent phase");
    modulated.reset();
    FMVoice fresh;
    const auto resetSample = modulated.process(rich);
    const auto firstSample = fresh.process(rich);
    okay &= check(resetSample.carrier == firstSample.carrier
                  && resetSample.modulator == firstSample.modulator,
                  "reset reproduces a fresh voice and discards feedback history");

    if (okay)
        std::puts("PASS: FM Voice standalone DSP pitch, modulation, controls, reset and finite safeguards");
    return okay ? 0 : 1;
}
