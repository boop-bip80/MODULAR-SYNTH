"""ChanceHold Macro8 port mapping and immutable v2 archive regression tests."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from control_mapping import (
    CHANCE_HOLD_CONTRACT, CLOCKED_LFO_CONTRACT, FOLD_DRIVE_CONTRACT,
    FM_VOICE_CONTRACT,
)
from instrument_builder import (
    InstrumentError, MANIFEST_MEMBER, PATCH_MEMBER, build_manifest, check,
    create_bundle, inspect, main, pack, read_bundle, unpack,
)
from test_control_mapping import manifest_entries
from test_instrument_builder import custom_archive, patch_bytes, sample_patch


ROOT = Path(__file__).resolve().parents[2]


def chance_hold_patch() -> dict:
    patch = sample_patch()
    patch["modules"].append(
        {"id": 93, "plugin": "ModularSynth", "model": "ChanceHold"})
    patch["cables"] = [
        {"id": 180 + input_id, "outputModuleId": 70, "outputId": input_id,
         "inputModuleId": 93, "inputId": input_id}
        for input_id in reversed(range(5))
    ]
    return patch


def cumulative_patch() -> dict:
    patch = chance_hold_patch()
    patch["modules"].extend([
        {"id": 92, "plugin": "ModularSynth", "model": "FMVoice"},
        {"id": 91, "plugin": "ModularSynth", "model": "FoldDrive"},
        {"id": 90, "plugin": "ModularSynth", "model": "ClockedLFO"},
    ])
    patch["cables"].extend([
        {"id": 190, "outputModuleId": 70, "outputId": 5,
         "inputModuleId": 92, "inputId": 2},
        {"id": 191, "outputModuleId": 70, "outputId": 6,
         "inputModuleId": 91, "inputId": 1},
        {"id": 192, "outputModuleId": 70, "outputId": 7,
         "inputModuleId": 90, "inputId": 4},
    ])
    return patch


def historical_bundle(patch: dict, name: str, marker: str | None) -> bytes:
    """Reproduce each pre-ChanceHold v2 contract without upgrading its ports."""
    raw = patch_bytes(patch)
    manifest = build_manifest(
        raw, name, format_version=2,
        legacy_v2_mapping=marker is None,
        legacy_fold_drive_mapping=marker in (None, CLOCKED_LFO_CONTRACT),
        legacy_fm_voice_mapping=marker in (
            None, CLOCKED_LFO_CONTRACT, FOLD_DRIVE_CONTRACT),
        legacy_chance_hold_mapping=True,
    )
    assert manifest["performance"].get("controlMappingContract") == marker
    saved_manifest = (json.dumps(
        manifest, sort_keys=True, ensure_ascii=True,
        allow_nan=False, indent=2) + "\n").encode("utf-8")
    return custom_archive([
        (MANIFEST_MEMBER, saved_manifest), (PATCH_MEMBER, raw)])


class ChanceHoldMappingTests(unittest.TestCase):
    def test_all_five_source_declared_chancehold_inputs_are_mapped(self) -> None:
        raw = patch_bytes(chance_hold_patch())
        manifest = build_manifest(raw, "Chance Source", format_version=2)
        self.assertEqual(manifest["performance"]["controlMappingContract"],
                         CHANCE_HOLD_CONTRACT)
        routes = manifest["performance"]["controlMappings"]
        self.assertEqual([row["cableId"] for row in routes],
                         [180, 181, 182, 183, 184])
        destinations = [row["destination"] for row in routes]
        self.assertEqual([d["inputId"] for d in destinations], list(range(5)))
        self.assertEqual([d["inputKind"] for d in destinations], ["cv"] * 5)
        self.assertEqual([d["inputLabel"] for d in destinations], [
            "Free clock rate CV (1 V/oct)",
            "External sample clock (2 V rising threshold)",
            "Reproducible random sequence reset (2 V rising threshold)",
            "Sample probability CV (+10 V adds 100%)",
            "Glide duration CV (+10 V adds 2 seconds)",
        ])
        self.assertEqual([d["modulatesParameter"] for d in destinations], [
            {"id": 0, "name": "Free-run sample rate"},
            None,
            None,
            {"id": 1, "name": "Probability of taking a sample"},
            {"id": 2, "name": "Glide time (99% settling)"},
        ])
        bundle = create_bundle(raw, "Chance Source", format_version=2)
        self.assertEqual(bundle, create_bundle(
            raw, "Chance Source", format_version=2))
        self.assertEqual(read_bundle(bundle), (manifest, raw))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "chance.msinstrument"
            path.write_bytes(bundle)
            report = check(path, ROOT, require_verified_routes=True)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["verifiedRoutes"]["summary"], {
                "total": 5, "sourceVerified": 5, "unverified": 0,
            })

    def test_new_marker_cumulatively_verifies_earlier_ports(self) -> None:
        raw = patch_bytes(cumulative_patch())
        manifest = build_manifest(raw, "Cumulative", format_version=2)
        self.assertEqual(manifest["performance"]["controlMappingContract"],
                         CHANCE_HOLD_CONTRACT)
        destinations = [r["destination"] for r
                        in manifest["performance"]["controlMappings"]]
        self.assertEqual([d["model"] for d in destinations],
                         ["ChanceHold"] * 5 + ["FMVoice", "FoldDrive", "ClockedLFO"])
        self.assertTrue(all(d["inputKind"] == "cv" for d in destinations))
        self.assertEqual(read_bundle(create_bundle(
            raw, "Cumulative", format_version=2)), (manifest, raw))

    def test_all_four_older_v2_markers_keep_chancehold_unverified(self) -> None:
        patch = cumulative_patch()
        for marker, name in (
            (None, "Original"),
            (CLOCKED_LFO_CONTRACT, "Clocked"),
            (FOLD_DRIVE_CONTRACT, "Fold"),
            (FM_VOICE_CONTRACT, "FM"),
        ):
            with self.subTest(marker=marker):
                saved = historical_bundle(patch, name, marker)
                manifest, recovered = read_bundle(saved)
                self.assertEqual(recovered, patch_bytes(patch))
                self.assertEqual(
                    manifest["performance"].get("controlMappingContract"),
                    marker)
                by_model = {
                    model: [r["destination"] for r in
                            manifest["performance"]["controlMappings"]
                            if r["destination"]["model"] == model]
                    for model in ("ChanceHold", "FMVoice", "FoldDrive",
                                  "ClockedLFO")
                }
                self.assertEqual(len(by_model["ChanceHold"]), 5)
                for destination in by_model["ChanceHold"]:
                    self.assertEqual(destination["inputKind"], "unverified")
                    self.assertIsNone(destination["inputLabel"])
                    self.assertIsNone(destination["modulatesParameter"])
                self.assertEqual(
                    by_model["FMVoice"][0]["inputKind"],
                    "cv" if marker == FM_VOICE_CONTRACT else "unverified")
                self.assertEqual(
                    by_model["FoldDrive"][0]["inputKind"],
                    "cv" if marker in (FOLD_DRIVE_CONTRACT, FM_VOICE_CONTRACT)
                    else "unverified")
                self.assertEqual(
                    by_model["ClockedLFO"][0]["inputKind"],
                    "unverified" if marker is None else "cv")
                self.assertEqual(saved, historical_bundle(patch, name, marker))
                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary) / "old.msinstrument"
                    path.write_bytes(saved)
                    self.assertEqual(
                        check(path, ROOT, require_verified_routes=True)["status"],
                        "FAIL")
                    self.assertEqual(path.read_bytes(), saved)

    def test_out_of_range_chancehold_ports_are_only_strict_in_new_contract(self) -> None:
        for port in (5, 4096):
            with self.subTest(port=port):
                patch = chance_hold_patch()
                patch["cables"][0]["inputId"] = port
                raw = patch_bytes(patch)
                self.assertEqual(build_manifest(raw, "Old")["formatVersion"], 1)
                with self.assertRaisesRegex(InstrumentError, "ChanceHold inputId"):
                    create_bundle(raw, "New", format_version=2)
                with tempfile.TemporaryDirectory() as temporary:
                    folder = Path(temporary)
                    source = folder / "source.vcv"
                    result = folder / "invalid.msinstrument"
                    source.write_bytes(raw)
                    with self.assertRaisesRegex(InstrumentError, "ChanceHold inputId"):
                        pack(source, result, "New", format_version=2)
                    self.assertFalse(result.exists())
                old = historical_bundle(patch, "Old", None)
                self.assertEqual(
                    read_bundle(old)[0]["performance"]["controlMappings"][0]
                    ["destination"]["inputKind"], "unverified")

    def test_marker_tampering_and_impossible_legacy_flags_are_rejected(self) -> None:
        raw = patch_bytes(chance_hold_patch())
        bundle = create_bundle(raw, "Authenticated", format_version=2)
        entries = manifest_entries(bundle)
        for action, error in (
            (lambda m: m["performance"].pop("controlMappingContract"),
             "does not match"),
            (lambda m: m["performance"].update(
                controlMappingContract=FM_VOICE_CONTRACT), "does not match"),
            (lambda m: m["performance"].update(
                controlMappingContract="fabricated"), "unsupported"),
            (lambda m: m["performance"]["controlMappings"][0]["destination"].update(
                inputLabel="not a source label"), "does not match"),
        ):
            with self.subTest(action=action):
                manifest = json.loads(dict(entries)[MANIFEST_MEMBER])
                action(manifest)
                altered = custom_archive([
                    (MANIFEST_MEMBER, json.dumps(manifest).encode("utf-8")),
                    (PATCH_MEMBER, raw),
                ])
                with self.assertRaisesRegex(InstrumentError, error):
                    read_bundle(altered)
        with self.assertRaisesRegex(
                InstrumentError, "incompatible historical v2 mapping contracts"):
            build_manifest(
                raw, "Impossible", format_version=2,
                legacy_fm_voice_mapping=True,
                legacy_chance_hold_mapping=False)

    def test_cli_roundtrip_stores_contract_without_mutating_patch(self) -> None:
        raw = patch_bytes(chance_hold_patch())
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / "source.vcv"
            target = folder / "saved.msinstrument"
            source.write_bytes(raw)
            manifest = pack(source, target, "Chance Routes", format_version=2)
            self.assertEqual(inspect(target), manifest)
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(main([
                    "check", str(target), "--require-verified-routes"]), 0)
            self.assertIn("source route check: PASS", output.getvalue())
            original = target.read_bytes()
            directory = folder / "unpacked"
            self.assertEqual(unpack(target, directory), manifest)
            self.assertEqual((directory / PATCH_MEMBER).read_bytes(), raw)
            repacked = folder / "repacked.msinstrument"
            pack(directory / PATCH_MEMBER, repacked,
                 "Chance Routes", format_version=2)
            self.assertEqual(original, repacked.read_bytes())


if __name__ == "__main__":
    unittest.main()
