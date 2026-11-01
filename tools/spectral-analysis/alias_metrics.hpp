/*
 * MODULAR-SYNTH spectral alias-energy analyzer (standalone C++17).
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * A coherent-bin, periodic-Hann FFT estimates in-band alias power outside
 * mathematically allowed harmonic bins. Aliases that coincide with allowed
 * harmonics cannot be separated and are a documented measurement limitation.
 */
#pragma once

#include "plugins/ModularSynth/src/MorphVCO.hpp"

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <utility>
#include <vector>

namespace modular_synth {
namespace spectral {

constexpr std::size_t kFftSize = 1u << 16;
constexpr double kPi = 3.1415926535897932384626433832795;
constexpr double kTwoPi = 2.0 * kPi;
constexpr int kGuardBins = 2;

enum class Waveform { Saw, Pulse };

inline const char* waveformName(Waveform type) noexcept {
    return type == Waveform::Saw ? "saw" : "pulse";
}

struct SpectralEnergy {
    double totalPower = 0.0;       // Mean squared amplitude, Hann-corrected
    double aliasPower = 0.0;       // Non-harmonic FFT bin mean squared energy
    double timeDomainPower = 0.0;  // Independent Parseval cross-check

    double aliasRms() const noexcept { return std::sqrt(aliasPower); }
    double aliasFraction() const noexcept {
        return totalPower > 0.0 ? aliasPower / totalPower : 0.0;
    }
};

struct Comparison {
    int sampleRate = 0;
    double nominalHz = 0.0;
    double coherentHz = 0.0;
    std::size_t fundamentalBin = 0;
    Waveform waveform = Waveform::Saw;
    SpectralEnergy naive;
    SpectralEnergy polyblep;

