/*
 * Original MODULAR-SYNTH FMVoice adversarial coherent spectral matrix.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * This is offline mathematical evidence from a Rack-independent DSP core.
 * It is not proof of alias-free synthesis or a listening/DAW audition.
 */
#include "../plugins/ModularSynth/src/FMVoice.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>

using modular_synth::dsp::FMVoice;

namespace {
constexpr int kWindow = 4800;

struct Bin {
    double re = 0.0;
    double im = 0.0;

    void add(double sample, int frame, double normalizedFrequency) noexcept {
        const double angle = FMVoice::kTwoPi * normalizedFrequency * frame;
        re += sample * std::cos(angle);
        im -= sample * std::sin(angle);
    }

    double amplitude() const noexcept {
        return 2.0 * std::hypot(re, im) / kWindow;
    }
};

struct PhaseModulationCase {
    double carrierFraction;
    double ratio;
    double foldedBinFraction;
    const char* label;
};

bool check(bool valid, const char* label) {
    if (!valid)
        std::fprintf(stderr, "FAIL spectral matrix: %s\n", label);
    return valid;
}

// Reproduce pre-index-guard sine phase modulation as a deliberately
// unbandlimited independent reference. All frequencies are coherent integer
// DFT bins, avoiding window/leakage corrections and subjective listening.
bool checkPhaseModulationBin(double sampleRate,
                             const PhaseModulationCase& test,
                             double& minimumReductionDb) {
    FMVoice voice;
    FMVoice::Input input;
    input.frequencyHz = sampleRate * test.carrierFraction;
    input.sampleRateHz = sampleRate;
    input.ratio = test.ratio;
    input.indexRadians = 3.0;
    input.feedback = 0.0;

    Bin unrestricted, guarded;
    double peak = 0.0;
    for (int n = 0; n < kWindow; ++n) {
        const double carrierAngle = FMVoice::kTwoPi * n * test.carrierFraction;
        const double modulatorAngle = carrierAngle * test.ratio;
        const double oldSample = std::sin(carrierAngle
                                          + 3.0 * std::sin(modulatorAngle));
        const auto output = voice.process(input);
        unrestricted.add(oldSample, n, test.foldedBinFraction);
        guarded.add(output.carrier, n, test.foldedBinFraction);
        peak = std::max(peak, std::abs(static_cast<double>(output.carrier)));
        if (!FMVoice::finite(output.carrier)
            || !FMVoice::finite(output.modulator))
            return check(false, "guarded PM emitted a non-finite sample");
    }

    const double oldAmp = unrestricted.amplitude();
    const double guardedAmp = guarded.amplitude();
    const double reduction = 20.0 * std::log10(oldAmp
        / std::max(1.0e-12, guardedAmp));
    minimumReductionDb = std::min(minimumReductionDb, reduction);
    std::printf("PM fold %s @ %.0f Hz: old %.7f, guarded %.7f, %.2f dB\n",
                test.label, sampleRate, oldAmp, guardedAmp, reduction);
    return check(oldAmp > 0.02 && guardedAmp < oldAmp * 0.32
                 && reduction > 9.5 && peak <= 1.000001,
                 "guarded PM folded coherent bin must be reduced >9.5 dB");
}

// Model the previous one-sample feedback equation directly. The brand-new
// taper must remove its second-harmonic folded bin near Nyquist for BOTH
// modulation polarities: negative = carrier loop, positive = modulator loop.
bool checkFeedbackBin(double sampleRate, double normalizedFrequency,
                      double signedFeedback, double& minimumReductionDb) {
    FMVoice voice;
    FMVoice::Input input;
    input.frequencyHz = sampleRate * normalizedFrequency;
    input.sampleRateHz = sampleRate;
    input.ratio = 1.0;
    input.indexRadians = 0.0;
    input.feedback = signedFeedback;

    double previous = 0.0;
    const double aliasFraction = 1.0 - 2.0 * normalizedFrequency;
    Bin unrestricted, guarded;
    for (int n = 0; n < kWindow; ++n) {
        const double phase = FMVoice::kTwoPi * n * normalizedFrequency;
        const double oldSample = std::sin(phase
            + std::abs(signedFeedback) * previous);
        previous = oldSample;
        const auto output = voice.process(input);
        const double newSample = signedFeedback > 0.0
                                 ? output.modulator : output.carrier;
        unrestricted.add(oldSample, n, aliasFraction);
        guarded.add(newSample, n, aliasFraction);
    }
    const double oldAmp = unrestricted.amplitude();
    const double guardedAmp = guarded.amplitude();
    // A pure sine has no independent second harmonic. Once the new output
    // reaches DFT/float precision, an extrapolated 200+ dB ratio is not a
    // meaningful physical filter metric; cap the reported reduction to 60 dB.
    const double reduction = 20.0 * std::log10(oldAmp
        / std::max(oldAmp * 1.0e-3, guardedAmp));
    minimumReductionDb = std::min(minimumReductionDb, reduction);
    std::printf("Feedback fold %s @ %.0f Hz f0 %.0f: old %.7f, "
                "guarded %.7f, %.2f dB (60 dB numerical-floor cap)\n",
                signedFeedback > 0 ? "mod" : "carrier", sampleRate,
                input.frequencyHz, oldAmp, guardedAmp, reduction);
    return check(oldAmp > 0.05 && guardedAmp < oldAmp * 0.02
                 && reduction > 33.0,
                 "feedback second-harmonic folded bin must be reduced >33 dB");
}

bool checkFeedbackTaperShape(double sampleRate) {
    bool okay = true;
    const auto taper = [sampleRate](double normalizedFrequency) {
        return FMVoice::harmonicFeedbackTaper(
            normalizedFrequency * sampleRate, sampleRate);
    };
    okay &= check(taper(0.0) == 1.0 && taper(0.16) == 1.0
                  && taper(0.225) == 0.0 && taper(0.45) == 0.0,
                  "taper must exactly preserve low notes and mute above second-harmonic edge");
    okay &= check(taper(0.17) > taper(0.19)
                  && taper(0.19) > taper(0.21)
                  && taper(0.21) > 0.0,
                  "feedback taper must be smooth and decreasing in the fade window");
    okay &= check(FMVoice::harmonicFeedbackTaper(
                      std::numeric_limits<double>::quiet_NaN(), sampleRate) == 0.0
                  && FMVoice::harmonicFeedbackTaper(
                      440.0, std::numeric_limits<double>::infinity()) == 0.0
                  && FMVoice::harmonicFeedbackTaper(-440.0, sampleRate) == 0.0,
                  "feedback guard fails closed for invalid oscillator/rate inputs");

    // Pitch CV may jump within one frame. Feedback attenuation must apply
    // before the first new waveform sample, without discarding phase.
    FMVoice jump;
    FMVoice::Input input;
    input.sampleRateHz = sampleRate;
    input.frequencyHz = 0.125 * sampleRate;
    input.indexRadians = 0.0;
    input.feedback = -0.95;
    input.ratio = 1.0;
    for (int n = 0; n < 2400; ++n)
        jump.process(input);
    const double phase = jump.carrierPhase;
    input.frequencyHz = 0.3125 * sampleRate;
    const auto first = jump.process(input);
    const double expected = std::sin(FMVoice::kTwoPi * phase);
    okay &= check(std::abs(first.carrier - expected) < 2.0e-6,
                  "upward pitch CV first frame must remove aliased feedback harmonic");
    okay &= check(std::abs(jump.carrierPhase - std::fmod(phase + 0.3125, 1.0))
                      < 1.0e-10,
                  "upward pitch feedback guard must preserve oscillator phase");
    return okay;
}

bool checkEnvelopeAndCvMatrix(double sampleRate) {
    FMVoice voice[16], identical[16];
    bool okay = true;
    // 16 independent lanes, six abrupt stages and non-integral ratios.
    // Bound/finite invariants matter even where folded-bin separation is
    // impossible because feedback and time-varying CV have broad spectra.
    for (int n = 0; n < 4800; ++n) {
        const int stage = n / 800;
        for (int lane = 0; lane < 16; ++lane) {
            FMVoice::Input input;
            input.sampleRateHz = sampleRate;
            input.frequencyHz = (stage % 2 == 0 ? 0.06 : 0.32)
                                * sampleRate * (1.0 + lane / 128.0);
            input.ratio = 0.125 + ((lane + stage) % 15) * 0.94;
            input.indexRadians = stage % 3 == 0 ? 0.0
                                : stage % 3 == 1 ? 3.0 : 8.0;
            input.feedback = (stage % 2 == 0 ? -0.95 : 0.95)
                             * ((lane + 1) / 16.0);
            const auto a = voice[lane].process(input);
            const auto b = identical[lane].process(input);
            okay &= a.carrier == b.carrier && a.modulator == b.modulator;
            okay &= FMVoice::finite(a.carrier) && FMVoice::finite(a.modulator);
            okay &= std::abs(a.carrier) <= 1.000001f
                    && std::abs(a.modulator) <= 1.000001f;
            okay &= voice[lane].carrierPhase >= 0.0
                    && voice[lane].carrierPhase < 1.0;
            okay &= voice[lane].modulatorPhase >= 0.0
                    && voice[lane].modulatorPhase < 1.0;
        }
    }
    return check(okay, "16-lane high-frequency CV/envelope stages replay bounded and finite");
}
} // namespace

