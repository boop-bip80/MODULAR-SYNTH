"""Regression for Cardinal's GNU C++11 first-party plugin build contract.

The standalone DSP runner uses C++17, but Cardinal's Makefile compiles
ModularSynth wrappers with -std=gnu++11.  Both paths must remain valid.
This stub smoke does not claim real Rack headers or host-loadable plugins.
"""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FMVoiceCpp11Tests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++"), "C++ compiler unavailable")
    def test_dsp_and_real_wrapper_compile_in_cardinal_cpp11_mode(self) -> None:
        with tempfile.TemporaryDirectory(prefix="modular-fm-cpp11-") as temp:
            executable = Path(temp) / "fm_voice_cpp11"
            standalone = subprocess.run(
                [
                    "c++", "-std=gnu++11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT), str(ROOT / "tests/fm_voice_dsp_test.cpp"),
                    "-o", str(executable),
                ],
                cwd=ROOT, capture_output=True, text=True, check=False, timeout=90,
            )
            self.assertEqual(standalone.returncode, 0, standalone.stderr)
            checked = subprocess.run(
                [str(executable)],
                cwd=ROOT, capture_output=True, text=True, check=False, timeout=30,
            )
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertIn("PASS: FM Voice standalone DSP", checked.stdout)

            # Compile the actual wrapper that constructs the five-field Input.
            # A C++17-only aggregate initializer would pass standalone modern
            # builds but fail the Cardinal production compiler here.
            wrapper = subprocess.run(
                [
                    "c++", "-std=gnu++11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-DHEADLESS",
                    "-DpluginInstance=pluginInstance__ModularSynth",
                    "-I", str(ROOT / "tests/rack_stub"), "-fsyntax-only",
                    str(ROOT / "plugins/ModularSynth/src/FMVoice.cpp"),
                ],
                cwd=ROOT, capture_output=True, text=True, check=False, timeout=90,
            )
            self.assertEqual(wrapper.returncode, 0, wrapper.stderr)


if __name__ == "__main__":
    unittest.main()
