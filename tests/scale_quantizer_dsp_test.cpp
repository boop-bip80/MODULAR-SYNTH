/*
 * MODULAR-SYNTH ScaleQuantizer deterministic source-level DSP regression.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "../plugins/ModularSynth/src/ScaleQuantizer.hpp"

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <new>

using modular_synth::dsp::ScaleQuantizer;

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
        std::fprintf(stderr, "FAIL ScaleQuantizer: %s\n", why);
    }
}
bool safe(const ScaleQuantizer::Output& output) {
    return std::isfinite(output.pitchVolts)
        && output.pitchVolts >= -10.000001f && output.pitchVolts <= 10.000001f
        && (output.changedGate == 0.0f || output.changedGate == 10.0f)
        && output.semitone >= -120 && output.semitone <= 120;
}
void expectNote(ScaleQuantizer& quantizer, ScaleQuantizer::Input& input,
                int semitone, const char* why) {
    const auto out = quantizer.process(input);
    expect(safe(out) && out.semitone == semitone
               && std::abs(out.pitchVolts - static_cast<float>(semitone / 12.0)) < 1.0e-6f,
           why);
}

void testChromaticOneVoltPerOctave() {
    ScaleQuantizer core;
    ScaleQuantizer::Input in;
    in.hysteresisCents = 0.0;
    for (int semitone = -120; semitone <= 120; ++semitone) {
        in.pitchVolts = semitone / 12.0;
        expectNote(core, in, semitone, "chromatic quantization preserves signed 1V/oct semitones");
    }
    core.reset();
    in.pitchVolts = 0.5 / 12.0;
    expectNote(core, in, 0, "exact positive midpoint tie goes to lower pitch");
    core.reset();
    in.pitchVolts = -0.5 / 12.0;
    expectNote(core, in, -1, "exact negative midpoint tie goes to lower pitch");
    core.reset();
    in.pitchVolts = -0.83;
    expectNote(core, in, -10, "negative semitone uses true floor, not truncation");
}

void testScaleRootsAndModes() {
    struct Mode {
        int scale;
        unsigned mask;
    };
    const Mode modes[] = {
        {ScaleQuantizer::Chromatic, 0xFFF},
        {ScaleQuantizer::Major, 0xAB5},
        {ScaleQuantizer::NaturalMinor, 0x5AD},
        {ScaleQuantizer::Dorian, 0x6AD},
        {ScaleQuantizer::HarmonicMinor, 0x9AD},
        {ScaleQuantizer::MajorPentatonic, 0x295},
        {ScaleQuantizer::MinorPentatonic, 0x4A9},
        {ScaleQuantizer::WholeTone, 0x555},
    };
    for (const Mode& mode : modes) {
        expect(ScaleQuantizer::scaleMask(mode.scale) == mode.mask,
               "scale degrees match reference intervals");
        for (int root = 0; root < 12; ++root) {
            for (int semitone = -120; semitone <= 120; ++semitone) {
                const bool allowed = (mode.mask &
                    (1U << ScaleQuantizer::positiveMod12(semitone - root))) != 0;
                expect(ScaleQuantizer::allowed(semitone, root, mode.scale) == allowed,
                       "pitch-class rotation works in all roots and octaves");
                ScaleQuantizer q;
                ScaleQuantizer::Input in;
                in.scale = mode.scale;
                in.root = root;
                in.pitchVolts = semitone / 12.0;
                const auto out = q.process(in);
                expect(safe(out) && ScaleQuantizer::allowed(out.semitone, root, mode.scale),
                       "each of eight modes emits only the selected rooted scale notes");
            }
        }
    }
    ScaleQuantizer q;
    ScaleQuantizer::Input in;
    in.scale = ScaleQuantizer::Major;
    in.root = 0;
    in.pitchVolts = 1.0 / 12.0;  // C# lands on C in C major, a lower tie.
    expectNote(q, in, 0, "C major rejects C# via deterministic lower tie");
    q.reset();
    in.root = 2;
    in.pitchVolts = 2.0 / 12.0;
    expectNote(q, in, 2, "D major admits D as tonic");
    q.reset();
    in.root = 0;
    in.rootCvVolts = 2.0 / 12.0; // transpose the root to D, not the pitch itself.
    expectNote(q, in, 2, "1V/oct semitone root CV rotates allowed scale pitches");
}

void testTransposeHysteresisAndChangePulse() {
    ScaleQuantizer q;
    ScaleQuantizer::Input in;
    in.sampleRateHz = 1000.0;
    in.hysteresisCents = 20.0;
    in.pitchVolts = 0.0;
    auto out = q.process(in);
    expect(out.semitone == 0 && out.changedGate == 10.0f,
           "first accepted note starts 2ms change trigger");
    out = q.process(in);
    expect(out.changedGate == 10.0f, "second 1kHz frame completes 2ms trigger");
    out = q.process(in);
    expect(out.changedGate == 0.0f, "held note does not retrigger");
    in.pitchVolts = 0.58 / 12.0;
    expectNote(q, in, 0, "20 cent hysteresis holds previous note just past midpoint");
    in.pitchVolts = 0.61 / 12.0;
    out = q.process(in);
    expect(out.semitone == 1 && out.changedGate == 10.0f,
           "crossing hysteresis margin emits a new note and trigger");
    in.pitchVolts = 0.48 / 12.0;
    expectNote(q, in, 1, "hysteresis suppresses small reverse jitter");
    in.pitchVolts = 0.39 / 12.0;
    expectNote(q, in, 0, "large enough reverse movement quantizes down");

    q.reset();
    in = ScaleQuantizer::Input{};
    in.pitchVolts = 1.0;
    in.transposeSemitones = -12;
    expectNote(q, in, 0, "transpose knob subtracts precisely one octave");
    q.reset();
    in.transposeSemitones = 0;
    in.transposeCvVolts = -0.5;
    expectNote(q, in, 6, "transpose CV is accurate 1V/oct and signed");

    q.reset();
    in = ScaleQuantizer::Input{};
    in.scale = ScaleQuantizer::MajorPentatonic;
    in.pitchVolts = 0.0;
    expectNote(q, in, 0, "major pentatonic C starts on C");
    in.root = 2;
    auto changed = q.process(in);
    expect(changed.semitone == -1 && changed.changedGate == 10.0f,
           "changing tonic rejects prior degree and generates note-change pulse");
}

void testUntrustedInputsAndSixteenLanes() {
    ScaleQuantizer q;
    ScaleQuantizer::Input in;
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double inf = std::numeric_limits<double>::infinity();
    in.pitchVolts = nan;
    in.transposeCvVolts = inf;
    in.rootCvVolts = -inf;
    in.hysteresisCents = nan;
    expect(safe(q.process(in)), "nonfinite pitch/control CV cannot escape DSP output");
    in.sampleRateHz = nan;
    const auto invalid = q.process(in);
    expect(!q.initialized() && invalid.pitchVolts == 0.0f
               && invalid.changedGate == 0.0f,
           "bad sample rate fails closed and clears held note/trigger state");
    in.sampleRateHz = 48000.0;
    in.pitchVolts = 0.0;
    in.transposeCvVolts = 0.0;
    in.rootCvVolts = 0.0;
    expect(safe(q.process(in)), "valid host rate restarts after invalid frame");

    std::array<ScaleQuantizer, 16> lanes;
    const auto start = allocations;
    for (int frame = 0; frame < 8192; ++frame) {
        for (int lane = 0; lane < 16; ++lane) {
            in.pitchVolts = ((frame + lane * 43) % 267 - 133) / 12.0;
            in.root = lane % 12;
            in.scale = lane % ScaleQuantizer::ScaleCount;
            in.transposeCvVolts = lane % 2 ? -0.25 : 0.25;
            in.rootCvVolts = (frame % 17) / 12.0;
            expect(safe(lanes[static_cast<std::size_t>(lane)].process(in)),
                   "all 16 lanes remain bounded and finite under CV stress");
        }
    }
    expect(allocations == start, "16-lane audio loop performs zero heap allocations");
}
}

int main() {
    testChromaticOneVoltPerOctave();
    testScaleRootsAndModes();
    testTransposeHysteresisAndChangePulse();
    testUntrustedInputsAndSixteenLanes();
    if (failures) {
        std::fprintf(stderr, "ScaleQuantizer: %d regressions failed\n", failures);
        return EXIT_FAILURE;
    }
    std::puts("PASS: ScaleQuantizer 1V/oct/scales/roots/CV/hysteresis/gate/reset/16-lane/zero-alloc");
    return EXIT_SUCCESS;
}
