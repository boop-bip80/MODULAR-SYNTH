"""Source-verified, offline Macro8 scene interpolation and CLI regression tests."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import BytesIO, StringIO
import json
import math
from pathlib import Path
import tempfile
import unittest
import zipfile

from instrument_builder import (InstrumentError, MANIFEST_MEMBER, create_bundle,
                                inspect, main, morph)
from morph_preview import MorphPreviewError, build_morph_preview, text_morph_preview
from test_instrument_builder import custom_archive, patch_bytes, sample_patch


class OfflineMacro8MorphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def save(self, patch: dict | None = None, *, version: int = 1,
             filename: str = "instrument") -> Path:
        path = self.root / f"{filename}.msinstrument"
        path.write_bytes(create_bundle(
            patch_bytes(sample_patch() if patch is None else patch),
            "Scene test", format_version=version))
        return path

    def cli(self, path: Path, *options: str) -> tuple[int, str, str]:
        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
            status = main(["morph", str(path), *options])
            return status, stdout.getvalue(), stderr.getvalue()

    def test_matches_one_pole_999_per_morph_time_and_is_read_only(self) -> None:
        path = self.save()
        original = path.read_bytes()
        report = morph(path, source="A", destination="B", elapsed_seconds=1.0)
        self.assertEqual(report["instrument"], "Scene test")
        self.assertEqual(report["moduleId"], 70)
        self.assertEqual(report["savedSelectedSource"], "A")
        self.assertEqual(report["fromScene"], "A")
        self.assertEqual(report["toScene"], "B")
        self.assertEqual(report["sampleRate"], 48000)
        self.assertEqual(report["sampleCount"], 48000)
        self.assertEqual(report["quantizedElapsedSeconds"], 1.0)
        self.assertAlmostEqual(report["completionFraction"], 0.999, places=12)
        expected = 0.125 + (0.75 - 0.125) * 0.999
        self.assertAlmostEqual(report["controls"][0]["predictedNormalized"], expected)
        self.assertAlmostEqual(report["controls"][0]["predictedNominalVolts"],
                               expected * 10)
        self.assertEqual(len(report["controls"]), 8)
        self.assertIn("NOT a live CV measurement", report["scope"])
        self.assertEqual(path.read_bytes(), original)

    def test_saved_live_knob_bipolar_snapshots_and_noswitch(self) -> None:
        patch = sample_patch()
        patch["modules"][0]["params"][15]["value"] = 1.0  # Bipolar -5..+5.
        patch["modules"][0]["data"]["selectedSlot"] = -1
        path = self.save(patch)
        before = path.read_bytes()
        start = morph(path, source="LIVE", destination="A", elapsed_seconds=0)
        first = start["controls"][0]
        self.assertEqual((first["fromNormalized"], first["toNormalized"]),
                         (0.25, 0.125))
        self.assertEqual(first["predictedNominalVolts"], -2.5)
        self.assertEqual(start["savedSelectedSource"], "LIVE")
        end = morph(path, source="B", destination="LIVE", elapsed_seconds=3600)
        self.assertEqual(end["controls"][0]["predictedNormalized"], 0.25)
        self.assertEqual(end["controls"][0]["predictedNominalVolts"], -2.5)
        self.assertEqual(path.read_bytes(), before)

    def test_exact_sample_count_rounding_and_zero_time_immediate_step(self) -> None:
        patch = sample_patch()
        patch["modules"][0]["params"][8]["value"] = 0.0
        path = self.save(patch)
        from_scene = morph(path, source="A", destination="B", elapsed_seconds=0)
        self.assertEqual(from_scene["sampleCount"], 0)
        self.assertEqual(from_scene["completionFraction"], 0)
        self.assertEqual(from_scene["controls"][0]["predictedNormalized"], 0.125)
        immediate = morph(path, source="A", destination="B",
                          elapsed_seconds=1 / 48000)
        self.assertEqual(immediate["sampleCount"], 1)
        self.assertEqual(immediate["completionFraction"], 1)
        self.assertEqual(immediate["controls"][0]["predictedNormalized"], 0.75)
        sub_sample = morph(path, source="A", destination="B",
                           elapsed_seconds=0.49 / 48000)
        self.assertEqual(sub_sample["sampleCount"], 0)
        self.assertEqual(sub_sample["controls"][0]["predictedNormalized"], 0.125)

    def test_steady_scene_and_one_pole_fraction_near_zero(self) -> None:
        report = morph(self.save(), source="A", destination="A",
                       elapsed_seconds=1 / 48000)
        self.assertEqual(report["controls"][0]["predictedNormalized"], 0.125)
        self.assertAlmostEqual(report["completionFraction"],
                               -math.expm1(-math.log(1000.0) / 48000))
        self.assertTrue(all(0 <= item["predictedNormalized"] <= 1
                            for item in report["controls"]))

    def test_requires_explicit_module_id_when_multiple_macro8(self) -> None:
        patch = sample_patch()
        second = deepcopy(patch["modules"][0])
        second["id"] = 19
        second["data"]["names"][0] = "Second"
        second["data"]["snapshots"][1] = [0.5] * 8
        patch["modules"].append(second)
        saved = self.save(patch, version=2)
        with self.assertRaisesRegex(InstrumentError, "--module-id"):
            morph(saved, source="A", destination="B", elapsed_seconds=0.5)
        report = morph(saved, source="A", destination="B", elapsed_seconds=0.5,
                       module_id=19)
        self.assertEqual(report["moduleId"], 19)
        self.assertEqual(report["controls"][0]["name"], "Second")
        self.assertEqual(report["controls"][0]["toNormalized"], 0.5)
        with self.assertRaisesRegex(InstrumentError, "no Macro8 module"):
            morph(saved, source="A", destination="B", elapsed_seconds=0.5,
                  module_id=404)

    def test_missing_saved_scene_and_invalid_numerics_fail_safely(self) -> None:
        saved = self.save()
        manifest = inspect(saved)
        for source, destination in (("C", "B"), ("A", "D")):
            with self.subTest(source=source, destination=destination):
                with self.assertRaisesRegex(InstrumentError, "no stored snapshot"):
                    morph(saved, source=source, destination=destination,
                          elapsed_seconds=0)
        for elapsed in (-1, float("nan"), float("inf"),
                        float("-inf"), 3600.01, True, "0.5", 10**1000):
            with self.subTest(elapsed=str(elapsed)[:40]):
                with self.assertRaises(MorphPreviewError):
                    build_morph_preview(manifest, source="A", destination="B",
                                        elapsed_seconds=elapsed)
        for rate in (0, 1, 7999, 384001, True, float("nan"), 48000.0):
            with self.subTest(rate=rate):
                with self.assertRaises(MorphPreviewError):
                    build_morph_preview(manifest, source="A", destination="B",
                                        elapsed_seconds=0.5, sample_rate=rate)
        for ident in (-1, True, 2**63, "70"):
            with self.subTest(module_id=ident):
                with self.assertRaises(MorphPreviewError):
                    build_morph_preview(manifest, source="A", destination="B",
                                        elapsed_seconds=0.5, module_id=ident)
        for invalid in ("E", "a", "", "Snapshot A", None):
            with self.subTest(scene=invalid):
                with self.assertRaises(MorphPreviewError):
                    build_morph_preview(manifest, source=invalid,
                                        destination="B", elapsed_seconds=1)

    def test_cli_text_and_json_report_identical_repeatable_read_only(self) -> None:
        saved = self.save(version=2)
        before = saved.read_bytes()
        args = ("--from", "A", "--to", "B", "--at", "0.5", "--sample-rate", "44100")
        code, output, stderr = self.cli(saved, *args)
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("A -> B", output)
        self.assertIn("22050 samples at 44100 Hz", output)
        self.assertIn("NOT a live CV measurement", output)
        self.assertIn("estimated", output)
        code2, structured, stderr2 = self.cli(saved, *args, "--json")
        self.assertEqual((code2, stderr2), (0, ""))
        self.assertEqual(json.loads(structured),
                         morph(saved, source="A", destination="B",
                               elapsed_seconds=0.5, sample_rate=44100))
        self.assertEqual(self.cli(saved, *args, "--json")[1], structured)
        self.assertEqual(text_morph_preview(json.loads(structured)), output)
        self.assertEqual(saved.read_bytes(), before)

    def test_forged_manifest_and_invalid_bundle_produce_no_preview(self) -> None:
        invalid = self.root / "invalid.msinstrument"
        invalid.write_bytes(b"not a ZIP")
        request = ("--from", "A", "--to", "B", "--at", "0.5", "--json")
        status, stdout, stderr = self.cli(invalid, *request)
        self.assertEqual((status, stdout), (2, ""))
        self.assertIn("invalid ZIP archive", stderr)

        genuine = create_bundle(patch_bytes(), "Genuine")
        with zipfile.ZipFile(BytesIO(genuine)) as archive:
            entries = [(name, archive.read(name)) for name in archive.namelist()]
        manifest = json.loads(dict(entries)[MANIFEST_MEMBER])
        manifest["performance"]["macro8"][0]["snapshots"][1][0] = 0.33
        forged = self.root / "forged.msinstrument"
        forged.write_bytes(custom_archive([
            (name, json.dumps(manifest).encode("utf-8")
             if name == MANIFEST_MEMBER else blob)
            for name, blob in entries
        ]))
        status, stdout, stderr = self.cli(forged, *request)
        self.assertEqual((status, stdout), (2, ""))
        self.assertIn("does not match its patch", stderr)


if __name__ == "__main__":
    unittest.main()
