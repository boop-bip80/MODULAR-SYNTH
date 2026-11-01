"""Manifest v2 Macro8 cable mapping, source contract and v1 compatibility."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from io import BytesIO, StringIO
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from control_mapping import FIRST_PARTY_INPUTS
from instrument_builder import (
    InstrumentError, MANIFEST_MEMBER, MAPPING_FORMAT_VERSION, PATCH_MEMBER,
    build_manifest, check, create_bundle, inspect, main, pack, preview,
    read_bundle, unpack,
)
from test_instrument_builder import custom_archive, patch_bytes, sample_patch


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "patches" / "examples"


def routed_patch() -> dict:
    patch = sample_patch()
    patch["modules"].extend([
        {"id": 80, "plugin": "ModularSynth", "model": "MorphVCO"},
        {"id": 81, "plugin": "ModularSynth", "model": "StateFilter"},
        {"id": 82, "plugin": "ModularSynth", "model": "StereoEcho"},
        {"id": 83, "plugin": "OtherVendor", "model": "OtherEffect"},
    ])
    patch["modules"][0]["params"][16]["value"] = 1.0  # Macro 2 bipolar
    patch["cables"].extend([
        {"id": 102, "outputModuleId": 70, "outputId": 0,
         "inputModuleId": 80, "inputId": 2},
        {"id": 103, "outputModuleId": 70, "outputId": 1,
         "inputModuleId": 81, "inputId": 2},
        {"id": 104, "outputModuleId": 70, "outputId": 2,
         "inputModuleId": 82, "inputId": 3},
        {"id": 105, "outputModuleId": 70, "outputId": 7,
         "inputModuleId": 81, "inputId": 0},
        {"id": 106, "outputModuleId": 70, "outputId": 4,
         "inputModuleId": 83, "inputId": 4096},
    ])
    return patch


def manifest_entries(bundle: bytes) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(BytesIO(bundle)) as archive:
        return [(name, archive.read(name)) for name in archive.namelist()]


class FirstPartyPortContractTests(unittest.TestCase):
    def test_contract_matches_rack_source_enum_and_config_labels(self) -> None:
        self.assertEqual(
            set(FIRST_PARTY_INPUTS),
            {"Macro8", "MorphVCO", "StateFilter", "StereoEcho"})
        for model, ports in FIRST_PARTY_INPUTS.items():
            with self.subTest(model=model):
                cpp = (ROOT / "plugins/ModularSynth/src" / f"{model}.cpp").read_text()
                match = re.search(r"\benum\s+InputIds\s*\{(.*?)\}", cpp, re.S)
                self.assertIsNotNone(match)
                enum = re.sub(r"/\*.*?\*/|//[^\n]*", "", match.group(1), flags=re.S)
                members = [part.strip() for part in enum.split(",") if part.strip()]
                self.assertEqual(members, [port.enum for port in ports] + ["NUM_INPUTS"])
                labels = re.findall(
                    r'\bconfigInput\s*\(\s*([A-Z_0-9]+)\s*,\s*"([^"]+)"', cpp)
                self.assertEqual(labels, [(port.enum, port.label) for port in ports])

                param_match = re.search(r"\benum\s+ParamIds\s*\{(.*?)\}", cpp, re.S)
                self.assertIsNotNone(param_match)
                param_members = [
                    part.strip() for part in param_match.group(1).split(",") if part.strip()
                ]
                declarations = dict(re.findall(
                    r'\bconfigParam\s*\(\s*([A-Z_0-9]+)\s*,[^;]*?"([^"]+)"',
                    cpp, flags=re.S))
                for port in ports:
                    self.assertIn(port.kind, {"cv", "audio"})
                    if port.parameter is None:
                        continue
                    index, label = port.parameter
                    self.assertLess(index, len(param_members) - 1)
                    self.assertEqual(declarations[param_members[index]], label)


class MappingV2Tests(unittest.TestCase):
    def test_exact_verified_and_unverified_destination_contract(self) -> None:
        manifest = build_manifest(
            patch_bytes(routed_patch()), "Routes", format_version=2)
        self.assertEqual(manifest["formatVersion"], MAPPING_FORMAT_VERSION)
        routes = manifest["performance"]["controlMappings"]
        self.assertEqual(len(routes), 6)
        self.assertEqual([route["cableId"] for route in routes],
                         [72, 102, 103, 104, 106, 105])
        by_cable = {route["cableId"]: route for route in routes}
        self.assertEqual(by_cable[102]["source"], {
            "moduleId": 70, "outputId": 0, "controlNumber": 1,
            "name": "Shape", "range": "unipolar",
        })
        self.assertEqual(by_cable[103]["source"]["range"], "bipolar")
        self.assertEqual(by_cable[102]["destination"], {
            "moduleId": 80, "plugin": "ModularSynth", "model": "MorphVCO",
            "inputId": 2, "inputKind": "cv",
            "inputLabel": "Wave morph CV (10 V full span; adds to knob)",
            "modulatesParameter": {"id": 2, "name": "Wave morph position"},
        })
        self.assertEqual(by_cable[103]["destination"]["modulatesParameter"],
                         {"id": 1, "name": "Resonance amount"})
        self.assertEqual(by_cable[104]["destination"]["modulatesParameter"],
                         {"id": 1, "name": "Feedback"})
        self.assertEqual(by_cable[105]["destination"]["inputKind"], "audio")
        self.assertIsNone(by_cable[105]["destination"]["modulatesParameter"])
        for cable in (72, 106):
            self.assertEqual(by_cable[cable]["destination"]["inputKind"],
                             "unverified")
            self.assertIsNone(by_cable[cable]["destination"]["inputLabel"])
            self.assertIsNone(by_cable[cable]["destination"]["modulatesParameter"])

    def test_mapping_order_does_not_depend_on_saved_cable_order(self) -> None:
        patch = routed_patch()
        first = build_manifest(patch_bytes(patch), "Routes", format_version=2)
        patch["cables"].reverse()
        other = build_manifest(patch_bytes(patch), "Routes", format_version=2)
        self.assertEqual(first["performance"]["controlMappings"],
                         other["performance"]["controlMappings"])

    def test_v1_output_remains_default_and_bitwise_identical(self) -> None:
        raw = patch_bytes(routed_patch())
        default = create_bundle(raw, "Routes")
        explicit = create_bundle(raw, "Routes", format_version=1)
        self.assertEqual(default, explicit)
        manifest, recovered = read_bundle(default)
        self.assertEqual(recovered, raw)
        self.assertEqual(manifest["formatVersion"], 1)
        self.assertNotIn("controlMappings", manifest["performance"])

    def test_v1_factory_archive_matches_unmodified_main_golden_sha256(self) -> None:
        path = EXAMPLES / "MODULAR_-_Morphing_State_Pad.vcv"
        if not path.is_file():
            self.skipTest("factory patch unavailable")
        raw = path.read_bytes()
        # Main prior to this increment (87f0c758) produced this exact ZIP.
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "633b68a55f6d6b255429527c11c9841e38342a79ad50ae1b0bd97b2a58bb81ea")
        self.assertEqual(hashlib.sha256(create_bundle(raw, "Morphing State Pad")).hexdigest(),
                         "439adfcfeb9555fe0bf69f179d46243412e2be9c7cdbcbd5892a0c86567619b8")

    def test_v2_bundle_is_deterministic_and_verifies_unchanged_patch(self) -> None:
        raw = patch_bytes(routed_patch())
        first = create_bundle(raw, "Routes", format_version=2)
        self.assertEqual(first, create_bundle(raw, "Routes", format_version=2))
        manifest, extracted = read_bundle(first)
        self.assertEqual(extracted, raw)
        self.assertEqual(manifest, build_manifest(raw, "Routes", format_version=2))
        self.assertEqual(manifest["patch"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(manifest["performance"]["controlMappings"]), 6)

    def test_manifest_mapping_tampering_is_rejected(self) -> None:
        bundle = create_bundle(patch_bytes(routed_patch()), "Routes", format_version=2)
        for mutate in (
            lambda manifest: manifest["performance"]["controlMappings"][0]["destination"].update(inputId=123),
            lambda manifest: manifest["performance"]["controlMappings"].pop(),
            lambda manifest: manifest["performance"]["controlMappings"].append({}),
            lambda manifest: manifest["performance"]["controlMappings"].append(
                deepcopy(manifest["performance"]["controlMappings"][0])),
            lambda manifest: manifest["performance"].pop("controlMappings"),
            lambda manifest: manifest.update(formatVersion=1),
        ):
            with self.subTest(mutate=mutate):
                entries = manifest_entries(bundle)
                tampered = json.loads(dict(entries)[MANIFEST_MEMBER])
                mutate(tampered)
                changed = [(name, (json.dumps(tampered).encode("utf-8")
                                   if name == MANIFEST_MEMBER else blob))
                           for name, blob in entries]
                with self.assertRaises(InstrumentError):
                    read_bundle(custom_archive(changed))

    def test_invalid_output_and_known_firstparty_input_rejected_before_pack(self) -> None:
        for cable_edit, expected in (
            ({"outputId": 8}, "Macro8 70 outputId 8"),
            ({"inputModuleId": 80, "inputId": 4}, "MorphVCO inputId 4"),
            ({"inputModuleId": 81, "inputId": 99}, "StateFilter inputId 99"),
            ({"inputModuleId": 70, "inputId": 0}, "Macro8 inputId 0"),
        ):
            with self.subTest(edit=cable_edit):
                patch = sample_patch()
                patch["modules"].extend([
                    {"id": 80, "plugin": "ModularSynth", "model": "MorphVCO"},
                    {"id": 81, "plugin": "ModularSynth", "model": "StateFilter"},
                ])
                patch["cables"][0].update(cable_edit)
                # Legacy v1 preserves its preexisting structural checks.
                self.assertEqual(build_manifest(patch_bytes(patch), "Legacy")["formatVersion"], 1)
                with self.assertRaisesRegex(InstrumentError, expected):
                    create_bundle(patch_bytes(patch), "Routes", format_version=2)

    def test_duplicate_source_to_target_routes_are_rejected_but_fanout_is_valid(self) -> None:
        patch = routed_patch()
        # 72 and 102 are a legitimate source-output fanout to different inputs.
        self.assertEqual(len(build_manifest(
            patch_bytes(patch), "Routes", format_version=2)
            ["performance"]["controlMappings"]), 6)
        duplicate = deepcopy(patch["cables"][1])
        duplicate["id"] = 150
        patch["cables"].append(duplicate)
        # Legacy v1 keeps its previous structural behavior.
        self.assertEqual(build_manifest(patch_bytes(patch), "Legacy")["formatVersion"], 1)
        with self.assertRaisesRegex(InstrumentError, "duplicate Macro8 route"):
            create_bundle(patch_bytes(patch), "Routes", format_version=2)

    def test_unknown_firstparty_future_model_is_not_assumed_to_have_ports(self) -> None:
        patch = sample_patch()
        patch["modules"].append(
            {"id": 88, "plugin": "ModularSynth", "model": "FutureModel"})
        patch["cables"][0].update(inputModuleId=88, inputId=4096)
        route = build_manifest(patch_bytes(patch), "Future", format_version=2)
        target = route["performance"]["controlMappings"][0]["destination"]
        self.assertEqual(target["inputKind"], "unverified")
        self.assertEqual(target["inputId"], 4096)

    def test_real_echo_motion_routes_all_four_controls(self) -> None:
        path = EXAMPLES / "MODULAR_-_Echo_Motion_Performance.vcv"
        if not path.is_file():
            self.skipTest("factory patch unavailable")
        raw = path.read_bytes()
        manifest, recovered = read_bundle(
            create_bundle(raw, "Echo Motion", format_version=2))
        self.assertEqual(recovered, raw)
        routes = manifest["performance"]["controlMappings"]
        self.assertEqual(len(routes), 4)
        self.assertEqual([route["source"]["outputId"] for route in routes],
                         [0, 1, 2, 3])
        self.assertEqual([route["destination"]["model"] for route in routes],
                         ["StereoEcho", "StereoEcho", "StereoEcho", "MorphVCO"])
        self.assertEqual([route["destination"]["inputId"] for route in routes],
                         [2, 3, 4, 2])
        self.assertEqual({route["destination"]["inputKind"] for route in routes},
                         {"cv"})

    def test_v2_pack_inspect_check_preview_unpack_and_repack(self) -> None:
        path = EXAMPLES / "MODULAR_-_Morphing_State_Pad.vcv"
        if not path.is_file():
            self.skipTest("factory patch unavailable")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "original.msinstrument"
            packed = pack(path, bundle, "Morphing State Pad", format_version=2)
            self.assertEqual(packed, inspect(bundle))
            self.assertEqual(check(bundle, ROOT)["status"], "PASS")
            svg_v2 = root / "v2.svg"
            preview(bundle, svg_v2)
            ET.fromstring(svg_v2.read_bytes())

            v1_bundle = root / "legacy.msinstrument"
            pack(path, v1_bundle, "Morphing State Pad")
            svg_v1 = root / "v1.svg"
            preview(v1_bundle, svg_v1)
            self.assertEqual(svg_v1.read_bytes(), svg_v2.read_bytes())

            out = root / "unpacked"
            self.assertEqual(unpack(bundle, out), packed)
            self.assertEqual((out / PATCH_MEMBER).read_bytes(), path.read_bytes())
            self.assertEqual(json.loads((out / MANIFEST_MEMBER).read_bytes()), packed)
            repacked = root / "repacked.msinstrument"
            pack(out / PATCH_MEMBER, repacked, "Morphing State Pad", format_version=2)
            self.assertEqual(bundle.read_bytes(), repacked.read_bytes())
            with self.assertRaises(FileExistsError):
                pack(path, repacked, "Morphing State Pad", format_version=2)

    def test_pack_cli_v2_explicit_and_no_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            patch = root / "source.vcv"
            patch.write_bytes(patch_bytes(routed_patch()))
            dest = root / "demo.msinstrument"
            with redirect_stdout(StringIO()) as stream:
                code = main(["pack", str(patch), "--format-version", "2",
                             "--name", "Routes", "--out", str(dest)])
            self.assertEqual(code, 0)
            self.assertIn("Packed", stream.getvalue())
            self.assertEqual(inspect(dest)["formatVersion"], 2)
            original = dest.read_bytes()
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["pack", str(patch), "--format-version", "2",
                                       "--name", "Routes", "--out", str(dest)]), 2)
            self.assertEqual(dest.read_bytes(), original)

    def test_noninteger_and_future_version_rejected(self) -> None:
        for version in (True, 0, -1, 3, 1.0, "2"):
            with self.subTest(version=version):
                with self.assertRaises(InstrumentError):
                    build_manifest(patch_bytes(), "Routes", format_version=version)


if __name__ == "__main__":
    unittest.main()
