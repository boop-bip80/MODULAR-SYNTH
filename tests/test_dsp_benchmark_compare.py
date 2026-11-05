"""Source-DSP benchmark trend comparison with hostile and noisy fixtures."""

import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPARE = ROOT / "tools/dsp-bench/compare.py"


def fixtures(factor=1.0, *, legacy=False):
    rows = []
    engines = ("MorphVCO", "StateFilter", "FMVoice", "StereoEcho")
    if not legacy:
        engines += ("FoldDrive", "ClockedLFO", "ChanceHold")
    for engine in engines:
        for voices in (1, 8, 16):
            for rate in (48000, 96000):
                milliseconds = (1.0 + voices * 0.09 + rate / 90000.0) * factor
                rows.append({
                    "engine": engine, "voices": voices, "sample_rate_hz": rate,
                    "frames": 1024, "elapsed_ms": milliseconds,
                    "ns_per_voice_sample": milliseconds * 1e6 / (voices * 1024),
                    "realtime_factor": milliseconds * rate / 1.024e6,
                    "mean_output_energy": 0.75, "cpp_new_calls": 0,
                    "prepared_bytes_hint": voices * 1024,
                    "prepared_cpp_new_bytes": voices * 1024,
                    "repetitions": 3,
                    "min_elapsed_ms": milliseconds * 0.95,
                    "p90_elapsed_ms": milliseconds * 1.05,
                    "max_elapsed_ms": milliseconds * 1.05,
                })
    return rows


class BenchmarkComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="modular-bench-compare-")
        self.base = Path(self.temp.name) / "baseline.json"
        self.candidate = Path(self.temp.name) / "candidate.json"

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, base=None, candidate=None, *options):
        self.base.write_text(json.dumps(fixtures() if base is None else base), encoding="utf-8")
        self.candidate.write_text(
            json.dumps(fixtures() if candidate is None else candidate),
            encoding="utf-8",
        )
        return subprocess.run(
            [sys.executable, str(COMPARE), str(self.base), str(self.candidate), *options],
            text=True, capture_output=True, check=False,
        )

    def test_identity_has_unit_geometric_ratio_and_no_claims(self):
        result = self.invoke(None, None, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(len(report["scenarios"]), 42)
        self.assertEqual(report["scenario_profile"], "extended-42")
        self.assertAlmostEqual(report["equal_weight_geometric_speedup"], 1.0)
        self.assertIn("not DAW/host CPU", report["scope"])
        self.assertEqual({row["observed_range"] for row in report["scenarios"]},
                         {"overlapping-ranges"})
        self.assertTrue(all(row["prepared_heap_bytes_delta"] == 0
                            for row in report["scenarios"]))

    def test_faster_and_slower_nonoverlap_cases_are_observations_only(self):
        faster = self.invoke(fixtures(), fixtures(0.7), "--json")
        self.assertEqual(faster.returncode, 0, faster.stderr)
        report = json.loads(faster.stdout)
        self.assertAlmostEqual(report["equal_weight_geometric_speedup"], 1 / 0.7)
        self.assertEqual({row["observed_range"] for row in report["scenarios"]},
                         {"nonoverlap-faster"})
        slower = self.invoke(fixtures(), fixtures(1.4))
        self.assertEqual(slower.returncode, 0, slower.stderr)
        self.assertIn("nonoverlap-slower", slower.stdout)
        self.assertIn("not host CPU", slower.stdout)

    def test_legacy_capture_is_accepted_but_never_compared_to_42_scenarios(self):
        legacy = fixtures(legacy=True)
        result = self.invoke(legacy, legacy, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["scenario_profile"], "legacy-24")
        self.assertEqual(len(report["scenarios"]), 24)
        mixed = self.invoke(legacy, fixtures())
        self.assertEqual(mixed.returncode, 2)
        self.assertIn("scenario sets differ", mixed.stderr)

    def test_missing_extended_engine_and_duplicate_engine_are_rejected(self):
        candidate = fixtures()
        with self.subTest(problem="missing ChanceHold"):
            result = self.invoke(fixtures(), candidate[:-6])
            self.assertEqual(result.returncode, 2)
            self.assertIn("benchmark scenarios", result.stderr)
        with self.subTest(problem="duplicated engine"):
            duplicated = fixtures()
            for row in duplicated:
                if row["engine"] == "FoldDrive":
                    row["engine"] = "FMVoice"
            result = self.invoke(fixtures(), duplicated)
            self.assertEqual(result.returncode, 2)
            self.assertIn("duplicate scenario", result.stderr)

    def test_bad_input_sets_and_numeric_types_fail_closed(self):
        bad_rows = []
        rows = fixtures()
        bad_rows.append(rows[:-1])
        bad_rows.append(rows[:-1] + [rows[0]])
        for key, value in (
            ("cpp_new_calls", 1),
            ("frames", 1536),
            ("repetitions", 0),
            ("voices", True),
            ("elapsed_ms", float("nan")),
            ("mean_output_energy", 0.0),
            ("prepared_cpp_new_bytes", -1),
            ("min_elapsed_ms", 9e9),
            ("ns_per_voice_sample", 1e9),
            ("realtime_factor", 1e9),
        ):
            invalid = json.loads(json.dumps(rows))
            invalid[0][key] = value
            bad_rows.append(invalid)
        for invalid in bad_rows:
            with self.subTest(invalid=invalid[0]):
                result = self.invoke(rows, invalid)
                self.assertEqual(result.returncode, 2)
                self.assertIn("DSP benchmark comparison:", result.stderr)

    def test_reject_mismatched_frames_or_nonfinite_speedup(self):
        mismatch = fixtures()
        for row in mismatch:
            row["frames"] = 4096
            row["ns_per_voice_sample"] = row["elapsed_ms"] * 1e6 / (
                row["voices"] * row["frames"])
            row["realtime_factor"] = row["elapsed_ms"] * row["sample_rate_hz"] / (
                1000 * row["frames"])
        result = self.invoke(fixtures(), mismatch)
        self.assertEqual(result.returncode, 2)
        self.assertIn("frames differ", result.stderr)

        underflow = fixtures()
        underflow[0]["ns_per_voice_sample"] = 1e-300
        huge = fixtures()
        huge[0]["ns_per_voice_sample"] = 1e300
        for rows in (underflow, huge):
            row = rows[0]
            row["elapsed_ms"] = row["ns_per_voice_sample"] * row["frames"] * row["voices"] / 1e6
            row["realtime_factor"] = row["elapsed_ms"] * row["sample_rate_hz"] / (
                1000 * row["frames"])
            row["min_elapsed_ms"] = row["elapsed_ms"] * 0.95
            row["p90_elapsed_ms"] = row["elapsed_ms"] * 1.05
            row["max_elapsed_ms"] = row["p90_elapsed_ms"]
        result = self.invoke(huge, underflow)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid timing ratio", result.stderr)

    def test_reject_non_json_and_single_repeat_dispersion(self):
        self.base.write_text("not json", encoding="utf-8")
        self.candidate.write_text(json.dumps(fixtures()), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(COMPARE), str(self.base), str(self.candidate)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        rows = fixtures()
        rows[0]["repetitions"] = 1
        result = self.invoke(rows, fixtures())
        self.assertEqual(result.returncode, 2)
        self.assertIn("single repeat", result.stderr)

    def test_reject_duplicate_json_object_properties(self):
        payload = json.dumps(fixtures())
        first = '"engine": "MorphVCO"'
        self.assertIn(first, payload)
        self.base.write_text(payload.replace(first, first + ', "engine": "FMVoice"', 1),
                             encoding="utf-8")
        self.candidate.write_text(json.dumps(fixtures()), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(COMPARE), str(self.base), str(self.candidate)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate JSON property", result.stderr)


if __name__ == "__main__":
    unittest.main()
