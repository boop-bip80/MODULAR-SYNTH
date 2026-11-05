"""DualVCA source-verified saved Macro8 routes and immutable v2 contracts."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from control_mapping import (
    CHANCE_HOLD_CONTRACT, CLOCKED_LFO_CONTRACT, DUAL_VCA_CONTRACT,
    FM_VOICE_CONTRACT, FOLD_DRIVE_CONTRACT,
)
from instrument_builder import (
    InstrumentError, MANIFEST_MEMBER, PATCH_MEMBER, build_manifest, check,
    create_bundle, inspect, pack, preview, read_bundle,
)
from route_report import build_route_report, text_route_report
from test_control_mapping import manifest_entries
from test_instrument_builder import custom_archive, patch_bytes, sample_patch


ROOT = Path(__file__).resolve().parents[2]
OLD_MARKERS = (None, CLOCKED_LFO_CONTRACT, FOLD_DRIVE_CONTRACT,
               FM_VOICE_CONTRACT, CHANCE_HOLD_CONTRACT)


def dual_vca_patch() -> dict:
    patch = sample_patch()
    patch["modules"].append(
        {"id": 94, "plugin": "ModularSynth", "model": "DualVCA"})
    patch["cables"] = [
        {"id": 200 + i, "outputModuleId": 70, "outputId": i,
         "inputModuleId": 94, "inputId": i}
        for i in reversed(range(4))
    ]
    return patch


def cumulative_patch() -> dict:
    patch = dual_vca_patch()
    patch["modules"].extend([
        {"id": 93, "plugin": "ModularSynth", "model": "ChanceHold"},
        {"id": 92, "plugin": "ModularSynth", "model": "FMVoice"},
        {"id": 91, "plugin": "ModularSynth", "model": "FoldDrive"},
        {"id": 90, "plugin": "ModularSynth", "model": "ClockedLFO"},
    ])
    for i, (module_id, input_id) in enumerate(
            ((93, 3), (92, 2), (91, 1), (90, 4)), start=4):
        patch["cables"].append({
            "id": 200 + i, "outputModuleId": 70, "outputId": i,
            "inputModuleId": module_id, "inputId": input_id,
        })
    return patch


def historical_bundle(patch: dict, marker: str | None) -> bytes:
    """Construct an authentic earlier v2 manifest without reinterpretation."""
    raw = patch_bytes(patch)
    manifest = build_manifest(
        raw, "Archived Dual", format_version=2,
        legacy_v2_mapping=marker is None,
        legacy_fold_drive_mapping=marker in (None, CLOCKED_LFO_CONTRACT),
        legacy_fm_voice_mapping=marker in (
            None, CLOCKED_LFO_CONTRACT, FOLD_DRIVE_CONTRACT),
        legacy_chance_hold_mapping=marker != CHANCE_HOLD_CONTRACT,
        legacy_dual_vca_mapping=True,
    )
    assert manifest["performance"].get("controlMappingContract") == marker
    data = (json.dumps(manifest, sort_keys=True, ensure_ascii=True,
                       allow_nan=False, indent=2) + "\n").encode("utf-8")
    return custom_archive([(MANIFEST_MEMBER, data), (PATCH_MEMBER, raw)])


class DualVCAMappingTests(unittest.TestCase):
    def test_source_port_ids_kinds_labels_and_absence_of_knob_claims(self) -> None:
        raw = patch_bytes(dual_vca_patch())
        manifest = build_manifest(raw, "Dual Source", format_version=2)
        self.assertEqual(manifest["performance"]["controlMappingContract"],
                         DUAL_VCA_CONTRACT)
        routes = manifest["performance"]["controlMappings"]
        self.assertEqual([r["cableId"] for r in routes], [200, 201, 202, 203])
        destinations = [r["destination"] for r in routes]
        self.assertEqual([d["inputId"] for d in destinations], [0, 1, 2, 3])
        self.assertEqual([d["inputKind"] for d in destinations],
                         ["audio", "cv", "audio", "cv"])
        self.assertEqual([d["inputLabel"] for d in destinations], [
            "A audio (nominal +/-5 V)",
            "A gain envelope (0 to +10 V; unpatched is unity)",
            "B audio (nominal +/-5 V)",
            "B gain envelope (0 to +10 V; unpatched is unity)",
        ])
        self.assertEqual([d["modulatesParameter"] for d in destinations],
                         [None] * 4)
        bundle = create_bundle(raw, "Dual Source", format_version=2)
        self.assertEqual(bundle, create_bundle(raw, "Dual Source", format_version=2))
        self.assertEqual(read_bundle(bundle), (manifest, raw))

    def test_reports_and_route_preview_use_saved_verified_destination(self) -> None:
        raw = patch_bytes(dual_vca_patch())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "dual.vcv"
            archive = root / "dual.msinstrument"
            svg = root / "dual.svg"
            source.write_bytes(raw)
            saved = pack(source, archive, "Dual Routes", format_version=2)
            self.assertEqual(inspect(archive), saved)
            self.assertEqual(check(
                archive, ROOT, require_verified_routes=True
            )["verifiedRoutes"]["summary"], {
                "total": 4, "sourceVerified": 4, "unverified": 0,
            })
            report = build_route_report(saved)
            self.assertEqual(report["mappingContract"], DUAL_VCA_CONTRACT)
            self.assertEqual([row["status"] for row in report["routes"]],
                             ["SOURCE_VERIFIED"] * 4)
            text = text_route_report(report)
            self.assertIn("DualVCA module 94 input 1 [cv:", text)
            self.assertIn("A gain envelope", text)
            self.assertIn("NOT a live Cardinal", text)
            self.assertEqual(preview(archive, svg, show_routes=True), saved)
            preview_svg = svg.read_text()
            self.assertIn("DualVCA", preview_svg)
            self.assertIn("A gain envelope", preview_svg)
            self.assertEqual(archive.read_bytes(), create_bundle(
                raw, "Dual Routes", format_version=2))

    def test_new_marker_inherits_previous_verified_models(self) -> None:
        raw = patch_bytes(cumulative_patch())
        manifest = build_manifest(raw, "Nine Models", format_version=2)
        self.assertEqual(manifest["performance"]["controlMappingContract"],
                         DUAL_VCA_CONTRACT)
        destinations = [row["destination"] for row in
                        manifest["performance"]["controlMappings"]]
        self.assertEqual([d["model"] for d in destinations],
                         ["DualVCA"] * 4 + [
                             "ChanceHold", "FMVoice", "FoldDrive", "ClockedLFO"])
        self.assertEqual([d["inputKind"] for d in destinations],
                         ["audio", "cv", "audio", "cv"] + ["cv"] * 4)
        self.assertEqual(read_bundle(create_bundle(
            raw, "Nine Models", format_version=2)), (manifest, raw))

    def test_all_historical_v2_markers_keep_dualvca_unverified(self) -> None:
        patch = cumulative_patch()
        for marker in OLD_MARKERS:
            with self.subTest(marker=marker):
                archive = historical_bundle(patch, marker)
                manifest, source = read_bundle(archive)
                self.assertEqual(source, patch_bytes(patch))
                self.assertEqual(
                    manifest["performance"].get("controlMappingContract"),
                    marker)
                targets = [r["destination"] for r in
                           manifest["performance"]["controlMappings"]]
                for destination in targets[:4]:
                    self.assertEqual(destination["model"], "DualVCA")
                    self.assertEqual(destination["inputKind"], "unverified")
                    self.assertIsNone(destination["inputLabel"])
                    self.assertIsNone(destination["modulatesParameter"])
                self.assertEqual([d["inputKind"] for d in targets[4:]], [
                    "cv" if marker == CHANCE_HOLD_CONTRACT else "unverified",
                    "cv" if marker in (FM_VOICE_CONTRACT,
                                       CHANCE_HOLD_CONTRACT) else "unverified",
                    "cv" if marker in (FOLD_DRIVE_CONTRACT, FM_VOICE_CONTRACT,
                                       CHANCE_HOLD_CONTRACT) else "unverified",
                    "cv" if marker is not None else "unverified",
                ])
                self.assertEqual(historical_bundle(patch, marker), archive)
                report = build_route_report(manifest)
                self.assertEqual([r["status"] for r in report["routes"][:4]],
                                 ["UNVERIFIED"] * 4)
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "historic.msinstrument"
                    svg = Path(folder) / "historical-routes.svg"
                    path.write_bytes(archive)
                    self.assertEqual(check(
                        path, ROOT, require_verified_routes=True)["status"],
                        "FAIL")
                    self.assertEqual(preview(path, svg, show_routes=True),
                                     manifest)
                    self.assertIn("UNVERIFIED INPUT", svg.read_text())
                    self.assertEqual(path.read_bytes(), archive)

    def test_default_v1_does_not_introduce_mapping_contract(self) -> None:
        raw = patch_bytes(dual_vca_patch())
        manifest = build_manifest(raw, "V1 Defaults")
        self.assertEqual(manifest["formatVersion"], 1)
        self.assertNotIn("controlMappings", manifest["performance"])
        self.assertNotIn("controlMappingContract", manifest["performance"])
        self.assertEqual(read_bundle(create_bundle(raw, "V1 Defaults")),
                         (manifest, raw))

    def test_invalid_ports_and_external_spoofs_never_gain_labels(self) -> None:
        for port in (4, 4096):
            with self.subTest(port=port):
                patch = dual_vca_patch()
                patch["cables"][0]["inputId"] = port
                raw = patch_bytes(patch)
                with self.assertRaisesRegex(InstrumentError, "DualVCA inputId"):
                    create_bundle(raw, "Fresh", format_version=2)
                old = historical_bundle(patch, None)
                self.assertEqual(read_bundle(old)[0]["performance"]
                                 ["controlMappings"][-1]["destination"]
                                 ["inputKind"], "unverified")
        patch = dual_vca_patch()
        patch["modules"][-1]["plugin"] = "ThirdParty"
        patch["cables"][0]["inputId"] = 4096
        manifest = build_manifest(patch_bytes(patch), "External", format_version=2)
        self.assertNotIn("controlMappingContract", manifest["performance"])
        self.assertTrue(all(d["destination"]["inputKind"] == "unverified"
                            for d in manifest["performance"]["controlMappings"]))

    def test_malicious_or_ambiguous_contracts_and_route_tampering_fail(self) -> None:
        raw = patch_bytes(dual_vca_patch())
        entries = manifest_entries(create_bundle(raw, "Untampered", format_version=2))
        for marker in (None, CHANCE_HOLD_CONTRACT, "dual-vca", "",
                       DUAL_VCA_CONTRACT.upper(), [], {}, True, 0):
            with self.subTest(marker=marker):
                manifest = json.loads(dict(entries)[MANIFEST_MEMBER])
                if marker is None:
                    manifest["performance"].pop("controlMappingContract")
                else:
                    manifest["performance"]["controlMappingContract"] = marker
                archive = custom_archive([
                    (MANIFEST_MEMBER, json.dumps(manifest).encode("utf-8")),
                    (PATCH_MEMBER, raw),
                ])
                with self.assertRaises(InstrumentError):
                    read_bundle(archive)
        manifest = json.loads(dict(entries)[MANIFEST_MEMBER])
        manifest["performance"]["controlMappings"][1]["destination"].update(
            inputKind="cv", inputLabel="guessed host parameter",
            modulatesParameter={"id": 0, "name": "A maximum gain"})
        archive = custom_archive([
            (MANIFEST_MEMBER, json.dumps(manifest).encode("utf-8")),
            (PATCH_MEMBER, raw),
        ])
        with self.assertRaisesRegex(InstrumentError, "does not match"):
            read_bundle(archive)
        with self.assertRaisesRegex(InstrumentError, "incompatible historical"):
            build_manifest(raw, "Impossible", format_version=2,
                           legacy_chance_hold_mapping=True,
                           legacy_dual_vca_mapping=False)


if __name__ == "__main__":
    unittest.main()
