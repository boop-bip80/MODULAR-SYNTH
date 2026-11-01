/*
 * MODULAR-SYNTH StereoEcho long-run standalone DSP stress regression.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Standalone C++17: randomized 16-lane state, changing rates, extreme CV,
 * denormal tail extinction, and an allocation counter outside the Rack host.
 */
#include "../plugins/ModularSynth/src/StereoEcho.hpp"

#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <new>

using modular_synth::dsp::StereoEchoDSP;

namespace {
// Only this standalone executable uses the replacement allocation functions.
// This counter observes C++ new/new[] calls, not arbitrary C malloc calls.
std::uint64_t allocationCalls = 0;
}

void* operator new(std::size_t size) {
    ++allocationCalls;
    if (void* memory = std::malloc(size == 0 ? 1 : size))
        return memory;
    throw std::bad_alloc();
}

void* operator new[](std::size_t size) {
    ++allocationCalls;
    if (void* memory = std::malloc(size == 0 ? 1 : size))
        return memory;
    throw std::bad_alloc();
}

void operator delete(void* pointer) noexcept { std::free(pointer); }
void operator delete[](void* pointer) noexcept { std::free(pointer); }
void operator delete(void* pointer, std::size_t) noexcept { std::free(pointer); }
void operator delete[](void* pointer, std::size_t) noexcept { std::free(pointer); }

