/*
 * Original MODULAR-SYNTH FM Voice standalone DSP regression.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Compiles without Rack, audio hardware, heap allocation or third-party SDKs.
 */
#include "../plugins/ModularSynth/src/FMVoice.hpp"

#include <cmath>
#include <cstddef>
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

    // Tiny positive frequencies are valid but unusable as audio.  They
    // must neither accidentally disable the FM bandwidth guard through
    // floating-point division overflow nor accumulate subnormal phases.
    okay &= check(FMVoice::bandwidthIndexCeiling(
                      440.0, std::numeric_limits<double>::denorm_min(),
                      48000.0) == FMVoice::kMaxIndexRadians,
                  "near-zero modulator preserves the full FM guard ceiling");
    FMVoice subaudio;
    FMVoice::Input tiny;
    tiny.frequencyHz = std::numeric_limits<double>::denorm_min();
    tiny.ratio = 16.0;
    tiny.indexRadians = 8.0;
    tiny.feedback = -0.95;
    for (int n = 0; n < 512; ++n) {
        const auto output = subaudio.process(tiny);
        okay &= check(output.carrier == 0.0f && output.modulator == 0.0f,
                      "sub-audio direct DSP does not leak denormal samples");
    }
    okay &= check(subaudio.carrierPhase == 0.0 && subaudio.modulatorPhase == 0.0,
                  "sub-audio direct DSP avoids subnormal phase accumulation");
    tiny.frequencyHz = FMVoice::frequencyForPitch(-20.0);
    subaudio.process(tiny);
    okay &= check(subaudio.carrierPhase > 0.0 && subaudio.modulatorPhase > 0.0,
                  "Rack's lowest supported 1V/oct frequency still advances phase");

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

    // A new higher frequency must immediately lower the *effective* PM
    // index. Delaying that protection for two milliseconds leaves an alias
    // burst; allowing a downward timbre step is preferable to extra
    // Nyquist-folded sidebands on the already-discontinuous pitch jump.
    // Returning to the low note still restores brightness over ~2 ms.
    FMVoice swept;
    FMVoice::Input sweep = plain;
    sweep.ratio = 2.0;
    sweep.indexRadians = 6.0;
    for (int n = 0; n < 256; ++n)
        swept.process(sweep);
    const double phaseBeforeJump = swept.carrierPhase;
    sweep.frequencyHz = 6000.0;
    sweep.ratio = 4.0;
    for (int n = 0; n < 2048; ++n) {
        const auto output = swept.process(sweep);
        const double effective = std::min(swept.smoothedIndex,
                                          swept.smoothedGuardCeiling);
        const double instantaneousCeiling = FMVoice::bandwidthIndexCeiling(
            sweep.frequencyHz, sweep.frequencyHz * swept.smoothedRatio,
            sweep.sampleRateHz);
        okay &= check(swept.smoothedGuardCeiling <= instantaneousCeiling + 1.0e-10,
                      "high-note FM index ceiling never exceeds immediate bandwidth limit");
        okay &= check(FMVoice::finite(output.carrier) &&
                      FMVoice::finite(output.modulator),
                      "steep pitch CV must preserve bounded finite output");
        if (n == 0)
            okay &= check(std::abs(swept.carrierPhase -
                std::fmod(phaseBeforeJump + 6000.0 / 48000.0, 1.0)) < 1.0e-9,
                "pitch CV jump must preserve carrier phase accumulator");
        if (n == 0)
            okay &= check(std::abs(swept.smoothedGuardCeiling
                                    - instantaneousCeiling) < 1.0e-10
                          && effective <= instantaneousCeiling + 1.0e-10,
                          "first high-note sample immediately protects Nyquist index");
    }
    okay &= check(swept.smoothedGuardCeiling == 0.0,
                  "high-frequency ceiling stays at safe zero index");
    sweep.frequencyHz = 440.0;
    sweep.ratio = 2.0;
    const double beforeRelease = swept.smoothedGuardCeiling;
    swept.process(sweep);
    okay &= check(swept.smoothedGuardCeiling > beforeRelease
                  && swept.smoothedGuardCeiling < 0.085,
                  "returning to low note restores guard brightness gradually");
    for (int n = 0; n < 4096; ++n)
        swept.process(sweep);
    okay &= check(std::abs(swept.smoothedGuardCeiling - 8.0) < 1.0e-9,
                  "low-note release reaches full index ceiling");

    // Coherent first-2-ms alias analysis after a pitch CV jump. The old
    // symmetric one-pole guard remains at the former 8-radian ceiling for
    // this whole 96-frame window and therefore permits a full index of 3.
    // The new one-sided guard clamps to 0.55 on the first high-pitch frame.
    // This tests a measured *selected* folded sideband, not all aliases.
    FMVoice attackSafe;
    FMVoice::Input instantJump = plain;
    instantJump.ratio = 4.0;
    instantJump.indexRadians = 3.0;
    // 1,200 samples of 440/1,760 Hz complete integer phase cycles before
    // the jump, so the 21 kHz DFT bins are coherent rather than phase-canceled.
    for (int n = 0; n < 1200; ++n)
        attackSafe.process(instantJump);
    double legacyCarrierPhase = attackSafe.carrierPhase;
    double legacyModulatorPhase = attackSafe.modulatorPhase;
    double legacyGuardCeiling = 8.0;
    instantJump.frequencyHz = 3000.0;
    constexpr int kAttackSamples = 96;
    double legacyAttackRe = 0.0, legacyAttackIm = 0.0;
    double safeAttackRe = 0.0, safeAttackIm = 0.0;
    for (int n = 0; n < kAttackSamples; ++n) {
        legacyGuardCeiling += (0.55 - legacyGuardCeiling) / 96.0;
        const double legacySample = std::sin(
            FMVoice::kTwoPi * legacyCarrierPhase
            + std::min(3.0, legacyGuardCeiling)
              * std::sin(FMVoice::kTwoPi * legacyModulatorPhase));
        const auto safer = attackSafe.process(instantJump);
        if (n == 0)
            okay &= check(std::abs(attackSafe.smoothedGuardCeiling - 0.55) < 1.0e-12,
                          "first sample after upward pitch jump clamps to safe ceiling");
        const double phase = FMVoice::kTwoPi * 21000.0 * n / 48000.0;
        legacyAttackRe += legacySample * std::cos(phase);
        legacyAttackIm -= legacySample * std::sin(phase);
        safeAttackRe += safer.carrier * std::cos(phase);
        safeAttackIm -= safer.carrier * std::sin(phase);
        legacyCarrierPhase += 3000.0 / 48000.0;
        legacyModulatorPhase += 12000.0 / 48000.0;
        if (legacyCarrierPhase >= 1.0)
            legacyCarrierPhase -= 1.0;
        if (legacyModulatorPhase >= 1.0)
            legacyModulatorPhase -= 1.0;
    }
    const double legacyAttackAlias = 2.0 * std::hypot(legacyAttackRe,
                                                       legacyAttackIm) / kAttackSamples;
    const double safeAttackAlias = 2.0 * std::hypot(safeAttackRe,
                                                     safeAttackIm) / kAttackSamples;
    const double attackReductionDb = 20.0 * std::log10(
        legacyAttackAlias / std::max(1.0e-12, safeAttackAlias));
    okay &= check(legacyAttackAlias > 0.50 && safeAttackAlias < 0.14
                  && attackReductionDb > 14.0,
                  "pitch-jump folded 21 kHz sideband attenuated in first 2 ms");
    std::printf("FM first-2ms jump 21k alias: old=%.6f, safe=%.6f, %.2f dB lower\n",
                legacyAttackAlias, safeAttackAlias, attackReductionDb);

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


    // The original nonnegative feedback equation is an archived patch
    // contract. Compare its direct recurrence against every new sample,
    // including self-feedback, using independent reference accumulators.
    FMVoice legacyCompatible;
    FMVoice::Input legacyInput = plain;
    legacyInput.ratio = 2.0;
    legacyInput.indexRadians = 3.0;
    legacyInput.feedback = 0.7;
    double referenceCarrierPhase = 0.0;
    double referenceModulatorPhase = 0.0;
    double referencePreviousModulator = 0.0;
    double largestLegacyDelta = 0.0;
    for (int n = 0; n < 4096; ++n) {
        const double oldMod = std::sin(
            FMVoice::kTwoPi * referenceModulatorPhase
            + 0.7 * referencePreviousModulator);
        referencePreviousModulator = oldMod;
        const double oldCarrier = std::sin(
            FMVoice::kTwoPi * referenceCarrierPhase + 3.0 * oldMod);
        const auto now = legacyCompatible.process(legacyInput);
        largestLegacyDelta = std::max<double>(largestLegacyDelta,
            std::max(std::abs(now.carrier - static_cast<float>(oldCarrier)),
                     std::abs(now.modulator - static_cast<float>(oldMod))));
        referenceCarrierPhase += 440.0 / 48000.0;
        referenceModulatorPhase += 880.0 / 48000.0;
        if (referenceCarrierPhase >= 1.0)
            referenceCarrierPhase -= 1.0;
        if (referenceModulatorPhase >= 1.0)
            referenceModulatorPhase -= 1.0;
    }
    okay &= check(largestLegacyDelta < 1.0e-5,
                  "positive feedback reproduces original carrier/modulator recurrence");
    std::printf("FM original positive-feedback maximum delta: %.9g\n",
                largestLegacyDelta);

    // Carrier feedback, unlike modulator feedback, enriches an otherwise
    // pure carrier at INDEX=0. Measure coherent 1500 Hz harmonic at 750 Hz
    // fundamental, at 48 kHz: 4096 samples = exactly 64 cycles.
    FMVoice carrierLoop, modulatorLoop;
    FMVoice::Input signedInput = plain;
    signedInput.frequencyHz = 750.0;
    signedInput.indexRadians = 0.0;
    signedInput.feedback = -0.95;
    FMVoice::Input oldPositive = signedInput;
    oldPositive.feedback = 0.95;
    for (int n = 0; n < 4800; ++n) {
        carrierLoop.process(signedInput);
        modulatorLoop.process(oldPositive);
    }
    double carrierRe = 0.0, carrierIm = 0.0;
    double modRe = 0.0, modIm = 0.0;
    double waveDifference = 0.0;
    for (int n = 0; n < 4096; ++n) {
        const auto negative = carrierLoop.process(signedInput);
        const auto positive = modulatorLoop.process(oldPositive);
        const double angle = FMVoice::kTwoPi * n * 1500.0 / 48000.0;
        carrierRe += negative.carrier * std::cos(angle);
        carrierIm -= negative.carrier * std::sin(angle);
        modRe += positive.carrier * std::cos(angle);
        modIm -= positive.carrier * std::sin(angle);
        waveDifference += std::abs(negative.carrier - positive.carrier);
        okay &= check(FMVoice::finite(negative.carrier)
                      && FMVoice::finite(negative.modulator),
                      "carrier topology outputs remain finite");
    }
    const double carrierSecond = 2.0 * std::hypot(carrierRe, carrierIm) / 4096.0;
    const double modSecond = 2.0 * std::hypot(modRe, modIm) / 4096.0;
    okay &= check(carrierSecond > 0.10 && modSecond < 1.0e-4
                  && waveDifference > 200.0,
                  "negative carrier loop adds a measurable harmonic at index zero");
    std::printf("FM signed feedback 2nd harmonic: carrier=%.6f, "
                "positive-modulator=%.6f; waveform L1=%.2f\n",
                carrierSecond, modSecond, waveDifference);

    // Crossing zero changes topology continuously: near-zero signed
    // feedback perturbations must tend toward the unmodified waveform.
    FMVoice signedLeft, signedZero, signedRight;
    FMVoice::Input zeroCross = plain;
    zeroCross.indexRadians = 2.0;
    double maximumZeroDelta = 0.0;
    for (int n = 0; n < 1024; ++n) {
        zeroCross.feedback = -1.0e-7;
        const auto left = signedLeft.process(zeroCross);
        zeroCross.feedback = 0.0;
        const auto center = signedZero.process(zeroCross);
        zeroCross.feedback = 1.0e-7;
        const auto right = signedRight.process(zeroCross);
        maximumZeroDelta = std::max<double>(maximumZeroDelta,
            std::max(std::abs(left.carrier - center.carrier),
                     std::abs(right.carrier - center.carrier)));
    }
    okay &= check(maximumZeroDelta < 1.0e-5,
                  "feedback topology approaches same waveform from both signs");

    // A full negative-to-positive control jump is slewed by the existing
    // 2 ms state; the ±0.95 topology routes never coexist at full gain.
    FMVoice crossing;
    FMVoice::Input changingSign = plain;
    changingSign.feedback = -0.95;
    for (int n = 0; n < 1024; ++n)
        crossing.process(changingSign);
    double previousFeedback = crossing.smoothedFeedback;
    changingSign.feedback = 0.95;
    bool reachedPositive = false;
    for (int n = 0; n < 4096; ++n) {
        const auto out = crossing.process(changingSign);
        okay &= check(std::abs(crossing.smoothedFeedback - previousFeedback) <= 0.020,
                      "feedback topology sign transition is slew-limited");
        okay &= check(FMVoice::finite(out.carrier) && FMVoice::finite(out.modulator)
                      && std::abs(out.carrier) <= 1.0f
                      && std::abs(out.modulator) <= 1.0f,
                      "feedback sign transition remains finite and bounded");
        reachedPositive |= crossing.smoothedFeedback > 0.0;
        previousFeedback = crossing.smoothedFeedback;
    }
    okay &= check(reachedPositive
                  && std::abs(crossing.smoothedFeedback - 0.95) < 1.0e-10,
                  "signed feedback slew crosses zero and converges");

    // Verify 16 independent lanes with different signed controls, and
    // exact replay after reset even when carrier feedback was active.
    FMVoice signedLanes[16], comparisonLanes[16];
    for (int n = 0; n < 1024; ++n) {
        for (int c = 0; c < 16; ++c) {
            FMVoice::Input input = plain;
            input.frequencyHz = 110.0 + 35.0 * c;
            input.ratio = 1.0 + c / 8.0;
            input.indexRadians = 1.0 + (c % 5);
            input.feedback = (c % 2 == 0 ? -0.95 : 0.95)
                             * (c + 1) / 16.0;
            const auto multi = signedLanes[c].process(input);
            const auto single = comparisonLanes[c].process(input);
            okay &= check(multi.carrier == single.carrier
                          && multi.modulator == single.modulator,
                          "signed 16-voice processing equals isolated voices");
            okay &= check(FMVoice::finite(multi.carrier)
                          && FMVoice::finite(multi.modulator),
                          "signed 16-lane outputs stay finite");
        }
    }
    std::size_t roundedResetSamples = 0;
    double largestResetError = 0.0;
    for (int c = 0; c < 16; ++c) {
        signedLanes[c].reset();
        okay &= check(signedLanes[c].carrierPhase == 0.0
                      && signedLanes[c].modulatorPhase == 0.0
                      && signedLanes[c].smoothedRatio == 1.0
                      && signedLanes[c].smoothedIndex == 0.0
                      && signedLanes[c].smoothedFeedback == 0.0
                      && signedLanes[c].smoothedGuardCeiling == FMVoice::kMaxIndexRadians,
                      "reset clears all exposed oscillator and control states");
        FMVoice pristine;
        FMVoice::Input input = plain;
        input.frequencyHz = 110.0 + 35.0 * c;
        input.ratio = 1.0 + c / 8.0;
        input.indexRadians = 1.0 + (c % 5);
        input.feedback = (c % 2 == 0 ? -0.95 : 0.95)
                         * (c + 1) / 16.0;
        for (int n = 0; n < 256; ++n) {
            const auto replayed = signedLanes[c].process(input);
            const auto first = pristine.process(input);
            const double carrierError = std::abs(static_cast<double>(replayed.carrier)
                                                 - first.carrier);
            const double modulatorError = std::abs(static_cast<double>(replayed.modulator)
                                                   - first.modulator);
            largestResetError = std::max(largestResetError,
                                         std::max(carrierError, modulatorError));
            if (replayed.carrier != first.carrier
                || replayed.modulator != first.modulator) {
                if (roundedResetSamples == 0)
                    std::printf("FM reset first rounding mismatch: lane=%d frame=%d "
                                "carrier_error=%.9g modulator_error=%.9g normalized\n",
                                c, n, carrierError, modulatorError);
                ++roundedResetSamples;
            }
            // A reset array lane and a fresh scalar instance may take
            // different libm/vectorization paths under -O3 -ffast-math.
            // Exact float-bit agreement is not a portable DSP invariant;
            // 2e-6 normalized amplitude is inaudibly small but still
            // detects uncleared one-sample carrier/modulator feedback.
            okay &= check(carrierError <= 2.0e-6 && modulatorError <= 2.0e-6,
                          "reset clears both feedback histories for all lanes");
            if (n == 0)
                okay &= check(replayed.carrier == 0.0f
                              && replayed.modulator == 0.0f,
                              "reset first sample has no feedback-history leakage");
            okay &= check(std::abs(signedLanes[c].carrierPhase
                                   - pristine.carrierPhase) <= 1.0e-12
                          && std::abs(signedLanes[c].modulatorPhase
                                      - pristine.modulatorPhase) <= 1.0e-12
                          && std::abs(signedLanes[c].smoothedFeedback
                                      - pristine.smoothedFeedback) <= 1.0e-12,
                          "reset reproduces pristine phase and feedback control evolution");
        }
    }
    std::printf("FM reset replay: rounded_samples=%zu/4096 max_audio_error=%.9g normalized\n",
                roundedResetSamples, largestResetError);

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

    // Event-heavy two-instance determinism regression: sample-rate changes,
    // abrupt frequency/rate/ratio CV, signed feedback, valid extremes and
    // occasional non-finite controls must remain bounded and replay exactly.
    FMVoice stress[16], reference[16];
    std::uint32_t randomState = UINT32_C(0x51a7e099);
    bool stressValid = true;
    for (int n = 0; n < 4096; ++n) {
        for (int c = 0; c < 16; ++c) {
            randomState = randomState * UINT32_C(1664525)
                          + UINT32_C(1013904223);
            FMVoice::Input varied;
            varied.sampleRateHz = (n / 256) % 4 == 0 ? 44100.0
                                  : (n / 256) % 4 == 1 ? 48000.0
                                  : (n / 256) % 4 == 2 ? 96000.0 : 192000.0;
            varied.frequencyHz = (randomState & 31u) == 0u
                                  ? std::numeric_limits<double>::denorm_min()
                                  : 20.0 + static_cast<double>(randomState % 24000u);
            varied.ratio = 0.125 + (randomState % 20000u) / 1000.0;
            varied.indexRadians = (randomState % 10000u) / 1000.0;
            varied.feedback = (randomState & 1u ? 1.0 : -1.0)
                              * (randomState % 1400u) / 1000.0;
            if ((n + c) % 179 == 0)
                varied.indexRadians = std::numeric_limits<double>::infinity();
            if ((n + c) % 227 == 0)
                varied.ratio = std::numeric_limits<double>::quiet_NaN();
            if (n % 997 == 0 && c == 3)
                varied.sampleRateHz = std::numeric_limits<double>::infinity();
            const auto a = stress[c].process(varied);
            const auto b = reference[c].process(varied);
            stressValid &= a.carrier == b.carrier && a.modulator == b.modulator;
            stressValid &= FMVoice::finite(a.carrier) && FMVoice::finite(a.modulator);
            stressValid &= std::abs(a.carrier) <= 1.0f
                           && std::abs(a.modulator) <= 1.0f;
            stressValid &= stress[c].carrierPhase >= 0.0
                           && stress[c].carrierPhase < 1.0;
            stressValid &= stress[c].modulatorPhase >= 0.0
                           && stress[c].modulatorPhase < 1.0;
            stressValid &= FMVoice::finite(stress[c].smoothedGuardCeiling)
                           && stress[c].smoothedGuardCeiling >= 0.0
                           && stress[c].smoothedGuardCeiling <= FMVoice::kMaxIndexRadians;
        }
    }
    okay &= check(stressValid,
                  "sample-rate and signed-CV stress stays bounded and deterministically replayable");

    if (okay)
        std::puts("PASS: FM Voice standalone DSP pitch, signed topology, modulation, controls, reset and finite safeguards");
    return okay ? 0 : 1;
}
