"""Source-only compatibility checks with genuine factory patch coverage."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from compatibility import (
    CompatibilityError, collection_slugs, compatibility_report,
    patch_references, text_report,
)
from instrument_builder import (
    InstrumentError, _canonical_json, _decode_json, check, create_bundle,
    main, read_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
COLLECTION = ROOT / "plugins/ModularSynth/plugin.json"
EXAMPLES = (
    "Cinematic_Drift_Pad",
    "Clockwork_Pulses",
    "Granular_Veil",
    "Morph_VCO_Performance",
    "Morphing_State_Pad",
    "Polyphonic_Motion_Pad",
    "Pulse_Bass",
    "Rhythmic_Grit_Bass",
    "Stereo_Echo_Showcase",
)


def example_patch(name: str = "Morphing_State_Pad") -> bytes:
    return (ROOT / f"patches/examples/MODULAR_-_{name}.vcv").read_bytes()


def registry() -> dict:
    return json.loads(COLLECTION.read_text(encoding="utf-8"))


def changed_patch(change) -> bytes:
    patch = json.loads(example_patch())
    change(patch)
    return (json.dumps(patch, sort_keys=True, ensure_ascii=True) + "\n").encode()


class CompatibilityTests(unittest.TestCase):
    def test_nine_genuine_examples_have_no_missing_firstparty_references(self):
        slugs = collection_slugs(registry())
        self.assertTrue({"Macro8", "MorphVCO", "StateFilter", "StereoEcho"}.issubset(slugs))
        macro_bundles = 0
        for name in EXAMPLES:
            with self.subTest(example=name):
                raw = example_patch(name)
                patch = _decode_json(raw, f"{name}.vcv")
                refs = patch_references(patch)
                report = compatibility_report(patch, registry())
                self.assertEqual(report["status"], "PASS")
                self.assertEqual(report["summary"]["missing"], 0)
                self.assertEqual(report["bundleIntegrity"], "NOT_CHECKED")
                for row in report["references"]:
                    if row["plugin"] == "ModularSynth":
                        self.assertEqual(row["status"], "DECLARED")
                        self.assertIn(row["model"], slugs)
                    else:
                        self.assertEqual(row["status"], "UNKNOWN")
                if ("ModularSynth", "Macro8") in refs:
                    archive = create_bundle(raw, name.replace("_", " "))
                    manifest, recovered = read_bundle(archive)
                    self.assertEqual(recovered, raw)
                    verified = compatibility_report(
                        patch, registry(),
                        patch_sha256=manifest["patch"]["sha256"],
                        required_plugins=manifest["requiredPlugins"])
                    self.assertEqual(verified["bundleIntegrity"], "VERIFIED")
                    self.assertEqual(verified["status"], "PASS")
                    macro_bundles += 1
        self.assertGreaterEqual(macro_bundles, 4)

    def test_valid_bundle_check_text_json_and_cli_are_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / "pad.msinstrument"
            original = create_bundle(example_patch(), "Morphing State Pad")
            bundle.write_bytes(original)
            first = check(bundle, ROOT)
            second = check(bundle, ROOT)
            self.assertEqual(first, second)
            self.assertEqual(first["status"], "PASS")
            self.assertEqual(first["bundleIntegrity"], "VERIFIED")
            self.assertEqual(first["summary"]["missing"], 0)
            self.assertGreater(first["summary"]["declared"], 0)
            self.assertGreater(first["summary"]["unknown"], 0)
            self.assertIn("DECLARED ModularSynth/Macro8", text_report(first))
            self.assertIn("UNKNOWN  Cardinal/", text_report(first))
            self.assertEqual(text_report(first), text_report(second))
            self.assertEqual(_canonical_json(first), _canonical_json(second))
            with redirect_stdout(StringIO()) as output:
                status = main(["check", str(bundle), "--repo-root", str(ROOT)])
            self.assertEqual(status, 0)
            self.assertEqual(output.getvalue(), text_report(first))
            with redirect_stdout(StringIO()) as output:
                status = main(["check", str(bundle), "--repo-root", str(ROOT),
                               "--format", "json"])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue()), first)
            self.assertEqual(output.getvalue(),
                             _canonical_json(first).decode("utf-8"))
            with redirect_stdout(StringIO()) as output:
                status = main(["check", str(bundle), "--json"])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue()), first)
            self.assertEqual(bundle.read_bytes(), original)
            self.assertNotIn(str(ROOT), text_report(first))

    def test_missing_firstparty_slug_fails_without_condemning_external_refs(self):
        def break_filter(patch):
            for module in patch["modules"]:
                if module["plugin"] == "ModularSynth" and module["model"] == "StateFilter":
                    module["model"] = "DefinitelyMissingFilter"
                    return
            raise AssertionError("real patch no longer has StateFilter")

        raw = changed_patch(break_filter)
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / "missing.msinstrument"
            bundle.write_bytes(create_bundle(raw, "Missing Filter Demo"))
            report = check(bundle, ROOT)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["summary"]["missing"], 1)
            missing = [ref for ref in report["references"] if ref["status"] == "MISSING"]
            self.assertEqual(len(missing), 1)
            self.assertEqual(missing[0]["plugin"], "ModularSynth")
            self.assertEqual(missing[0]["model"], "DefinitelyMissingFilter")
            self.assertTrue(any(
                ref["status"] == "UNKNOWN" and ref["plugin"] != "ModularSynth"
                for ref in report["references"]))
            with redirect_stdout(StringIO()) as output:
                code = main(["check", str(bundle), "--repo-root", str(ROOT)])
            self.assertEqual(code, 1)
            self.assertIn("MISSING  ModularSynth/DefinitelyMissingFilter",
                          output.getvalue())
            with redirect_stdout(StringIO()) as output:
                code = main(["check", str(bundle), "--format", "json"])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.getvalue())["status"], "FAIL")

    def test_unknown_thirdparty_or_case_variant_is_not_assumed_installed(self):
        def append_unknown(patch):
            patch["modules"].append({
                "id": 991234567, "plugin": "WishfulSynthesis",
                "model": "DreamOsc", "params": [],
            })
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / "external.msinstrument"
            bundle.write_bytes(create_bundle(
                changed_patch(append_unknown), "External Demo"))
            report = check(bundle, ROOT)
            self.assertEqual(report["status"], "PASS")
            unknown = [ref for ref in report["references"]
                       if ref["plugin"] == "WishfulSynthesis"]
            self.assertEqual(len(unknown), 1)
            self.assertEqual(unknown[0]["status"], "UNKNOWN")

        def case_mismatch(patch):
            for module in patch["modules"]:
                if module["plugin"] == "ModularSynth" and module["model"] == "StateFilter":
                    module["model"] = "statefilter"
                    return
        patch = _decode_json(changed_patch(case_mismatch), "case fixture")
        report = compatibility_report(patch, registry())
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["summary"]["missing"], 1)

    def test_model_instance_grouping_and_sort_order_are_stable(self):
        patch = {
            "version": "2.4.1",
            "modules": [
                {"id": 9, "plugin": "Cardinal", "model": "HostAudio2"},
                {"id": 2, "plugin": "ModularSynth", "model": "Macro8"},
                {"id": 1, "plugin": "Cardinal", "model": "HostAudio2"},
                {"id": 7, "plugin": "Fundamental", "model": "ADSR"},
            ],
        }
        refs = patch_references(patch)
        self.assertEqual(refs[("Cardinal", "HostAudio2")], [1, 9])
        report = compatibility_report(patch, registry())
        self.assertEqual(
            [(r["plugin"], r["model"], r["status"]) for r in report["references"]],
            [("ModularSynth", "Macro8", "DECLARED"),
             ("Cardinal", "HostAudio2", "UNKNOWN"),
             ("Fundamental", "ADSR", "UNKNOWN")])
        self.assertEqual(report["summary"],
                         {"declared": 1, "missing": 0, "unknown": 2})

    def test_registry_collisions_and_invalid_collection_are_rejected(self):
        source = registry()
        cases = [
            lambda c: c.update(slug="WrongCollection"),
            lambda c: c.update(modules=[]),
            lambda c: c["modules"].append({"slug": "macro8"}),
            lambda c: c["modules"].append({"slug": "../escape"}),
        ]
        for change in cases:
            with self.subTest(change=str(change)):
                modified = deepcopy(source)
                change(modified)
                with self.assertRaises(CompatibilityError):
                    collection_slugs(modified)

    def test_requiredplugins_mismatch_is_rejected(self):
        patch = _decode_json(example_patch(), "factory patch")
        with self.assertRaisesRegex(CompatibilityError, "requiredPlugins"):
            compatibility_report(
                patch, registry(), required_plugins=["ModularSynth"])
        with self.assertRaisesRegex(CompatibilityError, "SHA-256"):
            compatibility_report(patch, registry(), patch_sha256="not_a_hash")

    def test_tampered_bundle_manifest_is_rejected_before_report(self):
        raw = create_bundle(example_patch(), "Pad")
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            payload = json.loads(archive.read("manifest.json"))
            source = archive.read("patch/main.vcv")
        payload["requiredPlugins"] = ["ModularSynth"]
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / "tampered.msinstrument"
            with zipfile.ZipFile(bundle, "w") as archive:
                for name, content in (
                    ("manifest.json", json.dumps(payload).encode()),
                    ("patch/main.vcv", source),
                ):
                    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | 0o644) << 16
                    archive.writestr(info, content)
            with self.assertRaises(InstrumentError):
                check(bundle, ROOT)
            with redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as error:
                code = main(["check", str(bundle), "--repo-root", str(ROOT)])
            self.assertEqual(code, 2)
            self.assertEqual(output.getvalue(), "")
            self.assertIn("Instrument Builder:", error.getvalue())

    def test_invalid_registry_or_missing_file_never_looks_compatible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "pad.msinstrument"
            bundle.write_bytes(create_bundle(example_patch(), "Pad"))
            fake_root = root / "checkout"
            registry_file = fake_root / "plugins/ModularSynth/plugin.json"
            registry_file.parent.mkdir(parents=True)
            registry_file.write_text('{"slug":"not ModularSynth","modules":[]}')
            with self.assertRaises(InstrumentError):
                check(bundle, fake_root)
            registry_file.unlink()
            with self.assertRaises(InstrumentError):
                check(bundle, fake_root)
            self.assertTrue(bundle.is_file())

    def test_symlink_registry_file_is_rejected(self):
        if os.name != "posix":
            self.skipTest("symlink test on POSIX")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "pad.msinstrument"
            bundle.write_bytes(create_bundle(example_patch(), "Pad"))
            checkout = root / "checkout"
            link = checkout / "plugins/ModularSynth/plugin.json"
            link.parent.mkdir(parents=True)
            external = root / "manifest.json"
            external.write_text(COLLECTION.read_text())
            link.symlink_to(external)
            with self.assertRaises(InstrumentError):
                check(bundle, checkout)

    def test_patch_reference_parser_rejects_bad_module_ids_and_fields(self):
        source = {
            "version": "2.4.1",
            "modules": [{"id": 1, "plugin": "ModularSynth", "model": "Macro8"}],
        }
        variants = [
            lambda p: p["modules"][0].update(id=True),
            lambda p: p["modules"][0].update(plugin=""),
            lambda p: p["modules"][0].update(model="\n"),
            lambda p: p["modules"].append(deepcopy(p["modules"][0])),
            lambda p: p.update(modules=[]),
        ]
        for change in variants:
            with self.subTest(change=str(change)):
                modified = deepcopy(source)
                change(modified)
                with self.assertRaises(CompatibilityError):
                    patch_references(modified)


if __name__ == "__main__":
    unittest.main()
