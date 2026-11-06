"""Compile actual generated Rack wrappers against the test-only HEADLESS shim.

This is NOT a Rack SDK, Cardinal plugin, GUI, ABI or DAW host build. The shim
exercises only a small source-level API and process-flow contract.
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
STUB = ROOT / "tests" / "rack_stub"
COLLECTION = ROOT / "plugins" / "ModularSynth" / "src"


PROBE = r'''
#ifndef HEADLESS
#error "Generated wrapper shim probe must be built HEADLESS"
#endif
#include "ForgeOrbit.cpp"
#include "ForgeStereoLP.cpp"

#include <cmath>
#include <cstdint>
#include <cstring>
#include <initializer_list>

static bool bitsFinite(float value) {
    std::uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return (bits & 0x7f800000u) != 0x7f800000u;
}

static float fromBits(std::uint32_t bits) {
    float value = 0.f;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

static bool near(float actual, float expected, float tolerance = 0.001f) {
    return bitsFinite(actual) && std::fabs(actual - expected) <= tolerance;
}

int main() {
    if (!modelMSForgeOrbit || !modelMSForgeStereoLP)
        return 1;
    static_assert(MSForgeOrbitModule::NUM_PARAMS == 1, "oscillator params");
    static_assert(MSForgeOrbitModule::NUM_INPUTS == 1, "oscillator inputs");
    static_assert(MSForgeOrbitModule::NUM_OUTPUTS == 1, "oscillator outputs");
    static_assert(MSForgeStereoLPModule::NUM_PARAMS == 1, "effect params");
    static_assert(MSForgeStereoLPModule::NUM_INPUTS == 3, "effect inputs");
    static_assert(MSForgeStereoLPModule::NUM_OUTPUTS == 2, "effect outputs");

    const float nan = fromBits(0x7fc00000u);
    const float plusInf = fromBits(0x7f800000u);
    const float minusInf = fromBits(0xff800000u);
    if (bitsFinite(nan) || bitsFinite(plusInf) || bitsFinite(minusInf))
        return 2;

    rack::ProcessArgs args{};
    args.sampleRate = 48000.0;
    args.sampleTime = 1.0 / 48000.0;
    MSForgeOrbitModule oscillator;
    MSForgeOrbitWidget oscillatorWidget(&oscillator);
    if (oscillatorWidget.module != &oscillator)
        return 3;
    oscillator.inputs[MSForgeOrbitModule::PITCH_INPUT].setChannels(2);
    oscillator.inputs[MSForgeOrbitModule::PITCH_INPUT].setVoltage(0.f, 0);
    oscillator.inputs[MSForgeOrbitModule::PITCH_INPUT].setVoltage(1.f, 1);
    oscillator.process(args);
    if (oscillator.outputs[MSForgeOrbitModule::AUDIO_OUTPUT].getChannels() != 2)
        return 4;
    const float sine0 = oscillator.outputs[MSForgeOrbitModule::AUDIO_OUTPUT].getVoltage(0);
    const float sine1 = oscillator.outputs[MSForgeOrbitModule::AUDIO_OUTPUT].getVoltage(1);
    constexpr float twoPi = 6.28318530718f;
    if (!near(sine0, 5.f * std::sin(twoPi * 261.625565f / 48000.f))
        || !near(sine1, 5.f * std::sin(twoPi * 523.25113f / 48000.f)))
        return 5;

    // Rack may send reset from a different thread. Neither the legacy nor
    // event overload may touch audio-owned phase until process() consumes
    // the atomic request. The first post-reset frame must restart at phase 0.
    const float phaseBeforeHostReset = oscillator.phase[0];
    oscillator.onReset(rack::ResetEvent{});
    if (!oscillator.pendingReset.load() || oscillator.phase[0] != phaseBeforeHostReset
        || oscillator.activeChannels != 2)
        return 22;
    oscillator.process(args);
    if (oscillator.pendingReset.load()
        || !near(oscillator.outputs[MSForgeOrbitModule::AUDIO_OUTPUT].getVoltage(0), sine0))
        return 23;

    // Nonfinite coarse/pitch CV must fall back to 0 octaves even with strict
    // -ffast-math; baseline reference uses independently reset phase.
    for (float bad : {nan, plusInf, minusInf}) {
        oscillator.onReset();
        oscillator.params[MSForgeOrbitModule::COARSE_PARAM].setValue(bad);
        oscillator.inputs[MSForgeOrbitModule::PITCH_INPUT].setVoltage(0.f, 0);
        oscillator.process(args);
        if (!near(oscillator.outputs[MSForgeOrbitModule::AUDIO_OUTPUT].getVoltage(0), sine0))
            return 6;
        oscillator.onReset();
        oscillator.params[MSForgeOrbitModule::COARSE_PARAM].setValue(0.f);
        oscillator.inputs[MSForgeOrbitModule::PITCH_INPUT].setVoltage(bad, 0);
        oscillator.process(args);
        if (!near(oscillator.outputs[MSForgeOrbitModule::AUDIO_OUTPUT].getVoltage(0), sine0))
            return 7;
    }
    oscillator.params[MSForgeOrbitModule::COARSE_PARAM].setValue(0.f);
    oscillator.inputs[MSForgeOrbitModule::PITCH_INPUT].setVoltage(0.f, 0);
    for (double badRate : {0.0, -1.0, static_cast<double>(nan),
                           static_cast<double>(plusInf), 1.0e30}) {
        oscillator.onReset();
        args.sampleRate = badRate;
        oscillator.process(args);
        if (!near(oscillator.outputs[MSForgeOrbitModule::AUDIO_OUTPUT].getVoltage(0), sine0))
            return 8;
    }

    // The second oscillator lane must restart at phase zero after a
    // two-voice -> one-voice -> two-voice transition.
    args.sampleRate = 48000.0;
    oscillator.onReset();
    oscillator.inputs[MSForgeOrbitModule::PITCH_INPUT].setChannels(2);
    oscillator.inputs[MSForgeOrbitModule::PITCH_INPUT].setVoltage(1.f, 1);
    for (int i = 0; i < 137; ++i)
        oscillator.process(args);
    if (oscillator.phase[1] == 0.f)
        return 16;
    oscillator.inputs[MSForgeOrbitModule::PITCH_INPUT].setChannels(1);
    oscillator.process(args);
    if (oscillator.phase[1] != 0.f || oscillator.activeChannels != 1)
        return 17;
    oscillator.inputs[MSForgeOrbitModule::PITCH_INPUT].setChannels(2);
    oscillator.inputs[MSForgeOrbitModule::PITCH_INPUT].setVoltage(1.f, 1);
    oscillator.process(args);
    if (!near(oscillator.outputs[MSForgeOrbitModule::AUDIO_OUTPUT].getVoltage(1), sine1))
        return 18;

    MSForgeStereoLPModule effect;
    MSForgeStereoLPWidget effectWidget(&effect);
    if (effectWidget.module != &effect)
        return 9;
    args.sampleRate = 48000.0;
    effect.inputs[MSForgeStereoLPModule::LEFT_INPUT].setChannels(2);
    effect.inputs[MSForgeStereoLPModule::LEFT_INPUT].setVoltage(5.f, 0);
    effect.inputs[MSForgeStereoLPModule::LEFT_INPUT].setVoltage(-5.f, 1);
    for (int i = 0; i < 256; ++i)
        effect.process(args);
    if (effect.outputs[MSForgeStereoLPModule::LEFT_OUTPUT].getChannels() != 2
        || effect.outputs[MSForgeStereoLPModule::RIGHT_OUTPUT].getChannels() != 2)
        return 10;
    for (int voice = 0; voice < 2; ++voice) {
        const float left = effect.outputs[MSForgeStereoLPModule::LEFT_OUTPUT].getVoltage(voice);
        const float right = effect.outputs[MSForgeStereoLPModule::RIGHT_OUTPUT].getVoltage(voice);
        if (!near(left, right, 0.00001f)
            || !near(left, voice == 0 ? 5.f : -5.f, 0.01f))
            return 11; // Unconnected right input normalled to left.
    }

    effect.inputs[MSForgeStereoLPModule::RIGHT_INPUT].setChannels(2);
    effect.inputs[MSForgeStereoLPModule::RIGHT_INPUT].setVoltage(-2.f, 0);
    effect.inputs[MSForgeStereoLPModule::RIGHT_INPUT].setVoltage(2.f, 1);
    effect.onReset();
    for (int i = 0; i < 256; ++i)
        effect.process(args);
    if (!near(effect.outputs[MSForgeStereoLPModule::RIGHT_OUTPUT].getVoltage(0), -2.f, 0.01f)
        || !near(effect.outputs[MSForgeStereoLPModule::RIGHT_OUTPUT].getVoltage(1), 2.f, 0.01f))
        return 12;

    effect.inputs[MSForgeStereoLPModule::CUTOFF_CV_INPUT].setChannels(3);
    effect.inputs[MSForgeStereoLPModule::CUTOFF_CV_INPUT].setVoltage(1.f, 0);
    effect.process(args);
    if (effect.outputs[MSForgeStereoLPModule::LEFT_OUTPUT].getChannels() != 3)
        return 13;
    const float stateBeforeHostReset = effect.leftFilter[0].state;
    effect.onReset();
    if (!effect.pendingReset.load() || effect.leftFilter[0].state != stateBeforeHostReset)
        return 14;
    effect.inputs[MSForgeStereoLPModule::LEFT_INPUT].setChannels(1);
    effect.inputs[MSForgeStereoLPModule::LEFT_INPUT].setVoltage(0.f, 0);
    effect.inputs[MSForgeStereoLPModule::RIGHT_INPUT].setChannels(1);
    effect.inputs[MSForgeStereoLPModule::RIGHT_INPUT].setVoltage(0.f, 0);
    effect.inputs[MSForgeStereoLPModule::CUTOFF_CV_INPUT].setChannels(1);
    effect.inputs[MSForgeStereoLPModule::CUTOFF_CV_INPUT].setVoltage(0.f, 0);
    effect.process(args);
    if (effect.pendingReset.load() || effect.activeChannels != 1)
        return 14;
    for (const auto& voice : effect.leftFilter)
        if (voice.state != 0.f)
            return 14;
    for (const auto& voice : effect.rightFilter)
        if (voice.state != 0.f)
            return 14;

    // The real generated wrapper and Rack-free effect core together must
    // reject nonfinite audio/CV and host rate without returning NaN/Inf.
    for (float bad : {nan, plusInf, minusInf}) {
        effect.onReset();
        effect.inputs[MSForgeStereoLPModule::LEFT_INPUT].setVoltage(bad, 0);
        effect.inputs[MSForgeStereoLPModule::CUTOFF_CV_INPUT].setVoltage(bad, 0);
        args.sampleRate = static_cast<double>(bad);
        effect.process(args);
        if (!bitsFinite(effect.outputs[MSForgeStereoLPModule::LEFT_OUTPUT].getVoltage(0))
            || !bitsFinite(effect.outputs[MSForgeStereoLPModule::RIGHT_OUTPUT].getVoltage(0)))
            return 15;
    }
    // Reusing a dropped effect lane must not revive stale filter memory.
    args.sampleRate = 48000.0;
    effect.onReset();
    effect.inputs[MSForgeStereoLPModule::LEFT_INPUT].setChannels(2);
    effect.inputs[MSForgeStereoLPModule::RIGHT_INPUT].setChannels(2);
    effect.inputs[MSForgeStereoLPModule::CUTOFF_CV_INPUT].setChannels(2);
    effect.inputs[MSForgeStereoLPModule::LEFT_INPUT].setVoltage(5.f, 1);
    effect.inputs[MSForgeStereoLPModule::RIGHT_INPUT].setVoltage(-5.f, 1);
    effect.inputs[MSForgeStereoLPModule::CUTOFF_CV_INPUT].setVoltage(0.f, 1);
    for (int i = 0; i < 64; ++i)
        effect.process(args);
    if (effect.leftFilter[1].state == 0.f || effect.rightFilter[1].state == 0.f)
        return 19;
    effect.inputs[MSForgeStereoLPModule::LEFT_INPUT].setChannels(1);
    effect.inputs[MSForgeStereoLPModule::RIGHT_INPUT].setChannels(1);
    effect.inputs[MSForgeStereoLPModule::CUTOFF_CV_INPUT].setChannels(1);
    effect.process(args);
    if (effect.leftFilter[1].state != 0.f || effect.rightFilter[1].state != 0.f
        || effect.activeChannels != 1)
        return 20;
    effect.inputs[MSForgeStereoLPModule::LEFT_INPUT].setChannels(2);
    effect.inputs[MSForgeStereoLPModule::RIGHT_INPUT].setChannels(2);
    effect.inputs[MSForgeStereoLPModule::CUTOFF_CV_INPUT].setChannels(2);
    effect.inputs[MSForgeStereoLPModule::LEFT_INPUT].setVoltage(0.f, 1);
    effect.inputs[MSForgeStereoLPModule::RIGHT_INPUT].setVoltage(0.f, 1);
    effect.process(args);
    if (!near(effect.outputs[MSForgeStereoLPModule::LEFT_OUTPUT].getVoltage(1), 0.f)
        || !near(effect.outputs[MSForgeStereoLPModule::RIGHT_OUTPUT].getVoltage(1), 0.f))
        return 21;
    return 0;
}
'''


class GeneratedWrapperTests(unittest.TestCase):
    def test_all_oscillator_waveforms_bound_implausible_host_sample_rates(self) -> None:
        for waveform in ("sine", "saw", "pulse", "pwm", "triangle"):
            with self.subTest(waveform=waveform):
                source = render_files("RateGuard", "Rate Guard",
                                      waveform=waveform)["RateGuard.cpp"]
                self.assertIn("requestedSampleRate <= 384000.f", source)

    @staticmethod
    def _generate_pair(destination: Path) -> tuple[Path, Path]:
        oscillator = generate("ForgeOrbit", "Forge Orbit", destination)
        effect = generate("ForgeStereoLP", "Forge Stereo LP", destination,
                          kind="effect")
        return oscillator, effect

    @unittest.skipUnless(shutil.which("c++"), "C++ compiler unavailable")
    def test_generated_wrappers_compile_and_process_with_headless_test_shim(self) -> None:
        with tempfile.TemporaryDirectory(prefix="module-forge-wrapper-test-") as temp:
            root = Path(temp)
            oscillator, effect = self._generate_pair(root)
            self.assertEqual(check_module(oscillator), [])
            self.assertEqual(check_module(effect), [])
            modes = (
                ("cxx11_o2", ("-std=gnu++11",)),
                ("cxx11_production_fast_math", ("-std=gnu++11", "-ffast-math",
                                                "-fno-finite-math-only")),
                ("cxx11_strict_fast_math", ("-std=gnu++11", "-ffast-math")),
                ("cxx17_o2", ("-std=gnu++17",)),
                ("cxx17_strict_fast_math", ("-std=gnu++17", "-ffast-math")),
            )
            common = [
                shutil.which("c++"), "-O2", "-Wall", "-Wextra",
                "-Wpedantic", "-Werror", "-DHEADLESS",
                "-DpluginInstance=pluginInstance__ModularSynth",
                "-I", str(STUB), "-I", str(COLLECTION),
                "-I", str(oscillator), "-I", str(effect),
            ]
            for label, flags in modes:
                with self.subTest(mode=label):
                    for folder, slug in ((oscillator, "ForgeOrbit"),
                                         (effect, "ForgeStereoLP")):
                        checked = subprocess.run(
                            [*common, *flags, "-fsyntax-only",
                             str(folder / f"{slug}.cpp")],
                            capture_output=True, text=True, timeout=90,
                            check=False)
                        self.assertEqual(checked.returncode, 0,
                                         checked.stdout + checked.stderr)

                    probe = root / "wrapper_probe.cpp"
                    probe.write_text(PROBE, encoding="utf-8")
                    binary = root / f"wrapper_probe_{label}"
                    compiled = subprocess.run(
                        [*common, *flags, str(probe), "-o", str(binary)],
                        capture_output=True, text=True, timeout=90,
                        check=False)
                    self.assertEqual(compiled.returncode, 0,
                                     compiled.stdout + compiled.stderr)
                    completed = subprocess.run(
                        [str(binary)], capture_output=True, text=True,
                        timeout=30, check=False)
                    self.assertEqual(completed.returncode, 0,
                                     f"{label} exit {completed.returncode}: "
                                     + completed.stdout + completed.stderr)

    def test_generated_modules_plan_exact_static_collection_integration(self) -> None:
        with tempfile.TemporaryDirectory(prefix="module-forge-plan-test-") as temp:
            oscillator, effect = self._generate_pair(Path(temp))
            for folder, slug, files in (
                (oscillator, "ForgeOrbit", 6),
                (effect, "ForgeStereoLP", 7),
            ):
                with self.subTest(slug=slug):
                    edits = integration_plan(folder, ROOT)  # Dry-run only.
                    self.assertEqual(len(edits), files)
                    planned = {
                        edit.path.relative_to(ROOT).as_posix(): edit
                        for edit in edits
                    }
                    manifest_file = "plugins/ModularSynth/plugin.json"
                    self.assertIn(manifest_file, planned)
                    before = json.loads(planned[manifest_file].before)
                    after = json.loads(planned[manifest_file].after)
                    fragment = json.loads(
                        (folder / f"{slug}.module.json").read_text())
                    self.assertEqual(after["slug"], "ModularSynth")
                    self.assertEqual(after["modules"][:-1], before["modules"])
                    self.assertEqual(after["modules"][-1], fragment)
                    self.assertEqual(
                        sum(item["slug"] == slug for item in after["modules"]), 1)

                    symbol = f"modelMS{slug}"
                    header = planned["plugins/ModularSynth/src/plugin.hpp"].after.decode()
                    loader = planned["plugins/plugins.cpp"].after.decode()
                    makefile = planned["plugins/Makefile"].after.decode()
                    self.assertEqual(header.count(f"extern Model* {symbol};"), 1)
                    self.assertEqual(loader.count(f"p->addModel({symbol});"), 1)
                    self.assertEqual(
                        makefile.count(f"PLUGIN_FILES += ModularSynth/src/{slug}.cpp"), 1)
                    self.assertIn("-DpluginInstance=pluginInstance__ModularSynth",
                                  makefile)
                    self.assertIn(f"plugins/ModularSynth/src/{slug}.cpp", planned)
                    self.assertIn(f"plugins/ModularSynth/res/{slug}.svg", planned)
                    if slug == "ForgeStereoLP":
                        self.assertIn(
                            f"plugins/ModularSynth/src/{slug}.dsp.hpp", planned)
                    self.assertNotIn("plugins/plugins-mini.cpp", planned)


if __name__ == "__main__":
    unittest.main()