int main() {
    bool okay = true;
    double minimumPmReduction = 1000.0;
    double minimumFeedbackReduction = 1000.0;
    constexpr double sampleRates[] = {44100.0, 48000.0, 96000.0, 192000.0};
    const PhaseModulationCase pmCases[] = {
        {0.0625, 4.0, 0.4375, "3k/12k@48k"},
        {0.125, 2.0, 0.375, "6k/12k@48k"},
        {0.0625, 5.0, 0.3125, "3k/15k@48k"},
        {0.05, 5.0, 0.45, "2.205k/11.025k@44.1k"},
    };

    for (double sampleRate : sampleRates) {
        for (const auto& test : pmCases)
            okay &= checkPhaseModulationBin(sampleRate, test,
                                           minimumPmReduction);
        for (double sign : {-0.95, 0.95})
            okay &= checkFeedbackBin(sampleRate, 0.3125, sign,
                                     minimumFeedbackReduction);
        okay &= checkFeedbackTaperShape(sampleRate);
        okay &= checkEnvelopeAndCvMatrix(sampleRate);
    }
    std::printf("FM matrix: worst selected coherent PM fold reduction %.2f dB; "
                "worst selected feedback fold reduction %.2f dB\n",
                minimumPmReduction, minimumFeedbackReduction);
    if (okay)
        std::puts("PASS: FM Voice coherent spectral matrix, feedback alias taper, "
                  "pitch-CV first-sample guard and deterministic 16-lane envelope stress");
    return okay ? 0 : 1;
}
