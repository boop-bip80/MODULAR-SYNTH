"""Focused FoldDrive static registration and independent Rack-shim smoke.

Does not alter the existing 5-model rack_wrapper_smoke.cpp harness owned by
the separate Macro8 lifecycle workstream. This is source/shim only, not a host.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "plugins/ModularSynth"
WRAPPER = MODULE / "src/FoldDrive.cpp"


class FoldDriveContractTests(unittest.TestCase):
    def test_exact_first_party_registration_and_ui_resource(self) -> None:
        manifest = json.loads((MODULE / "plugin.json").read_text(encoding="utf-8"))
        entries = [module for module in manifest["modules"] if module["slug"] == "FoldDrive"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "Fold Drive")
        make = (ROOT / "plugins/Makefile").read_text(encoding="utf-8")
        registry = (ROOT / "plugins/plugins.cpp").read_text(encoding="utf-8")
        header = (MODULE / "src/plugin.hpp").read_text(encoding="utf-8")
        wrapper = WRAPPER.read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"(?m)^PLUGIN_FILES \+= ModularSynth/src/FoldDrive\.cpp$", make)), 1)
        self.assertEqual(len(re.findall(r"\bp->addModel\(modelFoldDrive\);", registry)), 1)
        self.assertEqual(len(re.findall(r"\bextern Model\* modelFoldDrive;", header)), 1)
        self.assertEqual(len(re.findall(
            r'Model\* modelFoldDrive = createModel<ModularSynthFoldDrive, '
            r'ModularSynthFoldDriveWidget>\("FoldDrive"\);', wrapper)), 1)
        self.assertIn('"res/FoldDrive.svg"', wrapper)
        self.assertTrue((MODULE / "res/FoldDrive.svg").is_file())
        self.assertRegex(wrapper, r"onReset\(const ResetEvent& e\) override")

    @unittest.skipUnless(shutil.which("c++"), "C++17 compiler not available")
    def test_actual_headless_wrapper_processes_and_retires_lanes(self) -> None:
        harness = ROOT / "tests/folddrive_wrapper_contract.cpp"
        for profile in (
            ("strict", "-O1", "-Werror"),
            ("aggressive-fastmath", "-O3", "-ffast-math", "-Werror"),
        ):
            with self.subTest(profile=profile[0]), tempfile.TemporaryDirectory() as temp:
                binary = Path(temp) / "folddrive_wrapper"
                compiled = subprocess.run(
                    ["c++", "-std=c++17", "-DHEADLESS", "-pthread", "-Wall", "-Wextra",
                     "-Wpedantic", *profile[1:], "-I", str(ROOT / "tests/rack_stub"),
                     str(harness), "-o", str(binary)],
                    cwd=ROOT, text=True, capture_output=True, check=False, timeout=90,
                )
                self.assertEqual(compiled.returncode, 0,
                                 "HEADLESS compile: " + compiled.stdout + compiled.stderr)
                result = subprocess.run([str(binary)], cwd=ROOT, text=True,
                                        capture_output=True, check=False, timeout=30)
                self.assertEqual(result.returncode, 0,
                                 "HEADLESS process: " + result.stdout + result.stderr)
                self.assertIn("8192 allocation-free ticks and concurrent UI ResetEvent",
                              result.stdout)


if __name__ == "__main__":
    unittest.main()
