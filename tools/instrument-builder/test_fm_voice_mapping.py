"""FMVoice v2 Macro8 source-port contract and immutable historical mapping tests."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from control_mapping import (
    CLOCKED_LFO_CONTRACT, FOLD_DRIVE_CONTRACT, FM_VOICE_CONTRACT,
)
from instrument_builder import (
    InstrumentError, MANIFEST_MEMBER, PATCH_MEMBER, build_manifest, check,
    create_bundle, inspect, main, pack, read_bundle, unpack,
)
from test_control_mapping import manifest_entries
from test_instrument_builder import custom_archive, patch_bytes, sample_patch


ROOT = Path(__file__).resolve().parents[2]


def fm_voice_patch() -> dict:
    patch = sample_patch()
    patch["modules"].append(
        {"id": 92, "plugin": "ModularSynth", "model": "FMVoice"})
    patch["cables"] = [
        {"id": 160 + input_id, "outputModuleId": 70, "outputId": input_id,
         "inputModuleId": 92, "inputId": input_id}
        for input_id in reversed(range(4))
    ]
    return patch


def fm_fold_clock_patch() -> dict:
    patch = fm_voice_patch()
    patch["modules"].extend([
        {"id": 91, "plugin": "ModularSynth", "model": "FoldDrive"},
        {"id": 90, "plugin": "ModularSynth", "model": "ClockedLFO"},
    ])
    patch["cables"].extend([
        {"id": 170, "outputModuleId": 70, "outputId": 4,
         "inputModuleId": 91, "inputId": 1},
        {"id": 171, "outputModuleId": 70, "outputId": 5,
         "inputModuleId": 90, "inputId": 1},
    ])
    return patch


def historical_bundle(patch: dict, name: str, marker: str | None) -> bytes:
    """Recreate older v2 semantics without granting modern FMVoice labels."""
    raw = patch_bytes(patch)
    manifest = build_manifest(
        raw, name, format_version=2,
        legacy_v2_mapping=(marker is None),
        legacy_fold_drive_mapping=marker in (None, CLOCKED_LFO_CONTRACT),
        legacy_fm_voice_mapping=True,
    )
    assert manifest["performance"].get("controlMappingContract") == marker
    serialized = (json.dumps(
        manifest, sort_keys=True, ensure_ascii=True,
        allow_nan=False, indent=2) + "\n").encode("utf-8")
    return custom_archive([(MANIFEST_MEMBER, serialized), (PATCH_MEMBER, raw)])


class FMVoiceMappingTests(unittest.TestCase):
    def test_all_four_source_declared_fmvoice_inputs_are_verified(self) -> None:
        raw = patch_bytes(fm_voice_patch())
        manifest = build_manifest(raw, "FM Source", format_version=2)
        self.assertEqual(manifest["performance"]["controlMappingContract"],
                         FM_VOICE_CONTRACT)
        routes = manifest["performance"]["controlMappings"]
        self.assertEqual([r["cableId"] for r in routes], [160, 161, 162, 163])
        destinations = [r["destination"] for r in routes]
        self.assertEqual([d["inputId"] for d in destinations], [0, 1, 2, 3])
        self.assertEqual([d["inputKind"] for d in destinations], ["cv"] * 4)
        self.assertEqual([d["inputLabel"] for d in destinations], [
            "Pitch CV (1 V/oct; C4 at 0 V)",
            "Ratio CV (1 V doubles ratio)",
            "Index CV (1 V adds 0.8 rad)",
            "Feedback CV (10 V adds 95%)",
        ])
        self.assertEqual([d["modulatesParameter"] for d in destinations], [
            None,
            {"id": 2, "name": "Modulator/carrier frequency ratio"},
            {"id": 3, "name": "Phase modulation index"},
            {"id": 4, "name": "Modulator self-feedback"},
        ])
        blob = create_bundle(raw, "FM Source", format_version=2)
        self.assertEqual(blob, create_bundle(raw, "FM Source", format_version=2))
        self.assertEqual(read_bundle(blob), (manifest, raw))
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "fm.msinstrument"
            bundle.write_bytes(blob)
            report = check(bundle, ROOT, require_verified_routes=True)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["verifiedRoutes"]["summary"], {
            "total": 4, "sourceVerified": 4, "unverified": 0,
        })

    def test_fmvoice_marker_implies_prior_fold_and_clock_contracts(self) -> None:
        raw = patch_bytes(fm_fold_clock_patch())
        manifest = build_manifest(raw, "FM Fold Clock", format_version=2)
        self.assertEqual(manifest["performance"]["controlMappingContract"],
                         FM_VOICE_CONTRACT)
        routes = manifest["performance"]["controlMappings"]
        self.assertEqual([r["destination"]["model"] for r in routes],
                         ["FMVoice"] * 4 + ["FoldDrive", "ClockedLFO"])
        self.assertTrue(all(r["destination"]["inputKind"] == "cv" for r in routes))
        self.assertEqual(read_bundle(create_bundle(
            raw, "FM Fold Clock", format_version=2)), (manifest, raw))

    def test_archived_v2_markers_never_gain_fmvoice_port_metadata(self) -> None:
        patch = fm_fold_clock_patch()
        for marker, name in (
            (None, "Original V2"),
            (CLOCKED_LFO_CONTRACT, "Clocked V2"),
            (FOLD_DRIVE_CONTRACT, "Fold V2"),
        ):
            with self.subTest(marker=marker):
                old = historical_bundle(patch, name, marker)
                old_manifest, saved_patch = read_bundle(old)
                self.assertEqual(saved_patch, patch_bytes(patch))
                self.assertEqual(
                    old_manifest["performance"].get("controlMappingContract"),
                    marker)
                routes = old_manifest["performance"]["controlMappings"]
                fm = [r for r in routes
                      if r["destination"]["model"] == "FMVoice"]
                self.assertEqual(len(fm), 4)
                self.assertTrue(all(
                    r["destination"]["inputKind"] == "unverified"
                    and r["destination"]["inputLabel"] is None
                    and r["destination"]["modulatesParameter"] is None
                    for r in fm))
                folds = [r for r in routes
                         if r["destination"]["model"] == "FoldDrive"]
                clocks = [r for r in routes
                          if r["destination"]["model"] == "ClockedLFO"]
                self.assertEqual(
                    folds[0]["destination"]["inputKind"],
                    "cv" if marker == FOLD_DRIVE_CONTRACT else "unverified")
                self.assertEqual(
                    clocks[0]["destination"]["inputKind"],
                    "unverified" if marker is None else "cv")
                # Reading never silently upgrades or rewrites historical bytes.
                self.assertEqual(old, historical_bundle(patch, name, marker))
                self.assertEqual(old, old)  # intact source input
                with tempfile.TemporaryDirectory() as temporary:
                    bundle = Path(temporary) / "old.msinstrument"
                    bundle.write_bytes(old)
                    self.assertEqual(
                        check(bundle, ROOT, require_verified_routes=True)["status"],
                        "FAIL")
                    self.assertEqual(bundle.read_bytes(), old)

    def test_fmvoice_invalid_input_is_strict_only_in_new_contract(self) -> None:
        for input_id in (4, 4096):
            with self.subTest(inputId=input_id):
                patch = fm_voice_patch()
                patch["cables"][0]["inputId"] = input_id
                raw = patch_bytes(patch)
                self.assertEqual(build_manifest(raw, "v1")["formatVersion"], 1)
                with self.assertRaisesRegex(InstrumentError, "FMVoice inputId"):
                    create_bundle(raw, "Modern", format_version=2)
                with tempfile.TemporaryDirectory() as temporary:
                    folder = Path(temporary)
                    source = folder / "source.vcv"
                    out = folder / "no.msinstrument"
                    source.write_bytes(raw)
                    with self.assertRaisesRegex(InstrumentError, "FMVoice inputId"):
                        pack(source, out, "Modern", format_version=2)
                    self.assertFalse(out.exists())
                old = historical_bundle(patch, "Historical", None)
                decoded, _ = read_bundle(old)
                self.assertEqual(
                    decoded["performance"]["controlMappings"][0]
                    ["destination"]["inputKind"], "unverified")

    def test_existing_legacy_flags_cannot_claim_later_source_contract(self) -> None:
        raw = patch_bytes(fm_voice_patch())
        old = build_manifest(
            raw, "Old Caller", format_version=2, legacy_v2_mapping=True)
        self.assertNotIn("controlMappingContract", old["performance"])
        self.assertTrue(all(
            r["destination"]["inputKind"] == "unverified"
            for r in old["performance"]["controlMappings"]))
        with self.assertRaisesRegex(
                InstrumentError, "incompatible historical v2 mapping contracts"):
            build_manifest(
                raw, "Impossible", format_version=2,
                legacy_v2_mapping=True, legacy_fold_drive_mapping=False)
        with self.assertRaisesRegex(
                InstrumentError, "incompatible historical v2 mapping contracts"):
            build_manifest(
                raw, "Impossible", format_version=2,
                legacy_fold_drive_mapping=True, legacy_fm_voice_mapping=False)

    def test_unpatched_fmvoice_does_not_retag_older_v2_manifest(self) -> None:
        patch = sample_patch()
        patch["modules"].append(
            {"id": 92, "plugin": "ModularSynth", "model": "FMVoice"})
        patch["cables"].append({
            "id": 180, "outputModuleId": 92, "outputId": 0,
            "inputModuleId": 71, "inputId": 0,
        })
        raw = patch_bytes(patch)
        manifest = build_manifest(raw, "Untouched", format_version=2)
        self.assertNotIn("controlMappingContract", manifest["performance"])
        self.assertEqual(read_bundle(
            create_bundle(raw, "Untouched", format_version=2))[0], manifest)

    def test_marker_and_mapping_tampering_are_rejected(self) -> None:
        raw = patch_bytes(fm_voice_patch())
        entries = manifest_entries(create_bundle(
            raw, "FM Source", format_version=2))
        for mutate, expected in (
            (lambda m: m["performance"].pop("controlMappingContract"),
             "manifest does not match"),
            (lambda m: m["performance"].update(
                controlMappingContract=FOLD_DRIVE_CONTRACT),
             "manifest does not match"),
            (lambda m: m["performance"].update(
                controlMappingContract=CLOCKED_LFO_CONTRACT),
             "manifest does not match"),
            (lambda m: m["performance"].update(
                controlMappingContract="fabricated"),
             "unsupported control mapping contract"),
            (lambda m: m["performance"]["controlMappings"][2]
             ["destination"].update(inputLabel="DAW automation certified"),
             "manifest does not match"),
            (lambda m: m["performance"]["controlMappings"][3]
             ["destination"].update(
                 modulatesParameter={"id": 3, "name": "host automation"}),
             "manifest does not match"),
        ):
            with self.subTest(mutate=mutate):
                manifest = json.loads(dict(entries)[MANIFEST_MEMBER])
                mutate(manifest)
                forged = custom_archive([
                    (path, json.dumps(manifest).encode("utf-8")
                     if path == MANIFEST_MEMBER else content)
                    for path, content in entries
                ])
                with self.assertRaisesRegex(InstrumentError, expected):
                    read_bundle(forged)

    def test_cli_pack_check_unpack_repack_preserves_source_bytes(self) -> None:
        raw = patch_bytes(fm_voice_patch())
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / "fm.vcv"
            bundle = folder / "fm.msinstrument"
            source.write_bytes(raw)
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(main([
                    "pack", str(source), "--name", "FM Source",
                    "--format-version", "2", "--out", str(bundle)]), 0)
            self.assertIn("Packed", output.getvalue())
            original = bundle.read_bytes()
            self.assertEqual(inspect(bundle)["performance"]
                             ["controlMappingContract"], FM_VOICE_CONTRACT)
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(main([
                    "check", str(bundle), "--require-verified-routes",
                    "--json"]), 0)
            self.assertEqual(json.loads(output.getvalue())[
                "verifiedRoutes"]["status"], "PASS")
            extracted = folder / "unpacked"
            unpack(bundle, extracted)
            self.assertEqual((extracted / PATCH_MEMBER).read_bytes(), raw)
            repacked = folder / "repacked.msinstrument"
            pack(extracted / PATCH_MEMBER, repacked, "FM Source",
                 format_version=2)
            self.assertEqual(repacked.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
