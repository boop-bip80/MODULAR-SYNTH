/*
 * MODULAR-SYNTH first-party DSP
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Pure C++ oscillator core: no Rack, UI, host, or heap dependencies.
 * Intended to be reusable by standalone DSP regression tests.
 */
#pragma once

#include <algorithm>
#include <cmath>

namespace modular_synth {
namespace dsp {

struct MorphOscillator {
    static constexpr double kTwoPi = 6.283185307179586476925286766559;
    double phase = 0.0;
    float smoothedMorph = 0.0f;
    float smoothedWidth = 0.5f;
    bool initialized = false;

    struct Sample {
        float sine;
        float morph;
    };

    static double polyBlep(double t, double dt) noexcept {
        if (dt <= 0.0)
            return 0.0;
        if (t < dt) {
            const double x = t / dt;
            return x + x - x * x - 1.0;
        }
        if (t > 1.0 - dt) {
            const double x = (t - 1.0) / dt;
            return x * x + x + x + 1.0;
        }
        return 0.0;
    }

    void reset() noexcept {
        phase = 0.0;
        smoothedMorph = 0.0f;
        smoothedWidth = 0.5f;
        initialized = false;
    }

    Sample process(double hz, double sampleRate, float morph, float width) noexcept {
        if (!std::isfinite(hz) || !std::isfinite(sampleRate) || sampleRate < 1.0)
            return {0.0f, 0.0f};

        // Keep the step below Nyquist. polyBLEP reduces discontinuity aliasing,
        // but is NOT a guarantee of alias-free output at high pitch.
        const double step = std::min(std::max(hz, 0.0), 0.45 * sampleRate) / sampleRate;
        const float targetMorph = std::min(1.0f, std::max(0.0f,
                                  std::isfinite(morph) ? morph : 0.0f));
        const float targetWidth = std::min(0.95f, std::max(0.05f,
                                  std::isfinite(width) ? width : 0.5f));

        // Avoid shape-control zipper noise. Reset/startup sets the controls
        // directly so loading a saved patch does not produce a fake glide.
        if (!initialized) {
            smoothedMorph = targetMorph;
            smoothedWidth = targetWidth;
            initialized = true;
        } else {
            const float alpha = static_cast<float>(std::min(1.0, 1.0 / (0.0025 * sampleRate)));
            smoothedMorph += alpha * (targetMorph - smoothedMorph);
            smoothedWidth += alpha * (targetWidth - smoothedWidth);
        }

        const double t = phase;
        const double s = std::sin(kTwoPi * t);
        const double saw = 2.0 * t - 1.0 - polyBlep(t, step);

        double shifted = t - static_cast<double>(smoothedWidth);
        if (shifted < 0.0)
            shifted += 1.0;

        const double pulse = (t < smoothedWidth ? 1.0 : -1.0)
                           + polyBlep(t, step) - polyBlep(shifted, step);

        // Sine -> saw -> pulse; both transitions are continuous in the
        // shape parameter and share a single phase accumulator.
        const double shape = static_cast<double>(smoothedMorph) * 2.0;
        const double mixed = shape < 1.0
            ? s + (saw - s) * shape
            : saw + (pulse - saw) * (shape - 1.0);

        phase += step;
        if (phase >= 1.0)
            phase -= 1.0;

        return {static_cast<float>(s), static_cast<float>(mixed)};
    }
};

} // namespace dsp
} // namespace modular_synth
