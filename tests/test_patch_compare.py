"""Offline semantic patch comparison regression tests (no audio host required)."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import random
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
    def test_reordered_feedback_cycle_and_same_model_remaps_are_stable(self) -> None:
        # Directed cycles are legal source patch topology, and saved-state
        # fingerprints, not new canvas positions or cable array order, pair
        # distinct instances of one model across Rack ID regeneration.
        before = patch([
            module(1, "ModularSynth", "MorphVCO", {1: 0.25}),
            module(2, "Fundamental", "VCA-1", {0: 0.2}),
            module(3, "Fundamental", "VCA-1", {0: 0.8}),
            module(4, "ModularSynth", "StateFilter", {0: 0.3}),
        ], [cable(10, 1, 0, 2, 1), cable(11, 2, 0, 4, 0),
            cable(12, 4, 0, 3, 1), cable(13, 3, 0, 1, 2)])
        remap = {1: 401, 2: 402, 3: 403, 4: 404}
        rng = random.Random(0x5EED)
        expected = None
        for _ in range(48):
            after = copy.deepcopy(before)
            rng.shuffle(after["modules"])
            rng.shuffle(after["cables"])
            for entry in after["modules"]:
                entry["id"] = remap[entry["id"]]
                entry["pos"] = [rng.randint(-1000, 1000), rng.randint(-1000, 1000)]
                rng.shuffle(entry["params"])
            for wire in after["cables"]:
                wire["id"] += 1000
                wire["outputModuleId"] = remap[wire["outputModuleId"]]
                wire["inputModuleId"] = remap[wire["inputModuleId"]]
                wire["color"] = "#010101"
            report = compare_patches(before, after)
            self.assertFalse(report["summary"]["changed"])
            self.assertEqual(report["summary"]["id_remaps_ignored"], 4)
            serialized = json.dumps(report, sort_keys=True)
            if expected is None:
                expected = serialized
            else:
                self.assertEqual(serialized, expected)

    def test_nested_non_json_and_cycles_fail_closed(self) -> None:
        bad: list[object] = []
        cycle: dict[str, object] = {}
        cycle["self"] = cycle
        bad.append(cycle)
        bad.extend(({"nested": {1: "invalid JSON key"}},
                    {"nested": {"opaque": {1, 2}}},
                    {"nested": {"complex": 1 + 2j}},
                    {"oversized_integer": 10**2000}))
        for payload in bad:
            with self.subTest(kind=str(type(payload))):
                original = fixture()
                original["modules"][0]["data"] = payload
                with self.assertRaises(PatchComparisonError):
                    compare_patches(original, fixture())

        # Shared Python objects are not cycles and serialize as normal JSON.
        shared = {"steps": [0, 7, 12]}
        reused = fixture()
        reused["modules"][0]["data"] = {"first": shared, "second": shared}
        self.assertFalse(compare_patches(reused, copy.deepcopy(reused))["summary"]["changed"])

    def test_extreme_nested_state_and_file_decoder_fail_without_tracebacks(self) -> None:
        nested: object = 1
        for _ in range(300):
            nested = {"state": nested}
        before = fixture()
        before["modules"][0]["data"] = nested
        with self.assertRaisesRegex(PatchComparisonError, "nesting depth"):
            compare_patches(before, fixture())

        script = ROOT / "tools" / "patches" / "patch_compare.py"
        with tempfile.TemporaryDirectory() as directory:
            p1, p2 = Path(directory) / "deep.vcv", Path(directory) / "plain.vcv"
            huge = '[' * 1200 + '0' + ']' * 1200
            p1.write_text('{"modules":[{"id":1,"plugin":"Cardinal",'
                          '"model":"HostMIDI","data":' + huge + '}],"cables":[]}',
                          encoding="utf-8")
            p2.write_text(json.dumps(fixture()), encoding="utf-8")
            result = subprocess.run([sys.executable, str(script), str(p1), str(p2)],
                                    cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("ERROR:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_generated_invalid_port_ids_and_id_collisions_fail_closed(self) -> None:
        # The comparator does not know a third-party module's *port range*,
        # but cable endpoints themselves must be nonnegative integer IDs.
        rng = random.Random(0xD3ADBEEF)
        invalid = ([], [0], {"id": 0}, "0", -1, True,
                   float("nan"), float("inf"), 1.5, None)
        cable_keys = ("inputId", "outputId", "inputModuleId", "outputModuleId")
        for key in cable_keys:
            for replacement in invalid:
                with self.subTest(field=key, value=repr(replacement)):
                    bad = fixture()
                    rng.choice(bad["cables"])[key] = replacement
                    with self.assertRaises(PatchComparisonError):
                        compare_patches(bad, fixture())

        for field in ("module", "parameter", "cable"):
            for _ in range(16):
                bad = fixture()
                if field == "module":
                    victim, duplicate = rng.sample(bad["modules"], 2)
                    victim["id"] = duplicate["id"]
                elif field == "parameter":
                    entry = bad["modules"][1]["params"]
                    entry.append(copy.deepcopy(rng.choice(entry)))
                else:
                    victim, duplicate = rng.sample(bad["cables"], 2)
                    victim["id"] = duplicate["id"]
                with self.subTest(field=field):
                    with self.assertRaises(PatchComparisonError):
                        compare_patches(bad, fixture())

    def test_same_model_reidentification_preserves_one_real_parameter_edit(self) -> None:
        before = patch([module(1, "Fundamental", "VCA-1", {0: 0.2}),
                        module(2, "Fundamental", "VCA-1", {0: 0.8}),
                        module(3, "Cardinal", "HostAudio2")],
                       [cable(10, 1, 0, 3, 0), cable(11, 2, 0, 3, 1)])
        rng = random.Random(0x600D)
        for _ in range(48):
            after = copy.deepcopy(before)
            remap = {1: rng.randrange(100, 100000),
                     2: rng.randrange(100000, 200000),
                     3: rng.randrange(200000, 300000)}
            for mod in after["modules"]:
                if mod["id"] == 2:
                    mod["params"][0]["value"] = 0.75
                mod["id"] = remap[mod["id"]]
            for wire in after["cables"]:
                wire["outputModuleId"] = remap[wire["outputModuleId"]]
                wire["inputModuleId"] = remap[wire["inputModuleId"]]
            rng.shuffle(after["modules"])
            rng.shuffle(after["cables"])
            report = compare_patches(before, after)
            self.assertEqual(report["summary"]["parameters_changed"], 1)
            self.assertEqual(report["summary"]["modules_added"], 0)
            self.assertEqual(report["summary"]["modules_removed"], 0)
            self.assertEqual(report["summary"]["cables_added"], 0)
            self.assertEqual(report["summary"]["cables_removed"], 0)
            self.assertTrue(report["summary"]["changed"])

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

    def test_host_midi_saved_configuration_must_not_be_silently_ignored(self) -> None:
        before = fixture()
        before["modules"][0]["data"] = {"channels": 1, "mapping": {"note": 0, "cc": [1, 74]}}
        after = copy.deepcopy(before)
        after["modules"][0]["data"]["channels"] = 8
        after["modules"][0]["data"]["mapping"]["cc"][1] = 71
        report = compare_patches(before, after)
        self.assertTrue(report["summary"]["changed"])
        self.assertEqual(report["summary"]["persisted_state_changed"], 2)
        self.assertEqual([entry["field"] for entry in report["modules"]["persisted_state"]],
                         ["data.channels", "data.mapping.cc[1]"])
        self.assertIn("data.channels: 1 -> 8", format_report(report))

    def test_module_bypass_and_version_are_conservatively_reported(self) -> None:
        before = fixture()
        after = copy.deepcopy(before)
        after["modules"][1]["bypass"] = True
        after["modules"][1]["version"] = "2.5.0"
        report = compare_patches(before, after)
        self.assertEqual(report["summary"]["persisted_state_changed"], 2)
        self.assertEqual([entry["field"] for entry in report["modules"]["persisted_state"]],
                         ["module.bypass", "module.version"])
        self.assertTrue(report["summary"]["changed"])

    def test_unknown_macro8_state_fields_are_reported_without_double_count(self) -> None:
        before = fixture()
        after = copy.deepcopy(before)
        data = next(m["data"] for m in after["modules"] if m["model"] == "Macro8")
        data["futureControls"] = {"learnedCC": 3}
        data["selectedSlot"] = 1
        report = compare_patches(before, after)
        self.assertEqual(report["summary"]["macro8_state_changed"], 1)
        self.assertEqual(report["summary"]["persisted_state_changed"], 1)
        self.assertEqual(report["modules"]["persisted_state"][0]["field"],
                         "data.futureControls")

    def test_global_saved_state_is_reported_but_view_only_fields_are_ignored(self) -> None:
        before = fixture()
        before["midiMappings"] = {"preset": {"cc": 11}}
        after = copy.deepcopy(before)
        after["midiMappings"]["preset"]["cc"] = 74
        after["zoom"] = 0.4
        after["offset"] = [99, 88]
        report = compare_patches(before, after)
        self.assertEqual(report["summary"]["patch_state_changed"], 1)
        self.assertEqual(report["patch_state"][0]["field"], "patch.midiMappings.preset.cc")
        self.assertIn("patch.midiMappings.preset.cc: 11 -> 74", format_report(report))

    def test_saved_state_dict_order_and_json_roundtrip_are_stable(self) -> None:
        before = fixture()
        before["modules"][0]["data"] = {"b": [{"y": 2, "x": 1}], "a": True}
        before["custom"] = {"two": [4, 5], "one": 1}
        after = json.loads(json.dumps(before, sort_keys=True))
        self.assertFalse(compare_patches(before, after)["summary"]["changed"])

    def test_saved_state_nested_list_order_is_musically_relevant(self) -> None:
        before = fixture()
        before["modules"][0]["data"] = {"steps": [0, 7, 12]}
        after = copy.deepcopy(before)
        after["modules"][0]["data"]["steps"] = [7, 0, 12]
        report = compare_patches(before, after)
        self.assertEqual([entry["field"] for entry in report["modules"]["persisted_state"]],
                         ["data.steps[0]", "data.steps[1]"])

    def test_json_boolean_is_not_interchangeable_with_numeric_zero_or_one(self) -> None:
        before = fixture()
        before["modules"][0]["data"] = {"enabled": True, "muted": False, "depth": 1}
        after = copy.deepcopy(before)
        after["modules"][0]["data"].update({"enabled": 1, "muted": 0, "depth": 1.0})
        report = compare_patches(before, after)
        self.assertEqual([entry["field"] for entry in report["modules"]["persisted_state"]],
                         ["data.enabled", "data.muted"])

    def test_missing_and_empty_module_data_have_same_default(self) -> None:
        before = fixture()
        after = copy.deepcopy(before)
        after["modules"][0]["data"] = {}
        self.assertFalse(compare_patches(before, after)["summary"]["changed"])

    def test_unknown_parameter_entry_fields_are_tracked_by_parameter_id(self) -> None:
        before = fixture()
        before["modules"][1]["params"][0]["hostMapping"] = {"cc": [7, 74]}
        after = copy.deepcopy(before)
        after["modules"][1]["params"].reverse()
        after["modules"][1]["params"][1]["hostMapping"]["cc"][1] = 71
        after["modules"][1]["params"][1]["locked"] = True
        report = compare_patches(before, after)
        self.assertEqual(report["summary"]["persisted_state_changed"], 2)
        self.assertEqual([entry["field"] for entry in report["modules"]["persisted_state"]],
                         ["param[0].hostMapping.cc[1]", "param[0].locked"])
        self.assertEqual(report["summary"]["parameters_changed"], 0)

    def test_unknown_cable_metadata_is_detected_without_ids_or_colors(self) -> None:
        before = fixture()
        before["cables"][0]["routing"] = {"gain": 1.0, "enabled": True}
        after = copy.deepcopy(before)
        after["cables"][0]["routing"]["gain"] = 0.5
        after["cables"][0]["routing"]["enabled"] = 1
        after["cables"][0]["id"] = 999
        after["cables"][0]["color"] = "#ffffff"
        report = compare_patches(before, after)
        self.assertEqual(report["summary"]["cable_state_changed"], 2)
        self.assertEqual([x["field"] for x in report["cables"]["saved_state"]],
                         ["cable.routing.enabled", "cable.routing.gain"])
        self.assertEqual(report["summary"]["cables_added"], 0)
        self.assertIn("cable.routing.gain: 1.0 -> 0.5", format_report(report))

    def test_duplicate_cable_metadata_is_order_independent_and_grouped(self) -> None:
        before = fixture()
        before["cables"][0]["modulation"] = {"level": 1, "enabled": True}
        duplicate = copy.deepcopy(before["cables"][0])
        duplicate["id"] = 99
        duplicate["modulation"] = {"level": 2, "enabled": False}
        before["cables"].append(duplicate)
        after = copy.deepcopy(before)
        after["cables"].reverse()
        for wire in after["cables"]:
            wire["id"] += 1000
        self.assertFalse(compare_patches(before, after)["summary"]["changed"])
        after["cables"][-1]["modulation"]["level"] = 3
        report = compare_patches(before, after)
        self.assertEqual(report["summary"]["cable_state_changed"], 1)
        self.assertEqual(report["cables"]["saved_state"][0]["field"], "cable.metadata")
        self.assertEqual(report["summary"]["cables_added"], 0)
        self.assertEqual(report["summary"]["cables_removed"], 0)

    def test_cable_metadata_numeric_equivalence_and_type_distinction(self) -> None:
        before = fixture()
        extra = copy.deepcopy(before["cables"][0])
        extra["id"] = 999
        before["cables"].append(extra)
        before["cables"][0]["routeMode"] = 1
        before["cables"][-1]["routeMode"] = 0
        after = copy.deepcopy(before)
        after["cables"][0]["routeMode"] = 1.0
        self.assertFalse(compare_patches(before, after)["summary"]["changed"])
        after["cables"][0]["routeMode"] = True
        self.assertEqual(compare_patches(before, after)["summary"]["cable_state_changed"], 1)

    def test_rewired_cable_does_not_double_report_saved_state(self) -> None:
        before = fixture()
        before["cables"][0]["gain"] = 0.1
        after = copy.deepcopy(before)
        after["cables"][0]["outputId"] = 1
        after["cables"][0]["gain"] = 0.9
        report = compare_patches(before, after)
        self.assertEqual(report["summary"]["cable_state_changed"], 0)
        self.assertEqual(report["summary"]["cables_added"], 1)
        self.assertEqual(report["summary"]["cables_removed"], 1)

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

    def test_unique_saved_state_reidentifies_duplicate_models_after_id_regeneration(self) -> None:
        # Rack can regenerate every module ID when reloading a project.
        # Distinct saved knob/snapshot state is strong enough to pair the two
        # same-model instances without guessing from their new IDs or layout.
        before = patch([
            module(1, "Fundamental", "VCA-1", {0: 0.2}, {"mode": "left"}),
            module(2, "Fundamental", "VCA-1", {0: 0.8}, {"mode": "right"}),
            module(3, "Cardinal", "HostAudio2"),
        ], [cable(10, 1, 0, 3, 0), cable(11, 2, 0, 3, 1)])
        after = copy.deepcopy(before)
        mapping = {1: 101, 2: 102, 3: 103}
        for entry in after["modules"]:
            entry["id"] = mapping[entry["id"]]
            entry["pos"] = [999, 0]
        for entry in after["cables"]:
            entry["outputModuleId"] = mapping[entry["outputModuleId"]]
            entry["inputModuleId"] = mapping[entry["inputModuleId"]]
        after["modules"].reverse()
        after["cables"].reverse()
        report = compare_patches(before, after)
        self.assertFalse(report["summary"]["changed"])
        self.assertEqual(report["summary"]["matched_modules"], 3)
        self.assertEqual(report["summary"]["id_remaps_ignored"], 3)

        # With identities recovered, a genuine cable rewire is still visible.
        altered = copy.deepcopy(after)
        for wire in altered["cables"]:
            wire["inputId"] = 1 - wire["inputId"]
        changed = compare_patches(before, altered)
        self.assertEqual(changed["summary"]["cables_added"], 2)
        self.assertEqual(changed["summary"]["cables_removed"], 2)
        self.assertEqual(changed["summary"]["modules_added"], 0)

        # One regenerated duplicate also has an edited parameter. After the
        # exact-state peer is paired, the remaining model is unambiguous and
        # must be reported as an edit, not a module removal/reinsertion.
        edited = copy.deepcopy(after)
        next(entry for entry in edited["modules"] if entry["id"] == 101)["params"][0]["value"] = 0.3
        edited_report = compare_patches(before, edited)
        self.assertEqual(edited_report["summary"]["matched_modules"], 3)
        self.assertEqual(edited_report["summary"]["parameters_changed"], 1)
        self.assertEqual(edited_report["summary"]["modules_added"], 0)

    def test_duplicate_model_matching_remains_conservative_if_state_ambiguous(self) -> None:
        before = patch([
            module(1, "Fundamental", "VCA-1", {0: 0.5}),
            module(2, "Fundamental", "VCA-1", {0: 0.5}),
        ], [])
        after = patch([
            module(11, "Fundamental", "VCA-1", {0: 0.5}),
            module(12, "Fundamental", "VCA-1", {0: 0.5}),
        ], [])
        report = compare_patches(before, after)
        self.assertEqual(report["summary"]["matched_modules"], 0)
        self.assertEqual(report["summary"]["modules_added"], 2)
        self.assertEqual(report["summary"]["modules_removed"], 2)

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
        case = fixture()
        case["modules"][0]["params"] = [{"id": 0, "value": 10**400}]
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
            saved = fixture()
            saved["modules"][0]["data"] = {"channels": 8}
            new_path.write_text(json.dumps(saved), encoding="utf-8")
            saved_changed = call("--json")
            self.assertEqual(saved_changed.returncode, 1, saved_changed.stderr)
            self.assertEqual(json.loads(saved_changed.stdout)["summary"]["persisted_state_changed"], 1)
            new_path.write_text('{"modules": [], "modules": [], "cables": []}', encoding="utf-8")
            malformed = call()
            self.assertEqual(malformed.returncode, 2)
            self.assertIn("duplicate JSON object key", malformed.stderr)
            new_path.write_text('{"modules":[],"cables":[],"version":NaN}', encoding="utf-8")
            nonfinite = call()
            self.assertEqual(nonfinite.returncode, 2)
            self.assertIn("non-finite JSON literal", nonfinite.stderr)
            huge = fixture()
            huge["modules"][0]["params"] = [{"id": 0, "value": 10**400}]
            new_path.write_text(json.dumps(huge), encoding="utf-8")
            huge_result = call()
            self.assertEqual(huge_result.returncode, 2)
            self.assertIn("finite numeric", huge_result.stderr)
            self.assertNotIn("Traceback", huge_result.stderr)

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
