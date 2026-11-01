"""Unit tests for the standalone DSP discovery runner."""
from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_dsp_tests


class DspRunnerTests(unittest.TestCase):
    def test_discovers_only_standalone_dsp_entrypoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            names = (
                "morphvco_dsp_smoke.cpp",
                "macro8_dsp_test.cpp",
                "statefilter_dsp_test.cpp",
                "soundtrack_dsp_test.cpp",
                "rack_wrapper_dsp_test.cpp",
                "wrapper_dsp_smoke.cpp",
                "ordinary_unit.cpp",
                "wrong_extension_dsp_test.hpp",
            )
            for name in names:
                (directory / name).write_text("// fixture\n", encoding="utf-8")
            (directory / "nested").mkdir()
            (directory / "nested" / "nested_dsp_test.cpp").write_text(
                "// not discovered recursively\n", encoding="utf-8"
            )

            found = [path.name for path in run_dsp_tests.discover_tests(directory)]
            self.assertEqual(
                found,
                [
                    "macro8_dsp_test.cpp",
                    "morphvco_dsp_smoke.cpp",
                    "soundtrack_dsp_test.cpp",
                    "statefilter_dsp_test.cpp",
                ],
            )

    def test_compiler_profiles_cover_strict_and_fast_math(self) -> None:
        strict = run_dsp_tests.COMPILER_PROFILES["strict"]
        production = run_dsp_tests.COMPILER_PROFILES["production"]
        aggressive = run_dsp_tests.COMPILER_PROFILES["aggressive-fastmath"]
        for flag in ("-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror"):
            self.assertIn(flag, strict)
        for flag in (
            "-std=c++17", "-O3", "-ffast-math",
            "-fno-finite-math-only", "-Wall", "-Wextra", "-Werror",
        ):
            self.assertIn(flag, production)
        self.assertIn("-ffast-math", aggressive)
        self.assertNotIn("-fno-finite-math-only", aggressive)

    def test_empty_discovery_is_failure_not_false_success(self) -> None:
        with patch.object(run_dsp_tests, "discover_tests", return_value=[]):
            with contextlib.redirect_stderr(io.StringIO()):
                status = run_dsp_tests.main([])
        self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
