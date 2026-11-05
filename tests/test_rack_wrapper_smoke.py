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
    "ClockedLFO.cpp", "FMVoice.cpp", "ChanceHold.cpp",
)


class RackWrapperSmokeTests(unittest.TestCase):
    def test_macro8_trigger_initialization_matches_pinned_rack_contract(self) -> None:
        """Guard the braced value-init that broke hosted Rack compilation.

        The shim compiler test below tests reset behavior; these checks ensure
        it cannot mask the pinned real SDK's inaccessible union constructor.
        """
        macro8 = (ROOT / "plugins/ModularSynth/src/Macro8.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("std::array<dsp::SchmittTrigger, 4> slotTriggers;", macro8)
        self.assertNotIn("slotTriggers{}", macro8)
        self.assertNotIn("dsp::SchmittTrigger{}", macro8)
        self.assertIn("trigger.reset();", macro8)
        self.assertIn("liveTrigger.reset();", macro8)

    @unittest.skipUnless(shutil.which("c++"), "C++17 compiler not installed")
    def test_seven_first_party_headless_wrappers_compile_and_process(self) -> None:
        with tempfile.TemporaryDirectory(prefix="modular-synth-wrapper-smoke-") as temp:
            # The production Makefile compiles these as separate translation
            # units and renames pluginInstance at preprocessing time.
            # Cardinal's production Makefile still compiles some wrappers in
            # GNU C++11 mode. The shim smoke harness itself uses newer test
            # utilities, so independently check every wrapper in both source
            # dialects instead of assuming a C++17-only smoke is sufficient.
            for dialect in ("gnu++11", "c++17"):
                for name in WRAPPER_SOURCES:
                    with self.subTest(dialect=dialect, wrapper=name):
                        source = ROOT / "plugins" / "ModularSynth" / "src" / name
                        checked = subprocess.run(
                            [
                                "c++", f"-std={dialect}", "-O1", "-Wall", "-Wextra",
                                "-Wpedantic", "-DHEADLESS",
                                "-DpluginInstance=pluginInstance__ModularSynth",
                                "-I", str(STUBS), "-fsyntax-only", str(source),
                            ],
                            cwd=ROOT, capture_output=True, text=True, timeout=90,
                            check=False,
                        )
                        self.assertEqual(
                            checked.returncode, 0,
                            f"{name} failed isolated {dialect} HEADLESS shim compilation:\n"
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
                    self.assertIn("PASS: 7 HEADLESS wrapper", completed.stdout)


if __name__ == "__main__":
    unittest.main()
