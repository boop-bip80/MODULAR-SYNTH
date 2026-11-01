"""Standalone C++17 numerical contract tests for Module Forge effect DSP."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from module_forge import render_files


PROBE = r'''
#include "StereoTPT.dsp.hpp"

#include <cmath>
#include <initializer_list>
#include <limits>

using Filter = moduleforge::MSStereoTPTOnePole;

int main() {
    for (float sampleRate : {44100.f, 48000.f, 96000.f}) {
        const float coefficient = Filter::coefficient(1000.f, sampleRate);
        if (!(coefficient > 0.f && coefficient < 1.f))
            return 1;
        Filter left;
        Filter right;
        for (int i = 0; i < 4096; ++i) {
            const float a = left.process(5.f, coefficient);
            const float b = right.process(-5.f, coefficient);
            if (!std::isfinite(a) || !std::isfinite(b))
                return 2;
        }
        if (std::fabs(left.state - 5.f) > 0.001f
            || std::fabs(right.state + 5.f) > 0.001f)
            return 3;

        left.reset();
        right.reset();
        if (left.state != 0.f || right.state != 0.f)
            return 4;
        if (!std::isfinite(left.process(
                std::numeric_limits<float>::quiet_NaN(), coefficient)))
            return 5;
    }

    const float invalidRate = Filter::coefficient(
        std::numeric_limits<float>::infinity(),
        std::numeric_limits<float>::quiet_NaN());
    if (!(invalidRate > 0.f && invalidRate < 1.f))
        return 6;
    const float veryHigh = Filter::coefficient(1e30f, 48000.f);
    const float veryLow = Filter::coefficient(-1e30f, 48000.f);
    if (!(veryHigh > 0.f && veryHigh < 1.f
          && veryLow > 0.f && veryLow < 1.f))
        return 7;

    Filter impulse;
    const float c = Filter::coefficient(1200.f, 48000.f);
    float previous = impulse.process(5.f, c);
    for (int i = 0; i < 2048; ++i) {
        const float y = impulse.process(0.f, c);
        if (!std::isfinite(y) || std::fabs(y) > 5.f)
            return 8;
        previous = y;
    }
    if (!std::isfinite(previous) || std::fabs(previous) > 0.01f)
        return 9;
    return 0;
}
'''


class EffectCoreTests(unittest.TestCase):
    def test_generated_standalone_core_compiles_and_handles_audio(self):
        compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            self.skipTest("C++17 compiler not available")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            header = root / "StereoTPT.dsp.hpp"
            header.write_text(
                render_files("StereoTPT", "Stereo TPT", kind="effect")[
                    "StereoTPT.dsp.hpp"
                ], encoding="utf-8")
            probe = root / "probe.cpp"
            probe.write_text(PROBE, encoding="utf-8")
            binary = root / "effect_core_test"
            compile_result = subprocess.run(
                [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                 "-pedantic", str(probe), "-o", str(binary)],
                capture_output=True, text=True, timeout=60, check=False)
            self.assertEqual(compile_result.returncode, 0,
                             compile_result.stdout + compile_result.stderr)
            run = subprocess.run(
                [str(binary)], capture_output=True, text=True,
                timeout=10, check=False)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
