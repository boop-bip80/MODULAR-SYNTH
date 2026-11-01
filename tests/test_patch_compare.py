"""Offline semantic patch comparison regression tests (no audio host required)."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.patches.patch_compare import (  # noqa: E402
    PatchComparisonError, compare_patches, format_report, load_patch,
)


def module(mid: int, plugin: str, model: str, params: dict[int, float] | None = None,
           data: dict | None = None) -> dict:
    result = {
        "id": mid, "plugin": plugin, "model": model,
        "params": [{"id": key, "value": val} for key, val in (params or {}).items()],
        "version": "2.4.1", "pos": [mid * 2, 0],
    }
    if data is not None:
        result["data"] = data
    return result


def cable(cid: int, src: int, output: int, dst: int, input_id: int) -> dict:
    return {
        "id": cid, "outputModuleId": src, "outputId": output,
        "inputModuleId": dst, "inputId": input_id, "color": "#ff5252",
    }


def patch(modules: list[dict], cables: list[dict]) -> dict:
    return {"version": "2.4.1", "zoom": 0.75, "modules": modules, "cables": cables}


def fixture() -> dict:
    """One complete signal route plus CV snapshot, with unique model types."""
    return patch([
        module(1, "Cardinal", "HostMIDI"),
        module(2, "ModularSynth", "MorphVCO", {0: 0.0, 2: 0.5}),
        module(3, "ModularSynth", "Macro8", {0: 0.3, 8: 1.0},
               {"macro8Version": 1, "names": ["Shape", "Res", "Drive"],
                "snapshots": [[0.2, 0.3, 0.4], None, None, None],
                "selectedSlot": -1}),
        module(4, "Cardinal", "HostAudio2", {0: 0.2}),
    ], [
        cable(10, 1, 0, 2, 0),
        cable(11, 3, 0, 2, 2),
        cable(12, 2, 0, 4, 0),
    ])


class PatchCompareTests(unittest.TestCase):
    def test_array_order_layout_cable_id_and_color_do_not_change_semantics(self) -> None:
        before = fixture()
        after = copy.deepcopy(before)
        after["modules"].reverse()
        after["cables"].reverse()
        after["zoom"] = 2.0
        for mod in after["modules"]:
            mod["pos"] = [999, 999]
            mod["params"].reverse()
        for index, wire in enumerate(after["cables"]):
            wire["id"] = 900 + index
            wire["color"] = "#000000"
        report = compare_patches(before, after)
        self.assertFalse(report["summary"]["changed"])
        self.assertEqual(report["summary"]["matched_modules"], 4)
        self.assertEqual(report["summary"]["id_remaps_ignored"], 0)
        self.assertIn("No semantic changes.", format_report(report))

    def test_unique_type_reidentified_after_rack_id_regeneration(self) -> None:
        before = fixture()
        after = copy.deepcopy(before)
        replacements = {1: 101, 2: 102, 3: 103, 4: 104}
        for mod in after["modules"]:
            mod["id"] = replacements[mod["id"]]
        for wire in after["cables"]:
            wire["outputModuleId"] = replacements[wire["outputModuleId"]]
            wire["inputModuleId"] = replacements[wire["inputModuleId"]]
        report = compare_patches(before, after)
        self.assertFalse(report["summary"]["changed"])
        self.assertEqual(report["summary"]["matched_modules"], 4)
        self.assertEqual(report["summary"]["id_remaps_ignored"], 4)
        self.assertFalse(report["cables"]["added"])
        self.assertFalse(report["cables"]["removed"])

    def test_parameter_add_remove_change_and_cable_endpoint_rewire(self) -> None:
        before = fixture()
        after = copy.deepcopy(before)
        morph = next(m for m in after["modules"] if m["model"] == "MorphVCO")
        morph["params"] = [{"id": 2, "value": 0.75}, {"id": 3, "value": 0.6}]
        wire = next(c for c in after["cables"] if c["id"] == 12)
        wire["outputId"] = 1
        report = compare_patches(before, after)
        self.assertTrue(report["summary"]["changed"])
        changes = report["modules"]["parameters"]
        self.assertEqual([(x["parameter_id"], x["change"]) for x in changes],
                         [(0, "removed"), (2, "changed"), (3, "added")])
        self.assertEqual(report["summary"]["cables_removed"], 1)
        self.assertEqual(report["summary"]["cables_added"], 1)
        self.assertEqual(report["cables"]["added"][0]["output"], 1)
        self.assertIn("param 2: 0.5 -> 0.75", format_report(report))

    def test_macro8_snapshots_names_slot_selection_and_new_slot(self) -> None:
        before = fixture()
        after = copy.deepcopy(before)
        state = next(m["data"] for m in after["modules"] if m["model"] == "Macro8")
        state["names"][0] = "Waveshape"
        state["snapshots"][0][2] = 0.9
        state["snapshots"][1] = [0.9, 0.4, 0.1]
        state["selectedSlot"] = 1
        report = compare_patches(before, after)
        self.assertEqual(report["summary"]["parameters_changed"], 0)
        fields = [x["field"] for x in report["modules"]["macro8_state"]]
        self.assertEqual(fields, [
            "selectedSlot", "name[1]", "snapshot[A].macro3", "snapshot[B]",
        ])
        self.assertEqual(report["summary"]["macro8_state_changed"], 4)
        self.assertIn("snapshot[A].macro3", format_report(report))
        self.assertEqual(report["modules"]["macro8_state"][-1]["before"], None)

    def test_macro8_missing_data_and_names_report_state_changes(self) -> None:
        before = fixture()
        after = copy.deepcopy(before)
        next(m for m in after["modules"] if m["model"] == "Macro8")["data"] = {}
        fields = [x["field"] for x in compare_patches(before, after)["modules"]["macro8_state"]]
        self.assertEqual(fields, ["macro8Version", "selectedSlot", "names", "snapshots"])

    def test_multiple_identical_type_instances_without_stable_ids_are_conservative(self) -> None:
        before = patch([
            module(1, "Fundamental", "VCA-1"),
            module(2, "Fundamental", "VCA-1"),
        ], [])
        after = patch([
            module(3, "Fundamental", "VCA-1"),
            module(4, "Fundamental", "VCA-1"),
        ], [])
        report = compare_patches(before, after)
        self.assertEqual(report["summary"]["matched_modules"], 0)
        self.assertEqual(report["summary"]["modules_removed"], 2)
        self.assertEqual(report["summary"]["modules_added"], 2)
        self.assertTrue(report["summary"]["changed"])

    def test_stable_id_distinguishes_same_model_duplicates(self) -> None:
        before = patch([
            module(1, "Fundamental", "VCA-1", {0: 0.1}),
            module(2, "Fundamental", "VCA-1", {0: 0.2}),
        ], [])
        after = patch(list(reversed(copy.deepcopy(before["modules"]))), [])
        report = compare_patches(before, after)
        self.assertFalse(report["summary"]["changed"])
        self.assertEqual(report["summary"]["matched_modules"], 2)

    def test_module_replacement_is_added_removed_not_mispaired(self) -> None:
        before = patch([module(1, "A", "One")], [])
        after = patch([module(1, "A", "Two")], [])
        report = compare_patches(before, after)
        self.assertEqual(report["summary"]["matched_modules"], 0)
        self.assertEqual(report["summary"]["modules_added"], 1)
        self.assertEqual(report["summary"]["modules_removed"], 1)

    def test_duplicate_cable_endpoints_preserve_multiplicity(self) -> None:
        before = fixture()
        after = copy.deepcopy(before)
        duplicate = copy.deepcopy(after["cables"][0])
        duplicate["id"] = 1000
        after["cables"].append(duplicate)
        report = compare_patches(before, after)
        self.assertEqual(report["summary"]["cables_added"], 1)
        self.assertEqual(report["cables"]["added"][0]["count"], 1)

    def test_deterministic_json_when_all_arrays_reordered(self) -> None:
        before = fixture()
        after = copy.deepcopy(before)
        after["modules"][1]["params"][0]["value"] = 1.0
        original = compare_patches(before, after, before_label="A", after_label="B")
        lhs, rhs = copy.deepcopy(before), copy.deepcopy(after)
        for current in (lhs, rhs):
            current["modules"].reverse()
            current["cables"].reverse()
            for mod in current["modules"]:
                mod["params"].reverse()
        shuffled = compare_patches(lhs, rhs, before_label="A", after_label="B")
        self.assertEqual(json.dumps(original, sort_keys=True), json.dumps(shuffled, sort_keys=True))
        self.assertEqual(format_report(original), format_report(shuffled))

    def test_bad_module_cable_and_param_data_fail_safely(self) -> None:
        cases = []
        case = fixture()
        case["modules"].append(copy.deepcopy(case["modules"][0]))
        cases.append(case)
        case = fixture()
        case["cables"][0]["inputModuleId"] = 999
        cases.append(case)
        case = fixture()
        case["modules"][0]["params"] = [{"id": 0, "value": float("nan")}]
        cases.append(case)
        case = fixture()
        case["modules"][0]["id"] = True
        cases.append(case)
        case = fixture()
        case["modules"][0]["params"] = [{"id": 0, "value": 0}, {"id": 0, "value": 1}]
        cases.append(case)
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(PatchComparisonError):
                    compare_patches(case, fixture())

    def test_cli_exit_codes_json_determinism_and_bad_json(self) -> None:
        script = ROOT / "tools" / "patches" / "patch_compare.py"
        with tempfile.TemporaryDirectory() as directory:
            old_path, new_path = Path(directory) / "old.vcv", Path(directory) / "new.vcv"
            old_path.write_text(json.dumps(fixture()), encoding="utf-8")
            new_path.write_text(json.dumps(fixture()), encoding="utf-8")

            def call(*flags: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [sys.executable, str(script), str(old_path), str(new_path), *flags],
                    cwd=ROOT, capture_output=True, text=True, check=False,
                )

            identical = call("--json")
            self.assertEqual(identical.returncode, 0, identical.stderr)
            self.assertFalse(json.loads(identical.stdout)["summary"]["changed"])
            modified = fixture()
            modified["modules"][1]["params"][0]["value"] = -2
            new_path.write_text(json.dumps(modified), encoding="utf-8")
            changed = call("--json")
            self.assertEqual(changed.returncode, 1, changed.stderr)
            self.assertTrue(json.loads(changed.stdout)["summary"]["changed"])
            self.assertEqual(changed.stdout, call("--json").stdout)
            new_path.write_text('{"modules": [], "modules": [], "cables": []}', encoding="utf-8")
            malformed = call()
            self.assertEqual(malformed.returncode, 2)
            self.assertIn("duplicate JSON object key", malformed.stderr)
            new_path.write_text('{"modules":[],"cables":[],"version":NaN}', encoding="utf-8")
            nonfinite = call()
            self.assertEqual(nonfinite.returncode, 2)
            self.assertIn("non-finite JSON literal", nonfinite.stderr)

    def test_real_cinematic_vs_bass_graph_on_checkout(self) -> None:
        samples = ROOT / "patches" / "examples"
        pad = samples / "MODULAR_-_Cinematic_Drift_Pad.vcv"
        bass = samples / "MODULAR_-_Rhythmic_Grit_Bass.vcv"
        if not (pad.is_file() and bass.is_file()):
            self.skipTest("full source checkout with first-party patches not present")
        report = compare_patches(load_patch(pad), load_patch(bass))
        self.assertEqual(report["summary"]["matched_modules"], 8)
        self.assertEqual(report["summary"]["modules_added"], 0)
        self.assertEqual(report["summary"]["modules_removed"], 0)
        self.assertEqual(report["summary"]["cables_added"], 0)
        self.assertEqual(report["summary"]["cables_removed"], 0)
        self.assertGreater(report["summary"]["parameters_changed"], 0)
        self.assertGreater(report["summary"]["macro8_state_changed"], 0)
        self.assertGreater(report["summary"]["id_remaps_ignored"], 0)


if __name__ == "__main__":
    unittest.main()
