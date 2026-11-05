/*
 * MODULAR-SYNTH ClockedLFO — original Rack-independent modulation engine.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * One instance per polyphonic lane. No dynamic memory, locks or host API.
 */
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>

namespace modular_synth {
namespace dsp {

class ClockedLFO {
public:
    static constexpr double kMinSampleRateHz = 1000.0;
    static constexpr double kMaxSampleRateHz = 384000.0;
    static constexpr double kMaxFrequencyHz = 200.0;
    static constexpr double kMinClockPeriodSeconds = 0.02; // 50 Hz clock
    static constexpr double kMaxClockPeriodSeconds = 10.0;
    static constexpr double kEndOfCyclePulseSeconds = 0.001;

    struct Input {
        double sampleRateHz = 48000.0;
        double log2RateHz = -1.0;
        double rateCvVolts = 0.0;
        double ratioIndex = 2.0; // 0:1/4, 1:1/2, 2:1, 3:2, 4:4
        double phaseOffset = 0.0;
        double phaseCvVolts = 0.0;
        double pulseWidth = 0.5;
        double widthCvVolts = 0.0;
        double clockVoltage = 0.0;
        double resetVoltage = 0.0;
        bool clockConnected = false;
    };

    struct Output {
        float sine = 0.0f;
        float triangle = 0.0f;
        float ramp = 0.0f;
        float pulse = 0.0f;
        float endOfCycle = 0.0f;
        double unshiftedPhase = 0.0;
        double frequencyHz = 0.0;
        bool clockLocked = false;
    };

    static_assert(sizeof(double) == 8 && std::numeric_limits<double>::is_iec559,
                  "ClockedLFO requires IEEE-754 binary64");

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

    static double clockRatio(double value) noexcept {
        static constexpr double ratios[] = {0.25, 0.5, 1.0, 2.0, 4.0};
        const int index = static_cast<int>(std::round(bounded(value, 2.0, 0.0, 4.0)));
        return ratios[index];
    }

    void reset() noexcept {
        phase_ = 0.0;
        endOfCycleSeconds_ = 0.0;
        clockArmed_ = true;
        resetArmed_ = true;
        sawClockEdge_ = false;
        clockLocked_ = false;
        secondsSinceClockEdge_ = 0.0;
        clockPeriodSeconds_ = 0.0;
        clockPulseIndex_ = 0;
        suspectedMissedBeatMultiple_ = 0;
    }

    double phase() const noexcept { return phase_; }
    bool locked() const noexcept { return clockLocked_; }

