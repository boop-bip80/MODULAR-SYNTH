/*
 * MODULAR-SYNTH StereoEcho — original, Rack-independent DSP core.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Two fractional-delay rings per voice. All memory is allocated in the
 * constructor; process()/reset() never allocate, lock or clear the rings.
 */
#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <vector>

namespace modular_synth {
namespace dsp {

class StereoEchoDSP {
public:
    struct Sample {
        float left;
        float right;
    };

    static constexpr double kMinDelayMs = 1.0;
    static constexpr double kMaxDelayMs = 1000.0;
    static constexpr double kMaxFeedback = 0.90;
    // -400 dB relative to 1 V; prevent immortal rounded subnormal tails.
    static constexpr double kFeedbackSilenceFloorVolts = 1.0e-20;
    static constexpr int kMaxFullRateHz = 192000;
    static constexpr std::size_t kCapacityFrames =
        static_cast<std::size_t>(kMaxFullRateHz) + 2u;
    static constexpr double kSlewSecondsTo99Point9Percent = 0.025;
    // Wet, feedback and stereo crossfeed reach 99.9% of a new setting in 10 ms.
    // Initialization/reset keep the first requested setting immediate.
    static constexpr double kControlSlewSecondsTo99Point9Percent = 0.010;

    static_assert(sizeof(float) == 4 && sizeof(double) == 8
                  && std::numeric_limits<float>::is_iec559
                  && std::numeric_limits<double>::is_iec559,
                  "StereoEcho requires IEEE-754 binary32/binary64");

    // 16 voices consume 16 * 2 * 192002 * sizeof(float) = 24,576,256 bytes
    // of audio ring memory (23.44 MiB), plus small vector metadata.
    static constexpr std::size_t reservedBytesPerVoice() noexcept {
        return 2u * kCapacityFrames * sizeof(float);
    }

    StereoEchoDSP()
        : leftBuffer_(kCapacityFrames, 0.0f),
          rightBuffer_(kCapacityFrames, 0.0f) {}

    StereoEchoDSP(const StereoEchoDSP&) = delete;
    StereoEchoDSP& operator=(const StereoEchoDSP&) = delete;

    static bool finite(double value) noexcept {
        std::uint64_t bits = 0;
        std::memcpy(&bits, &value, sizeof(bits));
        return (bits & UINT64_C(0x7ff0000000000000)) != UINT64_C(0x7ff0000000000000);
    }

    static double clampFinite(double value, double fallback,
                              double minValue, double maxValue) noexcept {
        if (!finite(value))
            return fallback;
        return std::min(maxValue, std::max(minValue, value));
    }

    // Reject microscopic input energy before arithmetic in both the dry path
    // and feedback path. The same -400 dB floor already protects the rings.
    static double inputVoltage(double value) noexcept {
        const double safe = clampFinite(value, 0.0, -20.0, 20.0);
        return safe > -kFeedbackSilenceFloorVolts && safe < kFeedbackSilenceFloorVolts
            ? 0.0 : safe;
    }

    static float outputVoltage(double value) noexcept {
        const double safe = clampFinite(value, 0.0, -10.0, 10.0);
        // A wet/dry combination can itself become subnormal even if both
        // inputs were normal. Never hand denormal floats to the host.
        return safe > -kFeedbackSilenceFloorVolts && safe < kFeedbackSilenceFloorVolts
            ? 0.0f : static_cast<float>(safe);
    }

    void reset() noexcept {
        // Logical generation reset. Never memset ~1.5 MiB from audio thread.
        writeIndex_ = 0;
        validFrames_ = 0;
        previousSampleRate_ = 0.0;
        currentDelaySamples_ = 0.0;
        slewAmount_ = 1.0;
        controlSlewAmount_ = 1.0;
        currentFeedback_ = 0.0;
        currentWet_ = 0.0;
        currentCrossfeed_ = 0.0;
        initialized_ = false;
        controlsInitialized_ = false;
    }

    double currentDelaySamples() const noexcept { return currentDelaySamples_; }
    double currentFeedback() const noexcept { return currentFeedback_; }
    double currentWet() const noexcept { return currentWet_; }
    double currentCrossfeed() const noexcept { return currentCrossfeed_; }

    // The maximum actual milliseconds decreases above 192 kHz rather than
    // allocating a larger ring in the audio thread.
    double effectiveMaxMs(double sampleRate) const noexcept {
        if (!finite(sampleRate) || sampleRate < 1000.0)
            return kMinDelayMs;
        return std::min(kMaxDelayMs,
                        1000.0 * (kCapacityFrames - 2u) / sampleRate);
    }

