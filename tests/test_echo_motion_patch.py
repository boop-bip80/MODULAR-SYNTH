"""Source-grounded Echo Motion preset contract and negative cable/data fixtures.

Saved VCV JSON only: no Cardinal host, MIDI performance, DSP, or audio audition.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "patches"))
import factory_patch_coverage as coverage  # noqa: E402
import patch_catalog  # noqa: E402

FILENAME = "MODULAR_-_Echo_Motion_Performance.vcv"


class EchoMotionCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.examples = Path(self.temp.name) / "examples"
        self.examples.mkdir()
        for filename in coverage.EXAMPLES:
            shutil.copyfile(ROOT / "patches" / "examples" / filename,
                            self.examples / filename)

    def mutate(self, edit) -> None:
        path = self.examples / FILENAME
        patch = json.loads(path.read_text(encoding="utf-8"))
        edit(patch)
        path.write_text(json.dumps(patch, indent=2), encoding="utf-8")

    def report(self) -> dict:
        return coverage.analyze(ROOT, self.examples)

    @staticmethod
    def unit(patch: dict, model: str) -> dict:
        matches = [m for m in patch["modules"]
                   if m.get("plugin") == "ModularSynth" and m.get("model") == model]
        if len(matches) != 1:
            raise AssertionError(f"expected one original {model}, found {len(matches)}")
        return matches[0]

    @staticmethod
    def params(module: dict) -> dict[int, float]:
        return {item["id"]: item["value"] for item in module["params"]}

    def test_full_graph_four_scenes_and_additive_cv_bounds(self) -> None:
        report = self.report()
        self.assertTrue(report["ok"], report["errors"])
        example = next(e for e in report["examples"] if e["patch"] == FILENAME)
        self.assertTrue(example["ok"], example["errors"])
        self.assertIn("4 versioned Macro8 snapshots", example["capabilities"])
        self.assertIn("documented Macro8 morph time", example["capabilities"])
        self.assertIn("two host audio input routes", example["capabilities"])
        for output in range(4):
            self.assertIn(f"unipolar Macro8 output {output} CV",
                          example["capabilities"])
        for label in ("Macro8 time CV to Echo input 2",
                      "Macro8 feedback CV to Echo input 3",
                      "Macro8 wet CV to Echo input 4",
                      "Macro8 wave CV to oscillator"):
            self.assertIn(label, example["capabilities"])
        patch = json.loads((self.examples / FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(len(patch["modules"]), 9)
        self.assertEqual(len(patch["cables"]), 13)
        echo = self.unit(patch, "StereoEcho")
        macro = self.unit(patch, "Macro8")
        oscillator = self.unit(patch, "MorphVCO")
        self.assertEqual(macro["data"]["macro8Version"], 1)
        self.assertEqual(macro["data"]["names"][:4],
                         ["Time", "Feedback", "Wet", "Wave"])
        self.assertEqual(macro["data"]["selectedSlot"], -1)  # LIVE on open
        self.assertAlmostEqual(self.params(macro)[8], 1.2)
        self.assertTrue(all(self.params(macro)[15 + i] == 0
                            for i in range(4)))
        baseline = self.params(echo)
        self.assertEqual(baseline, {0: 120, 1: 0.10, 2: 0.12, 3: 0.68})
        expected = ((190, 0.18, 0.28, 0.17),
                    (340, 0.28, 0.40, 0.35),
                    (550, 0.41, 0.48, 0.53),
                    (800, 0.54, 0.57, 0.67))
        slots = macro["data"]["snapshots"]
        self.assertEqual(len(slots), 4)
        for slot, (time_ms, feedback, wet, wave) in zip(slots, expected):
            with self.subTest(scene=expected.index((time_ms, feedback, wet, wave))):
                self.assertEqual(len(slot), 8)
                self.assertTrue(all(0 <= value <= 1 for value in slot))
                # Macro8 unipolar normalized knob -> +10V.
                # StereoEcho CV inputs 2/3/4 add 100 ms/V, 0.1/V, 0.1/V.
                actual = (baseline[0] + (slot[0] * 10) * 100,
                          baseline[1] + (slot[1] * 10) * 0.1,
                          baseline[2] + (slot[2] * 10) * 0.1,
                          self.params(oscillator)[2] + (slot[3] * 10) * 0.1)
                for got, exp in zip(actual, (time_ms, feedback, wet, wave)):
                    self.assertAlmostEqual(got, exp)
                self.assertLessEqual(actual[0], 1000)
                self.assertLessEqual(actual[1], 0.65)
                self.assertLessEqual(actual[2], 0.65)

    def test_all_three_echo_cv_ports_have_independent_exact_route_claims(self) -> None:
        expected = (
            (0, 2, "Macro8 time CV to Echo input 2"),
            (1, 3, "Macro8 feedback CV to Echo input 3"),
            (2, 4, "Macro8 wet CV to Echo input 4"),
        )
        source = ROOT / "patches" / "examples" / FILENAME
        for macro_output, echo_input, label in expected:
            with self.subTest(port=echo_input):
                shutil.copyfile(source, self.examples / FILENAME)

                def remove_cv(patch: dict) -> None:
                    macro_id = self.unit(patch, "Macro8")["id"]
                    echo_id = self.unit(patch, "StereoEcho")["id"]
                    patch["cables"] = [
                        c for c in patch["cables"] if not (
                            c["outputModuleId"] == macro_id
                            and c["outputId"] == macro_output
                            and c["inputModuleId"] == echo_id
                            and c["inputId"] == echo_input)
                    ]

                self.mutate(remove_cv)
                result = self.report()
                self.assertFalse(result["ok"])
                self.assertTrue(any(label in err for err in result["errors"]),
                                result["errors"])

    def test_missing_fourth_snapshot_fails_advertised_recall(self) -> None:
        self.mutate(lambda patch:
                    self.unit(patch, "Macro8")["data"]["snapshots"].__setitem__(3, None))
        report = self.report()
        self.assertFalse(report["ok"])
        self.assertTrue(any("missing documented Macro8 names" in err
                            for err in report["errors"]), report["errors"])

    def test_bipolar_time_cv_range_is_rejected(self) -> None:
        def make_bipolar(patch: dict) -> None:
            params = self.unit(patch, "Macro8")["params"]
            next(param for param in params if param["id"] == 15)["value"] = 1

        self.mutate(make_bipolar)
        report = self.report()
        self.assertFalse(report["ok"])
        self.assertTrue(any("macro output 0 CV range must be unipolar"
                            in err for err in report["errors"]), report["errors"])

    def test_disconnect_stereo_right_is_rejected(self) -> None:
        def disconnect(patch: dict) -> None:
            echo_id = self.unit(patch, "StereoEcho")["id"]
            patch["cables"] = [
                c for c in patch["cables"] if not (
                    c["outputModuleId"] == echo_id and c["outputId"] == 1
                    and c["inputModuleId"] == 1 and c["inputId"] == 1)
            ]

        self.mutate(disconnect)
        report = self.report()
        self.assertFalse(report["ok"])
        self.assertTrue(any("StereoEcho right into host right" in err
                            for err in report["errors"]), report["errors"])
        self.assertTrue(any("missing two saved HostAudio2 input routes" in err
                            for err in report["errors"]), report["errors"])

    def test_disconnect_midi_gate_is_rejected(self) -> None:
        def disconnect(patch: dict) -> None:
            adsr_id = next(m["id"] for m in patch["modules"]
                           if m.get("plugin") == "Fundamental"
                           and m.get("model") == "ADSR")
            patch["cables"] = [
                c for c in patch["cables"] if not (
                    c["outputModuleId"] == 2 and c["outputId"] == 1
                    and c["inputModuleId"] == adsr_id and c["inputId"] == 4)
            ]

        self.mutate(disconnect)
        report = self.report()
        self.assertFalse(report["ok"])
        self.assertTrue(any("MIDI gate to ADSR" in err
                            for err in report["errors"]), report["errors"])

    def test_dynamic_catalog_includes_echo_motion_without_catalog_edits(self) -> None:
        catalog = patch_catalog.collect(ROOT, self.examples)
        self.assertTrue(catalog["ok"], catalog["errors"])
        entry = next(e for e in catalog["patches"]
                     if e["file"].endswith("/" + FILENAME))
        self.assertEqual(entry["module_count"], 9)
        self.assertEqual(entry["cable_count"], 13)
        self.assertEqual(entry["macro8_stored_scenes"], 4)
        self.assertEqual(entry["midi_channels_saved"], 1)
        self.assertTrue(entry["midi_routed"])
        self.assertFalse(entry["host_transport_routed"])
        self.assertIn("StereoEcho", entry["original_modules"])
        self.assertIn("Macro8", entry["original_modules"])


if __name__ == "__main__":
    unittest.main()
