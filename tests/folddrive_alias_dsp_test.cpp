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
// A dry-only passage must still update the ADAA input history. Otherwise
// the first CV-slewed wet sample incorrectly averages against stale audio.
void checkDryReopenHistory() {
    constexpr double rate = 48000.0;
    constexpr double drive = 0.8;
    constexpr double bias = 0.31;
    constexpr double nextInput = 3.1;
    FoldDrive voice;

    require(voice.process(5.0, rate, drive, bias, 0.0) == 5.0f,
            "initial MIX=0 must remain exactly dry");
    require(voice.process(-5.0, rate, drive, bias, 0.0) == -5.0f,
            "changing MIX=0 audio must remain exactly dry");

    const double x = nextInput / 5.0;
    const double previous = -1.0;  // Most recent dry sample: -5 V.
    const double gain = FoldDrive::kHalfPi * (1.0 + 8.0 * drive * drive);
    const double phase = FoldDrive::kHalfPi * bias;
    const double wetAlpha = 1.0 / (FoldDrive::kSmoothingSeconds * rate);
    const auto expectedWithPrevious = [&](double prior) {
        const double halfDelta = 0.5 * gain * (x - prior);
        const double sinc = std::sin(halfDelta) / halfDelta;
        const double folded = std::sin(0.5 * gain * (x + prior) + phase)
                            * sinc - std::sin(phase);
        const double shaped = x + drive * (folded - x);
        return nextInput + wetAlpha * (5.0 * shaped - nextInput);
    };

    const double expected = expectedWithPrevious(previous);
    const double stale = expectedWithPrevious(1.0);  // Initial dry sample.
    require(std::abs(expected - stale) > 0.005,
            "reopen fixture distinguishes current history from stale history");
    const float reopened = voice.process(nextInput, rate, drive, bias, 1.0);
    require(std::abs(reopened - expected) < 2e-6,
            "reopened wet CV must use last dry sample for ADAA");

    // Reset must discard history and initialize with the current sample,
    // even if that sample immediately arrives fully wet.
    voice.reset();
    const double foldedFirst = std::sin(gain * x + phase) - std::sin(phase);
    const double firstExpected = 5.0 * (x + drive * (foldedFirst - x));
    const float firstAfterReset = voice.process(nextInput, rate, drive, bias, 1.0);
    require(std::abs(firstAfterReset - firstExpected) < 2e-6,
            "reset must discard dry history and use stationary transfer");
}

} // namespace

int main() {
    checkConstantInputExactness();
    checkDryReopenHistory();
    checkAliasRejection(751, 44100.0);
    checkAliasRejection(751, 48000.0);
    checkAliasRejection(891, 48000.0);
}
