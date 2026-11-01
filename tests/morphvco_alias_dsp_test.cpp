/*
 * MODULAR-SYNTH polyBLEP alias-energy regression (standalone C++17).
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "../tools/spectral-analysis/alias_metrics.hpp"

#include <array>
#include <cmath>
#include <cstdio>
#include <vector>

using modular_synth::spectral::Comparison;
using modular_synth::spectral::Waveform;
using modular_synth::spectral::analyzeSignal;
using modular_synth::spectral::chooseCoherentBin;
using modular_synth::spectral::compare;
using modular_synth::spectral::kFftSize;
using modular_synth::spectral::kTwoPi;

namespace {

int failures = 0;

void expect(bool condition, const char* reason) {
    if (!condition) {
        ++failures;
        std::fprintf(stderr, "FAIL: %s\n", reason);
    }
}

bool validPower(const modular_synth::spectral::SpectralEnergy& v) {
    return modular_synth::dsp::MorphOscillator::finite(v.totalPower)
        && modular_synth::dsp::MorphOscillator::finite(v.aliasPower)
        && modular_synth::dsp::MorphOscillator::finite(v.timeDomainPower)
        && v.aliasPower >= 0.0 && v.aliasPower <= v.totalPower
        && v.totalPower > 0.0;
}

void checkParseval(const Comparison& x) {
    for (const auto* energy : {&x.naive, &x.polyblep}) {
        const double relative = std::abs(energy->totalPower - energy->timeDomainPower)
            / energy->timeDomainPower;
        expect(relative < 1e-8,
               "Hann-normalized FFT one-sided power must match time-domain mean square");
    }
}

void testIsolationControls() {
    const std::size_t coherent = chooseCoherentBin(48000, 440.0);
    std::vector<double> pure(kFftSize);
    for (std::size_t i = 0; i < pure.size(); ++i)
        pure[i] = std::sin(kTwoPi * coherent * i / pure.size());
    const auto correctlyClassified = analyzeSignal(pure, coherent, Waveform::Saw);
    expect(correctlyClassified.aliasRms() < 1e-7,
           "coherent legitimate sine must have essentially zero alias energy");
    expect(std::abs(correctlyClassified.totalPower - 0.5) < 1e-6,
           "coherent 1.0-amplitude sine must have mean square 0.5");

    // A deliberately unrelated FFT tone should be counted as non-harmonic.
    for (std::size_t i = 0; i < pure.size(); ++i)
        pure[i] = std::sin(kTwoPi * (coherent + 17) * i / pure.size());
    const auto unrelated = analyzeSignal(pure, coherent, Waveform::Saw);
    expect(unrelated.aliasFraction() > 0.99,
           "unrelated in-band line must be counted as alias-bin energy");

    // A 50% duty pulse admits odd harmonics only; a digital 2nd harmonic
    // belongs to the alias/noise mask for pulse but not for saw.
    for (std::size_t i = 0; i < pure.size(); ++i)
        pure[i] = std::sin(kTwoPi * (2 * coherent) * i / pure.size());
    const auto pulse = analyzeSignal(pure, coherent, Waveform::Pulse);
    const auto saw = analyzeSignal(pure, coherent, Waveform::Saw);
    expect(pulse.aliasFraction() > 0.99,
           "50%-pulse even harmonic must not be marked as legitimate");
    expect(saw.aliasRms() < 1e-7,
           "saw second harmonic must be marked as legitimate");
}

void testMusicalRatesAndPolyBlep() {
    constexpr std::array<double, 6> musicalHz{{220.0, 440.0, 880.0,
                                                1760.0, 3520.0, 7040.0}};
    int comparisons = 0;
    for (int rate : {48000, 96000}) {
        for (double nominal : musicalHz) {
            for (const auto mode : {Waveform::Saw, Waveform::Pulse}) {
                const auto x = compare(rate, nominal, mode);
                ++comparisons;
                expect((x.fundamentalBin & 1u) == 1u,
                       "coherent FFT bin must be odd and coprime with N");
                expect(std::abs(x.coherentHz - nominal)
                           <= static_cast<double>(rate) / kFftSize + 1e-8,
                       "coherent pitch must stay within one FFT frequency bin");
                expect(validPower(x.naive) && validPower(x.polyblep),
                       "both oscillators must have finite, bounded FFT energy");
                checkParseval(x);
                expect(x.naive.aliasRms() > 1e-4,
                       "naive discontinuities must expose measurable aliases");
                expect(x.improvementDb() > 8.0,
                       "polyBLEP must reduce isolated alias-bin power by at least 8 dB");
                expect(x.polyblep.aliasFraction() < x.naive.aliasFraction(),
                       "polyBLEP alias power fraction must improve");
                expect(std::sqrt(x.polyblep.totalPower / x.naive.totalPower) > 0.65,
                       "alias improvement must not simply silence the musical oscillator");
            }
        }
    }
    expect(comparisons == 24, "musical matrix must cover 2 rates x 6 pitches x 2 shapes");
}

void testNearNyquistIsMeasuredNotOverclaimed() {
    for (int rate : {48000, 96000}) {
        for (const auto mode : {Waveform::Saw, Waveform::Pulse}) {
            // This deliberately pushes polyBLEP near its limit. No minimum
            // improvement is required here: waveform/fundamental attenuation
            // is significant and alias-bin power alone is not audio fidelity.
            const auto x = compare(rate, 0.42 * rate, mode);
            expect(validPower(x.naive) && validPower(x.polyblep),
                   "near-Nyquist stress must remain finite");
            checkParseval(x);
            expect(x.coherentHz < 0.45 * rate,
                   "near-Nyquist coherent tone stays within core's safe step");
            expect(x.polyblep.aliasRms() >= 0.0 && x.polyblep.totalPower > 0.0,
                   "near-Nyquist waveform must be analyzed and remain non-silent");
        }
    }
}

} // namespace

int main() {
    testIsolationControls();
    testMusicalRatesAndPolyBlep();
    testNearNyquistIsMeasuredNotOverclaimed();

    if (failures != 0) {
        std::fprintf(stderr, "MorphVCO alias: %d regression failures\n", failures);
        return 1;
    }
    std::puts("PASS: MorphVCO measured FFT alias power improved for 24 musical saw/pulse comparisons");
    return 0;
}