    Sample process(double inputL, double inputR, double sampleRate,
                   double delayMs, double feedback, double wet,
                   double crossfeed) noexcept {
        if (!finite(sampleRate) || sampleRate < 1000.0 || sampleRate > 384000.0) {
            reset();
            return {0.0f, 0.0f};
        }
        if (sampleRate != previousSampleRate_) {
            // O(1), discards incompatible history without clearing buffers.
            writeIndex_ = 0;
            validFrames_ = 0;
            previousSampleRate_ = sampleRate;
            initialized_ = false;
            controlsInitialized_ = false;
            slewAmount_ = 1.0 - std::exp(
                -6.907755278982137 / (kSlewSecondsTo99Point9Percent * sampleRate));
            controlSlewAmount_ = 1.0 - std::exp(
                -6.907755278982137 / (kControlSlewSecondsTo99Point9Percent * sampleRate));
        }

        const double safeL = inputVoltage(inputL);
        const double safeR = inputVoltage(inputR);
        const double maxMs = effectiveMaxMs(sampleRate);
        const double ms = clampFinite(delayMs, 250.0, kMinDelayMs, maxMs);
        const double targetSamples = ms * sampleRate / 1000.0;
        const double targetFeedback = clampFinite(feedback, 0.0, 0.0, kMaxFeedback);
        const double targetWet = clampFinite(wet, 0.0, 0.0, 1.0);
        const double targetCrossfeed = clampFinite(crossfeed, 0.0, 0.0, 1.0);
        if (!controlsInitialized_) {
            currentFeedback_ = targetFeedback;
            currentWet_ = targetWet;
            currentCrossfeed_ = targetCrossfeed;
            controlsInitialized_ = true;
        } else {
            // One-pole smoothing is bounded by the already-clamped targets,
            // and introduces no buffers, locks or allocations on the audio path.
            currentFeedback_ += controlSlewAmount_ * (targetFeedback - currentFeedback_);
            currentWet_ += controlSlewAmount_ * (targetWet - currentWet_);
            currentCrossfeed_ += controlSlewAmount_ * (targetCrossfeed - currentCrossfeed_);
        }
        const double fb = currentFeedback_;
        const double blend = currentWet_;
        const double swap = currentCrossfeed_;

        if (!initialized_) {
            currentDelaySamples_ = targetSamples;
            initialized_ = true;
        } else {
            currentDelaySamples_ += slewAmount_ * (targetSamples - currentDelaySamples_);
        }
        currentDelaySamples_ = std::min(static_cast<double>(kCapacityFrames - 2u),
                                        std::max(1.0, currentDelaySamples_));
        const auto whole = static_cast<std::size_t>(currentDelaySamples_);
        const double fraction = currentDelaySamples_ - whole;

        const double delayedL = (1.0 - fraction) * readAge(leftBuffer_, whole)
                                 + fraction * readAge(leftBuffer_, whole + 1u);
        const double delayedR = (1.0 - fraction) * readAge(rightBuffer_, whole)
                                 + fraction * readAge(rightBuffer_, whole + 1u);

        // This 2x2 crossfeed matrix has row sum 1. Feedback <= 0.90 keeps
        // the linear echo loop contractive, even at full ping-pong mode.
        const double nextL = safeL + fb * ((1.0 - swap) * delayedL + swap * delayedR);
        const double nextR = safeR + fb * ((1.0 - swap) * delayedR + swap * delayedL);
        // Sanitize and zero below -400 dB before converting to float.
        // A float's smallest subnormal can round 0.9 * x back to x,
        // otherwise leaving a perpetual feedback tail and denormal costs.
        leftBuffer_[writeIndex_] = ringVoltage(nextL);
        rightBuffer_[writeIndex_] = ringVoltage(nextR);

        ++writeIndex_;
        if (writeIndex_ == kCapacityFrames)
            writeIndex_ = 0;
        if (validFrames_ < kCapacityFrames - 2u)
            ++validFrames_;

        return {
            outputVoltage((1.0 - blend) * safeL + blend * delayedL),
            outputVoltage((1.0 - blend) * safeR + blend * delayedR)
        };
    }

private:
    static float ringVoltage(double value) noexcept {
        const double safe = clampFinite(value, 0.0, -20.0, 20.0);
        return safe > -kFeedbackSilenceFloorVolts && safe < kFeedbackSilenceFloorVolts
            ? 0.0f : static_cast<float>(safe);
    }

    double readAge(const std::vector<float>& data, std::size_t samplesAgo) const noexcept {
        if (samplesAgo == 0u || samplesAgo > validFrames_
            || samplesAgo >= kCapacityFrames)
            return 0.0;
        const auto index = writeIndex_ >= samplesAgo
            ? writeIndex_ - samplesAgo
            : kCapacityFrames + writeIndex_ - samplesAgo;
        return data[index];
    }

    std::vector<float> leftBuffer_;
    std::vector<float> rightBuffer_;
    std::size_t writeIndex_ = 0;
    std::size_t validFrames_ = 0;
    double previousSampleRate_ = 0.0;
    double currentDelaySamples_ = 0.0;
    double slewAmount_ = 1.0;
    double controlSlewAmount_ = 1.0;
    double currentFeedback_ = 0.0;
    double currentWet_ = 0.0;
    double currentCrossfeed_ = 0.0;
    bool initialized_ = false;
    bool controlsInitialized_ = false;
};

} // namespace dsp
} // namespace modular_synth
