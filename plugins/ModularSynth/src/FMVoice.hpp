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

    // Carson-style sideband guard for a *sine* phase modulator. This is
    // a conservative timbral roll-off near Nyquist, NOT alias elimination:
    // higher Bessel sidebands and feedback harmonics can still alias.
    static double bandwidthIndexCeiling(double carrierHz, double modulatorHz,
                                        double sampleRateHz) noexcept {
        if (!finite(sampleRateHz) || sampleRateHz < 1000.0
            || sampleRateHz > 384000.0
            || !finite(carrierHz) || carrierHz < 0.0
            || !finite(modulatorHz) || modulatorHz < 0.0)
            return 0.0;
        if (modulatorHz == 0.0)
            return kMaxIndexRadians;
        const double guardHz = 0.45 * sampleRateHz;
        const double roomHz = std::max(0.0, guardHz - std::min(carrierHz, guardHz));
        return bounded(roomHz / modulatorHz - 1.0, 0.0, 0.0,
                       kMaxIndexRadians);
    }

    void reset() noexcept {
        carrierPhase = 0.0;
        modulatorPhase = 0.0;
        previousModulator = 0.0;
        previousCarrier = 0.0;
        smoothedRatio = 1.0;
        smoothedIndex = 0.0;
        smoothedFeedback = 0.0;
        smoothedGuardCeiling = kMaxIndexRadians;
        initialized = false;
        guardInitialized = false;
    }

    Output process(const Input& input) noexcept {
        if (!finite(input.sampleRateHz) || input.sampleRateHz < 1000.0
            || input.sampleRateHz > 384000.0
            || !finite(input.frequencyHz) || input.frequencyHz < 0.0)
            return {};

        const double ratio = bounded(input.ratio, 1.0, 0.125, kMaxRatio);
        const double index = bounded(input.indexRadians, 0.0, 0.0,
                                     kMaxIndexRadians);
        const double feedback = bounded(input.feedback, 0.0, -kMaxFeedback,
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
        const double maxHz = 0.45 * input.sampleRateHz;
        const double carrierHz = std::min(input.frequencyHz, maxHz);
        // Divide before multiplication: extreme finite input frequencies
        // must not overflow when multiplied by the modulator ratio.
        const double modulatorHz = input.frequencyHz >= maxHz / smoothedRatio
            ? maxHz : input.frequencyHz * smoothedRatio;
        const double carrierStep = carrierHz / input.sampleRateHz;
        const double modulatorStep = modulatorHz / input.sampleRateHz;
        const double ceiling = bandwidthIndexCeiling(
            carrierHz, modulatorHz, input.sampleRateHz);
        if (!guardInitialized) {
            // Saved high-note timbre starts correctly; no fake reset glide.
            smoothedGuardCeiling = ceiling;
            guardInitialized = true;
        } else {
            // Pitch/ratio CV may jump while the module is sounding. Smooth
            // changes to the ceiling so the PM index cannot jump instantly.
            const double alpha = std::min(1.0, 1.0 / (0.002 * input.sampleRateHz));
            smoothedGuardCeiling += alpha * (ceiling - smoothedGuardCeiling);
        }
        const double effectiveIndex = std::min(smoothedIndex, smoothedGuardCeiling);

        // Positive values keep the original one-sample modulator loop.
        // Negative values route the same bounded amount to the carrier
        // loop instead. Both contributions approach zero at the sign
        // boundary; this is a topology choice, not negative modulator FM.
        const double modulatorFeedback = std::max(0.0, smoothedFeedback);
        const double carrierFeedback = std::max(0.0, -smoothedFeedback);
        const double modulator = std::sin(kTwoPi * modulatorPhase
                                          + modulatorFeedback * previousModulator);
        previousModulator = modulator;
        const double carrier = std::sin(kTwoPi * carrierPhase
                                        + effectiveIndex * modulator
                                        + carrierFeedback * previousCarrier);
        previousCarrier = carrier;

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
    double smoothedGuardCeiling = kMaxIndexRadians;

private:
    double previousModulator = 0.0;
    double previousCarrier = 0.0;
    bool initialized = false;
    bool guardInitialized = false;
};

} // namespace dsp
} // namespace modular_synth
