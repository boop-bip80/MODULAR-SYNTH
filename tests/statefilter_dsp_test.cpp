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

    // Prior behavior jumped approximately 31% between exactly zero drive
    // and an infinitesimal positive value. Test continuity and progression.
    StateFilter atZero, atTiny, atSmall, atLarger;
    StateFilter::Sample zero{}, tiny{}, small{}, larger{};
    for (int i = 0; i < 20000; ++i) {
        zero = atZero.process(0.35, 48000.0, 400.0, 0.0, 0.0);
        tiny = atTiny.process(0.35, 48000.0, 400.0, 0.0, 1e-5);
        small = atSmall.process(0.35, 48000.0, 400.0, 0.0, 1e-4);
        larger = atLarger.process(0.35, 48000.0, 400.0, 0.0, 1e-3);
    }
    expect(std::abs(tiny.low - zero.low) < 0.001f,
           "drive transfer is continuous near zero");
    expect(zero.low <= tiny.low + 0.00001f && tiny.low <= small.low + 0.00001f
           && small.low <= larger.low + 0.00001f,
           "near-zero drive progresses monotonically");
}

// An independent implementation of the original uncached TPT equations.
// This guards sonic parity when the control-coefficient cache is added or
// changed: held controls, rapid modulation and sample-rate changes must all
// produce the same voltage sequence, not merely a plausible filter response.
struct UncachedStateFilter {
    double ic1eq = 0.0;
    double ic2eq = 0.0;
    double previousSampleRate = 0.0;

    StateFilter::Sample process(double input, double sampleRate, double cutoff,
                                double resonance, double drive) {
        if (!StateFilter::ieeeFinite(sampleRate) || sampleRate < 1000.0) {
            ic1eq = ic2eq = previousSampleRate = 0.0;
            return {0.0f, 0.0f, 0.0f};
        }
        if (sampleRate != previousSampleRate) {
            ic1eq = ic2eq = 0.0;
            previousSampleRate = sampleRate;
        }
        const double maximum = std::min(20000.0, 0.45 * sampleRate);
        const double hz = StateFilter::finiteClamp(cutoff,
            std::min(1000.0, maximum), 5.0, maximum);
        const double resonant = StateFilter::finiteClamp(resonance, 0.0, 0.0, 1.0);
        const double distortion = StateFilter::finiteClamp(drive, 0.0, 0.0, 1.0);
        const double q = 0.5 + 11.5 * resonant * resonant;
        const double k = 1.0 / q;
        const double volts = StateFilter::finiteClamp(input, 0.0, -20.0, 20.0);
        double x = volts / 5.0;
        if (distortion > 0.0) {
            const double gain = 1.0 + 12.0 * distortion * distortion;
            const double shaped = std::tanh(gain * x) / std::tanh(gain);
            x += distortion * (shaped - x);
        }
        const double g = std::tan(kPi * hz / sampleRate);
        const double a1 = 1.0 / (1.0 + g * (g + k));
        const double a2 = g * a1;
        const double v3 = x - ic2eq;
        const double band = a1 * ic1eq + a2 * v3;
        const double low = ic2eq + g * band;
        const double high = x - k * band - low;
        ic1eq = StateFilter::finiteClamp(2.0 * band - ic1eq, 0.0, -16.0, 16.0);
        ic2eq = StateFilter::finiteClamp(2.0 * low - ic2eq, 0.0, -16.0, 16.0);
        if (std::abs(ic1eq) < 1e-20)
            ic1eq = 0.0;
        if (std::abs(ic2eq) < 1e-20)
            ic2eq = 0.0;
        return {StateFilter::boundedVoltage(low),
                StateFilter::boundedVoltage(band), StateFilter::boundedVoltage(high)};
    }
};

void testCoefficientCacheMatchesUncachedAudio() {
    StateFilter cached;
    UncachedStateFilter original;
    double maximumError = 0.0;
    for (int frame = 0; frame < 24000; ++frame) {
        // Long steady stretches test the cache hit path. Frequent transitions
        // test invalidation, including switching drive between 0 and nonzero.
        const double rate = frame < 9000 ? 48000.0
                           : frame < 18000 ? 96000.0 : 44100.0;
        const double hz = frame < 4000 ? 735.0 : frame < 8000 ? 3500.0
                        : frame < 12000 ? 735.0 : frame < 16000
                        ? 5.0 + 18000.0 * ((frame % 73) / 72.0) : 2500.0;
        const double resonance = frame < 10000 ? 0.5
                               : frame < 16000 ? (frame % 23) / 22.0 : 0.93;
        const double drive = frame < 5000 ? 0.0 : frame < 10000 ? 0.7
                           : frame < 16000 ? (frame % 5) / 4.0 : 0.7;
        const double signal = 4.0 * std::sin(frame * 0.217)
                            + 1.3 * std::sin(frame * 0.0017);
        const auto a = cached.process(signal, rate, hz, resonance, drive);
        const auto b = original.process(signal, rate, hz, resonance, drive);
        maximumError = std::max(maximumError, std::abs(double(a.low - b.low)));
        maximumError = std::max(maximumError, std::abs(double(a.band - b.band)));
        maximumError = std::max(maximumError, std::abs(double(a.high - b.high)));
    }
    expect(maximumError < 1e-6,
           "cached coefficients preserve uncached voltage output through automation and host-rate changes");

    cached.reset();
    original = UncachedStateFilter{};
    const auto afterReset = cached.process(2.0, 48000.0, 1250.0, 0.8, 0.75);
    const auto originalReset = original.process(2.0, 48000.0, 1250.0, 0.8, 0.75);
    expect(afterReset.low == originalReset.low &&
           afterReset.band == originalReset.band &&
           afterReset.high == originalReset.high,
           "explicit reset invalidates all cached coefficients");
}
} // namespace

int main() {
    testFrequencyResponse();
    testDCAndReset();
    testBoundsAndSampleRateChanges();
    testControlBehaviour();
    testCoefficientCacheMatchesUncachedAudio();

    if (failures != 0) {
        std::fprintf(stderr, "StateFilter: %d tests failed\n", failures);
        return 1;
    }
    std::puts("StateFilter: all DSP regression tests passed");
    return 0;
}
