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

    def check(self, patch: dict | None = None, *, strict_unknown: bool = False,
              require_acyclic: bool = False) -> dict:
        path = Path(self.tmp.name) / "test.vcv"
        path.write_text(json.dumps(patch or self.patch, indent=2), encoding="utf-8")
        return inspector.inspect_patch(path, ROOT, strict_unknown=strict_unknown,
                                       require_acyclic=require_acyclic)

    def test_feedback_scan_does_not_confuse_undirected_connections_with_cycles(self) -> None:
        self.patch["modules"].append(
            {"id": 3, "plugin": "ModularSynth", "model": "StateFilter", "params": []})
        self.patch["cables"].extend([
            {"id": 4, "outputModuleId": 1, "outputId": 0,
             "inputModuleId": 3, "inputId": 0},
            {"id": 5, "outputModuleId": 3, "outputId": 0,
             "inputModuleId": 2, "inputId": 1},
        ])
        report = self.check()
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["feedback_groups"], [])
        self.assertEqual(report["feedback_skipped_cables"], 0)
        self.assertEqual(len(report["components"]), 1)

    def test_feedback_self_loop_is_advisory_by_default_and_opt_in_error(self) -> None:
        self.patch["cables"].append(
            {"id": 4, "outputModuleId": 1, "outputId": 0,
             "inputModuleId": 1, "inputId": 0})
        report = self.check()
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(len(report["feedback_groups"]), 1)
        cycle = report["feedback_groups"][0]
        self.assertEqual(cycle["module_ids"], [1])
        self.assertEqual(cycle["cable_ids"], [4])
        self.assertEqual(cycle["port_contracts"], "source-bounded")
        self.assertEqual(cycle["timing_proof"], "not-established")
        self.assertEqual(cycle["delay_candidates"], [])
        gated = self.check(require_acyclic=True)
        self.assertFalse(gated["ok"])
        self.assertTrue(any("--require-acyclic" in e for e in gated["errors"]))

    def test_feedback_multi_module_cycle_tracks_only_internal_cables(self) -> None:
        self.patch["modules"].append(
            {"id": 3, "plugin": "ModularSynth", "model": "StateFilter", "params": []})
        self.patch["cables"].extend([
            {"id": 4, "outputModuleId": 1, "outputId": 0,
             "inputModuleId": 3, "inputId": 0},
            {"id": 5, "outputModuleId": 3, "outputId": 0,
             "inputModuleId": 1, "inputId": 0},
        ])
        report = self.check()
        self.assertTrue(report["ok"], report["errors"])
        cycle = report["feedback_groups"][0]
        self.assertEqual(cycle["module_ids"], [1, 3])
        self.assertEqual(cycle["cable_ids"], [4, 5])  # HostAudio2 branch not in loop.
        self.assertEqual(cycle["modules"], ["ModularSynth/MorphVCO[1]",
                                            "ModularSynth/StateFilter[3]"])

    def test_feedback_echo_presence_is_not_a_buffering_certificate(self) -> None:
        self.patch["modules"][0]["model"] = "StereoEcho"
        self.patch["modules"][0]["params"] = []
        self.patch["cables"].append(
            {"id": 4, "outputModuleId": 1, "outputId": 0,
             "inputModuleId": 1, "inputId": 0})
        report = self.check()
        self.assertTrue(report["ok"], report["errors"])
        cycle = report["feedback_groups"][0]
        self.assertEqual(cycle["delay_candidates"], [1])
        self.assertEqual(cycle["timing_proof"], "not-established")

    def test_feedback_unverified_ports_and_invalid_edges_remain_explicit(self) -> None:
        self.patch["modules"][0]["plugin"] = "UnknownThirdParty"
        self.patch["modules"][0]["model"] = "ExperimentalCV"
        self.patch["cables"].append(
            {"id": 4, "outputModuleId": 1, "outputId": 0,
             "inputModuleId": 1, "inputId": 0})
        report = self.check()
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["feedback_groups"][0]["port_contracts"],
                         "contains-unverified-ports")
        self.patch["cables"][-1]["outputId"] = -1
        invalid = self.check()
        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["feedback_groups"], [])
        self.assertEqual(invalid["feedback_skipped_cables"], 1)

    def test_feedback_scan_is_iterative_for_long_cycles(self) -> None:
        # Module graph may have long CV daisy chains; recursive SCC algorithms
        # would hit Python's recursion limit on this valid, unknown-port patch.
        nodes = 1200
        self.patch["modules"] = [
            {"id": mid, "plugin": "UnknownThirdParty", "model": "CVPass", "params": []}
            for mid in range(nodes)
        ]
        self.patch["cables"] = [
            {"id": mid, "outputModuleId": mid, "outputId": 0,
             "inputModuleId": (mid + 1) % nodes, "inputId": 0}
            for mid in range(nodes)
        ]
        report = self.check()
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(len(report["feedback_groups"]), 1)
        self.assertEqual(len(report["feedback_groups"][0]["module_ids"]), nodes)

    def test_feedback_separates_sccs_connected_by_one_way_cable(self) -> None:
        # A directed link between two closed CV loops does not merge their
        # independent feedback structures, even though the graph is connected.
        self.patch["modules"] = [
            {"id": mid, "plugin": "UnknownThirdParty", "model": "CVPass", "params": []}
            for mid in (10, 20)
        ]
        self.patch["cables"] = [
            {"id": 1, "outputModuleId": 10, "outputId": 0,
             "inputModuleId": 10, "inputId": 0},
            {"id": 2, "outputModuleId": 20, "outputId": 0,
             "inputModuleId": 20, "inputId": 0},
            {"id": 3, "outputModuleId": 10, "outputId": 1,
             "inputModuleId": 20, "inputId": 1},
        ]
        report = self.check()
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(len(report["components"]), 1)
        self.assertEqual([group["module_ids"] for group in report["feedback_groups"]],
                         [[10], [20]])
        self.assertEqual([group["cable_ids"] for group in report["feedback_groups"]],
                         [[1], [2]])

    def test_feedback_cli_flag_and_human_readable_summary(self) -> None:
        self.patch["cables"].append(
            {"id": 4, "outputModuleId": 1, "outputId": 0,
             "inputModuleId": 1, "inputId": 0})
        self.check()
        path = Path(self.tmp.name) / "test.vcv"
        cli = [sys.executable, str(ROOT / "tools" / "patches" / "patch_inspector.py")]
        normal = subprocess.run([*cli, "inspect", str(path)], cwd=ROOT,
                                capture_output=True, text=True, check=False)
        self.assertEqual(normal.returncode, 0, normal.stderr)
        self.assertIn("Potential directed cable feedback groups: 1", normal.stdout)
        self.assertIn("timing NOT established", normal.stdout)
        gated = subprocess.run([*cli, "validate", str(path), "--require-acyclic", "--json"],
                               cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(gated.returncode, 1, gated.stderr)
        self.assertFalse(json.loads(gated.stdout)[0]["ok"])

    def test_morph_example_is_structurally_valid(self) -> None:
        self.assertTrue(self.example.is_file())
        report = inspector.inspect_patch(self.example, ROOT)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["cables"], 8)
        self.assertEqual(report["module_inventory"]["ModularSynth/MorphVCO"], 1)
        self.assertEqual(report["module_inventory"]["ModularSynth/DualVCA"], 1)
        self.assertTrue(any("HostMIDI" in edge and "MorphVCO" in edge for edge in report["graph"]))
        self.assertEqual(len(report["components"]), 2)  # TextEditor is intentionally unconnected.

    def test_source_derived_morph_bounds(self) -> None:
        schema = inspector._source_bounds(ROOT, "ModularSynth", "MorphVCO")
        self.assertIsNotNone(schema)
        self.assertEqual((schema["params"], schema["inputs"], schema["outputs"]), (5, 4, 2))
        self.assertEqual(schema["ranges"][2], (0.0, 1.0))
        report = self.check()
        self.assertTrue(report["ok"], report["errors"])

    def test_huge_numeric_parameter_is_rejected_without_inspector_crash(self) -> None:
        self.patch["modules"][0]["params"] = [{"id": 0, "value": 10**400}]
        report = self.check()
        self.assertFalse(report["ok"])
        self.assertTrue(any("finite number" in error for error in report["errors"]),
                        report["errors"])

    def test_checked_in_cardinal_host_port_contracts(self) -> None:
        # These host models are part of this checkout, unlike arbitrary
        # bundled third-party modules whose port boundaries remain unknown.
        expected = {
            "HostMIDI": (0, 12, 12),
            "HostTime": (0, 0, 8),
            "HostAudio2": (1, 2, 2),
        }
        for name, counts in expected.items():
            with self.subTest(model=name):
                schema = inspector._source_bounds(ROOT, "Cardinal", name)
                self.assertIsNotNone(schema)
                self.assertEqual((schema["params"], schema["inputs"],
                                  schema["outputs"]), counts)
        self.assertEqual(inspector._source_bounds(ROOT, "Cardinal", "HostAudio2")["ranges"],
                         {0: (0.0, 2.0)})
        self.assertIsNone(inspector._source_bounds(ROOT, "Cardinal", "HostMIDICC"))

        for path in sorted((ROOT / "patches" / "examples").glob("MODULAR_-_*.vcv")):
            with self.subTest(patch=path.name):
                report = inspector.inspect_patch(path, ROOT)
                self.assertTrue(report["ok"], report["errors"])
                self.assertFalse(any("Cardinal/HostMIDI:" in warning or
                                     "Cardinal/HostTime:" in warning or
                                     "Cardinal/HostAudio2:" in warning
                                     for warning in report["warnings"]))

    def test_cardinal_host_saved_ports_and_gain_reject_invalid_values(self) -> None:
        # HostAudio2 exposes just two Rack-facing audio jacks (0 and 1).
        self.patch["cables"][0]["inputId"] = 2
        report = self.check()
        self.assertFalse(report["ok"])
        self.assertTrue(any("inputs index 2 exceeds known count 2" in e
                            for e in report["errors"]))

        self.patch["cables"][0]["inputId"] = 0
        self.patch["modules"][1]["params"] = [{"id": 0, "value": 2.001}]
        report = self.check()
        self.assertFalse(report["ok"])
        self.assertTrue(any("outside declared [0.0, 2.0]" in e
                            for e in report["errors"]))

        self.patch["modules"][1]["params"] = []
        self.patch["modules"].append(
            {"id": 3, "plugin": "Cardinal", "model": "HostMIDI", "params": []})
        self.patch["cables"][0]["outputModuleId"] = 3
        self.patch["cables"][0]["outputId"] = 12
        report = self.check()
        self.assertFalse(report["ok"])
        self.assertTrue(any("outputs index 12 exceeds known count 12" in e
                            for e in report["errors"]))

        self.patch["modules"][-1]["model"] = "HostTime"
        self.patch["cables"][0]["outputId"] = 8
        report = self.check()
        self.assertFalse(report["ok"])
        self.assertTrue(any("outputs index 8 exceeds known count 8" in e
                            for e in report["errors"]))

    def test_cardinal_host_schema_drift_becomes_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plugins" / "Cardinal" / "src" / "HostAudio.cpp"
            path.parent.mkdir(parents=True)
            original = (ROOT / "plugins" / "Cardinal" / "src" / "HostAudio.cpp").read_text()
            path.write_text(original.replace("struct HostAudio2 : HostAudio<2>",
                                             "struct HostAudio2 : HostAudio<4>"),
                            encoding="utf-8")
            self.assertIsNone(inspector._source_bounds(Path(tmp), "Cardinal", "HostAudio2"))

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

    def test_cinematic_drift_and_rhythmic_grit_factory_patches(self) -> None:
        cases = {
            "MODULAR_-_Cinematic_Drift_Pad.vcv": {
                "morph_time": 4.0, "vco_octave": 0.0, "host_max": 0.24,
            },
            "MODULAR_-_Rhythmic_Grit_Bass.vcv": {
                "morph_time": 0.20, "vco_octave": -2.0, "host_max": 0.23,
            },
        }
        for filename, expected in cases.items():
            with self.subTest(patch=filename):
                path = ROOT / "patches" / "examples" / filename
                report = inspector.inspect_patch(path, ROOT)
                self.assertTrue(report["ok"], report["errors"])
                self.assertEqual(report["cables"], 10)
                self.assertEqual(len(report["components"]), 2)  # Intentionally isolated note.
                for model in ("MorphVCO", "StateFilter", "Macro8"):
                    self.assertEqual(report["module_inventory"][f"ModularSynth/{model}"], 1)
                # Only pinned Fundamental and Cardinal host model bounds
                # should remain unverified; all original model bounds are known.
                self.assertFalse(any("ModularSynth/" in warning for warning in report["warnings"]))
                patch = json.loads(path.read_text(encoding="utf-8"))
                models = {module["model"]: module for module in patch["modules"]}
                macro = models["Macro8"]
                values = {param["id"]: param["value"] for param in macro["params"]}
                self.assertAlmostEqual(values[8], expected["morph_time"])
                self.assertEqual(values[18], 1.0)  # Fourth CV output bipolar.
                self.assertEqual(len(macro["data"]["snapshots"][0]), 8)
                self.assertEqual(len(macro["data"]["snapshots"][1]), 8)
                self.assertEqual(
                    next(param["value"] for param in models["MorphVCO"]["params"]
                         if param["id"] == 0),
                    expected["vco_octave"],
                )
                self.assertLessEqual(
                    next(param["value"] for param in models["HostAudio2"]["params"]
                         if param["id"] == 0),
                    expected["host_max"],
                )
                self.assertLessEqual(
                    next(param["value"] for param in models["VCA-1"]["params"]
                         if param["id"] == 0),
                    0.35,
                )
                # Require all four intended Macro8 CV routes, including the
                # bipolar cutoff sweep, not just the presence of the module.
                macro_id = macro["id"]
                filt_id = models["StateFilter"]["id"]
                morph_id = models["MorphVCO"]["id"]
                routes = {
                    (cable["outputModuleId"], cable["outputId"],
                     cable["inputModuleId"], cable["inputId"])
                    for cable in patch["cables"]
                }
                self.assertTrue({
                    (macro_id, 0, morph_id, 2),
                    (macro_id, 1, filt_id, 2),
                    (macro_id, 2, filt_id, 3),
                    (macro_id, 3, filt_id, 1),
                }.issubset(routes))

    def test_batch_cli_validates_both_new_performance_patches(self) -> None:
        paths = [
            ROOT / "patches" / "examples" / "MODULAR_-_Cinematic_Drift_Pad.vcv",
            ROOT / "patches" / "examples" / "MODULAR_-_Rhythmic_Grit_Bass.vcv",
        ]
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "patches" / "patch_inspector.py"),
             "validate", *(str(path) for path in paths), "--json"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        reports = json.loads(result.stdout)
        self.assertEqual(len(reports), 2)
        self.assertTrue(all(report["ok"] for report in reports))
        self.assertTrue(all(report["cables"] == 10 for report in reports))

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
