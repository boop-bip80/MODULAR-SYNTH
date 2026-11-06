"""Fail-closed saved stereo HostAudio2 export/check; never an audio test."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from instrument_builder import check, create_bundle, main, read_bundle
from stereo_host_routes import stereo_host_route_report
from test_instrument_builder import patch_bytes, sample_patch


ROOT = Path(__file__).resolve().parents[2]


def stereo_patch() -> dict:
    patch = sample_patch()
    patch["modules"].append({
        "id": 80, "plugin": "ModularSynth", "model": "MorphVCO",
    })
    patch["cables"] = [
        {"id": 72, "outputModuleId": 70, "outputId": 0,
         "inputModuleId": 80, "inputId": 0},
        {"id": 81, "outputModuleId": 80, "outputId": 0,
         "inputModuleId": 71, "inputId": 0},
        {"id": 82, "outputModuleId": 80, "outputId": 1,
         "inputModuleId": 71, "inputId": 1},
    ]
    return patch


class StereoHostRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)

    def bundle(self, patch: dict, version: int = 1) -> Path:
        path = self.folder / f"source-v{version}.msinstrument"
        path.write_bytes(create_bundle(
            patch_bytes(patch), "Stereo Source", format_version=version))
        return path

    def test_both_ports_require_distinct_terminal_proofs_with_trace_ids(self) -> None:
        for version in (1, 2):
            with self.subTest(version=version):
                path = self.bundle(stereo_patch(), version)
                original = path.read_bytes()
                report = check(path, ROOT, require_verified_stereo_host_routes=True)
                self.assertEqual(report["status"], "PASS")
                gate = report["verifiedStereoHostRoutes"]
                self.assertEqual(gate["status"], "PASS")
                self.assertIsNone(gate["reason"])
                self.assertEqual(gate["summary"], {
                    "hostModules": 1, "verifiedStereoHosts": 1,
                    "sourceVerifiedTerminalInputs": 2,
                    "missingTerminalInputs": 0,
                    "unverifiedWiredTerminalInputs": 0,
                })
                self.assertEqual(gate["hosts"][0]["sourceVerifiedInputs"], [0, 1])
                self.assertEqual(gate["hosts"][0]["generatorTraces"], [
                    {"generatorModuleId": 80, "generatorModel": "ModularSynth/MorphVCO",
                     "hostInputPort": 0, "cables": [81]},
                    {"generatorModuleId": 80, "generatorModel": "ModularSynth/MorphVCO",
                     "hostInputPort": 1, "cables": [82]},
                ])
                self.assertIn("NOT a test of audible audio", gate["scope"])
                self.assertEqual(path.read_bytes(), original)

    def test_unpatched_right_is_failed_and_reported_as_unpatched(self) -> None:
        patch = stereo_patch()
        patch["cables"] = patch["cables"][:-1]
        path = self.bundle(patch)
        self.assertEqual(check(path, ROOT)["status"], "PASS")
        gate = check(path, ROOT, require_verified_stereo_host_routes=True)[
            "verifiedStereoHostRoutes"]
        self.assertEqual(gate["reason"], "UNVERIFIED_STEREO_HOST_INPUTS")
        self.assertEqual(gate["hosts"][0]["sourceVerifiedInputs"], [0])
        self.assertEqual(gate["hosts"][0]["missingInputs"], [1])
        self.assertEqual(gate["summary"]["missingTerminalInputs"], 1)

    def test_cv_wired_right_is_not_mislabeled_as_audio(self) -> None:
        patch = stereo_patch()
        patch["cables"][-1]["outputModuleId"] = 70
        patch["cables"][-1]["outputId"] = 1
        gate = check(self.bundle(patch), ROOT,
                     require_verified_stereo_host_routes=True)["verifiedStereoHostRoutes"]
        self.assertEqual(gate["status"], "FAIL")
        self.assertEqual(gate["hosts"][0]["wiredInputs"], [0, 1])
        self.assertEqual(gate["hosts"][0]["unverifiedWiredInputs"], [1])
        self.assertEqual(gate["summary"]["unverifiedWiredTerminalInputs"], 1)

    def test_opaque_third_party_chain_fails_closed(self) -> None:
        patch = stereo_patch()
        patch["modules"].append({
            "id": 90, "plugin": "ThirdParty", "model": "OpaqueEffect"})
        # Even with a source-backed voice feeding the unknown DSP, this
        # second host terminal cannot become source-verified by graph reachability.
        patch["cables"][-1]["outputModuleId"] = 90
        patch["cables"][-1]["outputId"] = 0
        patch["cables"].append({
            "id": 83, "outputModuleId": 80, "outputId": 1,
            "inputModuleId": 90, "inputId": 0})
        report = check(self.bundle(patch), ROOT,
                       require_verified_stereo_host_routes=True)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["verifiedStereoHostRoutes"]["hosts"][0][
            "unverifiedWiredInputs"], [1])
        self.assertTrue(any(ref["plugin"] == "ThirdParty"
                            and ref["status"] == "UNKNOWN"
                            for ref in report["references"]))

    def test_every_host_must_be_complete_and_host_is_required(self) -> None:
        patch = stereo_patch()
        patch["modules"].append({
            "id": 75, "plugin": "Cardinal", "model": "HostAudio2"})
        gate = check(self.bundle(patch), ROOT,
                     require_verified_stereo_host_routes=True)["verifiedStereoHostRoutes"]
        self.assertEqual(gate["status"], "FAIL")
        self.assertEqual([host["moduleId"] for host in gate["hosts"]], [71, 75])
        self.assertEqual([host["status"] for host in gate["hosts"]], ["PASS", "FAIL"])
        self.assertEqual(gate["hosts"][1]["missingInputs"], [0, 1])

        patch["modules"] = [m for m in patch["modules"] if m["model"] != "HostAudio2"]
        patch["cables"] = patch["cables"][:1]
        gate = check(self.bundle(patch), ROOT,
                     require_verified_stereo_host_routes=True)["verifiedStereoHostRoutes"]
        self.assertEqual(gate["reason"], "NO_HOST_AUDIO2")

    def test_duplicate_cable_input_fails_patch_inspector_not_just_stereo_count(self) -> None:
        patch = stereo_patch()
        patch["cables"].append({
            "id": 84, "outputModuleId": 80, "outputId": 1,
            "inputModuleId": 71, "inputId": 1})
        # A v1 source bundle may represent this saved JSON, but strict
        # inspection rejects the duplicate Rack input rather than trusting it.
        gate = check(self.bundle(patch), ROOT,
                     require_verified_stereo_host_routes=True)["verifiedStereoHostRoutes"]
        self.assertEqual(gate["status"], "FAIL")
        self.assertEqual(gate["reason"], "PATCH_INSPECTION_FAILED")
        self.assertTrue(any("duplicate connection to input" in err
                            for err in gate["errors"]))

    def test_contract_drift_is_unknown_and_never_passes(self) -> None:
        patch = stereo_patch()
        gate = stereo_host_route_report(patch_bytes(patch), self.folder)
        self.assertEqual(gate["status"], "FAIL")
        self.assertFalse(gate["hostContractVerified"])
        self.assertIn(gate["reason"],
                      {"HOST_CONTRACT_UNVERIFIED", "PATCH_INSPECTION_FAILED"})

    def test_stable_gate_order_no_temp_paths_and_original_default_unchanged(self) -> None:
        patch = stereo_patch()
        path = self.bundle(patch, 2)
        original = path.read_bytes()
        plain = check(path, ROOT)
        self.assertNotIn("verifiedStereoHostRoutes", plain)
        gate = check(path, ROOT, require_verified_stereo_host_routes=True)[
            "verifiedStereoHostRoutes"]
        rearranged = deepcopy(patch)
        rearranged["modules"].reverse()
        rearranged["cables"].reverse()
        second = self.folder / "reordered.msinstrument"
        second.write_bytes(create_bundle(patch_bytes(rearranged),
                                         "Stereo Source", format_version=2))
        self.assertEqual(check(second, ROOT,
                               require_verified_stereo_host_routes=True)[
                                   "verifiedStereoHostRoutes"], gate)
        self.assertNotIn("msinstrument-host-routes-", json.dumps(gate))
        self.assertEqual(check(path, ROOT), plain)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(read_bundle(original)[1], patch_bytes(patch))

    def test_cli_check_json_text_and_optional_pack_gate(self) -> None:
        path = self.bundle(stereo_patch())
        with redirect_stdout(StringIO()) as success:
            self.assertEqual(main(["check", str(path),
                                   "--require-verified-stereo-host-routes"]), 0)
        self.assertIn("Strict stereo HostAudio2 source route check: PASS",
                      success.getvalue())
        self.assertIn("Left/M: SOURCE_VERIFIED", success.getvalue())
        with redirect_stdout(StringIO()) as plain:
            self.assertEqual(main(["check", str(path)]), 0)
        self.assertNotIn("stereo HostAudio2", plain.getvalue())

        failed_patch = stereo_patch()
        failed_patch["cables"].pop()
        failed = self.bundle(failed_patch, 2)
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(main(["check", str(failed),
                                   "--require-verified-stereo-host-routes", "--json"]), 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["verifiedStereoHostRoutes"]["status"], "FAIL")
        self.assertEqual(report["verifiedStereoHostRoutes"]["hosts"][0][
            "missingInputs"], [1])

        with redirect_stdout(StringIO()) as both:
            self.assertEqual(main(["check", str(path), "--require-verified-routes",
                                   "--require-verified-stereo-host-routes", "--json"]), 1)
        combined = json.loads(both.getvalue())
        self.assertEqual(combined["verifiedStereoHostRoutes"]["status"], "PASS")
        self.assertEqual(combined["verifiedRoutes"]["reason"],
                         "V1_NO_ROUTE_CONTRACT")

        source = self.folder / "patch.vcv"
        source.write_bytes(patch_bytes(failed_patch))
        rejected = self.folder / "should-not-exist.msinstrument"
        with redirect_stderr(StringIO()) as err:
            self.assertEqual(main(["pack", str(source), "--out", str(rejected),
                                   "--require-verified-stereo-host-routes"]), 2)
        self.assertIn("UNVERIFIED_STEREO_HOST_INPUTS", err.getvalue())
        self.assertFalse(rejected.exists())

        source.write_bytes(patch_bytes(stereo_patch()))
        generated = self.folder / "stereo-export.msinstrument"
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["pack", str(source), "--out", str(generated),
                                   "--require-verified-stereo-host-routes"]), 0)
        self.assertEqual(generated.read_bytes(), create_bundle(
            patch_bytes(stereo_patch()), "patch"))

    def test_strict_gate_does_not_bypass_verified_zip_requirements(self) -> None:
        invalid = self.folder / "broken.msinstrument"
        invalid.write_bytes(b"not a ZIP")
        with redirect_stderr(StringIO()) as errors, redirect_stdout(StringIO()) as output:
            self.assertEqual(main(["check", str(invalid),
                                   "--require-verified-stereo-host-routes"]), 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("Instrument Builder:", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
