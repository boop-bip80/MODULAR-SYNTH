/*
 * MODULAR-SYNTH SlewGlide deterministic standalone DSP regression.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "../plugins/ModularSynth/src/SlewGlide.hpp"

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <new>

using modular_synth::dsp::SlewGlide;

namespace {
std::uint64_t allocations = 0;
int failures = 0;
}
void* operator new(std::size_t size) {
    ++allocations;
    if (void* p = std::malloc(size ? size : 1)) return p;
    throw std::bad_alloc();
}
void* operator new[](std::size_t size) {
    ++allocations;
    if (void* p = std::malloc(size ? size : 1)) return p;
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }

namespace {
void expect(bool truth, const char* why) {
    if (!truth) {
        ++failures;
        std::fprintf(stderr, "FAIL SlewGlide: %s\n", why);
    }
}

bool safe(const SlewGlide::Output& output) {
    return SlewGlide::finite(output.linear)
        && SlewGlide::finite(output.exponential)
        && SlewGlide::finite(output.movingGate)
        && std::abs(output.linear) <= 10.00001f
        && std::abs(output.exponential) <= 10.00001f
        && (output.movingGate == 0.0f || output.movingGate == 10.0f);
}

void testTimeConstantAndDirectionalAsymmetry() {
    SlewGlide core;
    SlewGlide::Input in;
    in.sampleRateHz = 1000.0;
    in.voltage = 10.0;
    in.riseSeconds = 1.0;
    in.fallSeconds = 0.5;

    auto output = core.process(in);
    expect(safe(output), "first outputs bounded");
    expect(std::abs(output.linear - 0.01f) < 1.0e-6f,
           "linear 1s rise traverses 10V at 1000Hz with 0.01V steps");
    expect(output.movingGate == 10.0f, "movement gate active during rise");
    for (int frame = 1; frame < 1000; ++frame)
        output = core.process(in);
    expect(std::abs(output.linear - 10.0f) < 1.0e-4f,
           "linear 10V traversal finishes after configured 1s");
    expect(std::abs(output.exponential - 9.9f) < 0.015f,
           "exponential 1s rise approaches exactly 99% of a held 10V target");

    in.voltage = -10.0;
    output = core.process(in);
    expect(output.linear < 10.0f && output.linear > 9.9f,
           "linear fall is distinct from rising rate");
    expect(output.exponential < 9.9f,
           "exponential fall is distinct from rising rate");
    for (int frame = 1; frame < 1000; ++frame)
        output = core.process(in);
    expect(std::abs(output.linear + 10.0f) < 1.0e-4f,
           "20V downward travel takes 1s with 0.5s-per-10V fall");
    expect(std::abs(output.exponential + 9.99801f) < 0.02f,
           "downward exponential falls approximately 99% per 0.5s");
}

void testCvAndZeroTime() {
    SlewGlide core;
    SlewGlide::Input in;
    in.sampleRateHz = 2000.0;
    in.riseSeconds = 0.0;
    in.fallSeconds = 0.0;
    in.voltage = 6.0;
    auto output = core.process(in);
    expect(output.linear == 6.0f && output.exponential == 6.0f,
           "zero slew time bypasses both curves exactly");
    expect(output.movingGate == 0.0f, "zero-time step is not active motion");

    core.reset();
    in.riseCvVolts = 2.0; // 1s rise despite zero knob
    output = core.process(in);
    expect(std::abs(output.linear - 0.005f) < 1.0e-6f,
           "+2V rise CV adds one second at 2kHz");
    in.riseCvVolts = -20.0; // negative override clamps to zero
    output = core.process(in);
    expect(output.linear == 6.0f && output.exponential == 6.0f,
           "negative rise CV can shorten rise to instant zero");

    in.voltage = -6.0;
    in.fallCvVolts = 0.0;
    output = core.process(in);
    expect(output.linear == -6.0f && output.exponential == -6.0f,
           "zero fall time snaps on a reversed input");
    core.reset();
    in.voltage = 11.0;
    in.riseCvVolts = 0.0;
    output = core.process(in);
    expect(output.linear == 10.0f && output.exponential == 10.0f,
           "input and output are limited to 10V magnitude");
}

void testDeterminismResetAndSettling() {
    SlewGlide first;
    SlewGlide second;
    SlewGlide::Input in;
    in.sampleRateHz = 48000.0;
    in.voltage = 7.0;
    in.riseSeconds = 0.02;
    in.fallSeconds = 0.01;
    for (int i = 0; i < 32000; ++i) {
        const auto a = first.process(in);
        const auto b = second.process(in);
        expect(a.linear == b.linear && a.exponential == b.exponential
                   && a.movingGate == b.movingGate, "deterministic lane replay");
        if (i == 31999) {
            expect(a.movingGate == 0.0f,
                   "motion gate drops after both curves converge");
            expect(a.linear == 7.0f && a.exponential == 7.0f,
                   "denormal-safe exact-target snap reaches stable output");
        }
    }
    first.reset();
    expect(first.linearVoltage() == 0.0 && first.exponentialVoltage() == 0.0,
           "host reset clears first-party CV state");
    first.process(in);
    second.reset();
    const auto replay = second.process(in);
    expect(static_cast<float>(first.linearVoltage()) == replay.linear
               && static_cast<float>(first.exponentialVoltage()) == replay.exponential,
           "reset replay reproduces first-frame transition");
}

void testUntrustedInputsAndSixteenLanes() {
    std::array<SlewGlide, 16> cores;
    SlewGlide::Input in;
    in.sampleRateHz = 1000.0;
    in.voltage = std::numeric_limits<double>::quiet_NaN();
    in.riseSeconds = std::numeric_limits<double>::infinity();
    in.fallCvVolts = -std::numeric_limits<double>::infinity();
    for (auto& core : cores)
        expect(safe(core.process(in)), "nonfinite controls cannot leak NaN/Inf");

    in.sampleRateHz = -100.0;
    in.voltage = 7.0;
    for (auto& core : cores) {
        const auto output = core.process(in);
        expect(output.linear == 0.0f && output.exponential == 0.0f,
               "invalid host sample rate fails closed and resets lane");
    }
    in.sampleRateHz = 48000.0;
    in.riseSeconds = 0.1;
    in.fallSeconds = 0.01;
    in.voltage = 9.0;
    const auto startAllocations = allocations;
    for (int frame = 0; frame < 8192; ++frame) {
        for (int lane = 0; lane < 16; ++lane) {
            in.voltage = (lane % 2 ? -9.0 : 9.0) * (frame % 100 < 50 ? 1 : -1);
            in.riseCvVolts = (frame % 25 == 0) ? 4.0 : 0.0;
            in.fallCvVolts = (frame % 25 == 0) ? 3.0 : 0.0;
            expect(safe(cores[static_cast<std::size_t>(lane)].process(in)),
                   "16 independent lanes remain finite under stress");
        }
    }
    expect(allocations == startAllocations,
           "SlewGlide 16-lane audio path performs zero heap allocations");
}
}

int main() {
    testTimeConstantAndDirectionalAsymmetry();
    testCvAndZeroTime();
    testDeterminismResetAndSettling();
    testUntrustedInputsAndSixteenLanes();
    if (failures) {
        std::fprintf(stderr, "SlewGlide: %d regression failure(s)\n", failures);
        return EXIT_FAILURE;
    }
    std::puts("PASS: SlewGlide rise/fall/CV/linear/exponential/gate/reset/polyphony/fastmath/alloc");
    return EXIT_SUCCESS;
}
