"""Offline Instrument Builder roundtrip, schema, and hostile ZIP tests."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import warnings
import zipfile

from instrument_builder import (
    FORMAT, FORMAT_VERSION, InstrumentError, MANIFEST_MEMBER, MAX_BUNDLE_BYTES,
    MAX_PATCH_BYTES, PATCH_MEMBER, ZIP_TIMESTAMP, build_manifest, create_bundle,
    inspect, main, pack, patch_performance, read_bundle, unpack,
)


def sample_patch() -> dict:
    return {
        "version": "2.4.1",
        "modules": [
            {
                "id": 70, "plugin": "ModularSynth", "model": "Macro8",
                "params": [
                    {"id": i, "value": 0.25 if i < 8 else
                     (1.0 if i == 8 else 0.0)}
                    for i in range(23)
                ],
                "data": {
                    "macro8Version": 1,
                    "names": ["Shape", "Tone", "Drive", "Macro 4", "Macro 5",
                              "Macro 6", "Macro 7", "Macro 8"],
                    "snapshots": [
                        [0.125] * 8, [0.75] * 8, None, None,
                    ],
                    "selectedSlot": 0,
                },
            },
            {"id": 71, "plugin": "Cardinal", "model": "HostAudio2"},
        ],
        "cables": [{
            "id": 72, "outputModuleId": 70, "outputId": 0,
            "inputModuleId": 71, "inputId": 0,
        }],
    }


def patch_bytes(patch: dict | None = None) -> bytes:
    return (json.dumps(sample_patch() if patch is None else patch,
                       sort_keys=True, separators=(",", ":"), allow_nan=True)
            + "\n").encode("utf-8")


def custom_archive(entries: list[tuple[str, bytes]], *,
                   compression: int = zipfile.ZIP_STORED,
                   symlink: str | None = None,
                   create_system: int = 3) -> bytes:
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, blob in entries:
            info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
            info.create_system = create_system
            mode = stat.S_IFLNK if name == symlink else stat.S_IFREG
            info.external_attr = (mode | 0o644) << 16
            info.compress_type = compression
            archive.writestr(info, blob)
    return stream.getvalue()


def valid_entries() -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(BytesIO(create_bundle(patch_bytes(), "Synth"))) as archive:
        return [(name, archive.read(name)) for name in archive.namelist()]


class InstrumentBuilderTests(unittest.TestCase):
    def test_manifest_represents_actual_macro8_state(self):
        patch = sample_patch()
        macro = patch["modules"][0]
        macro["params"][15]["value"] = 1.0
        macro["params"][17]["value"] = 0.75
        macro["params"][9]["value"] = 1.0
        manifest = build_manifest(patch_bytes(patch), "Test Synth")
        self.assertEqual(manifest["format"], FORMAT)
        self.assertEqual(manifest["formatVersion"], FORMAT_VERSION)
        self.assertEqual(manifest["requiredPlugins"], ["Cardinal", "ModularSynth"])
        state = manifest["performance"]["macro8"][0]
        self.assertEqual(state["moduleId"], 70)
        self.assertEqual(state["stateVersion"], 1)
        self.assertEqual(state["names"][:3], ["Shape", "Tone", "Drive"])
        self.assertEqual(state["ranges"][:4],
                         ["bipolar", "unipolar", "bipolar", "unipolar"])
        self.assertEqual(state["liveValues"], [0.25] * 8)
        self.assertEqual(state["morphSeconds"], 1.0)
        self.assertEqual(state["snapshotAction"], "store")
        self.assertEqual(state["snapshots"][0], [0.125] * 8)
        self.assertEqual(state["snapshots"][1], [0.75] * 8)
        self.assertEqual(state["snapshots"][2:], [None, None])
        self.assertEqual(state["selectedSlot"], 0)

    def test_multiple_macro8_are_sorted_by_stable_module_id(self):
        patch = sample_patch()
        second = deepcopy(patch["modules"][0])
        second["id"] = 8
        second["data"]["names"][0] = "Other"
        patch["modules"].append(second)
        performance, plugins = patch_performance(patch_bytes(patch))
        self.assertEqual([item["moduleId"] for item in performance], [8, 70])
        self.assertEqual(performance[0]["names"][0], "Other")
        self.assertEqual(plugins, ["Cardinal", "ModularSynth"])

    def test_deterministic_zip_and_roundtrip_without_patch_reformatting(self):
        patch = patch_bytes()
        a = create_bundle(patch, "Test Synth")
        b = create_bundle(patch, "Test Synth")
        self.assertEqual(a, b)
        manifest, recovered = read_bundle(a)
        self.assertEqual(recovered, patch)
        self.assertEqual(manifest, build_manifest(patch, "Test Synth"))
        with zipfile.ZipFile(BytesIO(a)) as archive:
            self.assertEqual(archive.namelist(),
                             [MANIFEST_MEMBER, PATCH_MEMBER])
            for info in archive.infolist():
                self.assertEqual(info.date_time, ZIP_TIMESTAMP)
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(stat.S_IFMT(info.external_attr >> 16),
                                 stat.S_IFREG)
        self.assertLess(len(a), MAX_BUNDLE_BYTES)

    def test_pack_inspect_unpack_and_repack_are_lossless(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.vcv"
            source.write_bytes(patch_bytes())
            archive = root / "source.msinstrument"
            manifest = pack(source, archive, "Source Instrument")
            self.assertEqual(inspect(archive), manifest)
            destination = root / "unpacked"
            self.assertEqual(unpack(archive, destination), manifest)
            self.assertEqual((destination / "patch/main.vcv").read_bytes(),
                             source.read_bytes())
            self.assertEqual(json.loads(
                (destination / "manifest.json").read_text()), manifest)
            repacked = root / "repacked.msinstrument"
            pack(destination / "patch/main.vcv", repacked, "Source Instrument")
            self.assertEqual(archive.read_bytes(), repacked.read_bytes())

    def test_cli_command_flow(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            patch = root / "test.vcv"
            patch.write_bytes(patch_bytes())
            bundle = root / "test.msinstrument"
            out = root / "source"
            with redirect_stdout(StringIO()) as stream:
                self.assertEqual(main(["pack", str(patch), "--out", str(bundle),
                                       "--name", "Demo"]), 0)
                self.assertEqual(main(["inspect", str(bundle)]), 0)
                self.assertEqual(main(["unpack", str(bundle), "--out",
                                       str(out)]), 0)
            self.assertIn('"formatVersion": 1', stream.getvalue())
            self.assertTrue((out / "patch/main.vcv").is_file())

    def test_real_factory_macro8_patch_if_available(self):
        repository = Path(__file__).resolve().parents[2]
        patch = repository / "patches/examples/MODULAR_-_Morphing_State_Pad.vcv"
        if not patch.is_file():
            self.skipTest("bundled Macro8 factory patch not present")
        blob = patch.read_bytes()
        manifest, recovered = read_bundle(create_bundle(blob, "Morphing Pad"))
        self.assertEqual(recovered, blob)
        self.assertEqual(manifest["requiredPlugins"],
                         ["Cardinal", "Fundamental", "ModularSynth"])
        state = manifest["performance"]["macro8"][0]
        self.assertEqual(state["names"][:3], ["Shape", "Resonance", "Drive"])
        self.assertEqual(state["liveValues"][:3], [0.25, 0.18, 0.08])
        self.assertEqual(state["morphSeconds"], 1.0)
        self.assertEqual(state["snapshots"][0][:3], [0.12, 0.08, 0.04])
        self.assertEqual(state["snapshots"][1][:3], [0.74, 0.57, 0.26])

    def test_invalid_patch_schemas_rejected(self):
        cases = [
            ("no modules", lambda x: x.update(modules=[])),
            ("missing Macro8", lambda x: x["modules"].pop(0)),
            ("duplicate id", lambda x: x["modules"][1].update(id=70)),
            ("bad name", lambda x: x["modules"][0]["data"]["names"].__setitem__(
                0, "TOO-LONG-MACRO-LABEL")),
            ("unknown Macro8 state version", lambda x: x["modules"][0]["data"].update(
                macro8Version=2)),
            ("missing snapshot", lambda x: x["modules"][0]["data"].update(
                snapshots=[None, None])),
            ("bad snapshot value", lambda x: x["modules"][0]["data"]["snapshots"][0].__setitem__(
                3, 1.5)),
            ("selected empty slot", lambda x: x["modules"][0]["data"].update(
                selectedSlot=3)),
            ("invalid range", lambda x: x["modules"][0]["params"][15].update(
                value=42)),
            ("duplicate parameter", lambda x: x["modules"][0]["params"][1].update(
                id=0)),
            ("bad cable endpoint", lambda x: x["cables"][0].update(
                inputModuleId=999)),
            ("duplicate cable id", lambda x: x["cables"].append(
                deepcopy(x["cables"][0]))),
            ("nonfinite control", lambda x: x["modules"][0]["params"][0].update(
                value=float("nan"))),
            ("nonfinite snapshot", lambda x: x["modules"][0]["data"]["snapshots"][0].__setitem__(
                0, float("inf"))),
        ]
        for label, mutation in cases:
            with self.subTest(case=label):
                patch = sample_patch()
                mutation(patch)
                with self.assertRaises(InstrumentError):
                    build_manifest(patch_bytes(patch), "Demo")
        with self.assertRaisesRegex(InstrumentError, "duplicate JSON key"):
            patch_performance(b'{"version":"2.4.1","version":"2.4.1","modules":[]}')
        with self.assertRaises(InstrumentError):
            patch_performance(patch_bytes().replace(b"0.25", b"1e999", 1))
        with self.assertRaises(InstrumentError):
            patch_performance(b"x" * (MAX_PATCH_BYTES + 1))

    def test_invalid_name_and_unsupported_bundle_version_rejected(self):
        for name in ("", "bad\nname", "bad\x00name", "x" * 65):
            with self.subTest(name=repr(name)):
                with self.assertRaises(InstrumentError):
                    create_bundle(patch_bytes(), name)
        entries = valid_entries()
        fragment = json.loads(entries[0][1])
        fragment["formatVersion"] = 99
        entries[0] = (MANIFEST_MEMBER, json.dumps(fragment).encode())
        with self.assertRaisesRegex(InstrumentError, "format/version"):
            read_bundle(custom_archive(entries))

    def test_tampered_manifest_is_detected(self):
        entries = valid_entries()
        manifest = json.loads(entries[0][1])
        manifest["performance"]["macro8"][0]["names"][0] = "Spoofed"
        entries[0] = (MANIFEST_MEMBER, json.dumps(manifest).encode())
        with self.assertRaisesRegex(InstrumentError, "does not match"):
            read_bundle(custom_archive(entries))
        entries = valid_entries()
        entries[1] = (PATCH_MEMBER, entries[1][1] + b"\n")
        with self.assertRaisesRegex(InstrumentError, "does not match"):
            read_bundle(custom_archive(entries))

    def test_hostile_zip_paths_rejected_before_unpacked_files_written(self):
        good = valid_entries()
        candidates = (
            "../escaped.vcv", "/root/escaped.vcv", "patch/../../escape.vcv",
            "C:\\escape.vcv", "patch\\main.vcv", "./patch/main.vcv",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, name in enumerate(candidates):
                with self.subTest(name=name):
                    candidate = custom_archive([good[0], (name, good[1][1])])
                    bundle = root / f"bad{index}.msinstrument"
                    bundle.write_bytes(candidate)
                    destination = root / f"out{index}"
                    with self.assertRaises(InstrumentError):
                        unpack(bundle, destination)
                    self.assertFalse(destination.exists())
                    self.assertFalse((root / "escaped.vcv").exists())

    def test_zip_symlink_duplicate_compression_and_extra_entry_rejected(self):
        entries = valid_entries()
        archives = [
            custom_archive(entries, symlink=PATCH_MEMBER),
            custom_archive(entries, create_system=0),
            custom_archive(entries, compression=zipfile.ZIP_DEFLATED),
            custom_archive(entries + [("evil", b"payload")]),
        ]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            archives.append(custom_archive(entries + [entries[1]]))
        for archive in archives:
            with self.subTest(blob_size=len(archive)):
                with self.assertRaises(InstrumentError):
                    read_bundle(archive)
        with self.assertRaises(InstrumentError):
            read_bundle(b"not a zip file")
        with self.assertRaises(InstrumentError):
            read_bundle(b"x" * (MAX_BUNDLE_BYTES + 1))

    def test_pack_and_unpack_never_overwrite_existing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            patch = root / "example.vcv"
            patch.write_bytes(patch_bytes())
            archive = root / "example.msinstrument"
            archive.write_text("user file; keep me")
            with self.assertRaises(FileExistsError):
                pack(patch, archive, "Demo")
            self.assertEqual(archive.read_text(), "user file; keep me")
            archive.unlink()
            pack(patch, archive, "Demo")
            destination = root / "extracted"
            destination.mkdir()
            sentinel = destination / "important.txt"
            sentinel.write_text("do not overwrite")
            with self.assertRaises(FileExistsError):
                unpack(archive, destination)
            self.assertEqual(sentinel.read_text(), "do not overwrite")
            self.assertFalse((destination / "manifest.json").exists())

    def test_reject_source_or_destination_symlinks(self):
        if os.name != "posix":
            self.skipTest("requires POSIX symlinks/no-follow directories")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            actual = root / "actual"
            actual.mkdir()
            patch = actual / "real.vcv"
            patch.write_bytes(patch_bytes())
            link = root / "shortcut"
            link.symlink_to(actual, target_is_directory=True)
            with self.assertRaises((InstrumentError, OSError)):
                pack(link / "real.vcv", link / "bad.msinstrument", "Demo")
            self.assertFalse((actual / "bad.msinstrument").exists())
            source_link = root / "linked.vcv"
            source_link.symlink_to(patch)
            with self.assertRaises(InstrumentError):
                pack(source_link, root / "bad.msinstrument", "Demo")
            bundle = root / "safe.msinstrument"
            pack(patch, bundle, "Demo")
            with self.assertRaises((InstrumentError, OSError)):
                unpack(bundle, link / "new")
            self.assertFalse((actual / "new").exists())


if __name__ == "__main__":
    unittest.main()
