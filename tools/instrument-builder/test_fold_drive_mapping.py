"""Versioned FoldDrive routes: source contracts, legacy safety and tamper checks."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from control_mapping import CLOCKED_LFO_CONTRACT, FOLD_DRIVE_CONTRACT
from instrument_builder import (
    InstrumentError, MANIFEST_MEMBER, PATCH_MEMBER, build_manifest, check,
    create_bundle, inspect, main, pack, read_bundle, unpack,
)
from test_control_mapping import manifest_entries
from test_instrument_builder import custom_archive, patch_bytes, sample_patch


ROOT = Path(__file__).resolve().parents[2]


def fold_drive_patch() -> dict:
    patch = sample_patch()
    patch["modules"].append(
        {"id": 91, "plugin": "ModularSynth", "model": "FoldDrive"})
    # Four direct Macro8 cables: AUDIO, drive, asymmetry and wet mix.
    patch["cables"] = [
        {"id": 140 + input_id, "outputModuleId": 70, "outputId": input_id,
         "inputModuleId": 91, "inputId": input_id}
        for input_id in reversed(range(4))
    ]
    return patch


def fold_and_clock_patch() -> dict:
    patch = fold_drive_patch()
    patch["modules"].append(
        {"id": 90, "plugin": "ModularSynth", "model": "ClockedLFO"})
    patch["cables"].append({
        "id": 150, "outputModuleId": 70, "outputId": 4,
        "inputModuleId": 90, "inputId": 1,
    })
    return patch


def old_bundle(patch: dict, name: str, *,
               old_clocked: bool, old_fold: bool) -> bytes:
    """Recreate a historic v2 ZIP using only its historical source contract."""
    raw = patch_bytes(patch)
    manifest = build_manifest(raw, name, format_version=2,
                              legacy_v2_mapping=old_clocked,
                              legacy_fold_drive_mapping=old_fold)
    encoded = (json.dumps(manifest, sort_keys=True, ensure_ascii=True,
                          allow_nan=False, indent=2) + "\n").encode("utf-8")
    return custom_archive([(MANIFEST_MEMBER, encoded), (PATCH_MEMBER, raw)])


class FoldDriveMappingTests(unittest.TestCase):
    def test_all_four_real_folddrive_input_ports_are_verified(self) -> None:
        raw = patch_bytes(fold_drive_patch())
        manifest = build_manifest(raw, "Fold Source", format_version=2)
        self.assertEqual(manifest["performance"]["controlMappingContract"],
                         FOLD_DRIVE_CONTRACT)
        routes = manifest["performance"]["controlMappings"]
        self.assertEqual([route["cableId"] for route in routes],
                         [140, 141, 142, 143])
        destinations = [route["destination"] for route in routes]
        self.assertEqual([dest["inputId"] for dest in destinations], [0, 1, 2, 3])
        self.assertEqual([dest["inputKind"] for dest in destinations],
                         ["audio", "cv", "cv", "cv"])
        self.assertEqual([dest["inputLabel"] for dest in destinations], [
            "Audio signal (nominal +/-5 V)",
            "Drive CV (+10 V adds 100%; 3 ms slew)",
            "Bias CV (+10 V adds +100%; 3 ms slew)",
            "Wet mix CV (+10 V adds 100%; 3 ms slew)",
        ])
        self.assertEqual([dest["modulatesParameter"] for dest in destinations], [
            None,
            {"id": 0, "name": "Sine fold drive"},
            {"id": 1, "name": "Fold asymmetry bias"},
            {"id": 2, "name": "Wet mix"},
        ])
        self.assertEqual(create_bundle(raw, "Fold Source", format_version=2),
                         create_bundle(raw, "Fold Source", format_version=2))
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "fold.msinstrument"
            bundle.write_bytes(create_bundle(raw, "Fold Source", format_version=2))
            report = check(bundle, ROOT, require_verified_routes=True)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["verifiedRoutes"]["summary"],
                         {"total": 4, "sourceVerified": 4, "unverified": 0})
        self.assertEqual({route["status"]
                          for route in report["verifiedRoutes"]["routes"]},
                         {"SOURCE_VERIFIED"})

    def test_fold_and_clock_use_additive_six_model_contract(self) -> None:
        raw = patch_bytes(fold_and_clock_patch())
        manifest = build_manifest(raw, "Fold and Clock", format_version=2)
        self.assertEqual(manifest["performance"]["controlMappingContract"],
                         FOLD_DRIVE_CONTRACT)
        self.assertEqual([route["destination"]["model"] for route in
                          manifest["performance"]["controlMappings"]],
                         ["FoldDrive"] * 4 + ["ClockedLFO"])
        self.assertEqual({route["destination"]["inputKind"] for route in
                          manifest["performance"]["controlMappings"]},
                         {"audio", "cv"})
        decoded, original = read_bundle(create_bundle(
            raw, "Fold and Clock", format_version=2))
        self.assertEqual(decoded, manifest)
        self.assertEqual(original, raw)

    def test_legacy_unmarked_and_clocked_marked_v2_remain_verbatim(self) -> None:
        for historical, name, clocked_legacy, expected_marker in (
            (fold_drive_patch(), "Historic Unmarked", True, None),
            (fold_and_clock_patch(), "Historic Clocked", False,
             CLOCKED_LFO_CONTRACT),
        ):
            with self.subTest(name=name):
                old = old_bundle(historical, name, old_clocked=clocked_legacy,
                                 old_fold=True)
                saved_manifest, recovered = read_bundle(old)
                self.assertEqual(recovered, patch_bytes(historical))
                self.assertEqual(saved_manifest["performance"].get(
                    "controlMappingContract"), expected_marker)
                routes = saved_manifest["performance"]["controlMappings"]
                folds = [route for route in routes
                         if route["destination"]["model"] == "FoldDrive"]
                self.assertEqual(len(folds), 4)
                self.assertTrue(all(route["destination"]["inputKind"]
                                    == "unverified" for route in folds))
                self.assertTrue(all(route["destination"]["inputLabel"] is None
                                    and route["destination"]["modulatesParameter"] is None
                                    for route in folds))
                if expected_marker == CLOCKED_LFO_CONTRACT:
                    clocks = [route for route in routes
                              if route["destination"]["model"] == "ClockedLFO"]
                    self.assertEqual(len(clocks), 1)
                    self.assertEqual(clocks[0]["destination"]["inputKind"], "cv")
                self.assertNotEqual(old, create_bundle(
                    patch_bytes(historical), name, format_version=2))
                # Historic source ZIP bytes are stable and are never rewritten.
                self.assertEqual(old, old_bundle(
                    historical, name, old_clocked=clocked_legacy, old_fold=True))
                self.assertEqual(saved_manifest, read_bundle(old)[0])

    def test_folddrive_bad_input_indices_fail_before_bundle_output(self) -> None:
        for input_id in (4, 4096):
            with self.subTest(inputId=input_id):
                patch = fold_drive_patch()
                patch["cables"][0]["inputId"] = input_id
                raw = patch_bytes(patch)
                self.assertEqual(build_manifest(raw, "Legacy")["formatVersion"], 1)
                with self.assertRaisesRegex(InstrumentError, "FoldDrive inputId"):
                    create_bundle(raw, "Modern", format_version=2)
                with tempfile.TemporaryDirectory() as temporary:
                    source = Path(temporary) / "source.vcv"
                    output = Path(temporary) / "bad.msinstrument"
                    source.write_bytes(raw)
                    with self.assertRaisesRegex(InstrumentError, "FoldDrive inputId"):
                        pack(source, output, "Modern", format_version=2)
                    self.assertFalse(output.exists())
                # Older source bundles remain parseable with their frozen
                # unverified destination semantics, never falsely validated.
                old = old_bundle(patch, "Old Source", old_clocked=True,
                                 old_fold=True)
                self.assertEqual(read_bundle(old)[0]["performance"]
                                 ["controlMappings"][0]["destination"]["inputKind"],
                                 "unverified")

    def test_unrelated_and_non_macro_folddrive_cables_do_not_retag_v2(self) -> None:
        patch = sample_patch()
        patch["modules"].append(
            {"id": 91, "plugin": "ModularSynth", "model": "FoldDrive"})
        patch["cables"].append({
            "id": 142, "outputModuleId": 91, "outputId": 0,
            "inputModuleId": 71, "inputId": 0,
        })
        raw = patch_bytes(patch)
        self.assertNotIn("controlMappingContract", build_manifest(
            raw, "Legacy Compatible", format_version=2)["performance"])

    def test_v2_contract_marker_and_mapping_tampering_fail_closed(self) -> None:
        blob = create_bundle(patch_bytes(fold_drive_patch()),
                             "Fold Source", format_version=2)
        entries = manifest_entries(blob)
        for mutation, expected in (
            (lambda m: m["performance"].pop("controlMappingContract"),
             "manifest does not match"),
            (lambda m: m["performance"].update(
                controlMappingContract=CLOCKED_LFO_CONTRACT),
             "manifest does not match"),
            (lambda m: m["performance"].update(
                controlMappingContract="untrusted"),
             "unsupported control mapping contract"),
            (lambda m: m["performance"]["controlMappings"][1]["destination"].update(
                inputLabel="Not source verified"), "manifest does not match"),
            (lambda m: m["performance"]["controlMappings"][2]["destination"].update(
                modulatesParameter={"id": 2, "name": "DAW automation"}),
             "manifest does not match"),
        ):
            with self.subTest(mutation=mutation):
                manifest = json.loads(dict(entries)[MANIFEST_MEMBER])
                mutation(manifest)
                tampered = custom_archive([
                    (key, json.dumps(manifest).encode("utf-8")
                     if key == MANIFEST_MEMBER else content)
                    for key, content in entries
                ])
                with self.assertRaisesRegex(InstrumentError, expected):
                    read_bundle(tampered)

    def test_packing_roundtrip_cli_and_strict_gate(self) -> None:
        raw = patch_bytes(fold_drive_patch())
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / "fold.vcv"
            bundle = folder / "fold.msinstrument"
            source.write_bytes(raw)
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(main([
                    "pack", str(source), "--name", "Fold Source",
                    "--format-version", "2", "--out", str(bundle)]), 0)
            self.assertIn("Packed", output.getvalue())
            packed = bundle.read_bytes()
            self.assertEqual(inspect(bundle)["performance"]["controlMappingContract"],
                             FOLD_DRIVE_CONTRACT)
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(main([
                    "check", str(bundle), "--require-verified-routes", "--json"]), 0)
            self.assertEqual(json.loads(output.getvalue())[
                "verifiedRoutes"]["status"], "PASS")
            extracted = folder / "unpacked"
            unpack(bundle, extracted)
            self.assertEqual((extracted / PATCH_MEMBER).read_bytes(), raw)
            repacked = folder / "repacked.msinstrument"
            pack(extracted / PATCH_MEMBER, repacked, "Fold Source",
                 format_version=2)
            self.assertEqual(repacked.read_bytes(), packed)


if __name__ == "__main__":
    unittest.main()
