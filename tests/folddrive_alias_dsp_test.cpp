/*
 * MODULAR-SYNTH FoldDrive high-register alias regression.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * A deterministic, bin-coherent measurement of *discrete-time* output.
 * The reference implements the previous un-oversampled sine transfer, and
 * every measured odd harmonic from the selected tone is above Nyquist.
 * This tests alias-power reduction, not sound quality or plugin-host CPU.
 */
#include "../plugins/ModularSynth/src/FoldDrive.hpp"

#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>

using modular_synth::dsp::FoldDrive;

namespace {
constexpr int kFrames = 4096;
constexpr double kRate = 48000.0;
constexpr double kTwoPi = 6.283185307179586476925286766559;
constexpr double kAmplitude = 3.0;
constexpr double kDrive = 0.5;

void require(bool okay, const char* reason) {
    if (!okay) {
        std::fprintf(stderr, "FAIL FoldDrive alias test: %s\n", reason);
        std::exit(EXIT_FAILURE);
    }
}

double binPower(const std::array<float, kFrames>& signal, int bin) {
    double real = 0.0;
    double imaginary = 0.0;
    for (int n = 0; n < kFrames; ++n) {
        const double phase = kTwoPi * bin * n / kFrames;
        real += signal[n] * std::cos(phase);
        imaginary += signal[n] * std::sin(phase);
    }
    return (real * real + imaginary * imaginary)
         / static_cast<double>(kFrames * kFrames);
}

double oldInstantaneousTransfer(double input) {
    const double x = input / 5.0;
    const double gain = 1.0 + 8.0 * kDrive * kDrive;
    const double fold = std::sin(FoldDrive::kHalfPi * gain * x);
    return 5.0 * (x + kDrive * (fold - x));
}

void checkAliasRejection(int inputBin, double sampleRate) {
    std::array<float, kFrames> previousTransfer{};
    std::array<float, kFrames> antialiased{};
    FoldDrive voice;
    // One full cycle warms previous-input history. With constant controls,
    // there are no smoothing transients in either implementation.
    for (int n = 0; n < kFrames * 2; ++n) {
        const double input = kAmplitude * std::sin(kTwoPi * inputBin * n / kFrames);
        const float output = voice.process(input, sampleRate, kDrive, 0.0, 1.0);
        require(FoldDrive::ieeeFinite(output), "ADAA output finite");
        require(output >= -10.0f && output <= 10.0f, "ADAA output bounded");
        if (n >= kFrames) {
            antialiased[n - kFrames] = output;
            previousTransfer[n - kFrames] =
                static_cast<float>(oldInstantaneousTransfer(input));
        }
    }

    // For inputBin >= 751, all odd harmonics >= third exceed Nyquist;
    // their sampled spectral bins contain foldback artifacts, not usable
    // below-Nyquist harmonics. No FFT window/leakage assumptions are needed
    // because tone and analysis bins have integer cycle counts.
    double oldAlias = 0.0;
    double newAlias = 0.0;
    for (const int harmonic : {3, 5, 7, 9}) {
        const int aliasBin = (harmonic * inputBin) % kFrames;
        oldAlias += binPower(previousTransfer, aliasBin);
        newAlias += binPower(antialiased, aliasBin);
    }
    const double oldFundamental = binPower(previousTransfer, inputBin);
    const double newFundamental = binPower(antialiased, inputBin);
    require(oldAlias > 0.01, "reference must contain measurable alias energy");
    require(newAlias > 0.0 && newFundamental > 0.0,
            "ADAA outputs must have positive finite spectral energy");

    const double aliasDb = 10.0 * std::log10(oldAlias / newAlias);
    const double relativeDb = 10.0 * std::log10(
        (oldAlias / oldFundamental) / (newAlias / newFundamental));
    require(aliasDb > 6.0, "ADAA should reduce selected alias bins >6 dB");
    require(relativeDb > 4.0,
            "ADAA should reduce alias-to-fundamental ratio >4 dB");
    std::printf("PASS FoldDrive %.1f kHz at %.1f kHz / drive=0.5: "
                "alias %.3f -> %.3f (-%.2f dB), "
                "relative to fundamental -%.2f dB\n",
                inputBin * sampleRate / kFrames / 1000.0,
                sampleRate / 1000.0, oldAlias, newAlias, aliasDb, relativeDb);
}

void checkConstantInputExactness() {
    FoldDrive voice;
    constexpr double input = 2.7;
    const double expected = 5.0 * (input / 5.0 + 0.5 * (
        std::sin(FoldDrive::kHalfPi * (1.0 + 8.0 * 0.5 * 0.5)
                 * input / 5.0) - input / 5.0));
    for (int n = 0; n < 512; ++n) {
        const float out = voice.process(input, kRate, kDrive, 0.0, 1.0);
        require(std::abs(out - expected) < 1e-6,
                "steady/first-sample transfer matches un-antialiased transfer");
    }
}
} // namespace

int main() {
    checkConstantInputExactness();
    checkAliasRejection(751, 44100.0);
    checkAliasRejection(751, 48000.0);
    checkAliasRejection(891, 48000.0);
}
