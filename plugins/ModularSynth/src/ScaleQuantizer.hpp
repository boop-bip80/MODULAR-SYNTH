/*
 * MODULAR-SYNTH ScaleQuantizer — deterministic scale-aware polyphonic CV utility.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Rack-independent, fixed-memory DSP; one instance per polyphonic channel.
 */
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>

namespace modular_synth {
namespace dsp {

class ScaleQuantizer {
public:
    enum Scale {
        Chromatic = 0,
        Major = 1,
        NaturalMinor = 2,
        Dorian = 3,
        HarmonicMinor = 4,
        MajorPentatonic = 5,
        MinorPentatonic = 6,
        WholeTone = 7,
        ScaleCount = 8
    };

    struct Input {
        double sampleRateHz = 48000.0;
        double pitchVolts = 0.0;
        double transposeCvVolts = 0.0;
        double rootCvVolts = 0.0;
        int root = 0;                    // 0=C, 11=B
        int scale = Chromatic;
        int transposeSemitones = 0;      // -12 .. 12
        double hysteresisCents = 12.0;  // 0 .. 50 cents
    };

    struct Output {
        float pitchVolts = 0.0f;
        float changedGate = 0.0f;       // brief 10 V trigger on pitch changes
        int semitone = 0;
    };

    static_assert(sizeof(double) == 8 && std::numeric_limits<double>::is_iec559,
                  "ScaleQuantizer requires IEEE-754 binary64");

    static bool finite(double value) noexcept {
        std::uint64_t bits = 0;
        std::memcpy(&bits, &value, sizeof(bits));
        return (bits & UINT64_C(0x7ff0000000000000)) !=
               UINT64_C(0x7ff0000000000000);
    }

    static double bounded(double value, double fallback, double low, double high) noexcept {
        if (!finite(value))
            return fallback;
        return std::max(low, std::min(high, value));
    }

    static int positiveMod12(int semitone) noexcept {
        const int remainder = semitone % 12;
        return remainder < 0 ? remainder + 12 : remainder;
    }

    static unsigned short scaleMask(int scale) noexcept {
        switch (scale) {
        case Major:           return 0x0AB5; // 0 2 4 5 7 9 11
        case NaturalMinor:    return 0x05AD; // 0 2 3 5 7 8 10
        case Dorian:          return 0x06AD; // 0 2 3 5 7 9 10
        case HarmonicMinor:   return 0x09AD; // 0 2 3 5 7 8 11
        case MajorPentatonic: return 0x0295; // 0 2 4 7 9
        case MinorPentatonic: return 0x04A9; // 0 3 5 7 10
        case WholeTone:       return 0x0555; // 0 2 4 6 8 10
        default:              return 0x0FFF; // chromatic / unknown
        }
    }

    static bool allowed(int semitone, int root, int scale) noexcept {
        const int pc = positiveMod12(semitone - root);
        return (scaleMask(scale) & (1u << pc)) != 0;
    }

    static int nearestSemitone(double semitone, int root, int scale) noexcept {
        const int floorNote = static_cast<int>(std::floor(semitone));
        int lower = floorNote;
        int higher = floorNote + 1;
        // Every mode contains 0 and has at least five pitch classes; 12 probes
        // always suffice. Bounds preserve exact quantized notes near +/-10 V.
        for (int n = 0; n <= 24 && lower >= -120; ++n, --lower) {
            if (allowed(lower, root, scale))
                break;
        }
        for (int n = 0; n <= 24 && higher <= 120; ++n, ++higher) {
            if (allowed(higher, root, scale))
                break;
        }
        if (lower < -120)
            return higher <= 120 ? higher : -120;
        if (higher > 120)
            return lower;
        const double lowDistance = semitone - lower;
        const double highDistance = higher - semitone;
        // Rack ports are float CVs: values nominally on an exact scale tie
        // can round a few 1e-7 semitones upward. A sub-microcent tolerance
        // makes ties deterministic across float-to-double conversion without
        // audibly moving any decision boundary.
        return lowDistance <= highDistance + 1.0e-6 ? lower : higher;
    }

    void reset() noexcept {
        hasLast_ = false;
        lastSemitone_ = 0;
        triggerRemaining_ = 0;
    }

    bool initialized() const noexcept { return hasLast_; }
    int selectedSemitone() const noexcept { return lastSemitone_; }

    Output process(const Input& input) noexcept {
        if (!finite(input.sampleRateHz) || input.sampleRateHz < 1000.0 ||
            input.sampleRateHz > 384000.0) {
            reset();
            return {};
        }
        const int scale = std::max(0, std::min(ScaleCount - 1, input.scale));
        const int root = positiveMod12(std::max(0, std::min(11, input.root)) +
            static_cast<int>(std::round(12.0 * bounded(input.rootCvVolts, 0.0, -10.0, 10.0))));
        const int transpose = std::max(-12, std::min(12, input.transposeSemitones));
        const double pitchSemitone = 12.0 * bounded(
            bounded(input.pitchVolts, 0.0, -10.0, 10.0) +
            bounded(input.transposeCvVolts, 0.0, -10.0, 10.0) +
            static_cast<double>(transpose) / 12.0,
            0.0, -10.0, 10.0);
        const int nearest = nearestSemitone(pitchSemitone, root, scale);
        const double hysteresis = 0.01 * bounded(input.hysteresisCents, 12.0, 0.0, 50.0);
        int chosen = nearest;
        if (hasLast_ && allowed(lastSemitone_, root, scale)) {
            const double oldDistance = std::abs(pitchSemitone - lastSemitone_);
            const double newDistance = std::abs(pitchSemitone - nearest);
            if (newDistance + hysteresis >= oldDistance)
                chosen = lastSemitone_;
        }
        if (!hasLast_ || chosen != lastSemitone_) {
            lastSemitone_ = chosen;
            hasLast_ = true;
            triggerRemaining_ = static_cast<int>(std::max(
                1.0, std::round(input.sampleRateHz * 0.002)));
        }
        const bool trigger = triggerRemaining_ > 0;
        if (triggerRemaining_ > 0)
            --triggerRemaining_;
        Output output;
        output.pitchVolts = static_cast<float>(chosen / 12.0);
        output.changedGate = trigger ? 10.0f : 0.0f;
        output.semitone = chosen;
        return output;
    }

private:
    bool hasLast_ = false;
    int lastSemitone_ = 0;
    int triggerRemaining_ = 0;
};

} // namespace dsp
} // namespace modular_synth
