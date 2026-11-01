/*
 * Standalone smoke test for MODULAR-SYNTH Morph VCO DSP.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * From repository root:
 *   c++ -std=c++17 -O2 -Wall -Wextra -Werror tests/morphvco_dsp_smoke.cpp -o /tmp/morphvco_dsp_smoke
 *   /tmp/morphvco_dsp_smoke
 *
 * This test requires no Rack, audio device, GUI, or third-party libraries.
 */
#include "../plugins/ModularSynth/src/MorphVCO.hpp"

#include <array>
#include <cmath>
#include <cstdio>
#include <initializer_list>
#include <limits>

using modular_synth::dsp::MorphOscillator;

static bool check(bool passed, const char* message) {
    if (!passed)
        std::fprintf(stderr, "FAIL: %s\n", message);
    return passed;
}

int main() {
    bool okay = true;
    constexpr double sampleRate = 48000.0;

    // One second of A4 at 48 kHz. The sine must produce 440 cycles
    // regardless of morph position and pulse width.
    MorphOscillator oscillator;
    float previous = 0.0f;
    int risingCrossings = 0;
    for (int i = 0; i < 48000; ++i) {
        const auto frame = oscillator.process(440.0, sampleRate, 0.0f, 0.5f);
        okay &= check(std::isfinite(frame.sine) && std::isfinite(frame.morph),
                      "sine render must be finite");
        if (i > 0 && previous < 0.0f && frame.sine >= 0.0f)
            ++risingCrossings;
        previous = frame.sine;
    }
    okay &= check(risingCrossings >= 438 && risingCrossings <= 440,
                  "1-second A4 frequency outside tolerance");
    okay &= check(oscillator.phase >= 0.0 && oscillator.phase < 1.0,
                  "phase must remain normalized");

    // All waveform corners and pulse width extremes must stay finite.
    for (float shape : {0.0f, 0.25f, 0.5f, 0.75f, 1.0f}) {
        for (float pulseWidth : {0.05f, 0.5f, 0.95f}) {
            oscillator.reset();
            for (int i = 0; i < 4096; ++i) {
                const auto frame = oscillator.process(9000.0, sampleRate, shape, pulseWidth);
                if (!std::isfinite(frame.sine) || !std::isfinite(frame.morph)) {
                    okay &= check(false, "high-frequency morph/PWM render non-finite");
                    break;
                }
            }
        }
    }

    // Wave shape must transition continuously across the sine/saw and
    // saw/pulse boundaries. Two identically phased voices must agree
    // when separated by an infinitesimal morph change.
    MorphOscillator a, b;
    for (int i = 0; i < 1024; ++i) {
        a.process(330.0, sampleRate, 0.5f, 0.5f);
        b.process(330.0, sampleRate, 0.5f, 0.5f);
    }
    const auto left = a.process(330.0, sampleRate, 0.499999f, 0.5f);
    const auto right = b.process(330.0, sampleRate, 0.500001f, 0.5f);
    okay &= check(std::fabs(left.morph - right.morph) < 0.001f,
                  "wave morph must be continuous at saw boundary");
    okay &= check(std::fabs(left.sine - right.sine) < 0.00001f,
                  "sine phase must not depend on morph position");

    // Verify polyBLEP does correct both sides of a discontinuity.
    okay &= check(std::fabs(MorphOscillator::polyBlep(0.0, 0.125) + 1.0) < 1.0e-12,
                  "polyBLEP leading-edge correction missing");
    okay &= check(MorphOscillator::polyBlep(0.99, 0.125) > 0.0,
                  "polyBLEP trailing-edge correction missing");
    okay &= check(MorphOscillator::polyBlep(0.5, 0.125) == 0.0,
                  "polyBLEP must be zero away from edges");

    // Invalid host inputs must not propagate NaNs into the signal.
    const auto invalid = oscillator.process(std::numeric_limits<double>::quiet_NaN(),
                                            sampleRate, 0.5f, 0.5f);
    okay &= check(invalid.sine == 0.0f && invalid.morph == 0.0f,
                  "invalid frequency must output silence");
    oscillator.reset();
    okay &= check(oscillator.phase == 0.0 && !oscillator.initialized,
                  "reset must clear oscillator state");


    // 1 V/oct pitch mapping, saturation and non-finite defensive behavior.
    constexpr double c4 = 261.6255653005986;
    const double pitch0 = MorphOscillator::frequencyForPitch(0.0);
    const double pitchUp = MorphOscillator::frequencyForPitch(1.0);
    const double pitchDown = MorphOscillator::frequencyForPitch(-1.0);
    okay &= check(std::fabs(pitch0 - c4) < 1.0e-10,
                  "0 V/oct must produce C4");
    okay &= check(std::fabs(pitchUp / pitch0 - 2.0) < 1.0e-12,
                  "+1 V must double frequency");
    okay &= check(std::fabs(pitchDown / pitch0 - 0.5) < 1.0e-12,
                  "-1 V must halve frequency");
    okay &= check(MorphOscillator::frequencyForPitch(1.0e9) ==
                  MorphOscillator::frequencyForPitch(20.0),
                  "positive CV must saturate before exp2 overflow");
    okay &= check(MorphOscillator::frequencyForPitch(-1.0e9) ==
                  MorphOscillator::frequencyForPitch(-20.0),
                  "negative CV must saturate");
    okay &= check(MorphOscillator::frequencyForPitch(
                      std::numeric_limits<double>::quiet_NaN()) == c4,
                  "non-finite CV must fall back to C4");

    // Stable phase must be preserved when the host changes sample rate.
    MorphOscillator rateChanges;
    constexpr double tuningHz = 523.25;
    for (int i = 0; i < 8192; ++i)
        rateChanges.process(tuningHz, 48000.0, 0.0f, 0.5f);
    for (int i = 0; i < 8192; ++i)
        rateChanges.process(tuningHz, 96000.0, 0.0f, 0.5f);
    const double referencePhase = std::fmod(8192.0 * tuningHz / 48000.0
                                           + 8192.0 * tuningHz / 96000.0, 1.0);
    okay &= check(std::fabs(rateChanges.phase - referencePhase) < 1.0e-9,
                  "phase must survive a 48k -> 96k sample-rate transition");

    // Morph/PWM modulation must smooth transitions without changing phase.
    MorphOscillator smoothing;
    smoothing.process(440.0, 48000.0, 0.0f, 0.5f);
    const double phaseBefore = smoothing.phase;
    smoothing.process(440.0, 48000.0, 1.0f, 0.95f);
    okay &= check(smoothing.smoothedMorph > 0.0f && smoothing.smoothedMorph < 1.0f,
                  "morph jump must be slewed");
    okay &= check(smoothing.smoothedWidth > 0.5f && smoothing.smoothedWidth < 0.95f,
                  "PWM jump must be slewed");
    okay &= check(smoothing.phase > phaseBefore,
                  "changing wave shape must not reset phase");
    for (int i = 0; i < 4096; ++i)
        smoothing.process(440.0, 48000.0, 1.0f, 0.95f);
    okay &= check(std::fabs(smoothing.smoothedMorph - 1.0f) < 0.0001f,
                  "morph slew must eventually converge");
    okay &= check(std::fabs(smoothing.smoothedWidth - 0.95f) < 0.0001f,
                  "PWM slew must eventually converge");

    // Independent voices: each channel owns its own phase and oscillator state.
    std::array<MorphOscillator, 16> poly;
    for (int i = 0; i < 256; ++i) {
        for (int lane = 0; lane < 16; ++lane)
            poly[lane].process(110.0 * (1.0 + lane / 8.0), 48000.0, 0.25f, 0.5f);
    }
    okay &= check(poly[0].phase != poly[15].phase,
                  "independent polyphony lanes must not share phase");
    for (const auto& voice : poly)
        okay &= check(voice.phase >= 0.0 && voice.phase < 1.0,
                      "polyphony phase must stay normalized");

    // At 3 kHz / 48 kHz there are precisely 16 samples/cycle. Compare
    // generated saw/pulse to the first seven harmonics of the Fourier
    // series (all below Nyquist). This measures waveform error against
    // an ideal band-limited reference, NOT a general alias-energy proof.
    constexpr int period = 16;
    constexpr double pi = 3.1415926535897932384626433832795;
    MorphOscillator blSaw, blPulse;
    double sawError = 0.0;
    double naiveSawError = 0.0;
    double pulseError = 0.0;
    double naivePulseError = 0.0;
    for (int n = 0; n < period; ++n) {
        const double phase = static_cast<double>(n) / period;
        const double naiveSaw = 2.0 * phase - 1.0;
        const double naivePulse = phase < 0.5 ? 1.0 : -1.0;
        double idealSaw = 0.0;
        double idealPulse = 0.0;
        for (int harmonic = 1; harmonic < period / 2; ++harmonic) {
            const double w = 2.0 * pi * harmonic;
            idealSaw += -2.0 * std::sin(w * phase) / (pi * harmonic);
            idealPulse += 2.0 * (1.0 - std::cos(w * 0.5))
                          * std::sin(w * phase) / (pi * harmonic);
        }
        const double actualSaw = blSaw.process(3000.0, 48000.0, 0.5f, 0.5f).morph;
        const double actualPulse = blPulse.process(3000.0, 48000.0, 1.0f, 0.5f).morph;
        sawError += (actualSaw - idealSaw) * (actualSaw - idealSaw);
        naiveSawError += (naiveSaw - idealSaw) * (naiveSaw - idealSaw);
        pulseError += (actualPulse - idealPulse) * (actualPulse - idealPulse);
        naivePulseError += (naivePulse - idealPulse) * (naivePulse - idealPulse);
    }
    sawError = std::sqrt(sawError / period);
    naiveSawError = std::sqrt(naiveSawError / period);
    pulseError = std::sqrt(pulseError / period);
    naivePulseError = std::sqrt(naivePulseError / period);
    okay &= check(sawError < naiveSawError * 0.5,
                  "polyBLEP saw must improve band-limited reference error");
    okay &= check(pulseError < naivePulseError * 0.5,
                  "polyBLEP pulse must improve band-limited reference error");
    std::printf("Saw RMS error vs truncated Fourier: naive=%.5f polyBLEP=%.5f\n",
                naiveSawError, sawError);
    std::printf("Pulse RMS error vs truncated Fourier: naive=%.5f polyBLEP=%.5f\n",
                naivePulseError, pulseError);

    // Pulse-width changes intentionally change the DC component. At a
    // steady 25% duty cycle, the mean is -0.5 at integer cycles.
    MorphOscillator duty;
    double sum = 0.0;
    for (int i = 0; i < 16 * 64; ++i)
        sum += duty.process(3000.0, 48000.0, 1.0f, 0.25f).morph;
    okay &= check(std::fabs(sum / (16 * 64) + 0.5) < 0.02,
                  "PWM output DC level must match expected 25% duty cycle");

    // Finite-math assumptions must not suppress invalid-input handling.
    const auto invalidRate = oscillator.process(440.0,
                        std::numeric_limits<double>::infinity(), 0.5f, 0.5f);
    okay &= check(invalidRate.sine == 0.0f && invalidRate.morph == 0.0f,
                  "non-finite sample rate must output silence");
    const auto invalidShape = oscillator.process(440.0, 48000.0,
                        std::numeric_limits<float>::infinity(),
                        std::numeric_limits<float>::quiet_NaN());
    okay &= check(MorphOscillator::finite(invalidShape.morph)
                  && MorphOscillator::finite(invalidShape.sine),
                  "non-finite morph and PWM inputs must sanitize");
    okay &= check(!MorphOscillator::finite(std::numeric_limits<double>::quiet_NaN())
                  && !MorphOscillator::finite(std::numeric_limits<float>::infinity()),
                  "bitwise IEEE-754 finite detection must reject NaN/Inf");

    if (okay)
        std::puts("PASS: Morph VCO standalone DSP smoke");
    return okay ? 0 : 1;
}
