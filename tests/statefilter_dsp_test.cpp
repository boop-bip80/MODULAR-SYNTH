/*
 * MODULAR-SYNTH State Filter regression tests (no Rack dependency).
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "../plugins/ModularSynth/src/StateFilter.hpp"

#include <array>
#include <cmath>
#include <cstdio>
#include <limits>
#include <cstdint>
#include <cstring>

using modular_synth::dsp::StateFilter;

namespace {
int failures = 0;
constexpr double kPi = 3.1415926535897932384626433832795;
bool finiteFloat(float value) {
    std::uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return (bits & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
}

void expect(bool condition, const char* message) {
    if (!condition) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        ++failures;
    }
}

double rmsResponse(double sourceHz, double cutoffHz, int component) {
    StateFilter filter;
    const double sampleRate = 48000.0;
    double outputSumSquares = 0.0;
    double inputSumSquares = 0.0;
    int samples = 0;

    for (int i = 0; i < 52000; ++i) {
        const double input = std::sin(2.0 * kPi * sourceHz * i / sampleRate);
        const StateFilter::Sample s = filter.process(input, sampleRate, cutoffHz, 0.05, 0.0);
        if (i < 4000)
            continue;
        const double out = component == 0 ? s.low : component == 1 ? s.band : s.high;
        outputSumSquares += out * out;
        inputSumSquares += input * input;
        ++samples;
    }
    expect(samples > 0, "sine response has sample frames");
    return std::sqrt(outputSumSquares / inputSumSquares);
}

void testFrequencyResponse() {
    // A 500 Hz low-pass should pass 100 Hz but attenuate 8 kHz.
    const double lpLow = rmsResponse(100.0, 500.0, 0);
    const double lpHigh = rmsResponse(8000.0, 500.0, 0);
    const double hpLow = rmsResponse(100.0, 500.0, 2);
    const double hpHigh = rmsResponse(8000.0, 500.0, 2);
    expect(lpLow > 0.8 && lpLow < 1.2, "LP passes low-frequency sine");
    expect(lpHigh < 0.1, "LP attenuates high-frequency sine");
    expect(hpLow < 0.12, "HP rejects low-frequency sine");
    expect(hpHigh > 0.8 && hpHigh < 1.2, "HP passes high-frequency sine");
}

void testDCAndReset() {
    StateFilter filter;
    StateFilter::Sample s{};
    for (int i = 0; i < 50000; ++i)
        s = filter.process(2.5, 48000.0, 350.0, 0.15, 0.0);

    expect(std::abs(s.low - 2.5f) < 0.04f, "LP settles to DC input");
    expect(std::abs(s.band) < 0.04f, "BP rejects DC after settling");
    expect(std::abs(s.high) < 0.04f, "HP rejects DC after settling");

    filter.reset();
    s = filter.process(0.0, 48000.0, 350.0, 0.15, 0.0);
    expect(std::abs(s.low) < 1e-7f && std::abs(s.band) < 1e-7f
           && std::abs(s.high) < 1e-7f, "reset clears filter state");
}

void testBoundsAndSampleRateChanges() {
    constexpr double inf = std::numeric_limits<double>::infinity();
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const std::array<double, 13> hostile = {{
        -inf, inf, nan, -1e300, 1e300, -100000.0, 100000.0,
        -1e-300, 1e-300, -1.0, 0.0, 1.0, 8.0
    }};
    const std::array<double, 6> rates = {{44100.0, 48000.0, 96000.0, 192000.0, 1000.0, 0.0}};
    StateFilter filter;

    for (double rate : rates) {
        for (int i = 0; i < 20000; ++i) {
            const double a = hostile[static_cast<std::size_t>(i) % hostile.size()];
            const double b = hostile[static_cast<std::size_t>(i / 3) % hostile.size()];
            const double c = hostile[static_cast<std::size_t>(i / 7) % hostile.size()];
            const auto s = filter.process(a, rate, b, c, a);
            const float channels[] = {s.low, s.band, s.high};
            for (float voltage : channels) {
                if (!finiteFloat(voltage) || std::abs(voltage) > 10.0001f) {
                    expect(false, "extreme control/audio values produce bounded finite output");
                    return;
                }
            }
        }
    }

    const auto badSampleRate = filter.process(5.0, nan, 500.0, 0.0, 0.0);
    expect(badSampleRate.low == 0.0f && badSampleRate.band == 0.0f
           && badSampleRate.high == 0.0f, "invalid sample rate returns silence");

    // Recovery after an invalid rate and abrupt host-rate changes.
    for (double rate : {44100.0, 192000.0, 48000.0}) {
        for (int i = 0; i < 3000; ++i) {
            const auto s = filter.process(std::sin(i * 0.04), rate, 18000.0, 1.0, 1.0);
            if (!finiteFloat(s.low) || !finiteFloat(s.band) || !finiteFloat(s.high)) {
                expect(false, "sample-rate changes remain finite");
                return;
            }
        }
    }
}

void testControlBehaviour() {
    StateFilter dry;
    StateFilter saturated;
    double linearSum = 0.0;
    double driveSum = 0.0;
    for (int i = 0; i < 5000; ++i) {
        linearSum += std::abs(dry.process(0.35, 48000.0, 400.0, 0.0, 0.0).low);
        driveSum += std::abs(saturated.process(0.35, 48000.0, 400.0, 0.0, 1.0).low);
    }
    expect(driveSum > linearSum, "drive introduces bounded nonlinear gain/saturation");
}
} // namespace

int main() {
    testFrequencyResponse();
    testDCAndReset();
    testBoundsAndSampleRateChanges();
    testControlBehaviour();

    if (failures != 0) {
        std::fprintf(stderr, "StateFilter: %d tests failed\n", failures);
        return 1;
    }
    std::puts("StateFilter: all DSP regression tests passed");
    return 0;
}