    double improvementDb() const noexcept {
        return 10.0 * std::log10(std::max(naive.aliasPower, 1e-30)
                                 / std::max(polyblep.aliasPower, 1e-30));
    }
};

inline std::size_t chooseCoherentBin(int sampleRate, double requestedHz,
                                    std::size_t fftSize = kFftSize) {
    if (sampleRate < 1000 || !dsp::MorphOscillator::finite(requestedHz)
        || requestedHz <= 0.0 || requestedHz >= 0.45 * sampleRate
        || fftSize < 1024 || (fftSize & (fftSize - 1u)) != 0u)
        throw std::invalid_argument("Invalid spectral sample rate, frequency or FFT size");

    const double fractional = requestedHz * fftSize / sampleRate;
    std::int64_t bin = std::llround(fractional);
    // Odd bin and power-of-two FFT length are coprime: the coherent period
    // is the full FFT frame and most high-order aliases don't coincide with
    // legitimate harmonics.
    if ((bin & 1) == 0) {
        const std::int64_t lower = bin - 1;
        const std::int64_t upper = bin + 1;
        bin = (std::abs(fractional - lower) <= std::abs(fractional - upper))
            ? lower : upper;
    }
    if (bin < 5 || static_cast<std::size_t>(bin) >= fftSize / 2)
        throw std::invalid_argument("Frequency outside coherent FFT analysis range");
    return static_cast<std::size_t>(bin);
}

inline void fft(std::vector<std::complex<double>>& bins) {
    const std::size_t size = bins.size();
    if (size < 2 || (size & (size - 1u)) != 0u)
        throw std::invalid_argument("FFT requires a power-of-two size");

    for (std::size_t i = 1, j = 0; i < size; ++i) {
        std::size_t bit = size >> 1;
        while (j & bit) {
            j ^= bit;
            bit >>= 1;
        }
        j ^= bit;
        if (i < j)
            std::swap(bins[i], bins[j]);
    }
    for (std::size_t len = 2; len <= size; len <<= 1) {
        const double phase = -kTwoPi / static_cast<double>(len);
        const std::complex<double> step(std::cos(phase), std::sin(phase));
        for (std::size_t start = 0; start < size; start += len) {
            std::complex<double> rotation(1.0, 0.0);
            for (std::size_t i = 0; i < len / 2; ++i) {
                const auto a = bins[start + i];
                const auto b = bins[start + i + len / 2] * rotation;
                bins[start + i] = a + b;
                bins[start + i + len / 2] = a - b;
                rotation *= step;
            }
        }
    }
}

inline SpectralEnergy analyzeSignal(const std::vector<double>& samples,
                                    std::size_t fundamentalBin, Waveform waveform) {
    const std::size_t size = samples.size();
    if (size < 1024 || (size & (size - 1u)) != 0u
        || fundamentalBin < 5 || fundamentalBin >= size / 2)
        throw std::invalid_argument("Invalid spectral input");

    std::vector<std::complex<double>> bins(size);
    double windowSquares = 0.0;
    double windowedSignalSquares = 0.0;
    for (std::size_t i = 0; i < size; ++i) {
        if (!dsp::MorphOscillator::finite(samples[i]))
            throw std::invalid_argument("Non-finite oscillator sample");
        const double window = 0.5 - 0.5 * std::cos(kTwoPi * i / size);
        const double value = window * samples[i];
        bins[i] = {value, 0.0};
        windowSquares += window * window;
        windowedSignalSquares += value * value;
    }

    fft(bins);
    const std::size_t nyquist = size / 2;
    std::vector<bool> expected(nyquist + 1, false);
    expected[0] = expected[1] = true; // DC and its Hann side lobe are not aliases.
    for (std::size_t harmonic = 1; harmonic <= nyquist / fundamentalBin; ++harmonic) {
        if (waveform == Waveform::Pulse && harmonic % 2 == 0)
            continue; // Exactly 50% pulse has no even legitimate harmonics.
        const auto center = harmonic * fundamentalBin;
        for (int delta = -kGuardBins; delta <= kGuardBins; ++delta) {
            const auto bin = static_cast<std::int64_t>(center)
                           + static_cast<std::int64_t>(delta);
            if (bin >= 0 && static_cast<std::size_t>(bin) <= nyquist)
                expected[static_cast<std::size_t>(bin)] = true;
        }
    }

    SpectralEnergy result;
    const double scale = 1.0 / (size * windowSquares);
    for (std::size_t i = 0; i <= nyquist; ++i) {
        const double oneSided = (i == 0 || i == nyquist) ? 1.0 : 2.0;
        const double power = oneSided * std::norm(bins[i]) * scale;
        result.totalPower += power;
        if (!expected[i])
            result.aliasPower += power;
    }
    result.timeDomainPower = windowedSignalSquares / windowSquares;
    return result;
}

inline Comparison compare(int sampleRate, double nominalHz, Waveform waveform,
                          std::size_t fftSize = kFftSize) {
    const std::size_t bin = chooseCoherentBin(sampleRate, nominalHz, fftSize);
    const double coherentHz = static_cast<double>(sampleRate) * bin / fftSize;
    std::vector<double> naive(fftSize);
    std::vector<double> corrected(fftSize);
    dsp::MorphOscillator oscillator;
    const float morph = waveform == Waveform::Saw ? 0.5f : 1.0f;

    for (std::size_t i = 0; i < fftSize; ++i) {
        const double t = oscillator.phase;
        naive[i] = waveform == Waveform::Saw
            ? 2.0 * t - 1.0
            : (t < 0.5 ? 1.0 : -1.0);
        corrected[i] = oscillator.process(coherentHz, sampleRate, morph, 0.5f).morph;
    }

    Comparison result;
    result.sampleRate = sampleRate;
    result.nominalHz = nominalHz;
    result.coherentHz = coherentHz;
    result.fundamentalBin = bin;
    result.waveform = waveform;
    result.naive = analyzeSignal(naive, bin, waveform);
    result.polyblep = analyzeSignal(corrected, bin, waveform);
    return result;
}

} // namespace spectral
} // namespace modular_synth