    Output process(const Input& input) noexcept {
        const double rate = input.sampleRateHz;
        if (!finite(rate) || rate < kMinSampleRateHz || rate > kMaxSampleRateHz) {
            reset();
            return {};
        }

        const double sampleTime = 1.0 / rate;
        const double freeOctaves = bounded(
            bounded(input.log2RateHz, -1.0, -6.0, 4.0)
                + bounded(input.rateCvVolts, 0.0, -20.0, 20.0),
            -1.0, -8.0, 7.643856189774725);
        const double freeHz = std::exp2(freeOctaves);
        const double ratio = clockRatio(input.ratioIndex);

        // Arm below 1 V and trigger above 2 V. Repeated high gates do not
        // retrigger; pulses within 20 ms of a valid edge are ignored.
        const double clockCv = bounded(input.clockVoltage, 0.0, -20.0, 20.0);
        const double resetCv = bounded(input.resetVoltage, 0.0, -20.0, 20.0);
        const bool resetEdge = schmittRise(resetCv, resetArmed_);

        if (!input.clockConnected) {
            sawClockEdge_ = false;
            clockLocked_ = false;
            clockArmed_ = true;
            secondsSinceClockEdge_ = 0.0;
            clockPulseIndex_ = 0;
            suspectedMissedBeatMultiple_ = 0;
        } else {
            if (sawClockEdge_) {
                secondsSinceClockEdge_ += sampleTime;
                // A stopped external clock returns to the free oscillator
                // without resetting phase or replaying old tempo values.
                if (clockLocked_ && secondsSinceClockEdge_ >
                    4.0 * clockPeriodSeconds_) {
                    sawClockEdge_ = false;
                    clockLocked_ = false;
                    clockPulseIndex_ = 0;
                    suspectedMissedBeatMultiple_ = 0;
                }
            }
            if (schmittRise(clockCv, clockArmed_)) {
                if (!sawClockEdge_) {
                    sawClockEdge_ = true;
                    clockLocked_ = false;
                    secondsSinceClockEdge_ = 0.0;
                    clockPulseIndex_ = 0;
                    suspectedMissedBeatMultiple_ = 0;
                    phase_ = 0.0; // first pulse establishes a phase origin
                } else if (secondsSinceClockEdge_ >= kMinClockPeriodSeconds) {
                    if (secondsSinceClockEdge_ <= kMaxClockPeriodSeconds) {
                        double newPeriod = secondsSinceClockEdge_;
                        unsigned elapsedBeats = 1u;
                        if (clockLocked_ && clockPeriodSeconds_ >= kMinClockPeriodSeconds) {
                            // A missing external beat yields an interval almost
                            // exactly 2x/3x the previously locked period. Keep
                            // the prior tempo for one such gap and advance the
                            // divided phase by the full beat count. Two equal
                            // consecutive long gaps instead confirm a true
                            // slower tempo. Other tempo edits take effect now.
                            const double multiple = newPeriod / clockPeriodSeconds_;
                            const double rounded = std::round(multiple);
                            if (rounded >= 2.0 && rounded <= 3.0 &&
                                    std::abs(newPeriod - rounded * clockPeriodSeconds_) <=
                                        0.08 * clockPeriodSeconds_) {
                                const unsigned candidate = static_cast<unsigned>(rounded);
                                if (suspectedMissedBeatMultiple_ != candidate) {
                                    newPeriod = clockPeriodSeconds_;
                                    elapsedBeats = candidate;
                                    suspectedMissedBeatMultiple_ = candidate;
                                } else {
                                    suspectedMissedBeatMultiple_ = 0;
                                }
                            } else {
                                suspectedMissedBeatMultiple_ = 0;
                            }
                        } else {
                            suspectedMissedBeatMultiple_ = 0;
                        }
                        clockPeriodSeconds_ = newPeriod;
                        clockLocked_ = true;
                        clockPulseIndex_ = (clockPulseIndex_ + elapsedBeats) & 3u;
                        const int divider = ratio == 0.25 ? 4 : ratio == 0.5 ? 2 : 1;
                        const double aligned = static_cast<double>(
                            clockPulseIndex_ % static_cast<unsigned>(divider)) / divider;
                        phase_ = aligned;
                        if (aligned == 0.0)
                            endOfCycleSeconds_ = kEndOfCyclePulseSeconds;
                    } else {
                        // A new distant pulse starts a new clock measurement.
                        clockLocked_ = false;
                        clockPulseIndex_ = 0;
                        suspectedMissedBeatMultiple_ = 0;
                        phase_ = 0.0;
                    }
                    secondsSinceClockEdge_ = 0.0;
                }
            }
        }

        if (resetEdge) {
            phase_ = 0.0;
            clockPulseIndex_ = 0;
            endOfCycleSeconds_ = 0.0;
            suspectedMissedBeatMultiple_ = 0;
        }

        const double hz = clockLocked_
            ? std::min(static_cast<double>(kMaxFrequencyHz), ratio / clockPeriodSeconds_) : freeHz;
        const double offset = bounded(input.phaseOffset, 0.0, 0.0, 1.0)
                              + 0.1 * bounded(input.phaseCvVolts, 0.0, -20.0, 20.0);
        const double width = bounded(bounded(input.pulseWidth, 0.5, 0.05, 0.95)
                            + 0.1 * bounded(input.widthCvVolts, 0.0, -20.0, 20.0),
                            0.5, 0.05, 0.95);
        const double visiblePhase = wrapPhase(phase_ + offset);
        constexpr double tau = 6.2831853071795864769;

        Output output;
        output.sine = static_cast<float>(5.0 * std::sin(tau * visiblePhase));
        output.triangle = static_cast<float>(5.0 * (1.0 -
            4.0 * std::abs(visiblePhase - 0.5)));
        output.ramp = static_cast<float>(10.0 * visiblePhase - 5.0);
        output.pulse = visiblePhase < width ? 5.0f : -5.0f;
        output.endOfCycle = endOfCycleSeconds_ > 0.0 ? 10.0f : 0.0f;
        output.unshiftedPhase = phase_;
        output.frequencyHz = hz;
        output.clockLocked = clockLocked_;

        endOfCycleSeconds_ = std::max(0.0, endOfCycleSeconds_ - sampleTime);
        phase_ += hz * sampleTime;
        if (phase_ >= 1.0) {
            phase_ -= 1.0; // hz / sampleRate <= 0.2, so at most one wrap
            endOfCycleSeconds_ = kEndOfCyclePulseSeconds;
        }
        return output;
    }

private:
    static double wrapPhase(double value) noexcept {
        return value - std::floor(value);
    }

    static bool schmittRise(double value, bool& armed) noexcept {
        if (value <= 1.0) {
            armed = true;
            return false;
        }
        if (value >= 2.0 && armed) {
            armed = false;
            return true;
        }
        return false;
    }

    double phase_ = 0.0;
    double endOfCycleSeconds_ = 0.0;
    double secondsSinceClockEdge_ = 0.0;
    double clockPeriodSeconds_ = 0.0;
    bool clockArmed_ = true;
    bool resetArmed_ = true;
    bool sawClockEdge_ = false;
    bool clockLocked_ = false;
    unsigned clockPulseIndex_ = 0;
    unsigned suspectedMissedBeatMultiple_ = 0;
};

} // namespace dsp
} // namespace modular_synth
