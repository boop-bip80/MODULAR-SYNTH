/*
 * MODULAR-SYNTH Fold Drive — original first-party DSP.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Rack-independent sine-folding timbre processor. Uses first-order analytic
 * antiderivative anti-aliasing (ADAA); neither fully bandlimited nor a
 * circuit-accurate wavefolder.
 */
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>

namespace modular_synth {
namespace dsp {

struct FoldDrive {
    static constexpr double kHalfPi = 1.5707963267948966192313216916398;
    static constexpr double kSmoothingSeconds = 0.003;

    double smoothDrive = 0.0;
    double smoothBias = 0.0;
    double smoothMix = 0.0;
    double previousInput = 0.0;
    bool initialized = false;

    // Independent of std::isfinite: aggressive -ffast-math may optimize
    // ordinary floating-point finiteness predicates into unconditional true.
    static bool ieeeFinite(double value) noexcept {
        static_assert(sizeof(double) == sizeof(std::uint64_t), "Requires binary64");
        static_assert(std::numeric_limits<double>::is_iec559, "Requires IEEE-754");
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

    void reset() noexcept {
        smoothDrive = 0.0;
        smoothBias = 0.0;
        smoothMix = 0.0;
        previousInput = 0.0;
        initialized = false;
    }

    // sinc(z) = sin(z)/z with a small-argument polynomial to avoid loss of
    // precision for slowly varying signals. The bounded input/gain ensure
    // finite arguments, including in aggressive fast-math builds.
    static double sinc(double z) noexcept {
        if (std::abs(z) < 0.01) {
            const double z2 = z * z;
            return 1.0 + z2 * (-1.0 / 6.0 + z2 / 120.0);
        }
        return std::sin(z) / z;
    }

    // drive: [0,1]; bias: [-1,1]; wetMix: [0,1]. Audio: nominal +/-5V.
    // The 3ms CV slew is initialized from the first valid sample, so a new
    // polyphonic lane does not inherit an old lane's knob/automation state.
    float process(double inputVoltage, double sampleRate, double drive,
                  double bias, double wetMix) noexcept {
        if (!ieeeFinite(sampleRate) || sampleRate < 1000.0 || sampleRate > 768000.0) {
            reset();
            return 0.0f;
        }

        const double volts = finiteClamp(inputVoltage, 0.0, -10.0, 10.0);
        const double targetDrive = finiteClamp(drive, 0.0, 0.0, 1.0);
        const double targetBias = finiteClamp(bias, 0.0, -1.0, 1.0);
        const double targetMix = finiteClamp(wetMix, 0.0, 0.0, 1.0);

        const bool firstSample = !initialized;
        if (firstSample) {
            smoothDrive = targetDrive;
            smoothBias = targetBias;
            smoothMix = targetMix;
            initialized = true;
        } else {
            const double alpha = std::min(1.0, 1.0 / (kSmoothingSeconds * sampleRate));
            smoothDrive += alpha * (targetDrive - smoothDrive);
            smoothBias += alpha * (targetBias - smoothBias);
            smoothMix += alpha * (targetMix - smoothMix);
        }

        // Curved drive response emphasizes subtle coloration in the lower
        // knob range; at maximum, nine half-waves cross a +/-5V input span.
        const double x = volts / 5.0;
        const double prior = firstSample ? x : previousInput;
        previousInput = x;
        // Preserve exact dry behavior and avoid transcendental work for a
        // fully dry path. Keep history current while dry to avoid a burst
        // from stale input when modulation fades the fold back in.
        if (smoothDrive == 0.0 || smoothMix == 0.0)
            return static_cast<float>(volts);

        const double gain = 1.0 + 8.0 * smoothDrive * smoothDrive;
        const double biasAngle = kHalfPi * smoothBias;
        const double angularGain = kHalfPi * gain;
        // Analytically average the sine transfer along the straight input
        // segment between adjacent sample points. This is first-order ADAA:
        // integral[sin(k*t+b), prior..x] / (x-prior). The midpoint/sinc form
        // is stable at x==prior and avoids subtracting nearly equal cosines.
        // It rejects some above-Nyquist distortion at the expense of a small
        // signal-dependent phase shift; it does not eliminate all aliasing.
        const double midpoint = 0.5 * (x + prior);
        const double halfDelta = 0.5 * angularGain * (x - prior);
        const double fold = std::sin(angularGain * midpoint + biasAngle)
                          * sinc(halfDelta) - std::sin(biasAngle);

        // Subtracting the zero-input fold value preserves silence at 0V even
        // with positive/negative bias. Drive=0 and MIX=0 are dry-identical.
        const double shaped = x + smoothDrive * (fold - x);
        const double mixed = volts + smoothMix * (5.0 * shaped - volts);
        return static_cast<float>(std::min(10.0, std::max(-10.0, mixed)));
    }
};

} // namespace dsp
} // namespace modular_synth
