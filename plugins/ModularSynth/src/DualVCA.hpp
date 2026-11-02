/*
 * MODULAR-SYNTH Dual VCA — original Rack-independent gain engine.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * No heap allocation, lock, Rack dependency or host callback on the audio path.
 * Each polyphonic lane has an independent 2 ms control smoothing state.
 */
#pragma once

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <limits>

namespace modular_synth {
namespace dsp {

class DualVCA {
public:
    static constexpr double kSlewSeconds = 0.002;

    struct Input {
        double inputVoltage = 0.0;
        double sampleRateHz = 48000.0;
        double level = 1.0;
        double cvVolts = 10.0;
        double curve = 0.0;
        bool cvConnected = false;
    };

    static bool finite(double value) noexcept {
        static_assert(sizeof(double) == sizeof(std::uint64_t),
                      "DualVCA requires IEEE-754 binary64");
        static_assert(std::numeric_limits<double>::is_iec559,
                      "DualVCA requires IEEE-754 binary64");
        std::uint64_t bits = 0;
        std::memcpy(&bits, &value, sizeof(bits));
        return (bits & UINT64_C(0x7ff0000000000000)) !=
               UINT64_C(0x7ff0000000000000);
    }

    static double bounded(double value, double fallback,
                          double minimum, double maximum) noexcept {
        return finite(value)
            ? std::min(maximum, std::max(minimum, value))
            : fallback;
    }

    static float boundedSum(float a, float b) noexcept {
        const double first = bounded(static_cast<double>(a), 0.0, -10.0, 10.0);
        const double second = bounded(static_cast<double>(b), 0.0, -10.0, 10.0);
        return static_cast<float>(
            std::min(10.0, std::max(-10.0, first + second)));
    }

    void reset() noexcept {
        smoothedGain_ = 0.0;
        initialized_ = false;
    }

    double gain() const noexcept { return smoothedGain_; }

    // CV unconnected: unity envelope. Connected CV: 0 V mutes, +10 V
    // reaches the level-knob ceiling, and negative CV cannot invert phase.
    // Curve 0 is linear CV, curve 1 is cubic CV; both meet at 0 and 10 V.
    float process(const Input& input) noexcept {
        const double rate = input.sampleRateHz;
        if (!finite(rate) || rate < 1000.0 || rate > 768000.0) {
            reset();
            return 0.0f;
        }

        const double audio = bounded(input.inputVoltage, 0.0, -20.0, 20.0);
        const double level = bounded(input.level, 0.0, 0.0, 1.0);
        const double curve = bounded(input.curve, 0.0, 0.0, 1.0);
        // Fail closed on invalid connected CV, so corrupt automation cannot
        // unexpectedly turn a previously silent voice fully on.
        const double normalizedCV = input.cvConnected
            ? 0.1 * bounded(input.cvVolts, 0.0, 0.0, 10.0)
            : 1.0;
        const double cvSquared = normalizedCV * normalizedCV;
        const double response = normalizedCV *
            (1.0 - curve + curve * cvSquared);
        const double targetGain = level * response;

        if (!initialized_) {
            smoothedGain_ = targetGain;
            initialized_ = true;
        } else {
            // One-pole response (~2 ms time constant), bounded at all
            // supported sample rates, with no exp()/pow() on the audio path.
            const double alpha = std::min(1.0, 1.0 / (kSlewSeconds * rate));
            smoothedGain_ += alpha * (targetGain - smoothedGain_);
        }

        const double output = audio * smoothedGain_;
        return static_cast<float>(
            std::min(10.0, std::max(-10.0, output)));
    }

private:
    double smoothedGain_ = 0.0;
    bool initialized_ = false;
};

} // namespace dsp
} // namespace modular_synth