namespace {

int failures = 0;

void expect(bool value, const char* message) {
    if (!value) {
        ++failures;
        std::fprintf(stderr, "FAIL StereoEcho stress: %s\n", message);
    }
}

std::uint32_t floatBits(float value) {
    std::uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return bits;
}

bool isFinite(float value) {
    return (floatBits(value) & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
}

bool isSubnormal(float value) {
    const auto bits = floatBits(value);
    return (bits & UINT32_C(0x7f800000)) == 0
           && (bits & UINT32_C(0x007fffff)) != 0;
}

class DeterministicNoise {
public:
    std::uint32_t next() {
        state_ ^= state_ << 13u;
        state_ ^= state_ >> 17u;
        state_ ^= state_ << 5u;
        return state_;
    }

    double unit() {
        return static_cast<double>(next() >> 8u) / 16777216.0;
    }

    double bipolar() {
        return unit() * 2.0 - 1.0;
    }

private:
    std::uint32_t state_ = UINT32_C(0x9e3779b9);
};

std::uint64_t hashFloat(std::uint64_t hash, float value) {
    constexpr std::uint64_t fnvPrime = UINT64_C(1099511628211);
    return (hash ^ floatBits(value)) * fnvPrime;
}

void testOneMillisecondLongFeedbackTail() {
    StereoEchoDSP echo;
    constexpr int rate = 48000;
    constexpr int sampleCount = 240000; // 5 seconds; 5,000 echo cycles
    int lastNonzeroSample = -1;
    int subnormalSamples = 0;
    double peak = 0.0;
    const std::uint64_t allocated = allocationCalls;

    for (int i = 0; i <= sampleCount; ++i) {
        const auto out = echo.process(i == 0 ? 4.0 : 0.0, 0.0,
                                      rate, 1.0, 0.90, 1.0, 0.0);
        if (out.left != 0.0f || out.right != 0.0f)
            lastNonzeroSample = i;
        subnormalSamples += isSubnormal(out.left) || isSubnormal(out.right);
        if (!isFinite(out.left) || !isFinite(out.right)) {
            expect(false, "5-second tail must remain IEEE-754 finite");
            return;
        }
        peak = std::max(peak, static_cast<double>(std::abs(out.left)));
        if (i == 48)
            expect(std::abs(out.left - 4.0f) < 0.00001f
                   && out.right == 0.0f, "first 1 ms echo must retain original amplitude");
        if (i == 48 * 100)
            expect(std::abs(out.left - 4.0f * std::pow(0.9f, 99.0f)) < 0.0001f,
                   "high feedback must decay, not amplify, over 100 repeats");
    }
    expect(subnormalSamples == 0,
           "ring silence floor must prevent subnormal/immortal feedback tails");
    expect(lastNonzeroSample >= rate / 10 && lastNonzeroSample < rate,
           "feedback should decay for an audible interval and reach exact zero within 1 second");
    expect(peak <= 4.00001,
           "contractive 90% feedback must not exceed the initial impulse peak");
    expect(allocationCalls == allocated,
           "long tail audio processing must not perform C++ allocations");
    std::printf("TAIL rate=48000 5s: last_nonzero_sample=%d subnormals=%d peak=%.6g V\n",
                lastNonzeroSample, subnormalSamples, peak);
}

void testLongSlewsAtExtremeRates() {
    for (int rate : {48000, 192000, 384000}) {
        StereoEchoDSP echo;
        const double minSamples = rate / 1000.0;
        const double maxSamples =
            echo.effectiveMaxMs(rate) * rate / 1000.0;
        echo.process(0.0, 0.0, rate, 1.0, 0.0, 1.0, 0.0);
        expect(std::abs(echo.currentDelaySamples() - minSamples) < 1e-9,
               "initial 1 ms time must immediately match the rate");

        const int settleFrames = rate / 40; // 25 ms, nominal 99.9% response
        for (int i = 0; i < settleFrames; ++i)
            echo.process(0.0, 0.0, rate, 1000.0, 0.0, 1.0, 0.0);
        const double risingError = std::abs(echo.currentDelaySamples() - maxSamples);
        expect(risingError <= (maxSamples - minSamples) * 0.00105 + 1e-8,
               "25 ms upslew must settle to within nominal 0.1% of capped target");
        for (int i = 0; i < settleFrames; ++i)
            echo.process(0.0, 0.0, rate, 1.0, 0.0, 1.0, 0.0);
        const double fallingError = std::abs(echo.currentDelaySamples() - minSamples);
        expect(fallingError <= (maxSamples - minSamples) * 0.00105 + 1e-8,
               "25 ms downslew must settle to within nominal 0.1% of target");
        expect(echo.currentDelaySamples() >= 1.0
               && echo.currentDelaySamples() <= StereoEchoDSP::kCapacityFrames - 2u,
               "slewed delay must stay inside physical ring capacity");
        if (rate == 384000)
            expect(echo.effectiveMaxMs(rate) == 500.0,
                   "384 kHz maximum effective time must be 500 ms");
        else
            expect(echo.effectiveMaxMs(rate) == 1000.0,
                   "full 1000 ms range must remain available through 192 kHz");
        std::printf("SLEW %d Hz: max=%.0f samples rise_error=%.6f fall_error=%.6f\n",
                    rate, maxSamples, risingError, fallingError);
    }
}

void testChangingSampleRateInvalidatesHistory() {
    StereoEchoDSP echo;
    constexpr int rates[] = {44100, 96000, 384000, 192000, 48000};
    for (const int rate : rates) {
        const int minDelayFrames = rate / 1000;
        // A genuine impulse arrives exactly at its configured delay.
        for (int i = 0; i < minDelayFrames + 3; ++i) {
            const auto sample = echo.process(i == 0 ? 2.0 : 0.0, 0.0,
                                             rate, 1.0, 0.80, 1.0, 1.0);
            if (i < minDelayFrames)
                expect(sample.left == 0.0f && sample.right == 0.0f,
                       "sample-rate switch must invalidate all prior echo history");
            if (i == minDelayFrames)
                expect(std::abs(sample.left - 2.0f) < 1e-5f
                       && sample.right == 0.0f,
                       "new-rate first echo must arrive at exactly 1 ms");
        }
    }
    // Invalid rates must discard pending state and recover on next valid call.
    for (double badRate : {0.0, -48000.0, 384001.0,
                           std::numeric_limits<double>::infinity(),
                           std::numeric_limits<double>::quiet_NaN()}) {
        const auto silent = echo.process(10.0, 0.0, badRate, 1.0, 0.9, 1.0, 0.0);
        expect(silent.left == 0.0f && silent.right == 0.0f,
               "invalid rate must yield silence and logical reset");
    }
    const auto recovered = echo.process(0.0, 0.0, 48000.0, 1.0, 0.9, 1.0, 0.0);
    expect(recovered.left == 0.0f && recovered.right == 0.0f,
           "valid rate after invalid-rate reset may not replay stale buffer");
}

void testDeterministicSixteenLaneRateAndCvStress() {
    std::array<StereoEchoDSP, 16> voices;
    StereoEchoDSP laneZeroReference;
    DeterministicNoise noise;
    constexpr int framesPerRate = 210000; // forces full ring wrap at each rate
    constexpr int rates[] = {44100, 48000, 96000, 192000, 384000};
    constexpr std::uint64_t expectedUpdates =
        static_cast<std::uint64_t>(framesPerRate) * 5u * 16u;
    const double infinity = std::numeric_limits<double>::infinity();
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const std::uint64_t allocationsBefore = allocationCalls;
    std::uint64_t hash = UINT64_C(14695981039346656037);
    std::uint64_t updates = 0;
    double peak = 0.0;

    const auto start = std::chrono::steady_clock::now();
    for (const int rate : rates) {
        for (int frame = 0; frame < framesPerRate; ++frame) {
            const int sweepPhase = (frame / 13000) % 6;
            const double ramp = (frame % 13000) / 13000.0;
            double ms = sweepPhase == 0 ? 1.0
                        : sweepPhase == 1 ? 1000.0
                        : sweepPhase == 2 ? 1.0 + ramp * 999.0
                        : sweepPhase == 3 ? 1000.0 - ramp * 999.0
                        : sweepPhase == 4 ? -100.0 : 1500.0;
            for (int lane = 0; lane < 16; ++lane) {
                double inputL = 3.5 * noise.bipolar();
                double inputR = 3.5 * noise.bipolar();
                double feedback = 0.90 * noise.unit();
                double wet = noise.unit();
                double crossfeed = noise.unit();
                double laneMs = ms + lane * 0.03125;
                if (frame % 8191 == 0)
                    inputL += 4.0;
                if (lane == 7 && frame % 37011 == 0) {
                    inputL = nan;
                    feedback = infinity;
                }
                if (lane == 9 && frame % 52117 == 0) {
                    laneMs = infinity;
                    wet = nan;
                }
                if (lane == 11 && frame % 48007 == 0) {
                    inputR = -infinity;
                    crossfeed = -infinity;
                }

                const auto sample = voices[static_cast<std::size_t>(lane)].process(
                    inputL, inputR, rate, laneMs, feedback, wet, crossfeed);
                if (!isFinite(sample.left) || !isFinite(sample.right)
                    || std::abs(sample.left) > 10.0001f
                    || std::abs(sample.right) > 10.0001f) {
                    expect(false, "16-lane random audio/CV outputs must remain finite and <=10 V");
                    return;
                }
                const double delay = voices[static_cast<std::size_t>(lane)].currentDelaySamples();
                if (!StereoEchoDSP::finite(delay)
                    || delay < 1.0 || delay > StereoEchoDSP::kCapacityFrames - 2u) {
                    expect(false, "16-lane time slews must remain finite and in ring bounds");
                    return;
                }
                if (lane == 0) {
                    const auto independent = laneZeroReference.process(
                        inputL, inputR, rate, laneMs, feedback, wet, crossfeed);
                    if (floatBits(sample.left) != floatBits(independent.left)
                        || floatBits(sample.right) != floatBits(independent.right)) {
                        expect(false, "lane 0 must bitwise match an independent replay");
                        return;
                    }
                }
                peak = std::max(peak,
                                std::max(static_cast<double>(std::abs(sample.left)),
                                         static_cast<double>(std::abs(sample.right))));
                hash = hashFloat(hashFloat(hash, sample.left), sample.right);
                ++updates;
            }
        }
    }
    const auto elapsed = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - start).count();

    expect(updates == expectedUpdates, "every lane must execute at every rate");
    expect(allocationCalls == allocationsBefore,
           "process and sample-rate changes must not call C++ new/new[]");
    for (auto& voice : voices)
        voice.reset();
    laneZeroReference.reset();
    expect(allocationCalls == allocationsBefore,
           "16-lane reset must not allocate");
    std::printf("STRESS seed=0x9e3779b9 updates=%llu peak=%.6g V "
                "hash=%016llx elapsed=%.1f ms (includes PRNG/assertions)\n",
                static_cast<unsigned long long>(updates), peak,
                static_cast<unsigned long long>(hash), elapsed);
}

} // namespace

int main() {
    testOneMillisecondLongFeedbackTail();
    testLongSlewsAtExtremeRates();
    testChangingSampleRateInvalidatesHistory();
    testDeterministicSixteenLaneRateAndCvStress();
    if (failures != 0) {
        std::fprintf(stderr, "StereoEcho long-run stress: %d failure(s)\n", failures);
        return 1;
    }
    std::puts("PASS: StereoEcho 16-lane long-run CV/rate stress, bounded tail, "
              "denormal extinction and zero process/reset allocations");
    return 0;
}
