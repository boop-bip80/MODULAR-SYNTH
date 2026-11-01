/*
 * MODULAR-SYNTH StateFilter frequency-response analysis.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Pure C++17: deterministic sine correlation, no audio host or FFT library.
 */
#pragma once

#include "../../plugins/ModularSynth/src/StateFilter.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <vector>

namespace modular_synth {
namespace analysis {

constexpr double kPi = 3.1415926535897932384626433832795;
constexpr double kSignalVolts = 0.25;

enum class Output { Low, Band, High };

inline const char* outputName(Output o) noexcept {
    switch (o) {
        case Output::Low: return "LP";
        case Output::Band: return "BP";
        case Output::High: return "HP";
    }
    return "?";
}

struct Response {
    double low = 0.0;
    double band = 0.0;
    double high = 0.0;
};

struct Row {
    double sampleRate = 0.0;
    double cutoffHz = 0.0;
    double resonance = 0.0;
    double probeHz = 0.0;
    Output output = Output::Low;
    double predictedGain = 0.0;
    double measuredGain = 0.0;
    double errorDb = 0.0;
    bool passed = false;
};

struct Matrix {
    std::vector<Row> rows;
    std::size_t failed = 0;
    double worstDb = 0.0;
};

// Fitted fundamental amplitude, excluding startup transients.
// The least-squares sin/cos basis handles non-integer sample periods
// accurately, even for probes near the upper digital-audio band.
struct Correlator {
    double ss = 0.0;
    double cc = 0.0;
    double sc = 0.0;
    double ys = 0.0;
    double yc = 0.0;

    void observe(double sample, double s, double c) noexcept {
        ss += s * s;
        cc += c * c;
        sc += s * c;
        ys += sample * s;
        yc += sample * c;
    }

    double magnitude() const noexcept {
        const double det = ss * cc - sc * sc;
        if (!(det > 1.0e-10))
            return 0.0;
        const double sinAmplitude = (ys * cc - yc * sc) / det;
        const double cosAmplitude = (yc * ss - ys * sc) / det;
        return std::hypot(sinAmplitude, cosAmplitude);
    }
};

inline Response measure(double sampleRate, double cutoffHz,
                        double resonance, double probeHz) {
    dsp::StateFilter filter;
    Correlator low, band, high;
    const double phaseIncrement = 2.0 * kPi * probeHz / sampleRate;
    const int warmup = static_cast<int>(std::ceil(16.0 * sampleRate / probeHz));
    const int measurement = static_cast<int>(std::ceil(64.0 * sampleRate / probeHz));
    double phase = 0.0;

    for (int i = 0; i < warmup + measurement; ++i) {
        const double s = std::sin(phase);
        const double c = std::cos(phase);
        const auto result = filter.process(kSignalVolts * s, sampleRate,
                                           cutoffHz, resonance, 0.0);
        if (i >= warmup) {
            low.observe(result.low, s, c);
            band.observe(result.band, s, c);
            high.observe(result.high, s, c);
        }
        phase += phaseIncrement;
        if (phase >= 2.0 * kPi)
            phase -= 2.0 * kPi;
    }

    return {low.magnitude() / kSignalVolts,
            band.magnitude() / kSignalVolts,
            high.magnitude() / kSignalVolts};
}

// TPT's bilinear mapping warps digital frequency: tan(pi*f/Fs).
// Analog SVF prototypes (LP=1, BP=s, HP=s^2) evaluated at this ratio
// give exact expected steady-state magnitudes for the linear core.
inline Response predict(double sampleRate, double cutoffHz,
                        double resonance, double probeHz) noexcept {
    const double normalizedRes = dsp::StateFilter::finiteClamp(
        resonance, 0.0, 0.0, 1.0);
    const double q = 0.5 + 11.5 * normalizedRes * normalizedRes;
    const double ratio = std::tan(kPi * probeHz / sampleRate)
                       / std::tan(kPi * cutoffHz / sampleRate);
    const double ratio2 = ratio * ratio;
    const double denominator = std::hypot(1.0 - ratio2, ratio / q);
    return {1.0 / denominator,
            ratio / denominator,
            ratio2 / denominator};
}

inline Matrix evaluateMatrix() {
    constexpr std::array<double, 3> rates{{44100.0, 48000.0, 96000.0}};
    constexpr std::array<double, 3> cutoffs{{250.0, 1600.0, 7500.0}};
    constexpr std::array<double, 2> resonances{{0.1342, 0.58}};
    constexpr std::array<double, 3> ratios{{0.25, 1.0, 2.5}};

    Matrix matrix;
    matrix.rows.reserve(rates.size() * cutoffs.size()
                        * resonances.size() * ratios.size() * 3);

    for (double rate : rates) {
        for (double cutoff : cutoffs) {
            for (double resonance : resonances) {
                for (double probeRatio : ratios) {
                    const double probe = cutoff * probeRatio;
                    const Response expected = predict(rate, cutoff, resonance, probe);
                    const Response measured = measure(rate, cutoff, resonance, probe);
                    const std::array<double, 3> ex{{expected.low, expected.band, expected.high}};
                    const std::array<double, 3> got{{measured.low, measured.band, measured.high}};
                    for (int i = 0; i < 3; ++i) {
                        const double expectedGain = ex[static_cast<std::size_t>(i)];
                        const double actualGain = got[static_cast<std::size_t>(i)];
                        const bool finite = dsp::StateFilter::ieeeFinite(expectedGain)
                            && dsp::StateFilter::ieeeFinite(actualGain);
                        const double dbError = finite && expectedGain > 0.0 && actualGain > 0.0
                            ? 20.0 * std::log10(actualGain / expectedGain)
                            : 1.0e20;
                        // Deep stopbands are checked in absolute gain, where
                        // tiny numerical error need not be a large dB penalty.
                        const bool passed = finite && (expectedGain < 0.025
                            ? std::abs(actualGain - expectedGain) <= 0.010
                            : std::abs(dbError) <= 0.20);
                        matrix.rows.push_back({rate, cutoff, resonance, probe,
                            static_cast<Output>(i), expectedGain, actualGain,
                            dbError, passed});
                        if (!passed)
                            ++matrix.failed;
                        if (finite && std::abs(dbError) < 1.0e10)
                            matrix.worstDb = std::max(matrix.worstDb, std::abs(dbError));
                    }
                }
            }
        }
    }

    return matrix;
}

} // namespace analysis
} // namespace modular_synth
