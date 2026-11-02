"""Regression tests for safe, deterministic saved-instrument comparisons."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from instrument_builder import (
    MANIFEST_MEMBER, MAX_BUNDLE_BYTES, create_bundle, main, read_bundle,
)
from instrument_diff import compare_verified_bundles, text_diff_report
from test_instrument_builder import (
    custom_archive, patch_bytes, sample_patch,
)


class SavedInstrumentDifferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def bundle(self, content: bytes, name: str, label: str,
               version: int = 1) -> Path:
        target = self.root / f"{label}.msinstrument"
        target.write_bytes(create_bundle(
            content, name, format_version=version))
        return target

    def compare(self, before: Path, after: Path) -> dict:
        old_manifest, old_patch = read_bundle(before.read_bytes())
        new_manifest, new_patch = read_bundle(after.read_bytes())
        return compare_verified_bundles(
            old_manifest, old_patch, new_manifest, new_patch)

    def cli(self, before: Path, after: Path, *options: str) -> tuple[int, str, str]:
        with redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()) as err:
            status = main(["diff", str(before), str(after), *options])
            return status, out.getvalue(), err.getvalue()

    def test_identical_sources_have_no_changes(self) -> None:
        saved = self.bundle(patch_bytes(), "Same", "old")
        report = self.compare(saved, saved)
        self.assertFalse(report["changed"])
        self.assertFalse(report["sourcePatchBytesChanged"])
        self.assertEqual(report["changes"]["modules"], {
            "added": [], "removed": [], "modified": []})
        self.assertEqual(report["changes"]["cables"], {
            "added": [], "removed": [], "modified": []})
        self.assertEqual(report["changes"]["macro8"]["modified"], [])
        self.assertEqual(self.cli(saved, saved)[0], 0)
        self.assertIn("Semantic saved-state changes: NO",
                      text_diff_report(report))

    def test_reordered_arrays_and_json_whitespace_are_not_semantic(self) -> None:
        patch = sample_patch()
        new_bytes = (json.dumps(
            {"cables": list(reversed(patch["cables"])),
             "modules": list(reversed(patch["modules"])),
             "version": patch["version"]}, indent=4) + "\n").encode("utf-8")
        old = self.bundle(patch_bytes(patch), "Same", "old")
        new = self.bundle(new_bytes, "Same", "new")
        report = self.compare(old, new)
        self.assertFalse(report["changed"])
        self.assertTrue(report["sourcePatchBytesChanged"])
        self.assertEqual(report["changes"]["modules"]["modified"], [])
        self.assertEqual(report["changes"]["cables"]["modified"], [])
        self.assertEqual(self.cli(old, new, "--fail-on-change")[0], 0)
        self.assertIn("Only source JSON serialization/order changed",
                      text_diff_report(report))

    def test_absent_patch_metadata_differs_from_explicit_null(self) -> None:
        previous = sample_patch()
        current = deepcopy(previous)
        current["notes"] = None
        old = self.bundle(patch_bytes(previous), "Pad", "old")
        new = self.bundle(patch_bytes(current), "Pad", "new")
        report = self.compare(old, new)
        self.assertTrue(report["changed"])
        self.assertEqual(report["changes"]["patchMetadataFields"], ["notes"])

    def test_macro_values_labels_and_scenes_identify_changed_controls(self) -> None:
        original = sample_patch()
        edited = deepcopy(original)
        edited["modules"][0]["data"]["names"][0] = "Revoice"
        edited["modules"][0]["params"][0]["value"] = 0.6
        edited["modules"][0]["data"]["snapshots"][0][0] = 0.875
        old = self.bundle(patch_bytes(original), "Lead", "old")
        new = self.bundle(patch_bytes(edited), "Lead", "new")
        report = self.compare(old, new)
        self.assertTrue(report["changed"])
        self.assertEqual(report["changes"]["modules"]["modified"], [70])
        self.assertEqual(report["changes"]["cables"]["modified"], [])
        self.assertEqual(report["changes"]["macro8"]["modified"], [{
            "moduleId": 70,
            "fields": ["liveValues", "names", "snapshots"],
            "controlNumbers": [1],
            "snapshotSlots": ["A"],
        }])
        self.assertEqual(self.cli(old, new, "--fail-on-change")[0], 1)
        self.assertEqual(self.cli(old, new)[0], 0)

    def test_added_removed_and_rewired_graph_ids_are_stable(self) -> None:
        old_source = sample_patch()
        new_source = deepcopy(old_source)
        new_source["modules"][1]["id"] = 99
        new_source["modules"].append({
            "id": 13, "plugin": "Fundamental", "model": "VCO"})
        new_source["cables"][0]["inputModuleId"] = 99
        new_source["cables"].append({
            "id": 74, "outputModuleId": 13, "outputId": 0,
            "inputModuleId": 99, "inputId": 1})
        old = self.bundle(patch_bytes(old_source), "Patch", "old")
        new = self.bundle(patch_bytes(new_source), "Patch", "new")
        report = self.compare(old, new)
        self.assertEqual(report["changes"]["modules"], {
            "added": [13, 99], "removed": [71], "modified": []})
        self.assertEqual(report["changes"]["cables"], {
            "added": [74], "removed": [], "modified": [72]})
        self.assertTrue(report["changed"])

    def test_format_upgrade_is_explicit_not_a_live_route_claim(self) -> None:
        source = patch_bytes()
        old = self.bundle(source, "Pad", "v1", version=1)
        new = self.bundle(source, "Pad", "v2", version=2)
        report = self.compare(old, new)
        self.assertTrue(report["changes"]["formatVersion"])
        self.assertFalse(report["sourcePatchBytesChanged"])
        self.assertTrue(report["changed"])
        self.assertEqual(report["changes"]["modules"]["modified"], [])
        self.assertIn("historical routes are never reclassified in-place",
                      text_diff_report(report))
        code, output, error = self.cli(old, new, "--json")
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(json.loads(output), report)

    def test_name_only_change_is_distinct_from_patch_change(self) -> None:
        source = patch_bytes()
        old = self.bundle(source, "Old", "old")
        new = self.bundle(source, "New", "new")
        report = self.compare(old, new)
        self.assertTrue(report["changes"]["name"])
        self.assertFalse(report["sourcePatchBytesChanged"])
        self.assertEqual(report["changes"]["modules"]["modified"], [])

    def test_invalid_input_rejected_before_comparison_output(self) -> None:
        good = self.bundle(patch_bytes(), "Good", "good")
        corrupt = self.root / "corrupt.msinstrument"
        corrupt.write_bytes(b"not zip")
        for first, second in ((good, corrupt), (corrupt, good)):
            code, output, error = self.cli(first, second, "--json")
            self.assertEqual((code, output), (2, ""))
            self.assertIn("invalid ZIP archive", error)

        wrong_suffix = self.root / "other.zip"
        wrong_suffix.write_bytes(good.read_bytes())
        code, output, error = self.cli(good, wrong_suffix)
        self.assertEqual((code, output), (2, ""))
        self.assertIn("source bundle must end", error)

    def test_oversized_and_manifest_forgery_are_rejected(self) -> None:
        good = self.bundle(patch_bytes(), "Genuine", "good")
        oversized = self.root / "oversized.msinstrument"
        oversized.write_bytes(b"X" * (MAX_BUNDLE_BYTES + 1))
        code, output, error = self.cli(
            good, oversized, "--json", "--fail-on-change")
        self.assertEqual((code, output), (2, ""))
        self.assertIn("exceeds size limit", error)

        with zipfile.ZipFile(BytesIO(good.read_bytes())) as archive:
            entries = [(name, archive.read(name)) for name in archive.namelist()]
        manifest = json.loads(dict(entries)[MANIFEST_MEMBER])
        manifest["performance"]["macro8"][0]["liveValues"][0] = 0.99
        forged = self.root / "forged.msinstrument"
        forged.write_bytes(custom_archive([
            (name, json.dumps(manifest).encode("utf-8")
             if name == MANIFEST_MEMBER else data)
            for name, data in entries]))
        code, output, error = self.cli(
            forged, good, "--json", "--fail-on-change")
        self.assertEqual((code, output), (2, ""))
        self.assertIn("manifest does not match its patch", error)

    def test_json_and_text_reports_are_deterministic(self) -> None:
        old = self.bundle(patch_bytes(), "A", "old")
        newer = sample_patch()
        newer["version"] = "2.4.2"
        new = self.bundle(patch_bytes(newer), "B", "new")
        self.assertEqual(self.cli(old, new, "--json"),
                         self.cli(old, new, "--json"))
        status, output, error = self.cli(old, new, "--json")
        self.assertEqual((status, error), (0, ""))
        report = json.loads(output)
        self.assertEqual(report["changes"]["patchMetadataFields"], ["version"])
        status, output, error = self.cli(old, new, "--fail-on-change")
        self.assertEqual((status, error), (1, ""))
        self.assertIn("Patch-level fields changed: version", output)
        self.assertIn("NOT plugin loadability", output)


if __name__ == "__main__":
    unittest.main()
