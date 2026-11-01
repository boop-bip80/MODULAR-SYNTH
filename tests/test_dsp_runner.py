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
                "stereo_echo_dsp_test.cpp",
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
                    "stereo_echo_dsp_test.cpp",
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

    def test_sanitizer_profiles_enable_runtime_diagnostics(self) -> None:
        asan = run_dsp_tests.SANITIZER_PROFILES["asan-ubsan"]
        ubsan = run_dsp_tests.SANITIZER_PROFILES["ubsan"]
        for flags in (asan, ubsan):
            for flag in (
                "-std=c++17", "-O1", "-g", "-fno-omit-frame-pointer",
                "-fno-sanitize-recover=all", "-Wall", "-Wextra", "-Werror",
            ):
                self.assertIn(flag, flags)
            self.assertNotIn("-ffast-math", flags)
        self.assertIn("-fsanitize=address,undefined", asan)
        self.assertIn("-fsanitize=undefined", ubsan)

    def test_auto_prefers_asan_and_falls_back_only_for_probe_failure(self) -> None:
        workspace = Path("/no-files-written-by-mocked-probe")
        with patch.object(run_dsp_tests, "probe_sanitizer", return_value=None) as probe:
            selected, flags = run_dsp_tests.select_sanitizer_profile(
                ["c++"], "auto", workspace
            )
            self.assertEqual(selected, "asan-ubsan")
            self.assertEqual(flags, run_dsp_tests.SANITIZER_PROFILES[selected])
            self.assertEqual(probe.call_count, 1)

        with patch.object(
            run_dsp_tests, "probe_sanitizer",
            side_effect=[RuntimeError("ASan sandbox mapping failed"), None],
        ) as probe:
            with contextlib.redirect_stderr(io.StringIO()):
                selected, flags = run_dsp_tests.select_sanitizer_profile(
                    ["c++"], "auto", workspace
                )
            self.assertEqual(selected, "ubsan")
            self.assertEqual(flags, run_dsp_tests.SANITIZER_PROFILES[selected])
            self.assertEqual(
                [call.args[1] for call in probe.call_args_list],
                ["asan-ubsan", "ubsan"],
            )

    def test_sanitizer_support_failure_is_not_a_false_pass(self) -> None:
        with patch.object(
            run_dsp_tests, "probe_sanitizer",
            side_effect=RuntimeError("compiler/runtime missing"),
        ):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "no compile/runtime probe passed"):
                    run_dsp_tests.select_sanitizer_profile(
                        ["c++"], "auto", Path("/unused")
                    )

    def test_dsp_sanitizer_failure_does_not_fallback_or_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            test = Path(temp) / "fixture_dsp_test.cpp"
            test.write_text("int main(){return 0;}\n", encoding="utf-8")
            flags = run_dsp_tests.SANITIZER_PROFILES["asan-ubsan"]

            def simulated_step(command, description, timeout, env=None):
                if "run fixture_dsp_test.cpp / sanitizer-asan-ubsan" in description:
                    raise RuntimeError("ASan found a real DSP error")

            with patch.object(
                run_dsp_tests, "select_sanitizer_profile",
                return_value=("asan-ubsan", flags),
            ) as selector:
                with patch.object(run_dsp_tests, "run_checked", side_effect=simulated_step):
                    with contextlib.redirect_stdout(io.StringIO()):
                        with contextlib.redirect_stderr(io.StringIO()) as errors:
                            passed = run_dsp_tests.run_suite(
                                [test], ["c++"], sanitizer="auto"
                            )
                self.assertFalse(passed)
                self.assertIn("ASan found a real DSP error", errors.getvalue())
                selector.assert_called_once()

    def test_cli_passes_optional_sanitizer_selection(self) -> None:
        test = run_dsp_tests.ROOT / "tests" / "stereo_echo_dsp_test.cpp"
        with patch.object(run_dsp_tests, "discover_tests", return_value=[test]):
            with patch.object(run_dsp_tests, "compiler_command", return_value=["c++"]):
                with patch.object(run_dsp_tests, "run_suite", return_value=True) as suite:
                    self.assertEqual(run_dsp_tests.main(["--sanitize=ubsan"]), 0)
                    suite.assert_called_once_with([test], ["c++"], sanitizer="ubsan")

    def test_list_mode_never_probes_compiler_or_sanitizers(self) -> None:
        test = run_dsp_tests.ROOT / "tests" / "stereo_echo_dsp_test.cpp"
        with patch.object(run_dsp_tests, "discover_tests", return_value=[test]):
            with patch.object(run_dsp_tests, "compiler_command") as compiler:
                with patch.object(run_dsp_tests, "select_sanitizer_profile") as probe:
                    with contextlib.redirect_stdout(io.StringIO()) as out:
                        status = run_dsp_tests.main(["--list", "--sanitize=auto"])
                    self.assertEqual(status, 0)
                    self.assertIn("stereo_echo_dsp_test.cpp", out.getvalue())
                    compiler.assert_not_called()
                    probe.assert_not_called()

    def test_empty_discovery_is_failure_not_false_success(self) -> None:
        with patch.object(run_dsp_tests, "discover_tests", return_value=[]):
            with contextlib.redirect_stderr(io.StringIO()):
                status = run_dsp_tests.main([])
        self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
