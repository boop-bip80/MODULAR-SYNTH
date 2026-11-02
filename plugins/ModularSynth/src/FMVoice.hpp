/*
 * MODULAR-SYNTH FM Voice — original, Rack-independent two-operator DSP
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * One instance per voice; no allocations, locks, host calls, or I/O.
 */
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>

namespace modular_synth {
namespace dsp {

class FMVoice {
public:
    static constexpr double kTwoPi = 6.283185307179586476925286766559;
    static constexpr double kC4Hz = 261.6255653005986;
    static constexpr double kMaxRatio = 16.0;
    static constexpr double kMaxIndexRadians = 8.0;
    static constexpr double kMaxFeedback = 0.95;

    struct Input {
        double frequencyHz = kC4Hz;
        double sampleRateHz = 48000.0;
        double ratio = 1.0;
        double indexRadians = 0.0;
        double feedback = 0.0;
    };

    struct Output {
        float carrier = 0.0f;
        float modulator = 0.0f;
    };

    static_assert(sizeof(double) == 8 && sizeof(float) == 4
                  && std::numeric_limits<double>::is_iec559
                  && std::numeric_limits<float>::is_iec559,
                  "FM Voice requires IEEE-754 binary32/binary64");

    // Remain correct in the aggressive -ffast-math compiler test profile.
    static bool finite(double value) noexcept {
        std::uint64_t bits = 0;
        std::memcpy(&bits, &value, sizeof(bits));
        return (bits & UINT64_C(0x7ff0000000000000)) !=
               UINT64_C(0x7ff0000000000000);
    }

    static bool finite(float value) noexcept {
        std::uint32_t bits = 0;
        std::memcpy(&bits, &value, sizeof(bits));
        return (bits & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
    }

    static double bounded(double value, double fallback, double lo,
                          double hi) noexcept {
        return finite(value) ? std::min(hi, std::max(lo, value)) : fallback;
    }

    // Rack's 1 V/oct pitch convention places C4 at zero volts.
    static double frequencyForPitch(double octaveVolts) noexcept {
        return kC4Hz * std::exp2(bounded(octaveVolts, 0.0, -20.0, 20.0));
    }

    void reset() noexcept {
        carrierPhase = 0.0;
        modulatorPhase = 0.0;
        previousModulator = 0.0;
        smoothedRatio = 1.0;
        smoothedIndex = 0.0;
        smoothedFeedback = 0.0;
        initialized = false;
    }

    Output process(const Input& input) noexcept {
        if (!finite(input.sampleRateHz) || input.sampleRateHz < 1000.0
            || input.sampleRateHz > 384000.0
            || !finite(input.frequencyHz) || input.frequencyHz < 0.0)
            return {};

        const double ratio = bounded(input.ratio, 1.0, 0.125, kMaxRatio);
        const double index = bounded(input.indexRadians, 0.0, 0.0,
                                     kMaxIndexRadians);
        const double feedback = bounded(input.feedback, 0.0, 0.0,
                                        kMaxFeedback);

        // 2 ms smoothing, including ratio modulation. The first sample
        // adopts the patch's saved control state without a spurious glide.
        if (!initialized) {
            smoothedRatio = ratio;
            smoothedIndex = index;
            smoothedFeedback = feedback;
            initialized = true;
        } else {
            const double alpha = std::min(1.0, 1.0 / (0.002 * input.sampleRateHz));
            smoothedRatio += alpha * (ratio - smoothedRatio);
            smoothedIndex += alpha * (index - smoothedIndex);
            smoothedFeedback += alpha * (feedback - smoothedFeedback);
        }

        // Individual oscillator frequency caps avoid invalid phase steps;
        // FM/feedback sidebands themselves are NOT bandlimited.
        const double carrierStep = std::min(input.frequencyHz,
                                             0.45 * input.sampleRateHz)
                                   / input.sampleRateHz;
        const double modulatorStep = std::min(
            input.frequencyHz * smoothedRatio, 0.45 * input.sampleRateHz)
            / input.sampleRateHz;

        const double modulator = std::sin(kTwoPi * modulatorPhase
                                          + smoothedFeedback * previousModulator);
        previousModulator = modulator;
        const double carrier = std::sin(kTwoPi * carrierPhase
                                        + smoothedIndex * modulator);

        carrierPhase += carrierStep;
        modulatorPhase += modulatorStep;
        if (carrierPhase >= 1.0)
            carrierPhase -= 1.0;
        if (modulatorPhase >= 1.0)
            modulatorPhase -= 1.0;

        return {static_cast<float>(carrier), static_cast<float>(modulator)};
    }

    // Kept public for a transparent, allocation-free DSP test contract.
    double carrierPhase = 0.0;
    double modulatorPhase = 0.0;
    double smoothedRatio = 1.0;
    double smoothedIndex = 0.0;
    double smoothedFeedback = 0.0;

private:
    double previousModulator = 0.0;
    bool initialized = false;
};

} // namespace dsp
} // namespace modular_synth
