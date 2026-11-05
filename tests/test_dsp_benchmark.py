"""Executable source-only DSP benchmark contract, without timing thresholds."""

import csv
import io
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/dsp-bench/main.cpp"
ENGINE_NAMES = {"MorphVCO", "StateFilter", "FMVoice", "StereoEcho"}


class DSPBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="modular-synth-dsp-bench-")
        cls.binaries = {}
        compiler = shutil.which("c++")
        if not compiler:
            raise unittest.SkipTest("C++ compiler unavailable")
        for profile, flags in (
            ("debug", ["-O0"]),
            ("production", ["-O3", "-ffast-math", "-fno-finite-math-only"]),
        ):
            binary = Path(cls.temp.name) / profile
            command = [
                compiler, "-std=gnu++11", *flags, "-Wall", "-Wextra", "-Werror",
                str(SOURCE), "-o", str(binary),
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode:
                raise AssertionError(
                    f"{profile} benchmark C++11 compilation failed:\n{result.stderr}"
                )
            cls.binaries[profile] = binary

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def invoke(self, profile: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(self.binaries[profile]), *args],
            capture_output=True, text=True, check=False,
        )

    def assert_valid_rows(self, rows, frames: int) -> None:
        self.assertEqual(len(rows), 24)
        self.assertEqual({row["engine"] for row in rows}, ENGINE_NAMES)
        self.assertEqual({int(row["voices"]) for row in rows}, {1, 8, 16})
        self.assertEqual({int(row["sample_rate_hz"]) for row in rows}, {48000, 96000})
        seen = set()
        for row in rows:
            identifier = (
                row["engine"], int(row["voices"]), int(row["sample_rate_hz"]),
            )
            self.assertNotIn(identifier, seen)
            seen.add(identifier)
            self.assertEqual(int(row["frames"]), frames)
            self.assertEqual(int(row["cpp_new_calls"]), 0)
            self.assertGreater(int(row["prepared_bytes_hint"]), 0)
            self.assertGreater(float(row["elapsed_ms"]), 0.0)
            self.assertGreater(float(row["ns_per_voice_sample"]), 0.0)
            self.assertGreater(float(row["realtime_factor"]), 0.0)
            energy = float(row["mean_output_energy"])
            self.assertTrue(math.isfinite(energy))
            self.assertGreater(energy, 0.0)
            if row["engine"] == "StereoEcho":
                # Fixed-capacity stereo ring memory is preallocated outside
                # the timed section, never on an audio-process iteration.
                self.assertGreater(int(row["prepared_bytes_hint"]), 1_500_000)

    def test_cpp11_debug_and_production_csv(self) -> None:
        for profile in self.binaries:
            with self.subTest(profile=profile):
                result = self.invoke(profile, "--frames", "1024")
                self.assertEqual(result.returncode, 0, result.stderr)
                rows = list(csv.DictReader(io.StringIO(result.stdout)))
                self.assert_valid_rows(rows, frames=1024)

    def test_json_is_machine_readable_and_deterministic(self) -> None:
        first = self.invoke("production", "--frames", "1024", "--json")
        second = self.invoke("production", "--frames", "1024", "--json")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        a = json.loads(first.stdout)
        b = json.loads(second.stdout)
        self.assert_valid_rows(a, frames=1024)
        # Timings are expected to differ; source stimulus and DSP state are
        # deterministic for a single compiled executable.
        for left, right in zip(a, b):
            for field in (
                "engine", "voices", "sample_rate_hz", "frames", "cpp_new_calls",
                "prepared_bytes_hint", "mean_output_energy",
            ):
                self.assertEqual(left[field], right[field], (field, left, right))

    def test_cli_rejects_invalid_frames(self) -> None:
        for arguments in (
            ("--frames", "0"),
            ("--frames", "1000001"),
            ("--frames", "123garbage"),
            ("--frames",),
            ("--unknown",),
        ):
            with self.subTest(arguments=arguments):
                result = self.invoke("production", *arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("DSP benchmark:", result.stderr)

    def test_usage(self) -> None:
        result = self.invoke("production", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("no cardinal", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
