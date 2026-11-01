/*
 * StateFilter time-varying control and polyphony stability regression.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Standalone C++17: exercises the real Rack-independent DSP core.
 */
#include "../plugins/ModularSynth/src/StateFilter.hpp"

#include <array>
#include <cstddef>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <limits>

using modular_synth::dsp::StateFilter;

namespace {

constexpr std::size_t kVoices = 16;
constexpr std::array<double, 3> kSampleRates{{44100.0, 96000.0, 48000.0}};
int failures = 0;

void expect(bool ok, const char* description) {
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", description);
        ++failures;
    }
}

// IEEE exponent bits: portable within the binary32 contract, and resistant
// to -ffast-math assuming that NaNs/Inf never occur.
bool finiteFloat(float x) noexcept {
    static_assert(sizeof(float) == sizeof(std::uint32_t), "Requires binary32 float");
    std::uint32_t bits = 0;
    std::memcpy(&bits, &x, sizeof(bits));
    return (bits & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
}

bool validSample(const StateFilter::Sample& s) noexcept {
    return finiteFloat(s.low) && finiteFloat(s.band) && finiteFloat(s.high)
        && std::abs(s.low) <= 10.0001f
        && std::abs(s.band) <= 10.0001f
        && std::abs(s.high) <= 10.0001f;
}

double maxDifference(const StateFilter::Sample& a,
                     const StateFilter::Sample& b) noexcept {
    const double l = std::abs(static_cast<double>(a.low) - b.low);
    const double m = std::abs(static_cast<double>(a.band) - b.band);
    const double h = std::abs(static_cast<double>(a.high) - b.high);
    return std::fmax(l, std::fmax(m, h));
}

// This duplicates only the documented CV-to-core math in StateFilter.cpp.
// It does NOT instantiate or test the Rack host wrapper or jacks.
struct Controls {
    double cutoff;
    double resonance;
    double drive;
};

Controls controlsFromCV(double baseOct, double baseRes, double baseDrive,
                        double cutoffCV, double resCV, double driveCV) noexcept {
    const double octave = StateFilter::finiteClamp(
        baseOct + (StateFilter::ieeeFinite(cutoffCV) ? cutoffCV : 0.0),
        0.0, -30.0, 30.0);
    const double safeResCV = StateFilter::ieeeFinite(resCV) ? resCV : 0.0;
    const double safeDriveCV = StateFilter::ieeeFinite(driveCV) ? driveCV : 0.0;
    return {1000.0 * std::exp2(octave),
            baseRes + 0.1 * safeResCV,
            baseDrive + 0.1 * safeDriveCV};
}

std::uint32_t nextRandom(std::uint32_t& state) noexcept {
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    return state;
}

double uniform01(std::uint32_t& state) noexcept {
    return static_cast<double>(nextRandom(state)) / 4294967295.0;
}

void stressRapidCV() {
    constexpr double infinity = std::numeric_limits<double>::infinity();
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const std::array<double, 13> hostile{{
        -infinity, infinity, nan, -1e300, 1e300, -1000.0,
        -100.0, -10.0, -1.0, 0.0, 1.0, 10.0, 100.0
    }};

    std::array<StateFilter, kVoices> voices{};
    std::uint32_t rng = UINT32_C(0x1a2b3c4d);
    constexpr int kFrames = 49152; // 12 blocks x 4096 samples.
    for (int frame = 0; frame < kFrames; ++frame) {
        const double rate = kSampleRates[static_cast<std::size_t>(frame / 4096) % 3];
        for (std::size_t voice = 0; voice < kVoices; ++voice) {
            // Per-sample controls, including abrupt extremes every 127 frames.
            const bool special = ((frame + static_cast<int>(voice)) % 127) == 0;
            const std::size_t index = (static_cast<std::size_t>(frame / 127) + 7 * voice)
                                     % hostile.size();
            const double cutoffCV = special ? hostile[index] : 48.0 * uniform01(rng) - 24.0;
            const double resCV = special ? hostile[(index + 3) % hostile.size()]
                                         : 40.0 * uniform01(rng) - 20.0;
            const double driveCV = special ? hostile[(index + 6) % hostile.size()]
                                           : 40.0 * uniform01(rng) - 20.0;
            const Controls ctl = controlsFromCV(-0.5 + voice / 12.0, 0.15,
                                                 0.10, cutoffCV, resCV, driveCV);
            const double input = 60.0 * uniform01(rng) - 30.0;
            const auto out = voices[voice].process(input, rate, ctl.cutoff,
                                                    ctl.resonance, ctl.drive);
            if (!validSample(out)) {
                std::fprintf(stderr, "FAIL: non-finite/unbounded voice=%zu frame=%d rate=%.0f\n",
                             voice, frame, rate);
                ++failures;
                return;
            }
        }
    }
    std::printf("PASS: %zu polyphonic CV-stress samples, 12 alternating-rate blocks\n",
                static_cast<std::size_t>(kFrames) * kVoices);
}

void testRateReset() {
    std::array<StateFilter, kVoices> warm{};
    for (std::size_t segment = 0; segment < kSampleRates.size(); ++segment) {
        const double rate = kSampleRates[segment];
        for (int frame = 0; frame < 4096; ++frame) {
            for (std::size_t voice = 0; voice < kVoices; ++voice) {
                const double input = std::sin((frame + 3.0 * voice) * 0.032);
                (void)warm[voice].process(input, rate, 120.0 + 75.0 * voice,
                                          0.45, 0.55);
            }
        }
        const double nextRate = kSampleRates[(segment + 1) % kSampleRates.size()];
        for (std::size_t voice = 0; voice < kVoices; ++voice) {
            StateFilter fresh;
            const auto afterSwitch = warm[voice].process(1.25, nextRate, 2200.0,
                                                         0.6, 0.25);
            const auto cleanStart = fresh.process(1.25, nextRate, 2200.0,
                                                  0.6, 0.25);
            if (!validSample(afterSwitch) || !validSample(cleanStart)
                || maxDifference(afterSwitch, cleanStart) > 1e-6) {
                std::fprintf(stderr, "FAIL: rate switch %.0f -> %.0f differs from reset (voice %zu)\n",
                             rate, nextRate, voice);
                ++failures;
                return;
            }
        }
    }
    std::puts("PASS: 16-voice exact state reset at 44.1 -> 96 -> 48 -> 44.1 kHz");
}

void testLaneIsolation() {
    std::array<StateFilter, kVoices> voices{};
    StateFilter reference;
    double maximum = 0.0;
    constexpr std::size_t kTargetVoice = 7;
    for (int frame = 0; frame < 16000; ++frame) {
        for (std::size_t voice = 0; voice < kVoices; ++voice) {
            const double input = 0.5 * std::sin((frame + 29.0 * voice) * 0.018);
            const double cutoff = 80.0 + 170.0 * voice;
            const double res = 0.05 + 0.04 * voice;
            const double drive = 0.01 + 0.05 * voice;
            const auto actual = voices[voice].process(input, 48000.0,
                                                       cutoff, res, drive);
            if (voice == kTargetVoice) {
                const auto isolated = reference.process(input, 48000.0,
                                                         cutoff, res, drive);
                if (!validSample(actual) || !validSample(isolated)) {
                    expect(false, "isolated lane remains finite and bounded");
                    return;
                }
                maximum = std::fmax(maximum, maxDifference(actual, isolated));
            }
        }
    }
    expect(maximum <= 1e-6, "lane 7 in 16-voice bank matches one isolated StateFilter");

    for (auto& voice : voices)
        voice.reset();
    for (int frame = 0; frame < 1000; ++frame) {
        for (std::size_t voice = 0; voice < kVoices; ++voice) {
            const double input = frame == 0 && voice == 0 ? 5.0 : 0.0;
            const auto out = voices[voice].process(input, 48000.0, 1400.0,
                                                   0.72, 0.30);
            if (voice != 0 && (out.low != 0.0f || out.band != 0.0f
                               || out.high != 0.0f)) {
                expect(false, "single-channel impulse does not leak into quiet lanes");
                return;
            }
        }
    }
    std::printf("PASS: 16 independent voices, one-voice reference max difference %.8f V\n",
                maximum);
}

void testDenormalDecay() {
    StateFilter core;
    for (int frame = 0; frame < 4000; ++frame)
        (void)core.process(5.0, 48000.0, 1000.0, 0.2, 0.0);
    for (int frame = 0; frame < 30000; ++frame) {
        const auto out = core.process(0.0, 48000.0, 1000.0, 0.2, 0.0);
        if (!validSample(out)) {
            expect(false, "ring-down to silence stays finite and bounded");
            return;
        }
    }
    expect(core.ic1eq == 0.0 && core.ic2eq == 0.0,
           "silent input fully flushes tiny integrator states to zero");
    const auto silent = core.process(0.0, 48000.0, 1000.0, 0.2, 0.0);
    expect(silent.low == 0.0f && silent.band == 0.0f
           && silent.high == 0.0f, "continued silent input stays exactly silent");
    std::printf("INFO: decay states after 30000 frames %.3e, %.3e\n",
                core.ic1eq, core.ic2eq);
}

void testDriveAutomationContinuity() {
    StateFilter zeroDrive, automated;
    constexpr std::array<double, 5> tinyDrives{{0.0, 1e-7, 1e-6, 1e-5, 1e-4}};
    for (int frame = 0; frame < 12000; ++frame) {
        (void)zeroDrive.process(0.35, 48000.0, 400.0, 0.0, 0.0);
        (void)automated.process(0.35, 48000.0, 400.0, 0.0, 0.0);
    }
    double maxDeviation = 0.0;
    for (int frame = 0; frame < 10000; ++frame) {
        const auto baseline = zeroDrive.process(0.35, 48000.0, 400.0, 0.0, 0.0);
        const auto changed = automated.process(0.35, 48000.0, 400.0, 0.0,
            tinyDrives[static_cast<std::size_t>(frame) % tinyDrives.size()]);
        if (!validSample(baseline) || !validSample(changed)) {
            expect(false, "near-zero drive automation remains finite and bounded");
            return;
        }
        maxDeviation = std::fmax(maxDeviation, maxDifference(baseline, changed));
    }
    expect(maxDeviation < 0.001, "near-zero drive automation remains continuous");
    std::printf("INFO: max automation deviation from drive=0 %.8f V\n",
                maxDeviation);
}

} // namespace

int main() {
    stressRapidCV();
    testRateReset();
    testLaneIsolation();
    testDenormalDecay();
    testDriveAutomationContinuity();
    if (failures != 0) {
        std::fprintf(stderr, "StateFilter modulation/stability: %d failed\n", failures);
        return 1;
    }
    std::puts("StateFilter modulation/stability: all regression cases passed");
    return 0;
}
