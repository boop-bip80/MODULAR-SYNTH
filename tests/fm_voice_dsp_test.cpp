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

    // A Carson-style sideband ceiling deliberately rolls off FM index near
    // Nyquist. The coherent 21 kHz alias here comes from 3 kHz carrier
    // plus the second 12 kHz modulator sideband (27 kHz folded to 21 kHz).
    // Measure that alias bin against the previous unrestricted PM equation;
    // this is a *selected-bin* regression, not proof of alias-free FM.
    okay &= check(std::abs(FMVoice::bandwidthIndexCeiling(
                     3000.0, 12000.0, 48000.0) - 0.55) < 1.0e-12,
                  "high-frequency FM index ceiling matches bandwidth guard");
    okay &= check(FMVoice::bandwidthIndexCeiling(
                     440.0, 880.0, 48000.0) == 8.0,
                  "low-note musical FM indices remain unaltered");
    FMVoice guarded;
    FMVoice::Input bright = plain;
    bright.frequencyHz = 3000.0;
    bright.ratio = 4.0;
    bright.indexRadians = 3.0;
    constexpr int kSamples = 4800;
    double oldRe = 0.0, oldIm = 0.0;
    double guardedRe = 0.0, guardedIm = 0.0;
    for (int n = 0; n < kSamples; ++n) {
        const double carPhase = FMVoice::kTwoPi * n * 3000.0 / 48000.0;
        const double modPhase = FMVoice::kTwoPi * n * 12000.0 / 48000.0;
        const double oldCarrier = std::sin(carPhase + 3.0 * std::sin(modPhase));
        const double newCarrier = guarded.process(bright).carrier;
        const double analysisPhase = FMVoice::kTwoPi * n * 21000.0 / 48000.0;
        const double cosine = std::cos(analysisPhase);
        const double sine = std::sin(analysisPhase);
        oldRe += oldCarrier * cosine;
        oldIm -= oldCarrier * sine;
        guardedRe += newCarrier * cosine;
        guardedIm -= newCarrier * sine;
    }
    const double oldAlias = 2.0 * std::hypot(oldRe, oldIm) / kSamples;
    const double guardedAlias = 2.0 * std::hypot(guardedRe, guardedIm) / kSamples;
    const double reductionDb = 20.0 * std::log10(oldAlias / guardedAlias);
    okay &= check(oldAlias > 0.9 && guardedAlias < 0.1 && reductionDb > 20.0,
                  "coherent 21 kHz folded sideband reduced at least 20 dB");
    std::printf("FM coherent 21k alias: old=%.6f, guarded=%.6f, %.2f dB lower\n",
                oldAlias, guardedAlias, reductionDb);

    // Second high-note case: 6 kHz carrier, 12 kHz modulator and a
    // 30 kHz upper sideband folding to 18 kHz at 48 kHz. The guard reduces
    // this selected alias bin as well, not only one handpicked frequency.
    FMVoice highBright;
    FMVoice::Input highNote = plain;
    highNote.frequencyHz = 6000.0;
    highNote.ratio = 2.0;
    highNote.indexRadians = 3.0;
    double highOldRe = 0.0, highOldIm = 0.0;
    double highNewRe = 0.0, highNewIm = 0.0;
    for (int n = 0; n < kSamples; ++n) {
        const double carrierP = FMVoice::kTwoPi * n * 6000.0 / 48000.0;
        const double modP = FMVoice::kTwoPi * n * 12000.0 / 48000.0;
        const double oldSample = std::sin(carrierP + 3.0 * std::sin(modP));
        const double newSample = highBright.process(highNote).carrier;
        const double targetP = FMVoice::kTwoPi * n * 18000.0 / 48000.0;
        highOldRe += oldSample * std::cos(targetP);
        highOldIm -= oldSample * std::sin(targetP);
        highNewRe += newSample * std::cos(targetP);
        highNewIm -= newSample * std::sin(targetP);
    }
    const double highOldAlias = 2.0 * std::hypot(highOldRe, highOldIm) / kSamples;
    const double highNewAlias = 2.0 * std::hypot(highNewRe, highNewIm) / kSamples;
    okay &= check(20.0 * std::log10(highOldAlias / highNewAlias) > 15.0,
                  "second coherent high-note alias bin reduced at least 15 dB");
    std::printf("FM coherent 18k alias: old=%.6f, guarded=%.6f, %.2f dB lower\n",
                highOldAlias, highNewAlias,
                20.0 * std::log10(highOldAlias / highNewAlias));

    // Abrupt pitch+ratio CV changes cannot cause an instantaneous guard
    // index step: the ceiling itself slews ~2 ms. The oscillator phase
    // remains continuous. This is a control continuity check; a pitch
    // jump can still cause wideband transient energy or an audible click.
    FMVoice swept;
    FMVoice::Input sweep = plain;
    sweep.ratio = 2.0;
    sweep.indexRadians = 6.0;
    for (int n = 0; n < 256; ++n)
        swept.process(sweep);
    double previousIndex = std::min(swept.smoothedIndex,
                                    swept.smoothedGuardCeiling);
    const double phaseBeforeJump = swept.carrierPhase;
    sweep.frequencyHz = 6000.0;
    sweep.ratio = 4.0;
    for (int n = 0; n < 2048; ++n) {
        const auto output = swept.process(sweep);
        const double effective = std::min(swept.smoothedIndex,
                                          swept.smoothedGuardCeiling);
        okay &= check(std::abs(effective - previousIndex) <= 0.085,
                      "guard threshold crossing cannot step index abruptly");
        okay &= check(FMVoice::finite(output.carrier) &&
                      FMVoice::finite(output.modulator),
                      "steep pitch CV must preserve bounded finite output");
        if (n == 0)
            okay &= check(std::abs(swept.carrierPhase -
                std::fmod(phaseBeforeJump + 6000.0 / 48000.0, 1.0)) < 1.0e-9,
                "pitch CV jump must preserve carrier phase accumulator");
        previousIndex = effective;
    }
    okay &= check(previousIndex < 0.001,
                  "slewed high-frequency ceiling converges to index zero");

    FMVoice lowVoice;
    FMVoice::Input low = plain;
    low.ratio = 2.0;
    low.indexRadians = 8.0;
    for (int n = 0; n < 256; ++n) {
        const double expected = std::sin(
            FMVoice::kTwoPi * n * 440.0 / 48000.0
            + 8.0 * std::sin(FMVoice::kTwoPi * n * 880.0 / 48000.0));
        const auto output = lowVoice.process(low);
        okay &= check(std::abs(output.carrier - expected) < 2.0e-5,
                      "low-frequency FM must keep the full saved index");
    }

    FMVoice huge;
    FMVoice::Input maximum = plain;
    maximum.frequencyHz = std::numeric_limits<double>::max();
    maximum.ratio = 16.0;
    maximum.indexRadians = 8.0;
    for (int n = 0; n < 256; ++n) {
        const auto output = huge.process(maximum);
        okay &= check(FMVoice::finite(output.carrier) &&
                      FMVoice::finite(output.modulator),
                      "DBL_MAX carrier with ratio must remain finite");
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
