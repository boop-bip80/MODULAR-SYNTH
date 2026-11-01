/*
 * MODULAR-SYNTH State Filter — original first-party DSP.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Rack-independent trapezoidal-integrator (TPT) state-variable filter.
 * This is a digital topology, NOT a circuit-accurate analog model.
 */
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>

namespace modular_synth {
namespace dsp {

struct StateFilter {
    struct Sample {
        float low;
        float band;
        float high;
    };

    static constexpr double kPi = 3.1415926535897932384626433832795;
    double ic1eq = 0.0;
    double ic2eq = 0.0;
    double previousSampleRate = 0.0;

    // Do not use std::isfinite here: -ffast-math permits compilers to
    // assume all floating-point inputs are finite and optimize it away.
    // Reading IEEE-754 exponent bits via memcpy works under that mode.
    static bool ieeeFinite(double value) noexcept {
        static_assert(sizeof(double) == sizeof(std::uint64_t), "Requires binary64 doubles");
        static_assert(std::numeric_limits<double>::is_iec559, "Requires IEEE-754 doubles");
        std::uint64_t bits = 0;
        std::memcpy(&bits, &value, sizeof(bits));
        return (bits & UINT64_C(0x7ff0000000000000)) != UINT64_C(0x7ff0000000000000);
    }

    static double finiteClamp(double value, double fallback,
                              double minimum, double maximum) noexcept {
        return ieeeFinite(value)
            ? std::min(maximum, std::max(minimum, value))
            : fallback;
    }

    static float boundedVoltage(double normalized) noexcept {
        if (!ieeeFinite(normalized))
            return 0.0f;
        return static_cast<float>(std::min(10.0, std::max(-10.0,
                                                        normalized * 5.0)));
    }

    void reset() noexcept {
        ic1eq = 0.0;
        ic2eq = 0.0;
        previousSampleRate = 0.0;
    }

    Sample process(double inputVoltage, double sampleRate, double cutoffHz,
                   double resonance, double drive) noexcept {
        if (!ieeeFinite(sampleRate) || sampleRate < 1000.0) {
            reset();
            return {0.0f, 0.0f, 0.0f};
        }

        // A new host sample rate changes the integrator's time step.
        // Clear old state instead of carrying potentially mismatched history.
        if (sampleRate != previousSampleRate) {
            ic1eq = 0.0;
            ic2eq = 0.0;
            previousSampleRate = sampleRate;
        }

        const double maxCutoff = std::min(20000.0, 0.45 * sampleRate);
        const double frequency = finiteClamp(cutoffHz, std::min(1000.0, maxCutoff), 5.0, maxCutoff);
        const double resonance01 = finiteClamp(resonance, 0.0, 0.0, 1.0);
        const double drive01 = finiteClamp(drive, 0.0, 0.0, 1.0);

        // 0.5 <= Q <= 12.0: bounded but capable of a prominent resonant peak.
        // The state-variable filter damping coefficient is k = 1 / Q.
        const double q = 0.5 + 11.5 * resonance01 * resonance01;
        const double k = 1.0 / q;

        // A nonlinearity on the input, not inside the integrator loop.
        // Bypassed at drive=0 to preserve linear DC/low-frequency response.
        const double volts = finiteClamp(inputVoltage, 0.0, -20.0, 20.0);
        double x = volts / 5.0;
        if (drive01 > 0.0) {
            const double gain = 1.0 + 12.0 * drive01 * drive01;
            const double shaped = std::tanh(gain * x) / std::tanh(gain);
            // Crossfade through drive=0: the normalized tanh function does
            // not converge to x as gain tends to 1, so abruptly switching
            // from bypass would otherwise produce an audible gain jump.
            x += drive01 * (shaped - x);
        }

        // Trapezoidal integrator coefficients. g is finite because the
        // frequency is strictly below Nyquist (<= 0.45 * sampleRate).
        const double g = std::tan(kPi * frequency / sampleRate);
        const double a1 = 1.0 / (1.0 + g * (g + k));
        const double a2 = g * a1;

        const double v3 = x - ic2eq;
        const double band = a1 * ic1eq + a2 * v3;
        const double low = ic2eq + g * band;
        const double high = x - k * band - low;

        // Prevent corrupted automation or unusual host signals from making
        // the state unbounded; these are safety limits, not analog modeling.
        ic1eq = finiteClamp(2.0 * band - ic1eq, 0.0, -16.0, 16.0);
        ic2eq = finiteClamp(2.0 * low - ic2eq, 0.0, -16.0, 16.0);

        // Flush tiny denormal-prone state values without heap or locks.
        if (std::abs(ic1eq) < 1e-20)
            ic1eq = 0.0;
        if (std::abs(ic2eq) < 1e-20)
            ic2eq = 0.0;

        return {boundedVoltage(low), boundedVoltage(band), boundedVoltage(high)};
    }
};

} // namespace dsp
} // namespace modular_synth
