/*
 * MODULAR-SYNTH ClockedLFO deterministic standalone C++17 regression.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "../plugins/ModularSynth/src/ClockedLFO.hpp"

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <new>

using modular_synth::dsp::ClockedLFO;

namespace { std::uint64_t allocationCalls = 0; }

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
int failures = 0;
void expect(bool value, const char* message) {
    if (!value) {
        ++failures;
        std::fprintf(stderr, "FAIL ClockedLFO: %s\n", message);
    }
}

bool finiteFloat(float value) {
    std::uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return (bits & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
}

bool safe(const ClockedLFO::Output& v) {
    return finiteFloat(v.sine) && finiteFloat(v.triangle)
        && finiteFloat(v.ramp) && finiteFloat(v.pulse)
        && finiteFloat(v.endOfCycle) && ClockedLFO::finite(v.frequencyHz)
        && ClockedLFO::finite(v.unshiftedPhase)
        && std::abs(v.sine) <= 5.0001f && std::abs(v.triangle) <= 5.0001f
        && std::abs(v.ramp) <= 5.0001f && std::abs(v.pulse) <= 5.0001f
        && (v.endOfCycle == 0.0f || v.endOfCycle == 10.0f)
        && v.unshiftedPhase >= 0.0 && v.unshiftedPhase < 1.0
        && v.frequencyHz > 0.0 && v.frequencyHz <= 200.0001;
}

void testWaveformsAndWrapPulse() {
    ClockedLFO lfo;
    ClockedLFO::Input in;
    in.sampleRateHz = 1000.0;
    in.log2RateHz = 0.0; // 1 Hz
    for (int i = 0; i < 1003; ++i) {
        const auto v = lfo.process(in);
        expect(safe(v), "all five wave outputs must be finite and bounded");
        if (i == 0)
            expect(v.sine == 0.0f && v.triangle == -5.0f
                   && v.ramp == -5.0f && v.pulse == 5.0f,
                   "phase-zero waveform values are exact");
        if (i == 250)
            expect(std::abs(v.sine - 5.0f) < 1e-4f
                   && std::abs(v.triangle) < 1e-4f
                   && std::abs(v.ramp + 2.5f) < 1e-4f,
                   "quarter-cycle sine/triangle/ramp phase alignment");
        if (i == 500)
            expect(std::abs(v.sine) < 1e-4f
                   && std::abs(v.triangle - 5.0f) < 1e-4f
                   && v.pulse == -5.0f,
                   "half-cycle triangle peak and negative pulse");
        if (i == 1000)
            expect(v.endOfCycle == 10.0f,
                   "EOC must be a full 10 V trigger on cycle wrap");
        if (i == 1002)
            expect(v.endOfCycle == 0.0f,
                   "EOC trigger must expire after its one-millisecond duration");
    }
    expect(std::abs(lfo.phase() - 0.003) < 0.00001,
           "phase accumulator must wrap without long-term drift");
}

void testAllClockRatiosRateCVAndWidthLimits() {
    constexpr double ratios[] = {0.25, 0.5, 1.0, 2.0, 4.0};
    for (int i = 0; i < 5; ++i)
        expect(ClockedLFO::clockRatio(i) == ratios[i],
               "all five clock-ratio indices must map to documented beat divisions");
    expect(ClockedLFO::clockRatio(std::numeric_limits<double>::infinity()) == 1.0,
           "invalid clock-ratio knob input must fall back to 1:1");

    ClockedLFO lfo;
    ClockedLFO::Input in;
    in.sampleRateHz = 1000.0;
    in.log2RateHz = 0.0;
    in.rateCvVolts = 2.0;
    expect(lfo.process(in).frequencyHz == 4.0,
           "free-run 1 V/oct CV must double frequency for each volt");
    in.rateCvVolts = -2.0;
    expect(lfo.process(in).frequencyHz == 0.25,
           "negative free-run CV must reduce frequency exponentially");
    in.rateCvVolts = 0.0;
    in.pulseWidth = 0.05;
    for (int i = 0; i < 498; ++i)
        lfo.process(in);
    const auto narrow = lfo.process(in);
    expect(narrow.pulse == -5.0f,
           "5% duty must be low when the phase is near half a cycle");
    in.widthCvVolts = 10.0;
    const auto wide = lfo.process(in);
    expect(wide.pulse == 5.0f,
           "width CV must safely clamp to 95% duty at large positive voltage");
}

void testPhaseAndResetSchmitt() {
    ClockedLFO lfo;
    ClockedLFO::Input in;
    in.sampleRateHz = 1000.0;
    in.log2RateHz = 0.0;
    for (int i = 0; i < 123; ++i)
        lfo.process(in);
    in.resetVoltage = 3.0;
    const auto first = lfo.process(in);
    expect(first.unshiftedPhase == 0.0,
           "reset input rising edge must align phase precisely at zero");
    for (int i = 0; i < 75; ++i)
        lfo.process(in);
    expect(lfo.phase() > 0.07,
           "held-high reset must not retrigger every sample");
    in.resetVoltage = 0.0;
    lfo.process(in);
    in.resetVoltage = 2.0;
    const auto second = lfo.process(in);
    expect(second.unshiftedPhase == 0.0,
           "reset Schmitt must rearm at <=1 V and retrigger at >=2 V");
    in.resetVoltage = 0.0;
    in.phaseOffset = 0.25;
    const auto shifted = lfo.process(in);
    expect(std::abs(shifted.sine - 5.0f) < 0.001f,
           "phase-offset knob must shift output without resetting engine phase");
    in.phaseCvVolts = 2.5;
    const auto moreShifted = lfo.process(in);
    expect(std::abs(moreShifted.sine) < 0.1f,
           "phase CV adds 0.1 cycle per volt and safely wraps");
}

void testExternalClockRatiosAndTempo() {
    ClockedLFO divided;
    ClockedLFO doubled;
    ClockedLFO::Input a;
    a.sampleRateHz = 1000.0;
    a.log2RateHz = 0.0;
    a.clockConnected = true;
    a.ratioIndex = 0.0; // 1/4 cycle per external beat
    auto b = a;
    b.ratioIndex = 3.0; // 2 cycles per external beat
    int doubledEocCount = 0;
    for (int frame = 0; frame <= 2005; ++frame) {
        a.clockVoltage = (frame % 500 == 0) ? 5.0 : 0.0;
        b.clockVoltage = a.clockVoltage;
        const auto va = divided.process(a);
        const auto vb = doubled.process(b);
        if (frame == 500) {
            expect(va.clockLocked && std::abs(va.frequencyHz - 0.5) < 1e-9
                   && std::abs(va.unshiftedPhase - 0.25) < 1e-9,
                   "two beats at 120 BPM must acquire quarter-rate tempo lock");
            expect(vb.clockLocked && std::abs(vb.frequencyHz - 4.0) < 1e-9,
                   "2x clock ratio must yield 4 LFO cycles per second at 120 BPM");
        }
        if (frame == 1000)
            expect(std::abs(va.unshiftedPhase - 0.5) < 1e-9,
                   "1/4 clock ratio must progress through quarter-cycle beat phases");
        if (frame == 1500)
            expect(std::abs(va.unshiftedPhase - 0.75) < 1e-9,
                   "quarter-rate synchronization must remain phase-aligned");
        if (frame == 2000)
            expect(va.unshiftedPhase == 0.0 && va.endOfCycle == 10.0f,
                   "one divided cycle must close on the fourth clock interval");
        if (frame > 500 && frame <= 1000 && vb.endOfCycle == 10.0f)
            ++doubledEocCount;
        expect(safe(va) && safe(vb), "external beat sync must stay finite");
    }
    expect(doubledEocCount >= 2 && doubledEocCount <= 4,
           "2x clock ratio must emit internal end-of-cycle pulses between beats");
}

void testClockBounceTimeoutAndFallback() {
    ClockedLFO lfo;
    ClockedLFO::Input in;
    in.sampleRateHz = 1000.0;
    in.log2RateHz = -1.0; // 0.5 Hz in free-run mode
    in.clockConnected = true;
    for (int frame = 0; frame < 3100; ++frame) {
        in.clockVoltage = (frame == 0 || frame == 5 || frame == 500) ? 5.0 : 0.0;
        const auto v = lfo.process(in);
        if (frame == 500)
            expect(v.clockLocked && std::abs(v.frequencyHz - 2.0) < 1e-9,
                   "5 ms clock bounce must be rejected, preserving 500 ms period");
        if (frame == 2700)
            expect(!v.clockLocked && std::abs(v.frequencyHz - 0.5) < 1e-9,
                   "clock timeout must return to free-run rate");
    }
    const double previous = lfo.phase();
    in.clockConnected = false;
    in.clockVoltage = 0.0;
    const auto disconnected = lfo.process(in);
    expect(!disconnected.clockLocked &&
           std::abs(disconnected.unshiftedPhase - previous) < 1e-9,
           "disconnecting clock must preserve oscillator phase");
}

void testSampleRateChangesAndFractionalPeriod() {
    ClockedLFO lfo;
    ClockedLFO::Input in;
    in.log2RateHz = 0.0;
    in.sampleRateHz = 48000.0;
    for (int i = 0; i < 12000; ++i)
        lfo.process(in);
    const double quarter = lfo.phase();
    expect(std::abs(quarter - 0.25) < 0.00001,
           "quarter second at 48 kHz must yield quarter LFO phase");
    in.sampleRateHz = 96000.0;
    const auto first = lfo.process(in);
    expect(std::abs(first.unshiftedPhase - quarter) < 1e-10,
           "sample-rate change must preserve phase without reset");
    for (int i = 1; i < 24000; ++i)
        lfo.process(in);
    expect(std::abs(lfo.phase() - 0.5) < 0.00001,
           "same physical quarter second at 96 kHz must advance equal phase");

    ClockedLFO clocked;
    in.clockConnected = true;
    in.sampleRateHz = 48000.0;
    in.clockVoltage = 5.0;
    clocked.process(in); // first external pulse
    in.clockVoltage = 0.0;
    for (int i = 1; i < 12000; ++i)
        clocked.process(in);
    in.sampleRateHz = 96000.0;
    for (int i = 0; i < 24000; ++i)
        clocked.process(in);
    in.clockVoltage = 5.0;
    const auto locked = clocked.process(in);
    expect(locked.clockLocked && std::abs(locked.frequencyHz - 2.0) < 0.001,
           "external 0.5-second beat period must survive 48-to-96 kHz switch");
}

void testInvalidRatesAndHostileCVUnderFastMath() {
    constexpr double infinity = std::numeric_limits<double>::infinity();
    const double nan = std::numeric_limits<double>::quiet_NaN();
    expect(!ClockedLFO::finite(infinity) && !ClockedLFO::finite(nan),
           "bitwise finite guard must reject Inf/NaN with strict fastmath");
    ClockedLFO lfo;
    ClockedLFO::Input in;
    for (double invalidRate : {0.0, -1.0, 500.0, 384001.0, infinity, nan}) {
        in.sampleRateHz = invalidRate;
        const auto v = lfo.process(in);
        expect(v.sine == 0.0f && v.triangle == 0.0f && v.ramp == 0.0f
               && v.pulse == 0.0f && v.endOfCycle == 0.0f
               && lfo.phase() == 0.0 && !lfo.locked(),
               "invalid sample rate must reset to silent safe state");
    }
    in.sampleRateHz = 384000.0;
    in.clockConnected = true;
    const std::array<double, 12> cv{{
        nan, infinity, -infinity, 1e250, -1e250,
        0.0, 1.0, -1.0, 10.0, -10.0, 0.25, 4.0
    }};
    for (int i = 0; i < 100000; ++i) {
        in.log2RateHz = cv[static_cast<std::size_t>(i) % cv.size()];
        in.rateCvVolts = cv[static_cast<std::size_t>(i / 3) % cv.size()];
        in.ratioIndex = cv[static_cast<std::size_t>(i / 5) % cv.size()];
        in.phaseOffset = cv[static_cast<std::size_t>(i / 7) % cv.size()];
        in.phaseCvVolts = cv[static_cast<std::size_t>(i / 11) % cv.size()];
        in.pulseWidth = cv[static_cast<std::size_t>(i / 13) % cv.size()];
        in.widthCvVolts = cv[static_cast<std::size_t>(i / 17) % cv.size()];
        in.clockVoltage = cv[static_cast<std::size_t>(i / 19) % cv.size()];
        in.resetVoltage = cv[static_cast<std::size_t>(i / 23) % cv.size()];
        const auto v = lfo.process(in);
        if (!safe(v)) {
            expect(false, "hostile audio-rate CV/reset/clock must always remain bounded");
            return;
        }
    }
    in.clockConnected = false;
    in.log2RateHz = 0.0;
    in.rateCvVolts = 0.0;
    const auto recovered = lfo.process(in);
    expect(safe(recovered) && std::abs(recovered.frequencyHz - 1.0) < 1e-9,
           "LFO must recover from arbitrary non-finite CV without poisoning state");
}

void testSixteenIndependentPolyphonicLanesAndNoAllocation() {
    std::array<ClockedLFO, 16> lanes;
    std::array<ClockedLFO::Input, 16> inputs{};
    const std::uint64_t allocated = allocationCalls;
    int locked = 0;
    for (int frame = 0; frame < 8000; ++frame) {
        for (int lane = 0; lane < 16; ++lane) {
            auto& in = inputs[static_cast<std::size_t>(lane)];
            in.sampleRateHz = 2000.0;
            in.log2RateHz = -1.0 + lane / 10.0;
            in.clockConnected = lane % 2 == 0;
            in.clockVoltage = in.clockConnected && frame % (400 + lane * 10) == 0
                ? 5.0 : 0.0;
            in.resetVoltage = lane == 7 && frame == 500 ? 5.0 : 0.0;
            const auto v = lanes[static_cast<std::size_t>(lane)].process(in);
            if (!safe(v)) {
                expect(false, "16 polyphonic clock/rate/reset lanes must stay finite");
                return;
            }
            if (lane == 7 && frame == 500)
                expect(v.unshiftedPhase == 0.0,
                       "polyphonic reset lane 7 must independently zero phase");
            if (lane == 8 && frame == 500)
                expect(v.unshiftedPhase > 0.0,
                       "one lane's reset must not reset neighboring lanes");
            if (frame == 4000 && v.clockLocked)
                ++locked;
        }
    }
    expect(locked == 8,
           "only eight lanes with connected external clocks may be clock-locked");
    expect(allocationCalls == allocated,
           "process() must not allocate for 16 voice/audio-rate modulation");
    for (auto& lane : lanes)
        lane.reset();
    expect(allocationCalls == allocated,
           "reset() must not allocate for any of the 16 lanes");
    std::printf("POLY 16 voices: eight clocked, eight free, allocations=%llu\n",
                static_cast<unsigned long long>(allocationCalls - allocated));
}

} // namespace

int main() {
    testWaveformsAndWrapPulse();
    testAllClockRatiosRateCVAndWidthLimits();
    testPhaseAndResetSchmitt();
    testExternalClockRatiosAndTempo();
    testClockBounceTimeoutAndFallback();
    testSampleRateChangesAndFractionalPeriod();
    testInvalidRatesAndHostileCVUnderFastMath();
    testSixteenIndependentPolyphonicLanesAndNoAllocation();
    if (failures != 0) {
        std::fprintf(stderr, "ClockedLFO: %d regression failure(s)\n", failures);
        return 1;
    }
    std::puts("PASS: ClockedLFO 16-lane wave/clock/reset/phase/fastmath/alloc regression");
    return 0;
}
