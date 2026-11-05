"""Guard StereoEcho's production C++11 link ABI, including unoptimized builds.

The Cardinal integration uses C++11 in parts of its platform matrix. In that
dialect a class static constexpr floating-point member needs an out-of-line
definition when passed to std::min(const T&, ...); -O0 exposes the otherwise
hidden undefined reference at link time.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/stereo_echo_dsp_test.cpp"


class StereoEchoCxx11LinkTests(unittest.TestCase):
    def test_cxx11_debug_and_fastmath_link_and_execute(self) -> None:
        compiler = os.environ.get("CXX", "c++")
        if not shutil.which(compiler):
            self.skipTest(f"C++ compiler unavailable: {compiler}")

        with tempfile.TemporaryDirectory(prefix="stereo-echo-cxx11-") as temp:
            for name, flags in (
                ("debug", ["-O0"]),
                ("production", ["-O3", "-ffast-math", "-fno-finite-math-only"]),
            ):
                with self.subTest(profile=name):
                    binary = Path(temp) / f"stereo-echo-{name}"
                    command = [
                        compiler, "-std=gnu++11", *flags,
                        "-Wall", "-Wextra", "-Werror",
                        str(SOURCE), "-o", str(binary),
                    ]
                    compile_result = subprocess.run(
                        command, capture_output=True, text=True,
                        timeout=60, check=False,
                    )
                    self.assertEqual(
                        compile_result.returncode, 0,
                        "StereoEcho C++11 compile/link failed:\n"
                        + compile_result.stdout + compile_result.stderr,
                    )
                    run_result = subprocess.run(
                        [str(binary)], capture_output=True, text=True,
                        timeout=60, check=False,
                    )
                    self.assertEqual(
                        run_result.returncode, 0,
                        "StereoEcho C++11 DSP regression failed:\n"
                        + run_result.stdout + run_result.stderr,
                    )
                    self.assertIn("PASS: StereoEcho", run_result.stdout)


if __name__ == "__main__":
    unittest.main()
