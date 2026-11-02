"""Opt-in Macro8 source route gate: strict failures, legacy safety, stable output."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from compatibility import text_report
from instrument_builder import (
    MANIFEST_MEMBER, PATCH_MEMBER, build_manifest, check, create_bundle,
    inspect, main,
)
from test_control_mapping import clocked_lfo_patch, routed_patch
from test_instrument_builder import custom_archive, patch_bytes, sample_patch


ROOT = Path(__file__).resolve().parents[2]


def known_route_patch() -> dict:
    patch = sample_patch()
    patch["modules"][1] = {
        "id": 71, "plugin": "ModularSynth", "model": "MorphVCO",
    }
    patch["cables"][0]["inputId"] = 2
    return patch


class VerifiedRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def bundle(self, patch: dict, *, version: int = 2) -> Path:
        path = self.folder / "routes.msinstrument"
        path.write_bytes(create_bundle(
            patch_bytes(patch), "Routing Check", format_version=version))
        return path

    def test_verified_first_party_route_passes_without_export_claim(self) -> None:
        bundle = self.bundle(known_route_patch())
        report = check(bundle, ROOT, require_verified_routes=True)
        self.assertEqual(report["status"], "PASS")
        gate = report["verifiedRoutes"]
        self.assertEqual(gate["status"], "PASS")
        self.assertIsNone(gate["reason"])
        self.assertEqual(gate["summary"], {
            "total": 1, "sourceVerified": 1, "unverified": 0,
        })
        self.assertEqual(gate["routes"], [{
            "cableId": 72, "sourceModuleId": 70, "sourceOutputId": 0,
            "destinationModuleId": 71, "plugin": "ModularSynth",
            "model": "MorphVCO", "inputId": 2, "inputKind": "cv",
            "status": "SOURCE_VERIFIED",
        }])
        self.assertIn("not host automation", gate["scope"])
        text = text_report(report)
        self.assertIn("Strict Macro8 source route check: PASS", text)
        self.assertIn("SOURCE_VERIFIED", text)
        self.assertIn("not DAW parameter automation", text)

    def test_v2_mixed_routes_identify_every_unverified_cable_in_stable_order(self) -> None:
        patch = routed_patch()
        first = self.bundle(patch)
        report = check(first, ROOT, require_verified_routes=True)
        self.assertEqual(report["status"], "FAIL")
        gate = report["verifiedRoutes"]
        self.assertEqual(gate["reason"], "UNVERIFIED_DESTINATIONS")
        self.assertEqual(gate["summary"], {
            "total": 6, "sourceVerified": 4, "unverified": 2,
        })
        self.assertEqual([r["cableId"] for r in gate["routes"]],
                         [72, 102, 103, 104, 105, 106])
        unknown = [r for r in gate["routes"] if r["status"] == "UNVERIFIED"]
        self.assertEqual([(r["cableId"], r["plugin"], r["model"],
                           r["destinationModuleId"], r["inputId"])
                          for r in unknown], [
            (72, "Cardinal", "HostAudio2", 71, 0),
            (106, "OtherVendor", "OtherEffect", 83, 4096),
        ])
        text = text_report(report)
        self.assertIn("UNVERIFIED      cable 72", text)
        self.assertIn("UNVERIFIED      cable 106", text)

        patch["cables"].reverse()
        rewritten = self.folder / "reverse.msinstrument"
        rewritten.write_bytes(create_bundle(
            patch_bytes(patch), "Routing Check", format_version=2))
        other = check(rewritten, ROOT, require_verified_routes=True)
        self.assertEqual(other["verifiedRoutes"], gate)
        self.assertEqual(text_report(other), text)

    def test_v1_rejected_without_false_empty_route_claim(self) -> None:
        bundle = self.bundle(known_route_patch(), version=1)
        default = check(bundle, ROOT)
        self.assertEqual(default["status"], "PASS")
        self.assertNotIn("verifiedRoutes", default)
        strict = check(bundle, ROOT, require_verified_routes=True)
        self.assertEqual(strict["status"], "FAIL")
        routes = strict["verifiedRoutes"]
        self.assertEqual(routes["reason"], "V1_NO_ROUTE_CONTRACT")
        self.assertIsNone(routes["summary"]["total"])
        self.assertEqual(routes["routes"], [])
        self.assertIn("repack from source with --format-version 2",
                      text_report(strict))

    def test_empty_v2_route_list_fails_explicitly(self) -> None:
        patch = known_route_patch()
        patch["cables"] = []
        bundle = self.bundle(patch)
        strict = check(bundle, ROOT, require_verified_routes=True)
        routes = strict["verifiedRoutes"]
        self.assertEqual(strict["status"], "FAIL")
        self.assertEqual(routes["reason"], "NO_DIRECT_MACRO8_ROUTES")
        self.assertEqual(routes["summary"], {
            "total": 0, "sourceVerified": 0, "unverified": 0,
        })
        self.assertIn("No saved direct Macro8 output cables", text_report(strict))

    def test_clocked_lfo_marked_v2_passes_but_legacy_unmarked_fails(self) -> None:
        patch = clocked_lfo_patch()
        bundle = self.bundle(patch)
        gate = check(bundle, ROOT, require_verified_routes=True)["verifiedRoutes"]
        self.assertEqual(gate["status"], "PASS")
        self.assertEqual(gate["summary"]["total"], 5)
        self.assertEqual(gate["summary"]["sourceVerified"], 5)

        # Legacy v2 must retain its original UNVERIFIED port interpretation.
        raw = patch_bytes(patch)
        legacy = build_manifest(raw, "Clock Routes", format_version=2,
                                legacy_v2_mapping=True)
        encoded = (json.dumps(legacy, sort_keys=True, ensure_ascii=True,
                              allow_nan=False, indent=2) + "\n").encode("utf-8")
        original_bundle = custom_archive([
            (MANIFEST_MEMBER, encoded), (PATCH_MEMBER, raw),
        ])
        self.assertEqual(hashlib.sha256(original_bundle).hexdigest(),
                         "40cceaed8ce27ccdd24b6041f16e608648b36e97d7cb02203cd5c22e57bd1567")
        path = self.folder / "legacy.msinstrument"
        path.write_bytes(original_bundle)
        legacy_gate = check(path, ROOT, require_verified_routes=True)["verifiedRoutes"]
        self.assertEqual(legacy_gate["status"], "FAIL")
        self.assertEqual(legacy_gate["reason"], "UNVERIFIED_DESTINATIONS")
        self.assertEqual(legacy_gate["summary"]["unverified"], 5)
        self.assertEqual([r["cableId"] for r in legacy_gate["routes"]],
                         [120, 121, 122, 123, 124])
        self.assertTrue(all(r["status"] == "UNVERIFIED"
                            for r in legacy_gate["routes"]))
        self.assertEqual(path.read_bytes(), original_bundle)

    def test_non_macro8_cables_are_outside_direct_route_scope(self) -> None:
        patch = known_route_patch()
        patch["modules"].append(
            {"id": 82, "plugin": "Elsewhere", "model": "External"})
        patch["cables"].append({
            "id": 99, "outputModuleId": 82, "outputId": 4096,
            "inputModuleId": 71, "inputId": 4096,
        })
        gate = check(
            self.bundle(patch), ROOT, require_verified_routes=True)["verifiedRoutes"]
        self.assertEqual(gate["status"], "PASS")
        self.assertEqual([r["cableId"] for r in gate["routes"]], [72])

    def test_default_check_and_bundles_have_no_byte_or_report_change(self) -> None:
        patch = routed_patch()
        raw = patch_bytes(patch)
        path = self.bundle(patch)
        saved = path.read_bytes()
        manifest = inspect(path)
        self.assertEqual(saved, create_bundle(raw, "Routing Check", format_version=2))
        base = check(path, ROOT)
        self.assertEqual(base["status"], "PASS")
        self.assertNotIn("verifiedRoutes", base)
        self.assertEqual(base, check(path, ROOT, require_verified_routes=False))
        original_text = text_report(base)
        self.assertNotIn("Strict Macro8", original_text)
        self.assertEqual(inspect(path), manifest)
        strict = check(path, ROOT, require_verified_routes=True)
        self.assertEqual(strict["status"], "FAIL")
        self.assertEqual(path.read_bytes(), saved)
        self.assertEqual(check(path, ROOT), base)
        self.assertEqual(text_report(check(path, ROOT)), original_text)

    def test_cli_text_json_and_exit_statuses(self) -> None:
        path = self.bundle(routed_patch())
        for mode in ([], ["--format", "json"], ["--json"]):
            with self.subTest(mode=mode), redirect_stdout(StringIO()) as stream:
                self.assertEqual(main(["check", str(path),
                                       "--require-verified-routes", *mode]), 1)
                output = stream.getvalue()
                if mode:
                    parsed = json.loads(output)
                    self.assertEqual(parsed["verifiedRoutes"]["status"], "FAIL")
                    self.assertEqual(parsed["verifiedRoutes"]["routes"][0]["cableId"], 72)
                else:
                    self.assertIn("cable 106", output)
                    self.assertIn("Strict Macro8 source route check: FAIL", output)

        with redirect_stdout(StringIO()) as stream:
            self.assertEqual(main(["check", str(path)]), 0)
        self.assertNotIn("Strict Macro8", stream.getvalue())
        # CLI does not mutate the source bundle even on strict failure.
        self.assertEqual(path.read_bytes(), create_bundle(
            patch_bytes(routed_patch()), "Routing Check", format_version=2))

    def test_cli_strict_success_and_v1_rejection(self) -> None:
        known = self.bundle(known_route_patch())
        with redirect_stdout(StringIO()) as success:
            self.assertEqual(main(["check", str(known),
                                   "--require-verified-routes"]), 0)
        self.assertIn("source route check: PASS", success.getvalue())
        v1 = self.folder / "v1.msinstrument"
        v1.write_bytes(create_bundle(patch_bytes(known_route_patch()),
                                     "Routing Check", format_version=1))
        with redirect_stdout(StringIO()) as rejected:
            self.assertEqual(main(["check", str(v1),
                                   "--require-verified-routes"]), 1)
        self.assertIn("V1", json.dumps(check(
            v1, ROOT, require_verified_routes=True)))
        self.assertIn("repack from source", rejected.getvalue())


if __name__ == "__main__":
    unittest.main()
