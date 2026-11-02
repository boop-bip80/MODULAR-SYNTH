/*
 * MODULAR-SYNTH ChanceHold deterministic standalone C++17 DSP regression.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "../plugins/ModularSynth/src/ChanceHold.hpp"

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <new>

using modular_synth::dsp::ChanceHold;

namespace {
std::uint64_t allocationCalls = 0;
int failures = 0;
}
void* operator new(std::size_t n) {
    ++allocationCalls;
    if (void* memory = std::malloc(n ? n : 1))
        return memory;
    throw std::bad_alloc();
}
void* operator new[](std::size_t n) {
    ++allocationCalls;
    if (void* memory = std::malloc(n ? n : 1))
        return memory;
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }

namespace {

void expect(bool ok, const char* why) {
    if (!ok) {
        ++failures;
        std::fprintf(stderr, "FAIL ChanceHold: %s\n", why);
    }
}

bool finiteFloat(float value) {
    std::uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return (bits & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
}

bool safe(const ChanceHold::Output& v) {
    return finiteFloat(v.held) && finiteFloat(v.glide)
        && finiteFloat(v.trigger) && ChanceHold::finite(v.freeFrequencyHz)
        && std::abs(v.held) <= 5.00001f
        && std::abs(v.glide) <= 5.00001f
        && (v.trigger == 0.0f || v.trigger == 10.0f)
        && v.freeFrequencyHz > 0.0 && v.freeFrequencyHz <= 128.0;
}

void testFreeClockProbabilityAndRateCv() {
    ChanceHold unit;
    ChanceHold::Input in;
    in.sampleRateHz = 1000;
    in.log2RateHz = 0;
    in.probability = 1;
    in.glideSeconds = 0;

    int triggers = 0;
    for (int i = 0; i < 2500; ++i) {
        const auto o = unit.process(in);
        expect(safe(o), "valid outputs must always remain bounded");
        triggers += o.trigger == 10.0f ? 1 : 0;
        if (o.trigger == 10.0f)
            expect(o.glide == o.held, "zero glide jumps to held sample");
    }
    expect(triggers == 2, "1 Hz free clock creates two accepted hits in 2.5 seconds");

    unit.reset();
    in.log2RateHz = -4;
    in.rateCvVolts = 5; // 2 Hz; 1 V/oct
    const auto a = unit.process(in);
    expect(a.freeFrequencyHz == 2.0, "1 V/oct CV adds to log2 free rate");

    in.probability = 0.0;
    in.rateCvVolts = 7;
    int zeroHits = 0;
    for (int i = 0; i < 2000; ++i)
        zeroHits += unit.process(in).trigger == 10.0f ? 1 : 0;
    expect(zeroHits == 0 && unit.heldVoltage() == 0.0,
           "probability 0 rejects every internal sample");
    in.probabilityCvVolts = 10.0;
    bool accepted = false;
    for (int i = 0; i < 300; ++i)
        accepted |= unit.process(in).trigger == 10.0f;
    expect(accepted, "+10 V probability CV raises chance from zero to certainty");
}

void testClockSchmittNoHeldGateRetriggerAndResetPriority() {
    ChanceHold unit;
    ChanceHold::Input in;
    in.sampleRateHz = 1000;
    in.clockConnected = true;
    in.clockVoltage = 5;
    in.probability = 1;
    in.glideSeconds = 0.0;
    expect(unit.process(in).trigger == 10.0f,
           "first 2 V external rising edge samples immediately");
    int extra = 0;
    for (int i = 0; i < 50; ++i)
        extra += unit.process(in).trigger == 10.0f;
    expect(extra == 0, "held-high external gate does not keep sampling");

    in.clockVoltage = 1.5;
    unit.process(in);
    in.clockVoltage = 4;
    expect(unit.process(in).trigger == 0.0f,
           "1.5 V does not rearm Schmitt clock");
    in.clockVoltage = 0;
    unit.process(in);
    in.clockVoltage = 3;
    expect(unit.process(in).trigger == 10.0f,
           "clock rearms at <=1 V and triggers at >=2 V");

    in.clockVoltage = 0;
    in.resetVoltage = 0;
    unit.process(in);
    in.clockVoltage = 5;
    in.resetVoltage = 5;
    auto resetSample = unit.process(in);
    expect(resetSample.held == 0.0f && resetSample.glide == 0.0f
           && resetSample.trigger == 0.0f,
           "simultaneous reset and clock: reset must dominate");
    for (int i = 0; i < 20; ++i)
        expect(unit.process(in).held == 0.0f,
               "held-high reset and clock do not retrigger");
    in.resetVoltage = 0;
    in.clockVoltage = 0;
    unit.process(in);
    in.clockVoltage = 5;
    expect(unit.process(in).trigger == 10.0f,
           "clock resumes normally after reset is released");
}

void testTriggerWidthGlideAndQuantization() {
    ChanceHold unit;
    ChanceHold::Input in;
    in.sampleRateHz = 48000;
    in.clockConnected = true;
    in.clockVoltage = 5;
    in.probability = 1;
    in.glideSeconds = 0.50;
    in.semitoneQuantize = true;

    const auto first = unit.process(in);
    expect(first.trigger == 10.0f && first.held != 0.0f
           && std::abs(first.glide) < std::abs(first.held),
           "accepted sample triggers; nonzero glide starts gradually");
    const float nearestSemitone = std::round(first.held * 12.0f) / 12.0f;
    expect(std::abs(first.held - nearestSemitone) < 1e-5f,
           "quantized random CV lies on a 1/12 V semitone grid");

    int pulseFrames = 1;
    for (int i = 0; i < 100; ++i)
        pulseFrames += unit.process(in).trigger == 10.0f ? 1 : 0;
    expect(pulseFrames >= 47 && pulseFrames <= 49,
           "accepted trigger has 1 ms duration at 48 kHz");

    // With no further external clock, the filtered output converges.
    for (int i = 101; i < 24000; ++i)
        unit.process(in);
    expect(std::abs(unit.glideVoltage() - unit.heldVoltage()) < 0.011 * 
           std::max(0.1, std::abs(unit.heldVoltage())),
           "glide reaches within ~1% of target after 99% settling time");
}

void testDeterministicSequenceAndIndependentSeeds() {
    ChanceHold unit(UINT32_C(0x513e2ca7));
    ChanceHold::Input in;
    in.sampleRateHz = 1000;
    in.clockConnected = true;
    in.probability = 1.0;
    in.glideSeconds = 0.0;
    std::array<float, 8> sequence{};
    for (std::size_t j = 0; j < sequence.size(); ++j) {
        in.clockVoltage = 0;
        unit.process(in);
        in.clockVoltage = 5;
        sequence[j] = unit.process(in).held;
    }
    const auto afterEight = unit.generatorState();

    // User RESET yields the same stream, not a new system-random seed.
    in.clockVoltage = 0;
    in.resetVoltage = 5;
    unit.process(in);
    in.resetVoltage = 0;
    unit.process(in);
    for (std::size_t j = 0; j < sequence.size(); ++j) {
        in.clockVoltage = 0;
        unit.process(in);
        in.clockVoltage = 5;
        expect(unit.process(in).held == sequence[j],
               "explicit RESET must recreate exact seeded CV stream");
    }
    expect(unit.generatorState() == afterEight,
           "random state matches exactly after replay");

    ChanceHold another(UINT32_C(0x18513adf));
    in.clockVoltage = 0;
    another.process(in);
    in.clockVoltage = 5;
    const auto different = another.process(in);
    expect(different.held != sequence[0],
           "different lane seeds must produce independent random CV");
}

void testSampleRateChangeAndInvalidRateReset() {
    ChanceHold unit;
    ChanceHold::Input in;
    in.sampleRateHz = 1000;
    in.probability = 1;
    in.glideSeconds = 0;
    for (int i = 0; i < 500; ++i)
        unit.process(in);
    in.sampleRateHz = 2000;
    int hits = 0;
    for (int i = 0; i < 1100; ++i)
        hits += unit.process(in).trigger == 10.0f ? 1 : 0;
    expect(hits == 2, "sample-rate change preserves elapsed free-clock phase");
    // Invalid sample rate must zero all outputs and reset internal state.
    for (double bad : {0.0, -1.0, 999.0, 384001.0,
                       std::numeric_limits<double>::infinity(),
                       std::numeric_limits<double>::quiet_NaN()}) {
        in.sampleRateHz = bad;
        const auto o = unit.process(in);
        expect(o.held == 0.0f && o.glide == 0.0f &&
               o.trigger == 0.0f && unit.generatorState() == ChanceHold::kDefaultSeed,
               "invalid sample rate resets to silence and original seed");
    }
    in.sampleRateHz = 1000;
    expect(safe(unit.process(in)), "valid rate recovers after invalid rate");
}

void testHostileCvFastmathNoAllocAndSixteenLanes() {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double inf = std::numeric_limits<double>::infinity();
    expect(!ChanceHold::finite(nan) && !ChanceHold::finite(inf),
           "bitwise finite guard remains correct under -ffast-math");

    std::array<ChanceHold, 16> lanes;
    for (int c = 0; c < 16; ++c)
        lanes[static_cast<std::size_t>(c)].setSeed(
            UINT32_C(0x6d2b79f5) ^ (UINT32_C(0x9e3779b9) *
            static_cast<std::uint32_t>(c + 1)));
    std::array<double, 13> values{{
        nan, inf, -inf, 1e260, -1e260, 0, 0.25, -0.25, 1, -1, 5, 10, -10
    }};
    const auto allocations = allocationCalls;
    for (int frame = 0; frame < 12000; ++frame) {
        for (int c = 0; c < 16; ++c) {
            ChanceHold::Input in;
            in.sampleRateHz = frame % 2 == 0 ? 48000.0 : 96000.0;
            in.clockConnected = true;
            in.log2RateHz = values[(frame + c) % values.size()];
            in.rateCvVolts = values[(frame / 2 + c) % values.size()];
            in.probability = values[(frame / 3 + c) % values.size()];
            in.probabilityCvVolts = values[(frame / 5 + c) % values.size()];
            in.glideSeconds = values[(frame / 7 + c) % values.size()];
            in.glideCvVolts = values[(frame / 11 + c) % values.size()];
            in.clockVoltage = frame % 9 == 0 ? 5 : 0;
            in.resetVoltage = frame == 10 && c == 7 ? 5 : 0;
            in.semitoneQuantize = frame % 2 == 0;
            const auto out = lanes[static_cast<std::size_t>(c)].process(in);
            if (!safe(out)) {
                expect(false, "random hostile CV must not leak NaN/Inf or exceed 5 V");
                return;
            }
        }
    }
    expect(allocationCalls == allocations,
           "sixteen audio-rate lanes allocate no heap memory in process()");
    expect(lanes[0].generatorState() != lanes[1].generatorState(),
           "independent seeded lanes must not share generator state");
}

} // namespace

int main() {
    testFreeClockProbabilityAndRateCv();
    testClockSchmittNoHeldGateRetriggerAndResetPriority();
    testTriggerWidthGlideAndQuantization();
    testDeterministicSequenceAndIndependentSeeds();
    testSampleRateChangeAndInvalidRateReset();
    testHostileCvFastmathNoAllocAndSixteenLanes();
    if (failures) {
        std::fprintf(stderr, "ChanceHold: %d regression failure(s)\n", failures);
        return 1;
    }
    std::puts("PASS: ChanceHold clock/chance/glide/reset/CV/polyphony/fastmath/alloc");
    return 0;
}
