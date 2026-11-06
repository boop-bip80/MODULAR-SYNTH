/*
 * MODULAR-SYNTH SlewGlide — first-party independent linear/exponential CV slew.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Rack-independent, bounded, allocation-free, lock-free per-lane DSP.
 */
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>

namespace modular_synth {
namespace dsp {

class SlewGlide {
public:
    static constexpr double kMinSampleRateHz = 1000.0;
    static constexpr double kMaxSampleRateHz = 384000.0;
    static constexpr double kMaxTimeSeconds = 5.0;
    static constexpr double kMaxVolts = 10.0;
    static constexpr double kSnapEpsilon = 1.0e-6;
    // Two distinct thresholds prevent the MOVING output from chattering when
    // an externally modulated target jitters around the settled boundary.
    static constexpr double kMoveGateOffEpsilon = 1.0e-4;
    static constexpr double kMoveGateOnEpsilon = 2.0e-4;
    static constexpr double kMoveGateEpsilon = kMoveGateOffEpsilon;

    struct Input {
        double sampleRateHz = 48000.0;
        double voltage = 0.0;
        double riseSeconds = 0.20;
        double fallSeconds = 0.30;
        double riseCvVolts = 0.0; // +10 V adds 5 seconds
        double fallCvVolts = 0.0; // +10 V adds 5 seconds
    };

    struct Output {
        float linear = 0.0f;
        float exponential = 0.0f;
        float movingGate = 0.0f;
    };

    static_assert(sizeof(double) == 8 && std::numeric_limits<double>::is_iec559,
                  "SlewGlide requires IEEE-754 binary64");

    static bool finite(double value) noexcept {
        std::uint64_t bits = 0;
        std::memcpy(&bits, &value, sizeof(bits));
        return (bits & UINT64_C(0x7ff0000000000000)) !=
               UINT64_C(0x7ff0000000000000);
    }

    static double bounded(double value, double fallback, double low,
                          double high) noexcept {
        if (!finite(value))
            return fallback;
        return std::min(high, std::max(low, value));
    }

    void reset() noexcept {
        linear_ = 0.0;
        exponential_ = 0.0;
        moving_ = false;
        cachedSampleRate_ = -1.0;
        cachedRise_ = -1.0;
        cachedFall_ = -1.0;
        alphaRise_ = 1.0;
        alphaFall_ = 1.0;
    }

    double linearVoltage() const noexcept { return linear_; }
    double exponentialVoltage() const noexcept { return exponential_; }

    Output process(const Input& input) noexcept {
        const double sampleRate = input.sampleRateHz;
        if (!finite(sampleRate) || sampleRate < kMinSampleRateHz
            || sampleRate > kMaxSampleRateHz) {
            reset();
            return {};
        }

        const double target = bounded(input.voltage, 0.0, -kMaxVolts, kMaxVolts);
        const double riseTime = bounded(
            bounded(input.riseSeconds, 0.20, 0.0, kMaxTimeSeconds)
                + 0.5 * bounded(input.riseCvVolts, 0.0, -20.0, 20.0),
            0.20, 0.0, kMaxTimeSeconds);
        const double fallTime = bounded(
            bounded(input.fallSeconds, 0.30, 0.0, kMaxTimeSeconds)
                + 0.5 * bounded(input.fallCvVolts, 0.0, -20.0, 20.0),
            0.30, 0.0, kMaxTimeSeconds);

        if (cachedSampleRate_ != sampleRate || cachedRise_ != riseTime
            || cachedFall_ != fallTime) {
            cachedSampleRate_ = sampleRate;
            cachedRise_ = riseTime;
            cachedFall_ = fallTime;
            // Each envelope reaches 99% of a fixed target after its specified
            // directional time. Cache expm1 when controls are stationary.
            alphaRise_ = riseTime == 0.0 ? 1.0
                : -std::expm1(-4.605170185988092 / (sampleRate * riseTime));
            alphaFall_ = fallTime == 0.0 ? 1.0
                : -std::expm1(-4.605170185988092 / (sampleRate * fallTime));
        }

        const double linearDiff = target - linear_;
        const double linearTime = linearDiff >= 0.0 ? riseTime : fallTime;
        if (linearTime == 0.0 || std::abs(linearDiff) <= kSnapEpsilon) {
            linear_ = target;
        } else {
            // Defined as seconds to traverse 10 V, not arbitrary dB time.
            const double maxStep = 10.0 / (sampleRate * linearTime);
            linear_ += std::max(-maxStep, std::min(maxStep, linearDiff));
        }

        const double expDiff = target - exponential_;
        const double alpha = expDiff >= 0.0 ? alphaRise_ : alphaFall_;
        if (alpha == 1.0 || std::abs(expDiff) <= kSnapEpsilon) {
            exponential_ = target;
        } else {
            exponential_ += alpha * expDiff;
        }

        // Last-ditch safety for extreme input transients. All mathematical
        // branches above are bounded and finite for valid sample rates.
        linear_ = bounded(linear_, 0.0, -kMaxVolts, kMaxVolts);
        exponential_ = bounded(exponential_, 0.0, -kMaxVolts, kMaxVolts);

        Output output;
        output.linear = static_cast<float>(linear_);
        output.exponential = static_cast<float>(exponential_);
        const double remaining = std::max(std::abs(linear_ - target),
                                          std::abs(exponential_ - target));
        if (moving_) {
            if (remaining <= kMoveGateOffEpsilon)
                moving_ = false;
        } else if (remaining > kMoveGateOnEpsilon) {
            moving_ = true;
        }
        output.movingGate = moving_ ? 10.0f : 0.0f;
        return output;
    }

private:
    double linear_ = 0.0;
    double exponential_ = 0.0;
    bool moving_ = false;
    double cachedSampleRate_ = -1.0;
    double cachedRise_ = -1.0;
    double cachedFall_ = -1.0;
    double alphaRise_ = 1.0;
    double alphaFall_ = 1.0;
};

} // namespace dsp
} // namespace modular_synth
