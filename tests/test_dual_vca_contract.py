"""First-party DualVCA manifest and shim-compiled Rack wrapper regressions.

Shim compilation is not a real Rack ABI or host build.
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
MOD = ROOT / "plugins/ModularSynth"


class DualVCAContractTests(unittest.TestCase):
    def test_exact_static_registration_and_model_resource(self) -> None:
        manifest = json.loads((MOD / "plugin.json").read_text(encoding="utf-8"))
        matches = [module for module in manifest["modules"] if module["slug"] == "DualVCA"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["name"], "Dual VCA")
        files = {
            "makefile": (ROOT / "plugins/Makefile").read_text(encoding="utf-8"),
            "loader": (ROOT / "plugins/plugins.cpp").read_text(encoding="utf-8"),
            "header": (MOD / "src/plugin.hpp").read_text(encoding="utf-8"),
            "source": (MOD / "src/DualVCA.cpp").read_text(encoding="utf-8"),
        }
        self.assertEqual(len(re.findall(
            r"(?m)^PLUGIN_FILES \+= ModularSynth/src/DualVCA\.cpp$", files["makefile"])), 1)
        self.assertEqual(files["loader"].count("p->addModel(modelDualVCA);"), 1)
        self.assertEqual(files["header"].count("extern Model* modelDualVCA;"), 1)
        self.assertIn('createModel<ModularSynthDualVCA, ModularSynthDualVCAWidget>("DualVCA")',
                      " ".join(files["source"].split()))
        self.assertIn('"res/DualVCA.svg"', files["source"])
        self.assertTrue((MOD / "res/DualVCA.svg").is_file())
        self.assertRegex(files["source"], r"onReset\(const ResetEvent& e\) override")

    @unittest.skipUnless(shutil.which("c++"), "C++17 compiler unavailable")
    def test_headless_wrapper_process_and_lifecycle(self) -> None:
        harness = ROOT / "tests/dual_vca_wrapper_contract.cpp"
        for profile in (("strict", "-O1"), ("fastmath", "-O3", "-ffast-math")):
            with self.subTest(profile=profile[0]), tempfile.TemporaryDirectory() as tmp:
                binary = Path(tmp) / "dual_vca_wrapper"
                build = subprocess.run(
                    ["c++", "-std=c++17", "-DHEADLESS", "-pthread", "-Wall", "-Wextra",
                     "-Wpedantic", "-Werror", *profile[1:],
                     "-I", str(ROOT / "tests/rack_stub"),
                     str(harness), "-o", str(binary)],
                    cwd=ROOT, text=True, capture_output=True, check=False, timeout=90,
                )
                self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                process = subprocess.run(
                    [str(binary)], cwd=ROOT, text=True, capture_output=True,
                    check=False, timeout=30,
                )
                self.assertEqual(process.returncode, 0,
                                 process.stdout + process.stderr)
                self.assertIn("concurrent reset requests", process.stdout)


if __name__ == "__main__":
    unittest.main()
