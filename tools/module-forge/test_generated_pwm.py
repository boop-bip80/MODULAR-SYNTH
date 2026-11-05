"""Exercise an actual generated polyBLEP PWM starter, not handwritten DSP.

Generated C++ executes against the HEADLESS test Rack shim in C++11/C++17
and regular/fast-math builds. This is not real-Rack ABI or host-audio proof.
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
#error "The PWM probe requires the HEADLESS test Rack shim"
#endif
#include "ForgePWM.cpp"
#include "ForgePulse.cpp"

#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

constexpr int N = 8192;
constexpr int FundamentalBin = 1583;

static bool finiteBits(float value) {
    std::uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return (bits & 0x7f800000u) != 0x7f800000u;
}

static double binPower(const std::array<float, N>& values, int bin) {
    constexpr double twoPi = 6.28318530717958647692;
    double real = 0.0, imag = 0.0;
    for (int i = 0; i < N; ++i) {
        const double angle = twoPi * static_cast<double>(bin) * i / N;
        real += values[i] * std::cos(angle);
        imag += values[i] * std::sin(angle);
    }
    return (real * real + imag * imag) / (static_cast<double>(N) * N);
}

int main() {
    static_assert(MSForgePWMModule::NUM_PARAMS == 2, "coarse and pulse width");
    static_assert(MSForgePWMModule::NUM_INPUTS == 2, "pitch and width CV");
    static_assert(MSForgePWMModule::NUM_OUTPUTS == 1, "PWM audio output");
    if (!modelMSForgePWM || !modelMSForgePulse)
        return 1;

    rack::ProcessArgs args{};
    args.sampleRate = 48000.0;
    args.sampleTime = 1.0 / 48000.0;
    MSForgePWMModule pwm;
    MSForgePulseModule pulse;
    MSForgePWMWidget widget(&pwm);
    if (widget.module != &pwm)
        return 2;

    // New default 50% PWM is numerically equivalent to the legacy
    // fixed-width pulse, including phase lifecycle and both BLEP edges.
    // Strict fast-math may reassociate the fractional-edge calculation.
    pwm.inputs[MSForgePWMModule::PITCH_INPUT].setChannels(1);
    pulse.inputs[MSForgePulseModule::PITCH_INPUT].setChannels(1);
    float maxDefaultDifference = 0.f;
    for (int i = 0; i < 4096; ++i) {
        pwm.process(args);
        pulse.process(args);
        maxDefaultDifference = std::max(maxDefaultDifference,
            std::fabs(pwm.outputs[MSForgePWMModule::AUDIO_OUTPUT].getVoltage(0)
                      - pulse.outputs[MSForgePulseModule::AUDIO_OUTPUT].getVoltage(0)));
    }
    if (maxDefaultDifference > 2e-4f) {
        std::fprintf(stderr, "default pulse mismatch max=%.9f\n", maxDefaultDifference);
        return 3;
    }

    // PWM produces the expected unequal-duty pulse's mean/DC component.
    for (float duty : {0.25f, 0.75f}) {
        pwm.onReset();
        pwm.params[MSForgePWMModule::WIDTH_PARAM].setValue(duty);
        double average = 0.0;
        for (int i = 0; i < N; ++i) {
            pwm.process(args);
            const float sample = pwm.outputs[MSForgePWMModule::AUDIO_OUTPUT].getVoltage(0);
            if (!finiteBits(sample) || std::fabs(sample) > 5.02f)
                return 4;
            average += sample / 5.0;
        }
        average /= N;
        if (std::fabs(average - (2.0 * duty - 1.0)) > 0.035)
            return 5;
    }

    // Polyphonic 2.5 V width CV adds 25 percentage points: 25% -> 50%.
    pwm.onReset();
    pulse.onReset();
    pwm.params[MSForgePWMModule::WIDTH_PARAM].setValue(0.25f);
    pwm.inputs[MSForgePWMModule::WIDTH_CV_INPUT].setChannels(1);
    pwm.inputs[MSForgePWMModule::WIDTH_CV_INPUT].setVoltage(2.5f, 0);
    float maxCVEquivalentDifference = 0.f;
    for (int i = 0; i < 4096; ++i) {
        pwm.process(args);
        pulse.process(args);
        maxCVEquivalentDifference = std::max(maxCVEquivalentDifference,
            std::fabs(pwm.outputs[MSForgePWMModule::AUDIO_OUTPUT].getVoltage(0)
                      - pulse.outputs[MSForgePulseModule::AUDIO_OUTPUT].getVoltage(0)));
    }
    if (maxCVEquivalentDifference > 2e-4f) {
        std::fprintf(stderr, "CV pulse mismatch max=%.9f\n", maxCVEquivalentDifference);
        return 6;
    }

    // Match a naive pulse's exact generated phase and width, then measure
    // aliased harmonics that fold above the 48 kHz Nyquist boundary.
    constexpr double fundamentalHz = FundamentalBin * 48000.0 / N;
    const float pitchOctaves =
        static_cast<float>(std::log2(fundamentalHz / 261.625565));
    pwm.onReset();
    pwm.params[MSForgePWMModule::COARSE_PARAM].setValue(4.f);
    pwm.params[MSForgePWMModule::WIDTH_PARAM].setValue(0.25f);
    pwm.inputs[MSForgePWMModule::WIDTH_CV_INPUT].setChannels(0);
    pwm.inputs[MSForgePWMModule::PITCH_INPUT].setVoltage(pitchOctaves - 4.f, 0);
    std::array<float, N> corrected{};
    std::array<float, N> naive{};
    for (int i = 0; i < N; ++i) {
        pwm.process(args);
        corrected[i] = pwm.outputs[MSForgePWMModule::AUDIO_OUTPUT].getVoltage(0) / 5.f;
        naive[i] = pwm.phase[0] < 0.25f ? 1.f : -1.f;
    }
    double correctedAlias = 0.0, naiveAlias = 0.0;
    for (int harmonic : {3, 5, 6, 7}) {
        int bin = (harmonic * FundamentalBin) % N;
        if (bin > N / 2)
            bin = N - bin;
        correctedAlias += binPower(corrected, bin);
        naiveAlias += binPower(naive, bin);
    }
    if (!(naiveAlias > 1e-8) || !(correctedAlias > 0.0))
        return 7;
    const double aliasReductionDb = 10.0 * std::log10(correctedAlias / naiveAlias);
    std::printf("%.3f\n", aliasReductionDb);
    if (!(aliasReductionDb < -6.0))
        return 8;

    // Width CV is per voice; dropped pitch lanes must retire their phase.
    pwm.onReset();
    pwm.params[MSForgePWMModule::COARSE_PARAM].setValue(0.f);
    pwm.params[MSForgePWMModule::WIDTH_PARAM].setValue(0.5f);
    pwm.inputs[MSForgePWMModule::PITCH_INPUT].setChannels(2);
    pwm.inputs[MSForgePWMModule::PITCH_INPUT].setVoltage(0.f, 0);
    pwm.inputs[MSForgePWMModule::PITCH_INPUT].setVoltage(1.f, 1);
    pwm.inputs[MSForgePWMModule::WIDTH_CV_INPUT].setChannels(2);
    pwm.inputs[MSForgePWMModule::WIDTH_CV_INPUT].setVoltage(-2.f, 0);
    pwm.inputs[MSForgePWMModule::WIDTH_CV_INPUT].setVoltage(2.f, 1);
    for (int i = 0; i < 128; ++i)
        pwm.process(args);
    if (pwm.outputs[MSForgePWMModule::AUDIO_OUTPUT].getChannels() != 2
        || pwm.phase[1] == 0.f)
        return 9;
    pwm.inputs[MSForgePWMModule::PITCH_INPUT].setChannels(1);
    pwm.process(args);
    if (pwm.phase[1] != 0.f || pwm.activeChannels != 1)
        return 10;

    // Under strict -ffast-math, bitwise guards still reject NaN/Inf CV,
    // and clamp extreme but finite CV to a playable width.
    std::uint32_t nanBits = 0x7fc00000u;
    float nanCV = 0.f;
    std::memcpy(&nanCV, &nanBits, sizeof(nanCV));
    pwm.inputs[MSForgePWMModule::WIDTH_CV_INPUT].setVoltage(nanCV, 0);
    args.sampleRate = 0.0;
    pwm.process(args);
    if (!finiteBits(pwm.outputs[MSForgePWMModule::AUDIO_OUTPUT].getVoltage(0)))
        return 11;
    args.sampleRate = 48000.0;
    for (float cv : {-1e20f, 1e20f}) {
        pwm.inputs[MSForgePWMModule::WIDTH_CV_INPUT].setVoltage(cv, 0);
        for (int i = 0; i < 256; ++i) {
            pwm.process(args);
            const float value = pwm.outputs[MSForgePWMModule::AUDIO_OUTPUT].getVoltage(0);
            if (!finiteBits(value) || std::fabs(value) > 5.02f)
                return 12;
        }
    }
    return 0;
}
'''


class GeneratedPWMTests(unittest.TestCase):
    def test_pwm_is_opt_in_and_preserves_existing_waveforms(self) -> None:
        sine = render_files("ForgePWM", "Forge PWM")
        pulse = render_files("ForgePWM", "Forge PWM", waveform="pulse")
        pwm = render_files("ForgePWM", "Forge PWM", waveform="pwm")
        self.assertEqual(sine, render_files("ForgePWM", "Forge PWM", waveform="sine"))
        self.assertEqual(len(sine), len(pulse))
        self.assertEqual(len(pwm), 4)
        source = pwm["ForgePWM.cpp"]
        self.assertIn("enum ParamIds { COARSE_PARAM, WIDTH_PARAM, NUM_PARAMS };", source)
        self.assertIn("enum InputIds { PITCH_INPUT, WIDTH_CV_INPUT, NUM_INPUTS };", source)
        self.assertIn("polyBlep(oppositeEdge, dt)", source)
        self.assertIn("std::max(0.05f, std::min(0.95f, width))", source)
        self.assertIn("mm2px(Vec(36.8f, 36.f))", source)
        self.assertIn("mm2px(Vec(36.8f, 70.f))", source)
        self.assertIn("WIDTH", pwm["ForgePWM.svg"])
        self.assertIn("PW CV", pwm["ForgePWM.svg"])
        self.assertIn("PWM OUT", pwm["ForgePWM.svg"])
        self.assertNotIn("WIDTH_PARAM", pulse["ForgePWM.cpp"])
        self.assertIn("polyBLEP PWM", json.loads(pwm["ForgePWM.module.json"])["description"])
        self.assertIn("duty-dependent DC", pwm["INTEGRATION.md"])

    def test_pwm_rejects_effect_without_creating_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "only supported"):
                generate("StereoPWM", "Stereo PWM", Path(tmp), kind="effect", waveform="pwm")
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_pwm_integration_is_reviewed_and_nonmutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            generated = generate("ForgePWM", "Forge PWM", Path(tmp), waveform="pwm")
            self.assertEqual(check_module(generated), [])
            changes = integration_plan(generated, ROOT)
            self.assertEqual(len(changes), 6)
            self.assertFalse((ROOT / "plugins/ModularSynth/src/ForgePWM.cpp").exists())

    @unittest.skipUnless(shutil.which("c++"), "C++ compiler unavailable")
    def test_compiled_pwm_alias_and_cv_contract_across_modes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="module-forge-pwm-dsp-") as tmp:
            output = Path(tmp)
            pwm = generate("ForgePWM", "Forge PWM", output, waveform="pwm")
            pulse = generate("ForgePulse", "Forge Pulse", output, waveform="pulse")
            probe = output / "pwm_probe.cpp"
            probe.write_text(PROBE, encoding="utf-8")
            common = [
                shutil.which("c++"), "-O2", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                "-DHEADLESS", "-DpluginInstance=pluginInstance__ModularSynth",
                "-I", str(ROOT / "tests/rack_stub"),
                "-I", str(ROOT / "plugins/ModularSynth/src"),
                "-I", str(pwm), "-I", str(pulse),
            ]
            for mode, flags in (
                ("cxx11_o2", ("-std=gnu++11",)),
                ("cxx11_fast_math", ("-std=gnu++11", "-ffast-math")),
                ("cxx17_o2", ("-std=gnu++17",)),
                ("cxx17_fast_math", ("-std=gnu++17", "-ffast-math")),
                ("cxx17_safe_fast_math", ("-std=gnu++17", "-ffast-math", "-fno-finite-math-only")),
            ):
                with self.subTest(mode=mode):
                    syntax = subprocess.run(
                        [*common, *flags, "-fsyntax-only", str(pwm / "ForgePWM.cpp")],
                        text=True, capture_output=True, check=False, timeout=90,
                    )
                    self.assertEqual(syntax.returncode, 0, syntax.stdout + syntax.stderr)
                    executable = output / f"pwm_{mode}"
                    built = subprocess.run(
                        [*common, *flags, str(probe), "-o", str(executable)],
                        text=True, capture_output=True, check=False, timeout=90,
                    )
                    self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
                    ran = subprocess.run(
                        [str(executable)], text=True, capture_output=True,
                        check=False, timeout=30,
                    )
                    self.assertEqual(ran.returncode, 0,
                                     f"{mode}: {ran.stdout} {ran.stderr}")
                    self.assertLess(float(ran.stdout.strip()), -6.0)


if __name__ == "__main__":
    unittest.main()
