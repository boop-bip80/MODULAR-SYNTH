/*
 * MODULAR-SYNTH ChanceHold — first-party deterministic random CV generator.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Rack-independent per-lane DSP. Bounded CPU/memory; no allocation, locks,
 * system randomness, file I/O or other audio-thread side effects.
 */
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>

namespace modular_synth {
namespace dsp {

class ChanceHold {
public:
    static constexpr double kMinSampleRateHz = 1000.0;
    static constexpr double kMaxSampleRateHz = 384000.0;
    static constexpr double kTriggerSeconds = 0.001;
    static constexpr std::uint32_t kDefaultSeed = UINT32_C(0x6d2b79f5);

    struct Input {
        double sampleRateHz = 48000.0;
        double log2RateHz = 0.0;        // Free clock, 1 Hz default
        double rateCvVolts = 0.0;       // 1 V/oct
        double probability = 0.75;     // Acceptance probability 0...1
        double probabilityCvVolts = 0.0; // 10 V changes probability by 1
        double glideSeconds = 0.15;    // Approximate 99% settling time
        double glideCvVolts = 0.0;      // 10 V adds 2 seconds
        double clockVoltage = 0.0;
        double resetVoltage = 0.0;
        bool clockConnected = false;
        bool semitoneQuantize = false;
    };

    struct Output {
        float held = 0.0f;
        float glide = 0.0f;
        float trigger = 0.0f;
        double freeFrequencyHz = 0.0;
        bool externalClock = false;
    };

    static_assert(sizeof(double) == 8 && std::numeric_limits<double>::is_iec559,
                  "ChanceHold requires IEEE-754 binary64");

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

    explicit ChanceHold(std::uint32_t seed = kDefaultSeed) noexcept
        : seed_(seed ? seed : kDefaultSeed) {
        reset();
    }

    void setSeed(std::uint32_t seed) noexcept {
        seed_ = seed ? seed : kDefaultSeed;
        reset();
    }

    void reset() noexcept {
        resetState();
        clockArmed_ = true;
        resetArmed_ = true;
    }

    double heldVoltage() const noexcept { return held_; }
    double glideVoltage() const noexcept { return glide_; }
    std::uint32_t generatorState() const noexcept { return randomState_; }

    Output process(const Input& input) noexcept {
        const double sampleRate = input.sampleRateHz;
        if (!finite(sampleRate) || sampleRate < kMinSampleRateHz
            || sampleRate > kMaxSampleRateHz) {
            reset();
            return {};
        }
        const double dt = 1.0 / sampleRate;
        const double octaves = bounded(
            bounded(input.log2RateHz, 0.0, -4.0, 5.0)
                + bounded(input.rateCvVolts, 0.0, -20.0, 20.0),
            0.0, -8.0, 7.0);
        const double freeHz = std::exp2(octaves);
        const double chance = bounded(
            bounded(input.probability, 0.75, 0.0, 1.0)
                + 0.1 * bounded(input.probabilityCvVolts, 0.0, -20.0, 20.0),
            0.75, 0.0, 1.0);
        const double glideTime = bounded(
            bounded(input.glideSeconds, 0.15, 0.0, 2.0)
                + 0.2 * bounded(input.glideCvVolts, 0.0, -20.0, 20.0),
            0.15, 0.0, 2.0);

        const double clockCv = bounded(input.clockVoltage, 0.0, -20.0, 20.0);
        const double resetCv = bounded(input.resetVoltage, 0.0, -20.0, 20.0);
        const bool resetEdge = schmittRise(resetCv, resetArmed_);
        const bool clockEdge = schmittRise(clockCv, clockArmed_);

        bool shouldSample = false;
        if (resetEdge) {
            // Reset dominates a simultaneous clock pulse. Do not re-arm the
            // held-high reset gate, so a long MIDI gate cannot reset per tick.
            resetState();
            resetArmed_ = false;
            clockArmed_ = clockCv <= 1.0;
        } else if (input.clockConnected) {
            // No internal clock edges while externally clocked. Disconnecting
            // resumes a complete free-clock period with no surprise trigger.
            internalPhase_ = 0.0;
            shouldSample = clockEdge;
        } else {
            clockArmed_ = true; // a newly connected high clock counts as edge
            internalPhase_ += freeHz * dt;
            if (internalPhase_ >= 1.0) {
                internalPhase_ -= 1.0; // <=128 Hz, >=1 kHz: at most one wrap
                shouldSample = true;
            }
        }

        if (shouldSample) {
            // Advance RNG once for the chance decision on every edge, even
            // when probability is 0 or 1, for reproducible transport behavior.
            const double accept = uniform01();
            if (accept < chance) {
                const double value = 10.0 * uniform01() - 5.0;
                held_ = input.semitoneQuantize
                    ? std::round(value * 12.0) / 12.0 : value;
                held_ = std::max(-5.0, std::min(5.0, held_));
                triggerSeconds_ = kTriggerSeconds;
            }
        }

        if (glideTime == 0.0) {
            glide_ = held_;
        } else {
            // Cache the exponential coefficient when controls are stationary:
            // 99% target acquisition in approximately glideTime seconds.
            if (glideTime != cachedGlideTime_ || sampleRate != cachedSampleRate_) {
                cachedGlideTime_ = glideTime;
                cachedSampleRate_ = sampleRate;
                coefficient_ = -std::expm1(-4.605170185988092 * dt / glideTime);
            }
            glide_ += coefficient_ * (held_ - glide_);
            glide_ = std::max(-5.0, std::min(5.0, glide_));
        }

        Output out;
        out.held = static_cast<float>(held_);
        out.glide = static_cast<float>(glide_);
        out.trigger = triggerSeconds_ > 0.0 ? 10.0f : 0.0f;
        out.freeFrequencyHz = freeHz;
        out.externalClock = input.clockConnected;
        triggerSeconds_ = std::max(0.0, triggerSeconds_ - dt);
        return out;
    }

private:
    static bool schmittRise(double cv, bool& armed) noexcept {
        if (cv <= 1.0) {
            armed = true;
            return false;
        }
        if (cv >= 2.0 && armed) {
            armed = false;
            return true;
        }
        return false;
    }

    std::uint32_t nextRandom() noexcept {
        // xorshift32: a fixed, auditable non-cryptographic generator.
        std::uint32_t x = randomState_;
        x ^= x << 13u;
        x ^= x >> 17u;
        x ^= x << 5u;
        randomState_ = x;
        return x;
    }

    double uniform01() noexcept {
        // 24-bit uniformly distributed lattice in [0,1).
        return static_cast<double>(nextRandom() >> 8u)
            * (1.0 / 16777216.0);
    }

    void resetState() noexcept {
        randomState_ = seed_;
        internalPhase_ = 0.0;
        held_ = 0.0;
        glide_ = 0.0;
        triggerSeconds_ = 0.0;
        cachedSampleRate_ = -1.0;
        cachedGlideTime_ = -1.0;
        coefficient_ = 1.0;
    }

    std::uint32_t seed_ = kDefaultSeed;
    std::uint32_t randomState_ = kDefaultSeed;
    double internalPhase_ = 0.0;
    double held_ = 0.0;
    double glide_ = 0.0;
    double triggerSeconds_ = 0.0;
    double cachedSampleRate_ = -1.0;
    double cachedGlideTime_ = -1.0;
    double coefficient_ = 1.0;
    bool clockArmed_ = true;
    bool resetArmed_ = true;
};

} // namespace dsp
} // namespace modular_synth
