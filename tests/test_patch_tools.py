"""Regression tests for the offline patch inspector and Morph VCO tutorial patch."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "patches"))
import patch_inspector as inspector  # noqa: E402


class PatchInspectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.example = ROOT / "patches" / "examples" / "MODULAR_-_Morph_VCO_Performance.vcv"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.patch = {
            "version": "2.4.1",
            "modules": [
                {"id": 1, "plugin": "ModularSynth", "model": "MorphVCO",
                 "params": [{"id": 0, "value": 0.0}, {"id": 2, "value": 0.5}]},
                {"id": 2, "plugin": "Cardinal", "model": "HostAudio2", "params": []}
            ],
            "cables": [
                {"id": 3, "outputModuleId": 1, "outputId": 0,
                 "inputModuleId": 2, "inputId": 0}
            ]
        }

    def check(self, patch: dict | None = None, *, strict_unknown: bool = False) -> dict:
        path = Path(self.tmp.name) / "test.vcv"
        path.write_text(json.dumps(patch or self.patch, indent=2), encoding="utf-8")
        return inspector.inspect_patch(path, ROOT, strict_unknown=strict_unknown)

    def test_morph_example_is_structurally_valid(self) -> None:
        self.assertTrue(self.example.is_file())
        report = inspector.inspect_patch(self.example, ROOT)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["cables"], 5)
        self.assertEqual(report["module_inventory"]["ModularSynth/MorphVCO"], 1)
        self.assertTrue(any("HostMIDI" in edge and "MorphVCO" in edge for edge in report["graph"]))
        self.assertEqual(len(report["components"]), 2)  # TextEditor is intentionally unconnected.

    def test_source_derived_morph_bounds(self) -> None:
        schema = inspector._source_bounds(ROOT, "ModularSynth", "MorphVCO")
        self.assertIsNotNone(schema)
        self.assertEqual((schema["params"], schema["inputs"], schema["outputs"]), (5, 4, 2))
        self.assertEqual(schema["ranges"][2], (0.0, 1.0))
        report = self.check()
        self.assertTrue(report["ok"], report["errors"])

    def test_all_registered_original_models_have_source_schemas(self) -> None:
        manifest = json.loads(
            (ROOT / "plugins" / "ModularSynth" / "plugin.json").read_text(encoding="utf-8")
        )
        slugs = [entry["slug"] for entry in manifest["modules"]]
        self.assertTrue({"MorphVCO", "StateFilter", "Macro8"}.issubset(slugs))
        for slug in slugs:
            with self.subTest(model=slug):
                source = ROOT / "plugins" / "ModularSynth" / "src" / f"{slug}.cpp"
                self.assertTrue(source.is_file(), f"Missing source for {slug}")
                schema = inspector._source_bounds(ROOT, "ModularSynth", slug)
                self.assertIsNotNone(schema, f"Cannot derive port/parameter schema for {slug}")
                self.assertGreaterEqual(schema["params"], 0)
                self.assertGreaterEqual(schema["inputs"], 0)
                self.assertGreaterEqual(schema["outputs"], 0)
                self.assertEqual(
                    len(schema["ranges"]), schema["params"],
                    f"Missing declared parameter range evidence for {slug}",
                )

    def test_macro8_and_statefilter_source_bounds(self) -> None:
        macro = inspector._source_bounds(ROOT, "ModularSynth", "Macro8")
        filt = inspector._source_bounds(ROOT, "ModularSynth", "StateFilter")
        self.assertIsNotNone(macro)
        self.assertIsNotNone(filt)
        self.assertEqual((macro["params"], macro["inputs"], macro["outputs"]), (23, 0, 8))
        self.assertEqual(macro["ranges"][0], (0.0, 1.0))
        self.assertEqual(macro["ranges"][22], (0.0, 1.0))
        self.assertEqual((filt["params"], filt["inputs"], filt["outputs"]), (3, 4, 3))
        self.assertEqual(filt["ranges"][1], (0.0, 1.0))

    def test_morphing_state_pad_patch(self) -> None:
        path = ROOT / "patches" / "examples" / "MODULAR_-_Morphing_State_Pad.vcv"
        self.assertTrue(path.is_file())
        result = inspector.inspect_patch(path, ROOT)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["cables"], 9)
        self.assertEqual(result["module_inventory"]["ModularSynth/MorphVCO"], 1)
        self.assertEqual(result["module_inventory"]["ModularSynth/StateFilter"], 1)
        self.assertEqual(result["module_inventory"]["ModularSynth/Macro8"], 1)
        self.assertEqual(len(result["components"]), 2)  # TextEditor note is disconnected.
        patch = json.loads(path.read_text(encoding="utf-8"))
        macro = next(module for module in patch["modules"]
                     if module["plugin"] == "ModularSynth" and module["model"] == "Macro8")
        self.assertEqual(macro["data"]["macro8Version"], 1)
        self.assertEqual(len(macro["data"]["snapshots"][0]), 8)
        self.assertEqual(len(macro["data"]["snapshots"][1]), 8)
        self.assertTrue(any("Macro8" in edge and "StateFilter" in edge for edge in result["graph"]))

    def test_macro8_and_filter_reject_bad_values_or_ports(self) -> None:
        self.patch["modules"][0]["model"] = "Macro8"
        self.patch["modules"][0]["params"] = [{"id": 0, "value": 1.01}]
        result = self.check()
        self.assertFalse(result["ok"])
        self.assertTrue(any("outside declared" in message for message in result["errors"]))
        self.patch["modules"][0]["model"] = "StateFilter"
        self.patch["modules"][0]["params"] = [{"id": 1, "value": 0.5}]
        self.patch["cables"][0]["outputId"] = 3
        result = self.check()
        self.assertFalse(result["ok"])
        self.assertTrue(any("outputs index 3 exceeds known count 3" in message
                            for message in result["errors"]))

    def test_reject_out_of_range_param(self) -> None:
        self.patch["modules"][0]["params"][1]["value"] = 1.5
        report = self.check()
        self.assertFalse(report["ok"])
        self.assertTrue(any("outside declared" in err for err in report["errors"]))

    def test_reject_out_of_range_port(self) -> None:
        self.patch["cables"][0]["outputId"] = 2
        report = self.check()
        self.assertFalse(report["ok"])
        self.assertTrue(any("outputs index 2 exceeds known count 2" in err
                            for err in report["errors"]))

    def test_reject_duplicate_module_and_cable_ids(self) -> None:
        self.patch["modules"].append({"id": 1, "plugin": "Cardinal", "model": "HostMIDI"})
        self.patch["cables"].append({**self.patch["cables"][0], "inputId": 1})
        report = self.check()
        self.assertFalse(report["ok"])
        self.assertTrue(any("duplicate module id" in err for err in report["errors"]))
        self.assertTrue(any("duplicate cable id" in err for err in report["errors"]))

    def test_reject_two_cables_to_same_input(self) -> None:
        self.patch["cables"].append({**self.patch["cables"][0], "id": 4})
        report = self.check()
        self.assertFalse(report["ok"])
        self.assertTrue(any("duplicate connection to input" in err for err in report["errors"]))

    def test_reject_dangling_endpoint(self) -> None:
        self.patch["cables"][0]["outputModuleId"] = 9999
        report = self.check()
        self.assertFalse(report["ok"])
        self.assertTrue(any("does not exist" in err for err in report["errors"]))

    def test_reject_non_finite_and_duplicate_json_keys(self) -> None:
        path = Path(self.tmp.name) / "bad.vcv"
        path.write_text('{"version":"2.4.1","modules":[],"cables":[],"x":NaN}', encoding="utf-8")
        self.assertFalse(inspector.inspect_patch(path, ROOT)["ok"])
        path.write_text('{"version":"2.4.1","modules":[],"modules":[],"cables":[]}', encoding="utf-8")
        self.assertFalse(inspector.inspect_patch(path, ROOT)["ok"])

    def test_reject_nonfinite_param_from_regular_json(self) -> None:
        self.patch["modules"][0]["params"][0]["value"] = float("inf")
        report = self.check()
        self.assertFalse(report["ok"])
        self.assertTrue(any("Non-finite JSON" in err for err in report["errors"]))

    def test_unknown_first_party_model_is_error(self) -> None:
        self.patch["modules"][0]["model"] = "MorphVCOTypo"
        report = self.check()
        self.assertFalse(report["ok"])
        self.assertTrue(any("model absent from checked-in first-party manifest" in err
                            for err in report["errors"]))

    def test_unknown_third_party_is_warning_only_by_default(self) -> None:
        self.patch["modules"][0]["plugin"] = "ThirdPartyUnknown"
        self.patch["modules"][0]["model"] = "ImaginaryOsc"
        report = self.check()
        self.assertTrue(report["ok"])
        self.assertTrue(any("unverified" in warning for warning in report["warnings"]))
        strict = self.check(strict_unknown=True)
        self.assertFalse(strict["ok"])

    def test_cli_prints_inventory_and_json(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "patches" / "patch_inspector.py"),
             "inspect", str(self.example), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)[0]
        self.assertTrue(report["ok"])
        self.assertTrue(report["graph"])
        self.assertIn("ModularSynth/MorphVCO", report["module_inventory"])

    def test_legacy_bundled_synth_template_accepted_with_warnings(self) -> None:
        path = ROOT / "patches" / "templates" / "synth.vcv"
        report = inspector.inspect_patch(path, ROOT)
        self.assertTrue(report["ok"], report["errors"])
        self.assertIn("Fundamental/ADSR", report["module_inventory"])
        self.assertTrue(any("Fundamental/ADSR" in warning for warning in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
