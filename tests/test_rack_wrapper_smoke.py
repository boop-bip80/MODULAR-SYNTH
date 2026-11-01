"""HEADLESS first-party wrapper smoke against a test-only Rack API double.

This compiles the real module wrappers but **not** Cardinal/Rack, its GUI,
plugin ABI or third-party dependencies. A green result is a narrower source
signal than an actual fork plugin/DAW build.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "rack_wrapper_smoke.cpp"
STUBS = ROOT / "tests" / "rack_stub"
WRAPPER_SOURCES = (
    "MorphVCO.cpp", "StateFilter.cpp", "Macro8.cpp", "StereoEcho.cpp",
    "ClockedLFO.cpp",
)


class RackWrapperSmokeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++"), "C++17 compiler not installed")
    def test_five_first_party_headless_wrappers_compile_and_process(self) -> None:
        with tempfile.TemporaryDirectory(prefix="modular-synth-wrapper-smoke-") as temp:
            # The production Makefile compiles these as separate translation
            # units and renames pluginInstance at preprocessing time.
            for name in WRAPPER_SOURCES:
                source = ROOT / "plugins" / "ModularSynth" / "src" / name
                checked = subprocess.run(
                    [
                        "c++", "-std=c++17", "-O1", "-Wall", "-Wextra",
                        "-Wpedantic", "-DHEADLESS",
                        "-DpluginInstance=pluginInstance__ModularSynth",
                        "-I", str(STUBS), "-fsyntax-only", str(source),
                    ],
                    cwd=ROOT, capture_output=True, text=True, timeout=90,
                    check=False,
                )
                self.assertEqual(
                    checked.returncode, 0,
                    f"{name} failed isolated HEADLESS shim compilation:\n"
                    + checked.stdout + checked.stderr,
                )
            profiles = (
                ("strict", ["-O1"]),
                ("production", ["-O3", "-ffast-math", "-fno-finite-math-only"]),
                ("aggressive-fastmath", ["-O3", "-ffast-math"]),
            )
            for profile, flags in profiles:
                with self.subTest(profile=profile):
                    binary = Path(temp) / f"rack-wrapper-smoke-{profile}"
                    compile_command = [
                        "c++", "-std=c++17", *flags,
                        "-Wall", "-Wextra", "-Wpedantic", "-pthread",
                        "-DHEADLESS", "-I", str(STUBS), str(HARNESS), "-o", str(binary),
                    ]
                    compiled = subprocess.run(
                        compile_command, cwd=ROOT, capture_output=True, text=True,
                        timeout=90, check=False,
                    )
                    self.assertEqual(
                        compiled.returncode, 0,
                        f"HEADLESS wrapper shim compilation failed ({profile}):\n"
                        + compiled.stdout + compiled.stderr,
                    )
                    completed = subprocess.run(
                        [str(binary)], cwd=ROOT, capture_output=True, text=True,
                        timeout=30, check=False,
                    )
                    self.assertEqual(
                        completed.returncode, 0,
                        f"HEADLESS wrapper shim process smoke failed ({profile}):\n"
                        + completed.stdout + completed.stderr,
                    )
                    self.assertIn("PASS: 5 HEADLESS wrapper", completed.stdout)


if __name__ == "__main__":
    unittest.main()
