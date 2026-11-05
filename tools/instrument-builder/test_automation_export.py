"""Adversarial source-only Macro8 CV route automation export tests."""
from __future__ import annotations

import csv
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from automation_export import (AutomationExportError, CSV_FIELDS,
                               build_automation_export, text_automation_csv)
from instrument_builder import (InstrumentError, automation, create_bundle,
                                inspect, main)
from test_control_mapping import routed_patch
from test_instrument_builder import patch_bytes, sample_patch


def source_routed_patch() -> dict:
    patch = routed_patch()
    # Remove only the unknown third-party port. Every remaining direct cable
    # is checked against source model InputIds and configInput declarations.
    patch["cables"] = [x for x in patch["cables"] if x["id"] not in (72, 106)]
    return patch


class AutomationExportTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def saved(self, patch: dict | None = None, version: int = 2) -> Path:
        path = self.root / "source.msinstrument"
        path.write_bytes(create_bundle(
            patch_bytes(source_routed_patch() if patch is None else patch),
            "Performance route", format_version=version))
        return path

    def request(self, path: Path, **override: object) -> dict:
        flags = dict(source="A", event_spec="0:B,0.25:A,0.5:B",
                     time_spec="0,0.25,0.5,0.75", sample_rate=48000)
        flags.update(override)
        return automation(path, **flags)

    def test_sparse_route_matrix_is_sample_aligned_source_verifiable_and_deterministic(self) -> None:
        path = self.saved()
        before = path.read_bytes()
        report = self.request(path)
        self.assertEqual((report["routeCount"], report["sampleCount"], report["rowCount"]),
                         (4, 4, 16))
        self.assertIn("NOT measured Rack voltages", report["scope"])
        self.assertEqual([x["sampleCount"] for x in report["rows"][::4]],
                         [0, 12000, 24000, 36000])
        self.assertEqual([x["cableId"] for x in report["rows"][:4]],
                         [102, 103, 104, 105])
        self.assertEqual(report["rows"][0]["destinationInputLabel"],
                         "Wave morph CV (10 V full span; adds to knob)")
        self.assertEqual(report["rows"][0]["destinationInputKind"], "cv")
        self.assertEqual(report["rows"][0]["relatedKnobName"], "Wave morph position")
        self.assertEqual(report["rows"][0]["predictedNominalVolts"], 1.25)
        self.assertEqual(report["rows"][0]["activeTarget"], "B")
        self.assertEqual(report["rows"][1]["controlNumber"], 2)
        self.assertEqual(report["rows"][1]["predictedNominalVolts"], -3.75)
        self.assertEqual(report, self.request(path))
        self.assertEqual(path.read_bytes(), before)

    def test_source_cable_order_does_not_change_cv_export(self) -> None:
        original = source_routed_patch()
        path = self.saved(original)
        report = self.request(path)
        original["cables"].reverse()
        self.assertEqual(report["rows"], self.request(self.saved(original))["rows"])

    def test_cli_csv_and_json_match_programmatic_estimates(self) -> None:
        path = self.saved()
        expected = self.request(path)
        opts = ("--from", "A", "--events", "0:B,0.25:A,0.5:B", "--at",
                "0,0.25,0.5,0.75", "--sample-rate", "48000")
        import contextlib
        from io import StringIO as IO
        for fmt in ("json", "csv"):
            with contextlib.redirect_stdout(IO()) as out, contextlib.redirect_stderr(IO()) as err:
                code = main(["automation", str(path), *opts, "--format", fmt])
            self.assertEqual((code, err.getvalue()), (0, ""))
            if fmt == "json":
                self.assertEqual(json.loads(out.getvalue()), expected)
            else:
                self.assertEqual(out.getvalue(), text_automation_csv(expected))
                reader = csv.DictReader(StringIO(out.getvalue()))
                self.assertEqual(tuple(reader.fieldnames), CSV_FIELDS)
                rows = list(reader)
                self.assertEqual(len(rows), 16)
                self.assertEqual(rows[0]["sampleCount"], "0")
                self.assertEqual(rows[0]["cableId"], "102")

    def test_rejects_v1_unknown_destinations_and_no_direct_routes(self) -> None:
        with self.assertRaisesRegex(InstrumentError, "requires a v2 source bundle"):
            self.request(self.saved(version=1))
        with self.assertRaisesRegex(InstrumentError, "not source-verified"):
            self.request(self.saved(routed_patch()))
        import contextlib
        from io import StringIO as IO
        with contextlib.redirect_stdout(IO()) as out, contextlib.redirect_stderr(IO()) as err:
            status = main([
                "automation", str(self.root / "source.msinstrument"),
                "--from", "A", "--events", "0:B", "--at", "0,0.25",
                "--format", "csv",
            ])
        self.assertEqual((status, out.getvalue()), (2, ""))
        self.assertIn("not source-verified", err.getvalue())
        patch = sample_patch()
        patch["cables"] = []
        with self.assertRaisesRegex(InstrumentError, "no direct saved routes"):
            self.request(self.saved(patch))

    def test_missing_scene_and_sample_collisions_fail_closed(self) -> None:
        path = self.saved()
        with self.assertRaisesRegex(InstrumentError, "no stored snapshot C"):
            self.request(path, event_spec="0:C")
        with self.assertRaisesRegex(InstrumentError, "distinct increasing sample"):
            self.request(path, time_spec="0,0.000001", sample_rate=8000)
        with self.assertRaisesRegex(InstrumentError, "distinct increasing sample"):
            self.request(path, event_spec="0:A,0.000001:B", sample_rate=8000)
        with self.assertRaisesRegex(InstrumentError, "range 0..3600"):
            self.request(path, time_spec="NaN")

    def test_csv_names_are_formula_safe_while_json_retains_source_label(self) -> None:
        patch = source_routed_patch()
        patch["modules"][0]["data"]["names"][0] = "=SUM(1,2)"
        path = self.saved(patch)
        report = self.request(path)
        self.assertEqual(report["rows"][0]["controlName"], "=SUM(1,2)")
        rows = list(csv.DictReader(StringIO(text_automation_csv(report))))
        self.assertEqual(rows[0]["controlName"], "'=SUM(1,2)")

    def test_sparse_output_bound_and_module_selection(self) -> None:
        path = self.saved()
        manifest = inspect(path)
        # Synthetic verified fan-out beyond CLI's bounded row budget; no
        # untrusted bundle could emit this silently as a giant CSV.
        manifest = deepcopy(manifest)
        m = manifest["performance"]["controlMappings"]
        for i in range(36):
            entry = deepcopy(m[0])
            entry["cableId"] = 1000 + i
            entry["destination"]["moduleId"] = 1000 + i
            m.append(entry)
        times = [i / 1000 for i in range(256)]
        with self.assertRaisesRegex(AutomationExportError, "exceeds 8192 rows"):
            build_automation_export(
                manifest, source="A", events=[(0.0, "B")],
                query_times=times, sample_rate=48000)
        with self.assertRaisesRegex(InstrumentError, "no Macro8 module"):
            self.request(path, module_id=999999)

    def test_multiple_macro_modules_require_selected_source_and_only_its_verified_routes(self) -> None:
        patch = source_routed_patch()
        second = deepcopy(patch["modules"][0])
        second["id"] = 190
        second["data"]["names"][0] = "Glide"
        patch["modules"].append(second)
        patch["cables"].append({
            "id": 510, "outputModuleId": 190, "outputId": 0,
            "inputModuleId": 80, "inputId": 3,
        })
        path = self.saved(patch)
        with self.assertRaisesRegex(InstrumentError, "--module-id"):
            self.request(path)
        first = self.request(path, module_id=70)
        second = self.request(path, module_id=190)
        self.assertEqual((first["routeCount"], second["routeCount"]), (4, 1))
        self.assertEqual({r["macroModuleId"] for r in second["rows"]}, {190})
        self.assertEqual({r["controlName"] for r in second["rows"]}, {"Glide"})
        self.assertEqual({r["cableId"] for r in second["rows"]}, {510})


if __name__ == "__main__":
    unittest.main()
