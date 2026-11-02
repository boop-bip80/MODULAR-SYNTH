"""Compile and measure the opt-in fixed-duty polyBLEP pulse starter.

This exercises generated C++ against the HEADLESS test Rack shim, not a host.
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
#error "The generated pulse test requires the HEADLESS Rack shim"
#endif
#include "ForgePulse.cpp"

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
    double imag = 0.0;
    for (int i = 0; i < N; ++i) {
        const double angle = twoPi * static_cast<double>(bin) * i / N;
        real += values[i] * std::cos(angle);
        imag += values[i] * std::sin(angle);
    }
    return (real * real + imag * imag) / (static_cast<double>(N) * N);
}

int main() {
    if (!modelMSForgePulse)
        return 1;
    static_assert(MSForgePulseModule::NUM_PARAMS == 1, "coarse pitch");
    static_assert(MSForgePulseModule::NUM_INPUTS == 1, "pitch CV");
    static_assert(MSForgePulseModule::NUM_OUTPUTS == 1, "pulse output");

    rack::ProcessArgs args{};
    args.sampleRate = 48000.0;
    args.sampleTime = 1.0 / 48000.0;
    MSForgePulseModule pulse;
    MSForgePulseWidget widget(&pulse);
    if (widget.module != &pulse)
        return 2;

    // Coherent fundamental at ~9.28kHz: only the fundamental of a pulse
    // belongs below Nyquist; odd harmonics 3/5/7/9 fold into the passband.
    constexpr double fundamentalHz = fundamentalBin * 48000.0 / N;
    const float pitchOctaves =
        static_cast<float>(std::log2(fundamentalHz / 261.625565));
    pulse.params[MSForgePulseModule::COARSE_PARAM].setValue(4.f);
    pulse.inputs[MSForgePulseModule::PITCH_INPUT].setChannels(1);
    pulse.inputs[MSForgePulseModule::PITCH_INPUT].setVoltage(pitchOctaves - 4.f, 0);

    std::array<float, N> corrected{};
    std::array<float, N> naive{};
    for (int i = 0; i < N; ++i) {
        pulse.process(args);
        const float sample = pulse.outputs[MSForgePulseModule::AUDIO_OUTPUT].getVoltage(0);
        if (!finiteBits(sample) || std::fabs(sample) > 5.02f)
            return 3;
        corrected[i] = sample / 5.f;
        // Same exact generated phase, without either BLEP edge correction.
        naive[i] = pulse.phase[0] < 0.5f ? 1.f : -1.f;
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

    pulse.params[MSForgePulseModule::COARSE_PARAM].setValue(0.f);
    pulse.inputs[MSForgePulseModule::PITCH_INPUT].setChannels(2);
    pulse.inputs[MSForgePulseModule::PITCH_INPUT].setVoltage(0.f, 0);
    pulse.inputs[MSForgePulseModule::PITCH_INPUT].setVoltage(1.f, 1);
    pulse.onReset();
    for (int i = 0; i < 128; ++i)
        pulse.process(args);
    if (pulse.outputs[MSForgePulseModule::AUDIO_OUTPUT].getChannels() != 2
        || pulse.phase[1] == 0.f)
        return 5;
    pulse.inputs[MSForgePulseModule::PITCH_INPUT].setChannels(1);
    pulse.process(args);
    if (pulse.phase[1] != 0.f || pulse.activeChannels != 1)
        return 6;
    pulse.inputs[MSForgePulseModule::PITCH_INPUT].setChannels(2);
    pulse.process(args);
    if (!finiteBits(pulse.outputs[MSForgePulseModule::AUDIO_OUTPUT].getVoltage(1))
        || pulse.phase[1] < 0.f || pulse.phase[1] >= 1.f)
        return 7;

    // Invalid host sample-rate and nonfinite CV must remain finite even when
    // compiled under aggressive -ffast-math.
    std::uint32_t nanBits = 0x7fc00000u;
    float nanPitch = 0.f;
    std::memcpy(&nanPitch, &nanBits, sizeof(nanBits));
    pulse.inputs[MSForgePulseModule::PITCH_INPUT].setVoltage(nanPitch, 0);
    args.sampleRate = 0.0;
    pulse.process(args);
    if (!finiteBits(pulse.outputs[MSForgePulseModule::AUDIO_OUTPUT].getVoltage(0)))
        return 8;
    return 0;
}
'''


class GeneratedPulseTests(unittest.TestCase):
    def test_pulse_is_opt_in_and_default_sine_is_unchanged(self):
        old = render_files("ForgePulse", "Forge Pulse")
        self.assertEqual(old, render_files("ForgePulse", "Forge Pulse", waveform="sine"))
        pulse = render_files("ForgePulse", "Forge Pulse", waveform="pulse")
        self.assertEqual(len(pulse), 4)
        source = pulse["ForgePulse.cpp"]
        self.assertIn("rawPulse + polyBlep(t, dt)", source)
        self.assertIn("- polyBlep(oppositeEdge, dt)", source)
        self.assertNotIn("std::sin(6.28318530718f * phase[voice])", source)
        self.assertIn("PULSE OUT", pulse["ForgePulse.svg"])
        manifest = json.loads(pulse["ForgePulse.module.json"])
        self.assertEqual(manifest["tags"], ["Oscillator", "Polyphonic"])
        self.assertIn("polyBLEP pulse", manifest["description"])
        self.assertIn("Both edges are corrected", pulse["INTEGRATION.md"])

    def test_pulse_only_available_for_oscillator(self):
        with self.assertRaisesRegex(ValueError, "only supported"):
            render_files("StereoPulse", "Stereo Pulse", kind="effect", waveform="pulse")

    def test_generated_pulse_integration_dry_run_is_read_only(self):
        with tempfile.TemporaryDirectory(prefix="module-forge-pulse-plan-") as tmp:
            pulse = generate("ForgePulse", "Forge Pulse", Path(tmp), waveform="pulse")
            self.assertEqual(check_module(pulse), [])
            edits = integration_plan(pulse, ROOT)
            self.assertEqual(len(edits), 6)
            self.assertFalse((ROOT / "plugins/ModularSynth/src/ForgePulse.cpp").exists())

    @unittest.skipUnless(shutil.which("c++"), "C++17 compiler unavailable")
    def test_pulse_compiles_and_reduces_folded_odd_harmonics(self):
        with tempfile.TemporaryDirectory(prefix="module-forge-pulse-dsp-") as tmp:
            folder = generate("ForgePulse", "Forge Pulse", Path(tmp), waveform="pulse")
            probe = Path(tmp) / "pulse_probe.cpp"
            probe.write_text(PROBE, encoding="utf-8")
            common = [
                shutil.which("c++"), "-std=c++17", "-O2",
                "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                "-DHEADLESS",
                "-DpluginInstance=pluginInstance__ModularSynth",
                "-I", str(ROOT / "tests/rack_stub"),
                "-I", str(ROOT / "plugins/ModularSynth/src"),
                "-I", str(folder),
            ]
            modes = (
                ("o2", ()),
                ("production_fast_math", ("-ffast-math", "-fno-finite-math-only")),
                ("strict_fast_math", ("-ffast-math",)),
            )
            for mode, flags in modes:
                with self.subTest(mode=mode):
                    syntax = subprocess.run(
                        [*common, *flags, "-fsyntax-only", str(folder / "ForgePulse.cpp")],
                        capture_output=True, text=True, timeout=90, check=False)
                    self.assertEqual(syntax.returncode, 0,
                                     syntax.stdout + syntax.stderr)
                    executable = Path(tmp) / f"pulse_{mode}"
                    compiled = subprocess.run(
                        [*common, *flags, str(probe), "-o", str(executable)],
                        capture_output=True, text=True, timeout=90, check=False)
                    self.assertEqual(compiled.returncode, 0,
                                     compiled.stdout + compiled.stderr)
                    ran = subprocess.run(
                        [str(executable)], capture_output=True, text=True,
                        timeout=30, check=False)
                    self.assertEqual(ran.returncode, 0,
                                     f"{mode}: {ran.stdout}{ran.stderr}")
                    self.assertLessEqual(float(ran.stdout.strip()), -8.0, mode)


if __name__ == "__main__":
    unittest.main()
