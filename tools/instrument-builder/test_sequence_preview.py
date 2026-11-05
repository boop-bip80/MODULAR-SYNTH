"""Source-bundle multi-scene CV timeline and adversarial CLI regressions."""
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

from instrument_builder import (InstrumentError, MANIFEST_MEMBER,
                                create_bundle, inspect, main, sequence)
from sequence_preview import (SequencePreviewError, build_sequence_preview,
                              parse_events, parse_query_times,
                              text_sequence_preview)
from test_instrument_builder import custom_archive, patch_bytes, sample_patch


class Macro8SequencePreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def save(self, patch: dict | None = None, *, version: int = 1) -> Path:
        path = self.root / "scene.msinstrument"
        path.write_bytes(create_bundle(
            patch_bytes(sample_patch() if patch is None else patch),
            "Sequencer test", format_version=version))
        return path

    def cli(self, path: Path, *flags: str) -> tuple[int, str, str]:
        with redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()) as err:
            code = main(["sequence", str(path), *flags])
            return code, out.getvalue(), err.getvalue()

    def test_single_scene_matches_one_pole_and_preserves_archive_bytes(self) -> None:
        bundle = self.save(version=2)
        raw = bundle.read_bytes()
        result = sequence(bundle, source="A", event_spec="0:B",
                          time_spec="0,0.5,1,2", sample_rate=48000)
        self.assertIn("NOT emitted CV", result["scope"])
        self.assertEqual(result["moduleId"], 70)
        self.assertEqual(result["events"], [
            {"requestedSeconds": 0.0, "sampleCount": 0,
             "quantizedSeconds": 0.0, "scene": "B"}])
        self.assertEqual([x["sampleCount"] for x in result["snapshots"]],
                         [0, 24000, 48000, 96000])
        first = result["snapshots"][0]["controls"][0]
        last = result["snapshots"][2]["controls"][0]
        self.assertEqual((first["predictedNormalized"], first["predictedNominalVolts"]),
                         (0.125, 1.25))
        self.assertAlmostEqual(last["predictedNormalized"],
                               0.125 + (0.75 - 0.125) * .999, places=12)
        self.assertEqual(result["snapshots"][0]["activeTarget"], "B")
        self.assertEqual(bundle.read_bytes(), raw)

    def test_unfinished_scene_switch_matches_independent_per_sample_reference(self) -> None:
        bundle = self.save()
        rate = 8000
        query = [0, 0.125, 0.2, 0.3]
        events = [(0.0, "B"), (0.125, "A"), (0.2, "B")]
        result = sequence(bundle, source="A", event_spec="0:B,0.125:A,0.2:B",
                          time_spec="0,0.125,0.2,0.3", sample_rate=rate)
        # Independent process(sampleTime) recurrence, event applied before the
        # next sample, not a chain of falsely settled single-scene previews.
        values = {"A": 0.125, "B": 0.75}
        coefficient = 1.0 - math.exp(-math.log(1000.0) / rate)
        ref_state, target, e = values["A"], values["A"], 0
        for requested, report in zip(query, result["snapshots"]):
            until = round(requested * rate)
            for sample in range(until - (0 if requested == query[0] else last_sample)):
                absolute = sample + (0 if requested == query[0] else last_sample)
                while e < len(events) and round(events[e][0] * rate) == absolute:
                    target = values[events[e][1]]
                    e += 1
                ref_state += coefficient * (target - ref_state)
            # For the first query at zero, no samples processed; apply the
            # boundary target before inspecting activeTarget.
            while e < len(events) and round(events[e][0] * rate) == until:
                target = values[events[e][1]]
                e += 1
            self.assertAlmostEqual(report["controls"][0]["predictedNormalized"],
                                   ref_state, delta=1e-11)
            last_sample = until
        self.assertEqual([x["activeTarget"] for x in result["snapshots"]],
                         ["B", "A", "B", "B"])
        # A partly completed B->A transition at 0.2 seconds isn't equal to A.
        value_at_switch = result["snapshots"][2]["controls"][0]["predictedNormalized"]
        self.assertGreater(value_at_switch, values["A"])
        self.assertLess(value_at_switch, values["B"])

    def test_zero_morph_advances_at_next_sample_not_event_boundary(self) -> None:
        patch = sample_patch()
        patch["modules"][0]["params"][8]["value"] = 0.0
        bundle = self.save(patch)
        result = sequence(bundle, source="A", event_spec="0:B,0.000125:A",
                          time_spec="0,0.000125,0.00025", sample_rate=8000)
        self.assertEqual([x["sampleCount"] for x in result["snapshots"]],
                         [0, 1, 2])
        actual = [x["controls"][0]["predictedNormalized"]
                  for x in result["snapshots"]]
        self.assertEqual(actual, [0.125, 0.75, 0.125])

    def test_two_rates_and_bipolar_nominal_volts(self) -> None:
        patch = sample_patch()
        patch["modules"][0]["params"][15]["value"] = 1.0
        bundle = self.save(patch)
        for rate in (8000, 44100, 48000, 96000):
            with self.subTest(rate=rate):
                result = sequence(bundle, source="A", event_spec="0:B",
                                  time_spec="0.25,0.5", sample_rate=rate)
                control = result["snapshots"][0]["controls"][0]
                self.assertEqual(control["range"], "bipolar")
                self.assertAlmostEqual(control["predictedNominalVolts"],
                                       10 * control["predictedNormalized"] - 5)
                self.assertTrue(0 <= control["predictedNormalized"] <= 1)

    def test_cli_text_json_are_deterministic_and_use_validated_zip(self) -> None:
        saved = self.save(version=2)
        before = saved.read_bytes()
        flags = ("--from", "A", "--events", "0:B,0.25:A,0.5:B",
                 "--at", "0,0.25,0.75", "--sample-rate", "48000")
        code, text, err = self.cli(saved, *flags)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("NOT emitted CV", text)
        self.assertIn("Sample 12000", text)
        code, raw, err = self.cli(saved, *flags, "--json")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(raw), sequence(
            saved, source="A", event_spec="0:B,0.25:A,0.5:B",
            time_spec="0,0.25,0.75", sample_rate=48000))
        self.assertEqual(text_sequence_preview(json.loads(raw)), text)
        self.assertEqual(self.cli(saved, *flags, "--json")[1], raw)
        self.assertEqual(before, saved.read_bytes())

    def test_rejects_missing_scene_and_requires_explicit_module_selection(self) -> None:
        path = self.save()
        with self.assertRaisesRegex(InstrumentError, "no stored snapshot"):
            sequence(path, source="A", event_spec="0:C", time_spec="0")
        patch = sample_patch()
        second = deepcopy(patch["modules"][0])
        second["id"] = 19
        second["data"]["names"][0] = "Second"
        patch["modules"].append(second)
        path = self.save(patch, version=2)
        with self.assertRaisesRegex(InstrumentError, "--module-id"):
            sequence(path, source="A", event_spec="0:B", time_spec="0.1")
        report = sequence(path, source="A", event_spec="0:B", time_spec="0.1",
                          module_id=19)
        self.assertEqual((report["moduleId"], report["snapshots"][0]["controls"][0]["name"]),
                         (19, "Second"))
        with self.assertRaisesRegex(InstrumentError, "no Macro8"):
            sequence(path, source="A", event_spec="0:B", time_spec="0.1",
                     module_id=111)

    def test_strict_event_and_sample_validation_rejects_hostile_times(self) -> None:
        path = self.save()
        invalid = ("", "NaN:A", "inf:A", "-1:B", "3601:B", "0:E", "0:A:B",
                   "0:A,", "0:A,0:B", "1:A,0:B", "0.00001:A,0.00002:B",
                   "0:A," * 129, " " + "0:A", "0 :A", "0:A ", "1e999:A",
                   "0:A," + "a" * 8200)
        for value in invalid:
            with self.subTest(events=value[:50]):
                code, output, err = self.cli(path, "--from", "A", f"--events={value}",
                                             "--at", "0.5", "--sample-rate", "8000")
                self.assertEqual((code, output), (2, ""))
                self.assertIn("Instrument Builder", err)
        invalid_times = ("", "nan", "inf", "-1", "3601", "0,0",
                         "0.00001,0.00002", "1,0", "0,", "0,1e999",
                         "0," * 300, "0," + "5" * 8200)
        for value in invalid_times:
            with self.subTest(times=value[:40]):
                code, output, err = self.cli(path, "--from", "A", "--events", "0:B",
                                             "--at", value, "--sample-rate", "8000")
                self.assertEqual((code, output), (2, ""))
                self.assertIn("Instrument Builder", err)

    def test_invalid_sample_rate_module_id_and_structure_fail_closed(self) -> None:
        saved = self.save()
        manifest = inspect(saved)
        for rate in (0, 7999, 384001, 48000.0, True, float("nan")):
            with self.subTest(rate=rate):
                with self.assertRaises(SequencePreviewError):
                    build_sequence_preview(manifest, source="A", events=[(0, "B")],
                                           query_times=[0], sample_rate=rate)
        for ident in (-1, True, 2**63, "70"):
            with self.subTest(ident=ident):
                with self.assertRaises(SequencePreviewError):
                    build_sequence_preview(manifest, source="A", events=[(0, "B")],
                                           query_times=[0], module_id=ident)
        for events, queries in (([], [0]), ([(0, "B")], []),
                                ([(0, "B")] * 129, [0]),
                                ([(0, "B")], [0] * 257),
                                ([([0], "B")], [0]),
                                ([(True, "B")], [0]),
                                ([(0, [])], [0]),
                                ([(0, "B")], [True]),
                                ([(0, "B")], [10**1000])):
            with self.subTest(structure=str((events, queries))[:70]):
                with self.assertRaises(SequencePreviewError):
                    build_sequence_preview(manifest, source="A", events=events,
                                           query_times=queries)

    def test_forged_zip_state_fails_before_preview_and_writes_nothing(self) -> None:
        bad = self.root / "invalid.msinstrument"
        bad.write_bytes(b"not a zip")
        opts = ("--from", "A", "--events", "0:B", "--at", "0.5", "--json")
        status, output, err = self.cli(bad, *opts)
        self.assertEqual((status, output), (2, ""))
        self.assertIn("invalid ZIP", err)

        genuine = create_bundle(patch_bytes(), "Genuine")
        with zipfile.ZipFile(BytesIO(genuine)) as archive:
            items = [(name, archive.read(name)) for name in archive.namelist()]
        forged = json.loads(dict(items)[MANIFEST_MEMBER])
        forged["performance"]["macro8"][0]["snapshots"][1][0] = 0.01
        bad.write_bytes(custom_archive([
            (name, json.dumps(forged).encode("utf-8") if name == MANIFEST_MEMBER
             else content) for name, content in items]))
        before = bad.read_bytes()
        status, output, err = self.cli(bad, *opts)
        self.assertEqual((status, output), (2, ""))
        self.assertIn("does not match its patch", err)
        self.assertEqual(bad.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
