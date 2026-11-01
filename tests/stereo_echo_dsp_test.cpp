/*
 * MODULAR-SYNTH StereoEcho standalone C++17 DSP regression.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "../plugins/ModularSynth/src/StereoEcho.hpp"

#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>

using modular_synth::dsp::StereoEchoDSP;

namespace {

int failures = 0;

void expect(bool valid, const char* message) {
    if (!valid) {
        ++failures;
        std::fprintf(stderr, "FAIL StereoEcho: %s\n", message);
    }
}

bool finiteFloat(float value) {
    std::uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return (bits & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
}

void testMemoryAndDryWet() {
    expect(StereoEchoDSP::reservedBytesPerVoice() == 1536016u,
           "reserved delay memory must be an explicit fixed bound");
    expect(StereoEchoDSP::reservedBytesPerVoice() * 16u == 24576256u,
           "16-stereo-voice memory budget must be documented exactly");
    StereoEchoDSP delay;
    const auto dry = delay.process(1.5, -0.75, 48000.0, 100.0, 0.0, 0.0, 0.0);
    expect(dry.left == 1.5f && dry.right == -0.75f,
           "zero wet must reproduce dry stereo inputs");
    const auto half = delay.process(2.0, -1.0, 48000.0, 100.0, 0.0, 0.5, 0.0);
    expect(half.left == 1.0f && half.right == -0.5f,
           "50% wet must half dry when delay history is still silent");
    delay.reset();
    const auto silent = delay.process(0.0, 0.0, 48000.0, 100.0, 0.0, 1.0, 0.0);
    expect(silent.left == 0.0f && silent.right == 0.0f,
           "O(1) reset must logically invalidate previously written history");
}

void testImpulseTiming(int sampleRate, double delayMs) {
    StereoEchoDSP delay;
    const int offset = static_cast<int>(sampleRate * delayMs / 1000.0);
    StereoEchoDSP::Sample sample{};
    for (int i = 0; i < offset + 3; ++i) {
        sample = delay.process(i == 0 ? 4.0 : 0.0, i == 0 ? -2.0 : 0.0,
                               sampleRate, delayMs, 0.0, 1.0, 0.0);
        if (i < offset)
            expect(sample.left == 0.0f && sample.right == 0.0f,
                   "full-wet impulse may not arrive before configured delay");
        if (i == offset)
            expect(std::abs(sample.left - 4.0f) < 0.0002f
                   && std::abs(sample.right + 2.0f) < 0.0002f,
                   "full-wet stereo impulse must arrive at expected sample");
        if (i > offset)
            expect(sample.left == 0.0f && sample.right == 0.0f,
                   "zero feedback must produce exactly one echo");
    }
}

void testFractionalLinearInterpolation() {
    StereoEchoDSP delay;
    // At 48 kHz, 48.5 samples is 1.010416... ms (above the 1 ms minimum).
    constexpr double milliseconds = 48.5 / 48.0;
    for (int i = 0; i <= 51; ++i) {
        const auto s = delay.process(i == 0 ? 4.0 : 0.0, 0.0,
                                     48000.0, milliseconds, 0.0, 1.0, 0.0);
        if (i == 48 || i == 49)
            expect(std::abs(s.left - 2.0f) < 0.0002f,
                   "fractional delay must interpolate impulse across two frames");
        else
            expect(s.left == 0.0f,
                   "fractional delay must not emit extra impulse samples");
        expect(s.right == 0.0f,
               "fractional delay must not cross into the silent right channel");
    }
}

void testMaximumBufferBoundary() {
    for (int rate : {192000, 384000}) {
        StereoEchoDSP delay;
        // 1000 ms at 192 kHz and a capped 500 ms at 384 kHz both
        // require exactly 192,000 samples of ring history.
        for (int i = 0; i <= 192001; ++i) {
            const auto s = delay.process(i == 0 ? 2.0 : 0.0, 0.0,
                                         rate, 1000.0, 0.0, 1.0, 0.0);
            if (i == 192000)
                expect(std::abs(s.left - 2.0f) < 0.0002f,
                       "maximum-capacity delay must read its oldest valid sample");
            else
                expect(s.left == 0.0f,
                       "maximum-capacity delay must not wrap or repeat early");
        }
    }
}

void testPingPongDecay() {
    StereoEchoDSP delay;
    constexpr int rate = 48000;
    constexpr int gap = 240; // 5 ms
    for (int i = 0; i <= gap * 4; ++i) {
        const auto s = delay.process(i == 0 ? 4.0 : 0.0, 0.0,
                                     rate, 5.0, 0.5, 1.0, 1.0);
        if (i == gap)
            expect(std::abs(s.left - 4.0f) < 0.0002f && s.right == 0.0f,
                   "first echo must stay on original left channel");
        if (i == gap * 2)
            expect(s.left == 0.0f && std::abs(s.right - 2.0f) < 0.0002f,
                   "second echo must ping-pong to right at half amplitude");
        if (i == gap * 3)
            expect(std::abs(s.left - 1.0f) < 0.0002f && s.right == 0.0f,
                   "third echo must ping-pong left at quarter amplitude");
        if (i == gap * 4)
            expect(s.left == 0.0f && std::abs(s.right - 0.5f) < 0.0002f,
                   "fourth echo must ping-pong right with stable decay");
    }
}

void testTimeSlewAndSampleRateReset() {
    StereoEchoDSP delay;
    delay.process(1.0, 0.0, 48000.0, 5.0, 0.2, 1.0, 0.0);
    const double before = delay.currentDelaySamples();
    delay.process(0.0, 0.0, 48000.0, 500.0, 0.2, 1.0, 0.0);
    const double after = delay.currentDelaySamples();
    expect(before == 240.0 && after > before && after < 24000.0,
           "delay knob movement must smoothly slew the read tap");
    for (int i = 0; i < 100; ++i)
        delay.process(0.0, 0.0, 48000.0, 500.0, 0.2, 1.0, 0.0);
    for (int i = 0; i < 96001; ++i) {
        const auto s = delay.process(0.0, 0.0, 96000.0, 20.0, 0.8, 1.0, 1.0);
        expect(s.left == 0.0f && s.right == 0.0f,
               "sample-rate switch must never replay stale buffer history");
    }
    expect(std::abs(delay.currentDelaySamples() - 1920.0) < 0.0001,
           "new sample rate must convert milliseconds to fresh delay samples");
    expect(delay.effectiveMaxMs(192000.0) == 1000.0
           && delay.effectiveMaxMs(384000.0) == 500.0,
           "max delay must reflect fixed ring capacity at high host rates");
}

void testSixteenVoiceIsolation() {
    std::array<StereoEchoDSP, 16> voices;
    constexpr int gap = 480;
    for (int i = 0; i <= gap; ++i) {
        for (int lane = 0; lane < 16; ++lane) {
            const double amplitude = 0.25 * (lane + 1);
            const auto s = voices[static_cast<std::size_t>(lane)].process(
                i == 0 ? amplitude : 0.0, 0.0, 48000.0, 10.0, 0.0, 1.0, 0.0);
            if (i == gap)
                expect(std::abs(s.left - amplitude) < 0.0002 && s.right == 0.0f,
                       "each polyphonic lane must retain independent echo state");
            else
                expect(s.left == 0.0f && s.right == 0.0f,
                       "one voice may not leak into any other voice");
        }
    }
}

void testHostileValuesUnderFastMath() {
    constexpr double inf = std::numeric_limits<double>::infinity();
    const double nan = std::numeric_limits<double>::quiet_NaN();
    expect(!StereoEchoDSP::finite(nan) && !StereoEchoDSP::finite(inf),
           "IEEE finite guard must reject NaNs/Infs under strict fast-math");
    StereoEchoDSP delay;
    const std::array<double, 12> hostile{{
        -inf, inf, nan, -1e250, 1e250, -10000.0,
        10000.0, -5.0, 0.0, 0.5, 1.0, 20.0
    }};
    for (int rate : {44100, 48000, 96000, 192000, 384000}) {
        for (int i = 0; i < 20000; ++i) {
            const double a = hostile[static_cast<std::size_t>(i) % hostile.size()];
            const double b = hostile[static_cast<std::size_t>(i / 3) % hostile.size()];
            const double c = hostile[static_cast<std::size_t>(i / 7) % hostile.size()];
            const double d = hostile[static_cast<std::size_t>(i / 11) % hostile.size()];
            const auto s = delay.process(a, b, rate, c, d, a, b);
            if (!finiteFloat(s.left) || !finiteFloat(s.right)
                || std::abs(s.left) > 10.0001f || std::abs(s.right) > 10.0001f) {
                expect(false, "hostile CV/audio must remain finite and within 10 V");
                return;
            }
        }
    }
    for (double rate : {nan, inf, 0.0, -44100.0, 1000000.0}) {
        const auto s = delay.process(5.0, 5.0, rate, 10.0, 0.5, 1.0, 0.0);
        expect(s.left == 0.0f && s.right == 0.0f,
               "invalid sample rates must reset and output silence");
    }
    const auto recovered = delay.process(2.0, 0.0, 48000.0, 1.0, 0.0, 0.0, 0.0);
    expect(recovered.left == 2.0f && recovered.right == 0.0f,
           "valid input after hostile rate must recover immediately");
}

} // namespace

int main() {
    testMemoryAndDryWet();
    for (int rate : {44100, 48000, 96000, 192000})
        testImpulseTiming(rate, 10.0);
    testFractionalLinearInterpolation();
    testMaximumBufferBoundary();
    testPingPongDecay();
    testTimeSlewAndSampleRateReset();
    testSixteenVoiceIsolation();
    testHostileValuesUnderFastMath();

    if (failures != 0) {
        std::fprintf(stderr, "StereoEcho: %d DSP tests failed\n", failures);
        return 1;
    }
    std::puts("PASS: StereoEcho impulse timing, ping-pong, 16 voices, fastmath safety and reset");
    return 0;
}
