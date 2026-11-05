"""Compile and quantify the opt-in polyBLEP saw generated Rack wrapper.

Uses the HEADLESS test shim, not the production Rack SDK or a DAW.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from integrate import integration_plan
from module_forge import check_module, generate


ROOT = Path(__file__).resolve().parents[2]
PROBE = r'''
#ifndef HEADLESS
#error "Generated saw test must use HEADLESS Rack shim"
#endif
#include "ForgeSaw.cpp"

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
    if (!modelMSForgeSaw)
        return 1;
    static_assert(MSForgeSawModule::NUM_PARAMS == 1, "pitch control");
    static_assert(MSForgeSawModule::NUM_INPUTS == 1, "pitch CV");
    static_assert(MSForgeSawModule::NUM_OUTPUTS == 1, "audio out");

    rack::ProcessArgs args{};
    args.sampleRate = 48000.0;
    args.sampleTime = 1.0 / 48000.0;
    MSForgeSawModule saw;
    MSForgeSawWidget widget(&saw);
    if (widget.module != &saw)
        return 2;

    // Exact coherent-bin target (about 9.28 kHz): there are two legitimate
    // in-band harmonics. The 3rd–9th fold back into otherwise empty bins.
    constexpr double fundamentalHz = fundamentalBin * 48000.0 / N;
    const float pitchOctaves =
        static_cast<float>(std::log2(fundamentalHz / 261.625565));
    saw.params[MSForgeSawModule::COARSE_PARAM].setValue(4.f);
    saw.inputs[MSForgeSawModule::PITCH_INPUT].setChannels(1);
    saw.inputs[MSForgeSawModule::PITCH_INPUT].setVoltage(pitchOctaves - 4.f, 0);

    std::array<float, N> corrected{};
    std::array<float, N> naive{};
    for (int i = 0; i < N; ++i) {
        saw.process(args);
        const float audio = saw.outputs[MSForgeSawModule::AUDIO_OUTPUT].getVoltage(0);
        if (!finiteBits(audio) || std::fabs(audio) > 5.01f)
            return 3;
        corrected[i] = audio / 5.f;
        // Same generated oscillator phase, without BLEP correction:
        // apples-to-apples alias comparison with no tuning drift.
        naive[i] = 2.f * saw.phase[0] - 1.f;
    }

    double correctedAlias = 0.0;
    double naiveAlias = 0.0;
    for (int harmonic = 3; harmonic <= 9; ++harmonic) {
        int bin = (harmonic * fundamentalBin) % N;
        if (bin > N / 2)
            bin = N - bin;
        correctedAlias += binPower(corrected, bin);
        naiveAlias += binPower(naive, bin);
    }
    if (!(naiveAlias > 1e-8) || !(correctedAlias > 0.0))
        return 4;
    const double reductionDb = 10.0 * std::log10(correctedAlias / naiveAlias);
    std::printf("%.4f\n", reductionDb);

    // Polyphony contraction must retain the existing sine-starter lifecycle.
    saw.params[MSForgeSawModule::COARSE_PARAM].setValue(0.f);
    saw.inputs[MSForgeSawModule::PITCH_INPUT].setChannels(2);
    saw.inputs[MSForgeSawModule::PITCH_INPUT].setVoltage(0.f, 0);
    saw.inputs[MSForgeSawModule::PITCH_INPUT].setVoltage(1.f, 1);
    saw.onReset();
    for (int i = 0; i < 128; ++i)
        saw.process(args);
    if (saw.outputs[MSForgeSawModule::AUDIO_OUTPUT].getChannels() != 2
        || saw.phase[1] == 0.f)
        return 5;
    saw.inputs[MSForgeSawModule::PITCH_INPUT].setChannels(1);
    saw.process(args);
    if (saw.phase[1] != 0.f || saw.activeChannels != 1)
        return 6;
    saw.inputs[MSForgeSawModule::PITCH_INPUT].setChannels(2);
    saw.inputs[MSForgeSawModule::PITCH_INPUT].setVoltage(1.f, 1);
    saw.process(args);
    if (!finiteBits(saw.outputs[MSForgeSawModule::AUDIO_OUTPUT].getVoltage(1))
        || saw.phase[1] < 0.f || saw.phase[1] >= 1.f)
        return 7;
    return 0;
}
'''


class GeneratedSawTests(unittest.TestCase):
    def test_generated_saw_integration_is_read_only(self):
        with tempfile.TemporaryDirectory(prefix="module-forge-saw-plan-") as tmp:
            saw = generate("ForgeSaw", "Forge Saw", Path(tmp), waveform="saw")
            self.assertEqual(check_module(saw), [])
            edits = integration_plan(saw, ROOT)
            self.assertEqual(len(edits), 6)
            self.assertFalse(
                (ROOT / "plugins/ModularSynth/src/ForgeSaw.cpp").exists())

    @unittest.skipUnless(shutil.which("c++"), "C++ compiler unavailable")
    def test_generated_saw_compiles_and_reduces_alias_bins(self):
        with tempfile.TemporaryDirectory(prefix="module-forge-saw-dsp-") as tmp:
            folder = generate("ForgeSaw", "Forge Saw", Path(tmp), waveform="saw")
            probe = Path(tmp) / "saw_probe.cpp"
            probe.write_text(PROBE, encoding="utf-8")
            common = [
                shutil.which("c++"), "-O2",
                "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                "-DHEADLESS",
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
                    checked = subprocess.run(
                        [*common, *flags, "-fsyntax-only",
                         str(folder / "ForgeSaw.cpp")],
                        capture_output=True, text=True, timeout=90, check=False)
                    self.assertEqual(checked.returncode, 0,
                                     checked.stdout + checked.stderr)
                    binary = Path(tmp) / f"saw_{name}"
                    compiled = subprocess.run(
                        [*common, *flags, str(probe), "-o", str(binary)],
                        capture_output=True, text=True, timeout=90, check=False)
                    self.assertEqual(compiled.returncode, 0,
                                     compiled.stdout + compiled.stderr)
                    executed = subprocess.run(
                        [str(binary)], capture_output=True, text=True,
                        timeout=30, check=False)
                    self.assertEqual(executed.returncode, 0,
                                     f"{name}: {executed.stdout}{executed.stderr}")
                    reduction_db = float(executed.stdout.strip())
                    self.assertLessEqual(reduction_db, -8.0, name)


if __name__ == "__main__":
    unittest.main()
