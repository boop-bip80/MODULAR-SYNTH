"""Source-only Macro8 control inventory regressions and CLI safety tests."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from control_report import build_control_report, text_control_report
from instrument_builder import MANIFEST_MEMBER, create_bundle, inspect, main
from test_control_mapping import routed_patch
from test_instrument_builder import custom_archive, patch_bytes, sample_patch


class SavedControlsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def saved(self, patch: dict, *, version: int = 1,
              name: str = "Performance", filename: str = "patch") -> Path:
        path = self.root / f"{filename}.msinstrument"
        path.write_bytes(create_bundle(
            patch_bytes(patch), name, format_version=version))
        return path

    def cli(self, bundle: Path, *options: str) -> tuple[int, str, str]:
        with redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as error:
            code = main(["controls", str(bundle), *options])
            return code, output.getvalue(), error.getvalue()

    def test_v1_lists_every_control_but_never_invents_cable_counts(self) -> None:
        saved = self.saved(sample_patch())
        before = saved.read_bytes()
        report = build_control_report(inspect(saved))
        self.assertEqual(report["instrument"], "Performance")
        self.assertEqual(report["bundleFormatVersion"], 1)
        self.assertEqual(len(report["controllers"]), 1)
        controller = report["controllers"][0]
        self.assertEqual(controller["selectedSource"], "A")
        self.assertEqual(controller["snapshotAction"], "recall")
        self.assertEqual(controller["storedSlots"], ["A", "B"])
        self.assertEqual(len(controller["controls"]), 8)
        shape = controller["controls"][0]
        self.assertEqual(shape["name"], "Shape")
        self.assertEqual(shape["live"], {
            "normalized": 0.25, "nominalVolts": 2.5})
        self.assertEqual(shape["savedTarget"], {
            "source": "A", "normalized": 0.125, "nominalVolts": 1.25})
        self.assertEqual(shape["snapshots"]["B"]["normalized"], 0.75)
        self.assertIsNone(shape["snapshots"]["C"])
        self.assertIsNone(shape["routes"])
        code, output, error = self.cli(saved)
        self.assertEqual((code, error), (0, ""))
        self.assertIn("saved A target 0.125", output)
        self.assertIn("routes unknown (v1)", output)
        self.assertIn("not measure emitted CV", output)
        self.assertEqual(saved.read_bytes(), before)

    def test_bipolar_and_live_target_keep_saved_snapshots_separate(self) -> None:
        patch = sample_patch()
        macro = patch["modules"][0]
        macro["params"][15]["value"] = 1.0  # Control 1 becomes bipolar.
        macro["data"]["selectedSlot"] = -1  # LIVE, not stored scene A/B.
        report = build_control_report(inspect(self.saved(patch)))
        control = report["controllers"][0]["controls"][0]
        self.assertEqual(control["range"], "bipolar")
        self.assertEqual(control["live"]["nominalVolts"], -2.5)
        self.assertEqual(control["savedTarget"], {
            "source": "LIVE", "normalized": 0.25, "nominalVolts": -2.5})
        self.assertEqual(control["snapshots"]["A"]["nominalVolts"], -3.75)
        self.assertEqual(control["snapshots"]["B"]["nominalVolts"], 2.5)

        macro["data"]["selectedSlot"] = 1
        report = build_control_report(inspect(
            self.saved(patch, filename="selected_B")))
        self.assertEqual(report["controllers"][0]["selectedSource"], "B")
        self.assertEqual(
            report["controllers"][0]["controls"][0]["savedTarget"],
            {"source": "B", "normalized": 0.75, "nominalVolts": 2.5})

    def test_v2_counts_saved_direct_fanout_and_unverified_ports(self) -> None:
        saved = self.saved(routed_patch(), version=2)
        report = build_control_report(inspect(saved))
        controls = report["controllers"][0]["controls"]
        self.assertEqual(controls[0]["routes"], {
            "total": 2, "sourceVerified": 1, "unverified": 1,
        })
        self.assertEqual(controls[1]["routes"], {
            "total": 1, "sourceVerified": 1, "unverified": 0,
        })
        self.assertEqual(controls[3]["routes"], {
            "total": 0, "sourceVerified": 0, "unverified": 0,
        })
        self.assertEqual(controls[4]["routes"], {
            "total": 1, "sourceVerified": 0, "unverified": 1,
        })
        code, stdout, error = self.cli(saved, "--json")
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(json.loads(stdout), report)
        self.assertIn("NOT live CV measurements", stdout)
        self.assertEqual(
            text_control_report(report).count("source-verified, "), 8)

    def test_empty_v2_routes_differ_from_unknown_v1_routes(self) -> None:
        patch = sample_patch()
        patch["cables"] = []
        no_routes = self.saved(patch, version=2, filename="no_routes")
        report = build_control_report(inspect(no_routes))
        self.assertTrue(all(control["routes"]["total"] == 0
                            for control in report["controllers"][0]["controls"]))
        code, output, error = self.cli(no_routes)
        self.assertEqual((code, error), (0, ""))
        self.assertIn("0 saved routes (0 source-verified, 0 unverified)", output)
        self.assertNotIn("routes unknown", output)

    def test_multiple_controllers_sorted_and_cli_repeatable(self) -> None:
        patch = sample_patch()
        macro = deepcopy(patch["modules"][0])
        macro["id"] = 12
        macro["data"]["names"][0] = "Second"
        patch["modules"].append(macro)
        saved = self.saved(patch, version=2)
        original = saved.read_bytes()
        first = build_control_report(inspect(saved))
        self.assertEqual(
            [controller["moduleId"] for controller in first["controllers"]],
            [12, 70])
        self.assertEqual(first["controllers"][0]["controls"][0]["name"], "Second")
        result_a = self.cli(saved, "--json")
        result_b = self.cli(saved, "--json")
        self.assertEqual(result_a, result_b)
        self.assertEqual(result_a[0], 0)
        self.assertEqual(saved.read_bytes(), original)

    def test_invalid_or_forged_bundle_produces_no_inventory(self) -> None:
        invalid = self.root / "invalid.msinstrument"
        invalid.write_bytes(b"not a ZIP")
        code, output, error = self.cli(invalid, "--json")
        self.assertEqual((code, output), (2, ""))
        self.assertIn("invalid ZIP", error)

        genuine = create_bundle(patch_bytes(), "Genuine", format_version=2)
        with zipfile.ZipFile(BytesIO(genuine)) as source:
            entries = [(name, source.read(name)) for name in source.namelist()]
        manifest = json.loads(dict(entries)[MANIFEST_MEMBER])
        manifest["performance"]["macro8"][0]["liveValues"][0] = 0.99
        tampered = custom_archive([
            (name, json.dumps(manifest).encode("utf-8")
             if name == MANIFEST_MEMBER else content)
            for name, content in entries
        ])
        fake = self.root / "forged.msinstrument"
        fake.write_bytes(tampered)
        code, output, error = self.cli(fake)
        self.assertEqual((code, output), (2, ""))
        self.assertIn("manifest does not match its patch", error)


if __name__ == "__main__":
    unittest.main()
