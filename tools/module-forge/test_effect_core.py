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
#include <cstdint>
#include <cstring>
#include <initializer_list>

using Filter = moduleforge::MSStereoTPTOnePole;

// Never use std::isfinite in this test: strict -ffast-math may fold it to true.
bool bitsFinite(float value) {
    std::uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return (bits & 0x7f800000u) != 0x7f800000u;
}

float fromBits(std::uint32_t bits) {
    float value = 0.f;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

int main() {
    const float nan = fromBits(0x7fc00000u);
    const float plusInf = fromBits(0x7f800000u);
    const float minusInf = fromBits(0xff800000u);
    if (bitsFinite(nan) || bitsFinite(plusInf) || bitsFinite(minusInf))
        return 1; // Ensure test inputs themselves remain IEEE nonfinite.
    if (Filter::finite(nan) || Filter::finite(plusInf)
        || Filter::finite(minusInf) || !Filter::finite(1000.f))
        return 2;

    for (float sampleRate : {44100.f, 48000.f, 96000.f}) {
        const float coefficient = Filter::coefficient(1000.f, sampleRate);
        if (!bitsFinite(coefficient)
            || !(coefficient > 0.f && coefficient < 1.f))
            return 3;
        Filter left;
        Filter right;
        for (int i = 0; i < 4096; ++i) {
            const float a = left.process(5.f, coefficient);
            const float b = right.process(-5.f, coefficient);
            if (!bitsFinite(a) || !bitsFinite(b))
                return 4;
        }
        if (std::fabs(left.state - 5.f) > 0.001f
            || std::fabs(right.state + 5.f) > 0.001f)
            return 5;

        left.reset();
        right.reset();
        if (left.state != 0.f || right.state != 0.f)
            return 6;
        for (float bad : {nan, plusInf, minusInf}) {
            if (!bitsFinite(left.process(bad, coefficient)))
                return 7;
        }
    }

    const float reference = Filter::coefficient(1000.f, 48000.f);
    for (float bad : {nan, plusInf, minusInf}) {
        const float invalidCutoff = Filter::coefficient(bad, 48000.f);
        const float invalidRate = Filter::coefficient(1000.f, bad);
        if (!bitsFinite(invalidCutoff) || !bitsFinite(invalidRate))
            return 8;
        if (std::fabs(invalidCutoff - reference) > 0.000001f
            || std::fabs(invalidRate - reference) > 0.000001f)
            return 9;
    }
    const float invalidBoth = Filter::coefficient(nan, plusInf);
    if (!bitsFinite(invalidBoth)
        || std::fabs(invalidBoth - reference) > 0.000001f)
        return 10;

    Filter invalidProcess;
    const float c = Filter::coefficient(1200.f, 48000.f);
    for (float bad : {nan, plusInf, minusInf}) {
        invalidProcess.reset();
        const float nonfiniteAudio = invalidProcess.process(bad, c);
        if (!bitsFinite(nonfiniteAudio) || nonfiniteAudio != 0.f)
            return 11;
        invalidProcess.reset();
        const float nonfiniteCoefficient = invalidProcess.process(5.f, bad);
        if (!bitsFinite(nonfiniteCoefficient) || nonfiniteCoefficient != 0.f)
            return 12;
    }

    const float veryHigh = Filter::coefficient(1e30f, 48000.f);
    const float veryLow = Filter::coefficient(-1e30f, 48000.f);
    if (!bitsFinite(veryHigh) || !bitsFinite(veryLow)
        || !(veryHigh > 0.f && veryHigh < 1.f)
        || !(veryLow > 0.f && veryLow < 1.f))
        return 13;

    Filter impulse;
    float previous = impulse.process(5.f, c);
    for (int i = 0; i < 2048; ++i) {
        const float y = impulse.process(0.f, c);
        if (!bitsFinite(y) || std::fabs(y) > 5.f)
            return 14;
        previous = y;
    }
    if (!bitsFinite(previous) || std::fabs(previous) > 0.01f)
        return 15;
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
            modes = (
                ("o2", ()),
                ("production_fast_math",
                 ("-ffast-math", "-fno-finite-math-only")),
                ("strict_fast_math", ("-ffast-math",)),
            )
            for label, flags in modes:
                with self.subTest(mode=label):
                    binary = root / f"effect_core_{label}"
                    compile_result = subprocess.run(
                        [compiler, "-std=c++17", "-O2", *flags,
                         "-Wall", "-Wextra", "-Werror", "-pedantic",
                         str(probe), "-o", str(binary)],
                        capture_output=True, text=True, timeout=60, check=False)
                    self.assertEqual(
                        compile_result.returncode, 0,
                        compile_result.stdout + compile_result.stderr)
                    run = subprocess.run(
                        [str(binary)], capture_output=True, text=True,
                        timeout=10, check=False)
                    self.assertEqual(
                        run.returncode, 0,
                        f"{label}: {run.stdout}{run.stderr}, exit {run.returncode}")


if __name__ == "__main__":
    unittest.main()
