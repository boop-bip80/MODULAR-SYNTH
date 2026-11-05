"""Compile and measure the opt-in polyBLAMP triangle starter.

The generated C++ runs against a HEADLESS Rack test double, not a plugin host.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from integrate import integration_plan
from module_forge import check_module, generate, render_files


ROOT = Path(__file__).resolve().parents[2]
PROBE = r'''
#ifndef HEADLESS
#error "Triangle regression must use the HEADLESS Rack shim"
#endif
#include "ForgeTriangle.cpp"

#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

static bool finiteBits(float value) {
    std::uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return (bits & 0x7f800000u) != 0x7f800000u;
}

constexpr int N = 8192;
constexpr int fundamentalBin = 1583;

static double binPower(const std::array<float, N>& values, int bin) {
    constexpr double twoPi = 6.28318530717958647692;
    double real = 0.0;
    double imaginary = 0.0;
    for (int i = 0; i < N; ++i) {
        const double phase = twoPi * static_cast<double>(bin) * i / N;
        real += values[i] * std::cos(phase);
        imaginary += values[i] * std::sin(phase);
    }
    return (real * real + imaginary * imaginary) / (static_cast<double>(N) * N);
}

int main() {
    if (!modelMSForgeTriangle)
        return 1;
    static_assert(MSForgeTriangleModule::NUM_PARAMS == 1, "coarse pitch");
    static_assert(MSForgeTriangleModule::NUM_INPUTS == 1, "pitch CV");
    static_assert(MSForgeTriangleModule::NUM_OUTPUTS == 1, "triangle output");

    rack::ProcessArgs args{};
    args.sampleRate = 48000.0;
    args.sampleTime = 1.0 / 48000.0;
    MSForgeTriangleModule triangle;
    MSForgeTriangleWidget widget(&triangle);
    if (widget.module != &triangle)
        return 2;

    // Coherent 9.28-kHz fundamental: a true triangle has odd harmonics
    // decaying as 1/n^2. Harmonics 3/5/7/9 are above Nyquist and alias.
    constexpr double frequency = fundamentalBin * 48000.0 / N;
    const float octaves = static_cast<float>(std::log2(frequency / 261.625565));
    triangle.params[MSForgeTriangleModule::COARSE_PARAM].setValue(4.f);
    triangle.inputs[MSForgeTriangleModule::PITCH_INPUT].setChannels(1);
    triangle.inputs[MSForgeTriangleModule::PITCH_INPUT].setVoltage(octaves - 4.f, 0);

    std::array<float, N> corrected{};
    std::array<float, N> naive{};
    for (int i = 0; i < N; ++i) {
        triangle.process(args);
        const float audio = triangle.outputs[MSForgeTriangleModule::AUDIO_OUTPUT]
                                     .getVoltage(0);
        if (!finiteBits(audio) || std::fabs(audio) > 5.01f)
            return 3;
        corrected[i] = audio / 5.f;
        const float phase = triangle.phase[0];
        naive[i] = 1.f - 4.f * std::min(phase, 1.f - phase);
    }

    double correctedAlias = 0.0;
    double naiveAlias = 0.0;
    for (int harmonic : {3, 5, 7, 9}) {
        int bin = (harmonic * fundamentalBin) % N;
        if (bin > N / 2)
            bin = N - bin;
        correctedAlias += binPower(corrected, bin);
        naiveAlias += binPower(naive, bin);
    }
    if (!(naiveAlias > 1e-8) || !(correctedAlias > 0.0))
        return 4;
    std::printf("%.4f\n", 10.0 * std::log10(correctedAlias / naiveAlias));

    // A low-frequency triangle must still reach approximately full scale,
    // alternate slope and remain centered in both compiled math modes.
    triangle.onReset();
    triangle.params[MSForgeTriangleModule::COARSE_PARAM].setValue(0.f);
    triangle.inputs[MSForgeTriangleModule::PITCH_INPUT].setVoltage(-1.f, 0);
    float low = 10.f;
    float high = -10.f;
    double sum = 0.0;
    for (int i = 0; i < 48000; ++i) {
        triangle.process(args);
        const float sample = triangle.outputs[MSForgeTriangleModule::AUDIO_OUTPUT]
                                      .getVoltage(0);
        if (!finiteBits(sample))
            return 5;
        low = std::min(low, sample);
        high = std::max(high, sample);
        sum += sample;
    }
    if (low > -4.95f || high < 4.95f || std::fabs(sum / 48000.0) > 0.03)
        return 6;

    // Inactive voice phases must be retired and cannot resume stale notes.
    triangle.inputs[MSForgeTriangleModule::PITCH_INPUT].setChannels(2);
    triangle.inputs[MSForgeTriangleModule::PITCH_INPUT].setVoltage(0.f, 0);
    triangle.inputs[MSForgeTriangleModule::PITCH_INPUT].setVoltage(1.f, 1);
    triangle.onReset();
    for (int i = 0; i < 128; ++i)
        triangle.process(args);
    if (triangle.outputs[MSForgeTriangleModule::AUDIO_OUTPUT].getChannels() != 2
        || triangle.phase[1] == 0.f)
        return 7;
    triangle.inputs[MSForgeTriangleModule::PITCH_INPUT].setChannels(1);
    triangle.process(args);
    if (triangle.phase[1] != 0.f || triangle.activeChannels != 1)
        return 8;
    triangle.inputs[MSForgeTriangleModule::PITCH_INPUT].setChannels(2);
    triangle.process(args);
    if (triangle.phase[1] < 0.f || triangle.phase[1] >= 1.f)
        return 9;

    // Nonfinite CV, a nonfinite coarse control and invalid sample rates
    // must not break the oscillator under aggressive -ffast-math.
    std::uint32_t nanBits = 0x7fc00000u;
    float nanPitch = 0.f;
    std::memcpy(&nanPitch, &nanBits, sizeof(nanBits));
    triangle.inputs[MSForgeTriangleModule::PITCH_INPUT].setVoltage(nanPitch, 0);
    args.sampleRate = 0.0;
    triangle.process(args);
    if (!finiteBits(triangle.outputs[MSForgeTriangleModule::AUDIO_OUTPUT].getVoltage(0)))
        return 10;
    args.sampleRate = 96000.0;
    triangle.process(args);
    if (!finiteBits(triangle.outputs[MSForgeTriangleModule::AUDIO_OUTPUT].getVoltage(0)))
        return 11;

    // Full channel count with extreme pitch and all conventional host rates:
    // no stale voice state, nonfinite output or >5 V overshoot at Nyquist.
    for (double sampleRate : {44100.0, 48000.0, 96000.0}) {
        args.sampleRate = sampleRate;
        triangle.inputs[MSForgeTriangleModule::PITCH_INPUT].setChannels(16);
        triangle.params[MSForgeTriangleModule::COARSE_PARAM].setValue(0.f);
        for (int voice = 0; voice < 16; ++voice)
            triangle.inputs[MSForgeTriangleModule::PITCH_INPUT].setVoltage(
                static_cast<float>(voice - 8), voice);
        for (int i = 0; i < 512; ++i) {
            triangle.process(args);
            if (triangle.outputs[MSForgeTriangleModule::AUDIO_OUTPUT].getChannels() != 16)
                return 12;
            for (int voice = 0; voice < 16; ++voice) {
                const float sample = triangle.outputs[MSForgeTriangleModule::AUDIO_OUTPUT]
                                          .getVoltage(voice);
                if (!finiteBits(sample) || std::fabs(sample) > 5.01f)
                    return 13;
            }
        }
    }
    return 0;
}
'''


class GeneratedTriangleTests(unittest.TestCase):
    def test_triangle_is_opt_in_and_preserves_default_sine(self):
        old = render_files("ForgeTriangle", "Forge Triangle")
        self.assertEqual(old, render_files("ForgeTriangle", "Forge Triangle",
                                           waveform="sine"))
        triangle = render_files("ForgeTriangle", "Forge Triangle", waveform="triangle")
        self.assertEqual(len(triangle), 4)
        source = triangle["ForgeTriangle.cpp"]
        self.assertIn("static float polyBlamp(float t, float dt)", source)
        self.assertIn("rawTriangle - 4.f * polyBlamp(t, dt)", source)
        self.assertIn("+ 4.f * polyBlamp(oppositeCorner, dt)", source)
        self.assertNotIn("std::sin(6.28318530718f * phase[voice])", source)
        self.assertIn("TRI OUT", triangle["ForgeTriangle.svg"])
        manifest = json.loads(triangle["ForgeTriangle.module.json"])
        self.assertEqual(manifest["tags"], ["Oscillator", "Polyphonic"])
        self.assertIn("polyBLAMP triangle", manifest["description"])
        self.assertIn("High-frequency amplitude rolls off", triangle["INTEGRATION.md"])

    def test_triangle_only_available_for_oscillator(self):
        with self.assertRaisesRegex(ValueError, "only supported"):
            render_files("StereoTriangle", "Stereo Triangle", kind="effect",
                         waveform="triangle")

    def test_triangle_integration_plan_is_read_only(self):
        with tempfile.TemporaryDirectory(prefix="module-forge-triangle-plan-") as tmp:
            folder = generate("ForgeTriangle", "Forge Triangle", Path(tmp),
                              waveform="triangle")
            self.assertEqual(check_module(folder), [])
            edits = integration_plan(folder, ROOT)
            self.assertEqual(len(edits), 6)
            self.assertFalse((ROOT / "plugins/ModularSynth/src/ForgeTriangle.cpp").exists())

    @unittest.skipUnless(shutil.which("c++"), "C++ compiler unavailable")
    def test_triangle_compiles_and_reduces_folded_odd_harmonics(self):
        with tempfile.TemporaryDirectory(prefix="module-forge-triangle-dsp-") as tmp:
            folder = generate("ForgeTriangle", "Forge Triangle", Path(tmp),
                              waveform="triangle")
            probe = Path(tmp) / "triangle_probe.cpp"
            probe.write_text(PROBE, encoding="utf-8")
            common = [
                shutil.which("c++"), "-O2", "-Wall", "-Wextra",
                "-Wpedantic", "-Werror", "-DHEADLESS",
                "-DpluginInstance=pluginInstance__ModularSynth",
                "-I", str(ROOT / "tests/rack_stub"),
                "-I", str(ROOT / "plugins/ModularSynth/src"),
                "-I", str(folder),
            ]
            modes = (
                ("cxx11_o2", ("-std=gnu++11",)),
                ("cxx11_strict_fast_math", ("-std=gnu++11", "-ffast-math")),
                ("cxx17_o2", ("-std=gnu++17",)),
                ("cxx17_production_fast_math", ("-std=gnu++17", "-ffast-math",
                                                 "-fno-finite-math-only")),
                ("cxx17_strict_fast_math", ("-std=gnu++17", "-ffast-math")),
            )
            for name, flags in modes:
                with self.subTest(mode=name):
                    syntax = subprocess.run(
                        [*common, *flags, "-fsyntax-only", str(folder / "ForgeTriangle.cpp")],
                        capture_output=True, text=True, timeout=90, check=False)
                    self.assertEqual(syntax.returncode, 0, syntax.stdout + syntax.stderr)
                    binary = Path(tmp) / f"triangle_{name}"
                    compiled = subprocess.run(
                        [*common, *flags, str(probe), "-o", str(binary)],
                        capture_output=True, text=True, timeout=90, check=False)
                    self.assertEqual(compiled.returncode, 0,
                                     compiled.stdout + compiled.stderr)
                    ran = subprocess.run(
                        [str(binary)], capture_output=True, text=True,
                        timeout=30, check=False)
                    self.assertEqual(ran.returncode, 0,
                                     f"{name}: {ran.stdout}{ran.stderr}")
                    self.assertLessEqual(float(ran.stdout.strip()), -8.0, name)


if __name__ == "__main__":
    unittest.main()
