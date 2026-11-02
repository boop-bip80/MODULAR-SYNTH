"""Musician-facing Macro8 cable report: compatibility, safety and CLI tests."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from instrument_builder import (
    MANIFEST_MEMBER, PATCH_MEMBER, create_bundle, inspect, main,
)
from route_report import build_route_report, text_route_report
from test_control_mapping import routed_patch
from test_fold_drive_mapping import fold_drive_patch, old_bundle
from test_instrument_builder import custom_archive, patch_bytes
from test_verified_routes import known_route_patch


class ReadableRouteReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def saved(self, patch: dict, name: str = "Musician Routes", *,
              format_version: int = 2, filename: str = "instrument") -> Path:
        target = self.root / f"{filename}.msinstrument"
        target.write_bytes(create_bundle(
            patch_bytes(patch), name, format_version=format_version))
        return target

    def cli(self, target: Path, *options: str) -> tuple[int, str, str]:
        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
            status = main(["routes", str(target), *options])
            return status, stdout.getvalue(), stderr.getvalue()

    def test_verified_cv_report_names_real_macro_and_related_knob(self) -> None:
        saved = self.saved(known_route_patch())
        before = saved.read_bytes()
        manifest = inspect(saved)
        report = build_route_report(manifest)
        self.assertEqual(report["instrument"], "Musician Routes")
        self.assertEqual(report["bundleFormatVersion"], 2)
        self.assertEqual(report["verification"]["status"], "PASS")
        self.assertEqual(report["verification"]["summary"], {
            "total": 1, "sourceVerified": 1, "unverified": 0,
        })
        self.assertEqual(report["routes"], [{
            "cableId": 72,
            "macro": {
                "moduleId": 70, "number": 1,
                "name": "Shape", "range": "unipolar",
            },
            "destination": {
                "moduleId": 71, "plugin": "ModularSynth", "model": "MorphVCO",
                "inputId": 2, "kind": "cv",
                "label": "Wave morph CV (10 V full span; adds to knob)",
                "relatedKnob": {"id": 2, "name": "Wave morph position"},
            },
            "status": "SOURCE_VERIFIED",
        }])
        self.assertEqual(manifest, inspect(saved))  # no mutation of input
        code, view, errors = self.cli(saved)
        self.assertEqual((code, errors), (0, ""))
        self.assertIn("control 1 'Shape' (unipolar)", view)
        self.assertIn("Wave morph CV (10 V full span; adds to knob)", view)
        self.assertIn("source-related knob 2: Wave morph position", view)
        self.assertIn("not host automation", view)
        self.assertIn("not a live cardinal build", view.lower())
        self.assertEqual(saved.read_bytes(), before)

    def test_mixed_unknown_ports_are_described_not_promoted_to_verified(self) -> None:
        patch = routed_patch()
        saved = self.saved(patch)
        original = saved.read_bytes()
        report = build_route_report(inspect(saved))
        self.assertEqual(report["verification"]["status"], "FAIL")
        self.assertEqual(report["verification"]["reason"], "UNVERIFIED_DESTINATIONS")
        self.assertEqual(report["verification"]["summary"], {
            "total": 6, "sourceVerified": 4, "unverified": 2,
        })
        unknown = [r for r in report["routes"] if r["status"] == "UNVERIFIED"]
        self.assertEqual([(r["cableId"], r["destination"]["plugin"],
                           r["destination"]["inputId"]) for r in unknown], [
            (72, "Cardinal", 0), (106, "OtherVendor", 4096),
        ])
        self.assertTrue(all(r["destination"]["label"] is None
                            and r["destination"]["relatedKnob"] is None
                            for r in unknown))
        status, view, errors = self.cli(saved)
        # Reporting is informative; CI users have the separate strict check.
        self.assertEqual((status, errors), (0, ""))
        self.assertIn("6 saved; 4 source-verified; 2 unverified", view)
        self.assertIn("UNVERIFIED: input label and port semantics unknown", view)
        self.assertIn("check --require-verified-routes", view)
        self.assertEqual(saved.read_bytes(), original)

    def test_json_alias_is_stable_and_names_are_not_derived_from_text(self) -> None:
        saved = self.saved(routed_patch())
        code, output, errors = self.cli(saved, "--json")
        self.assertEqual((code, errors), (0, ""))
        parsed = json.loads(output)
        self.assertEqual(parsed, build_route_report(inspect(saved)))
        # Route order follows Macro8 controls, not saved cable IDs.
        self.assertEqual([r["cableId"] for r in parsed["routes"]],
                         [72, 102, 103, 104, 106, 105])
        # Patch cable array order is not a report-order dependency.
        reversed_patch = routed_patch()
        reversed_patch["cables"].reverse()
        reversed_file = self.saved(
            reversed_patch, filename="reversed")
        self.assertEqual(
            build_route_report(inspect(reversed_file))["routes"],
            parsed["routes"])
        self.assertNotIn("host automation mapping established", output)

    def test_v1_and_empty_v2_report_no_invented_routes(self) -> None:
        legacy = self.saved(
            known_route_patch(), format_version=1, filename="v1")
        status, view, errors = self.cli(legacy)
        self.assertEqual((status, errors), (0, ""))
        self.assertIn("No route metadata in v1", view)
        self.assertIn("pack --format-version 2", view)
        code, output, errors = self.cli(legacy, "--json")
        self.assertEqual((code, errors), (0, ""))
        report = json.loads(output)
        self.assertEqual(report["routes"], [])
        self.assertEqual(report["verification"]["reason"], "V1_NO_ROUTE_CONTRACT")
        self.assertIsNone(report["verification"]["summary"]["total"])

        no_routes = known_route_patch()
        no_routes["cables"] = []
        empty = self.saved(no_routes, filename="empty")
        status, view, errors = self.cli(empty)
        self.assertEqual((status, errors), (0, ""))
        self.assertIn("No direct Macro8 output cables", view)
        self.assertIn("0 saved; 0 source-verified; 0 unverified", view)
        self.assertEqual(build_route_report(inspect(empty))["verification"]["reason"],
                         "NO_DIRECT_MACRO8_ROUTES")

    def test_historical_unmarked_fold_routes_stay_unverified(self) -> None:
        source = fold_drive_patch()
        old = old_bundle(source, "Historical", old_clocked=True, old_fold=True)
        path = self.root / "old.msinstrument"
        path.write_bytes(old)
        report = build_route_report(inspect(path))
        self.assertIsNone(report["mappingContract"])
        self.assertEqual(report["verification"]["summary"], {
            "total": 4, "sourceVerified": 0, "unverified": 4,
        })
        self.assertTrue(all(row["status"] == "UNVERIFIED"
                            for row in report["routes"]))
        _, display, errors = self.cli(path)
        self.assertEqual(errors, "")
        self.assertNotIn("Sine fold drive", display)
        self.assertIn("4 unverified", display)
        self.assertEqual(path.read_bytes(), old)

    def test_invalid_zip_and_forged_manifest_fail_before_any_report(self) -> None:
        broken = self.root / "broken.msinstrument"
        broken.write_bytes(b"not a zip file")
        status, output, errors = self.cli(broken)
        self.assertEqual((status, output), (2, ""))
        self.assertIn("invalid ZIP", errors)

        raw = patch_bytes(known_route_patch())
        genuine = create_bundle(raw, "Source", format_version=2)
        from io import BytesIO
        import zipfile
        with zipfile.ZipFile(BytesIO(genuine)) as archive:
            entries = [(name, archive.read(name)) for name in archive.namelist()]
        forged_manifest = json.loads(dict(entries)[MANIFEST_MEMBER])
        forged_manifest["performance"]["controlMappings"][0]["destination"][
            "inputLabel"] = "DAW automation certified"
        forged = custom_archive([
            (name, json.dumps(forged_manifest).encode("utf-8")
             if name == MANIFEST_MEMBER else blob)
            for name, blob in entries
        ])
        self.assertIn(PATCH_MEMBER, dict(entries))
        tampered = self.root / "tampered.msinstrument"
        tampered.write_bytes(forged)
        status, output, errors = self.cli(tampered, "--json")
        self.assertEqual((status, output), (2, ""))
        self.assertIn("manifest does not match its patch", errors)


if __name__ == "__main__":
    unittest.main()
