"""Fail-closed orchestration tests for Module Forge's real-Rack source gate.

These unit tests mock the compiler; only the separate hosted job with pinned
Gitlinks is allowed to claim actual real-header C++ syntax compatibility.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import check_real_generated_headers as gate


class GeneratedRealHeaderGateTests(unittest.TestCase):
    def test_five_generated_sources_are_valid_and_waveforms_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            sources = gate.generate_starters(Path(temp))
            self.assertEqual([path.name for path in sources],
                             ["ForgeRealOsc.cpp", "ForgeRealSaw.cpp",
                              "ForgeRealPulse.cpp", "ForgeRealTriangle.cpp",
                              "ForgeRealLP.cpp"])
            for source in sources:
                self.assertTrue(source.is_file())
                self.assertIn("#include \"plugin.hpp\"", source.read_text())
            self.assertIn("std::sin(", sources[0].read_text())
            saw = sources[1].read_text()
            self.assertIn("static float polyBlep(float t, float dt)", saw)
            self.assertIn("rawSaw - correction", saw)
            self.assertNotIn("std::sin(", saw)
            self.assertIn("SAW OUT", (Path(temp) / "ForgeRealSaw" /
                                      "ForgeRealSaw.svg").read_text())
            pulse = sources[2].read_text()
            self.assertIn("rawPulse + polyBlep(t, dt)", pulse)
            self.assertIn("- polyBlep(oppositeEdge, dt)", pulse)
            self.assertNotIn("std::sin(", pulse)
            self.assertIn("PULSE OUT", (Path(temp) / "ForgeRealPulse" /
                                         "ForgeRealPulse.svg").read_text())
            triangle = sources[3].read_text()
            self.assertIn("static float polyBlamp(float t, float dt)", triangle)
            self.assertIn("rawTriangle - 4.f * polyBlamp(t, dt)", triangle)
            self.assertNotIn("std::sin(", triangle)
            self.assertIn("TRI OUT", (Path(temp) / "ForgeRealTriangle" /
                                       "ForgeRealTriangle.svg").read_text())
            self.assertFalse((Path(temp) / "ForgeRealOsc" / "ForgeRealOsc.dsp.hpp").exists())
            self.assertFalse((Path(temp) / "ForgeRealSaw" / "ForgeRealSaw.dsp.hpp").exists())
            self.assertFalse((Path(temp) / "ForgeRealPulse" / "ForgeRealPulse.dsp.hpp").exists())
            self.assertFalse((Path(temp) / "ForgeRealTriangle" /
                              "ForgeRealTriangle.dsp.hpp").exists())
            self.assertTrue((Path(temp) / "ForgeRealLP" / "ForgeRealLP.dsp.hpp").exists())

    def test_gate_uses_headless_real_header_flags_not_test_shim(self) -> None:
        paths = [Path("/tmp/a/ForgeRealOsc.cpp"),
                 Path("/tmp/b/ForgeRealSaw.cpp"),
                 Path("/tmp/c/ForgeRealPulse.cpp"),
                 Path("/tmp/e/ForgeRealTriangle.cpp"),
                 Path("/tmp/d/ForgeRealLP.cpp")]
        sdk_rack_headers = str(gate.ROOT / "src" / "Rack" / "include")
        flags = ["-DHEADLESS", "-fsyntax-only", "-I", sdk_rack_headers]
        commands = gate.syntax_commands("c++", flags, paths)
        self.assertEqual(len(commands), 5)
        for command, source in zip(commands, paths):
            self.assertEqual(command[0], "c++")
            self.assertEqual(command[1:3], ["-iquote", str(gate.COLLECTION)])
            self.assertLess(command.index(str(gate.COLLECTION)),
                            command.index(sdk_rack_headers))
            self.assertIn("-I", command)
            self.assertIn(str(gate.COLLECTION), command)
            self.assertEqual(command[-1], str(source))
            self.assertNotIn("rack_stub", " ".join(command))

        for bad in (
            ["-fsyntax-only"],
            ["-DHEADLESS"],
            ["-DHEADLESS", "-fsyntax-only", "-Itests/rack_stub"],
        ):
            with self.subTest(flags=bad), self.assertRaises(gate.sdk.PreflightError):
                gate.syntax_commands("c++", bad, paths)

    def test_generated_dialects_include_cardinal_cpp11_without_duplicate_standard(self) -> None:
        flags = ["-std=gnu++17", "-DHEADLESS", "-fsyntax-only"]
        self.assertEqual(gate.dialect_flags(flags, "gnu++11"),
                         ["-std=gnu++11", "-DHEADLESS", "-fsyntax-only"])
        self.assertEqual(gate.dialect_flags(flags, "gnu++17"), flags)
        for bad_flags in ([], ["-std=gnu++11"],
                          ["-std=gnu++17", "-std=gnu++11"]):
            with self.subTest(bad_flags=bad_flags), self.assertRaises(
                    gate.sdk.PreflightError):
                gate.dialect_flags(bad_flags, "gnu++11")
        with self.assertRaises(gate.sdk.PreflightError):
            gate.dialect_flags(flags, "gnu++20")

    @unittest.skipUnless(shutil.which("c++"), "C++ compiler unavailable")
    def test_quote_header_priority_over_rack_i_path(self) -> None:
        """GCC must choose first-party plugin.hpp despite earlier Rack -I."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake_rack = root / "rack"
            fake_first_party = root / "first-party"
            fake_rack.mkdir()
            fake_first_party.mkdir()
            (fake_rack / "plugin.hpp").write_text("#define RACK_HEADER_WAS_SELECTED 1\n")
            (fake_first_party / "plugin.hpp").write_text(
                "#define FIRST_PARTY_HEADER_WAS_SELECTED 1\n")
            source = root / "generated.cpp"
            source.write_text(
                "#include \"plugin.hpp\"\n"
                "#ifndef FIRST_PARTY_HEADER_WAS_SELECTED\n"
                "#error \"Wrong plugin.hpp resolved\"\n"
                "#endif\n")
            command = [shutil.which("c++"), "-std=c++17", "-fsyntax-only",
                       "-I", str(fake_rack), "-iquote", str(fake_first_party),
                       str(source)]
            completed = subprocess.run(command, text=True, capture_output=True,
                                       check=False, timeout=20)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_sdk_preflight_failure_is_not_treated_as_success(self) -> None:
        with mock.patch.object(gate.sdk, "check_dependencies",
                               side_effect=gate.sdk.PreflightError("wrong pinned gitlink")):
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                result = gate.main(["--preflight-only"])
            self.assertEqual(result, 2)
            self.assertIn("wrong pinned gitlink", output.getvalue())

    def test_compiler_invokes_all_five_real_header_translation_units(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            rack = Path(temp) / "rack"
            template = rack / "dep/speexdsp/include/speex/speexdsp_config_types.h.in"
            template.parent.mkdir(parents=True)
            template.write_text("template", encoding="utf-8")
            calls = []

            def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
                calls.append(command)
                self.assertEqual(kwargs["cwd"], gate.ROOT)
                return SimpleNamespace(returncode=0, stdout="")

            with (mock.patch.object(gate.sdk, "check_dependencies"),
                  mock.patch.object(gate.sdk, "render_linux_speex_types",
                                    return_value="#pragma once\n"),
                  mock.patch.object(gate.sdk, "compiler_flags",
                                    return_value=["-std=gnu++17", "-DHEADLESS", "-fsyntax-only",
                                                  "-I", "/pinned/rack/include"]),
                  mock.patch.object(gate.shutil, "which", return_value="c++"),
                  mock.patch.object(gate.subprocess, "run", side_effect=fake_run)):
                # A mocked compiler must not print misleading real-SDK PASS lines.
                with contextlib.redirect_stdout(io.StringIO()):
                    result = gate.main(["--rack-root", str(rack),
                                        "--dpf-root", str(Path(temp) / "dpf")])
            self.assertEqual(result, 0)
            self.assertEqual(len(calls), 10)
            for index, dialect in ((0, "-std=gnu++11"), (5, "-std=gnu++17")):
                self.assertTrue(calls[index][-1].endswith("/ForgeRealOsc/ForgeRealOsc.cpp"))
                self.assertTrue(calls[index + 1][-1].endswith("/ForgeRealSaw/ForgeRealSaw.cpp"))
                self.assertTrue(calls[index + 2][-1].endswith("/ForgeRealPulse/ForgeRealPulse.cpp"))
                self.assertTrue(calls[index + 3][-1].endswith("/ForgeRealTriangle/ForgeRealTriangle.cpp"))
                self.assertTrue(calls[index + 4][-1].endswith("/ForgeRealLP/ForgeRealLP.cpp"))
                self.assertTrue(all(dialect in call for call in calls[index:index + 5]))
            self.assertTrue(all("rack_stub" not in " ".join(c) for c in calls))


    def test_invalid_generated_saw_fails_closed_before_compile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            def check(folder: Path) -> list[str]:
                return ["tampered saw"] if folder.name == "ForgeRealSaw" else []

            with mock.patch.object(gate, "check_module", side_effect=check):
                with self.assertRaisesRegex(gate.sdk.PreflightError, "tampered saw"):
                    gate.generate_starters(Path(temp))

    def test_invalid_generated_pulse_fails_closed_before_compile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            def check(folder: Path) -> list[str]:
                return ["tampered pulse"] if folder.name == "ForgeRealPulse" else []

            with mock.patch.object(gate, "check_module", side_effect=check):
                with self.assertRaisesRegex(gate.sdk.PreflightError, "tampered pulse"):
                    gate.generate_starters(Path(temp))

    def test_invalid_generated_triangle_fails_closed_before_compile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            def check(folder: Path) -> list[str]:
                return ["tampered triangle"] if folder.name == "ForgeRealTriangle" else []

            with mock.patch.object(gate, "check_module", side_effect=check):
                with self.assertRaisesRegex(gate.sdk.PreflightError, "tampered triangle"):
                    gate.generate_starters(Path(temp))

    def test_saw_compiler_failure_is_reported_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            rack = Path(temp) / "rack"
            template = rack / "dep/speexdsp/include/speex/speexdsp_config_types.h.in"
            template.parent.mkdir(parents=True)
            template.write_text("template", encoding="utf-8")
            calls = []

            def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
                calls.append(command)
                if command[-1].endswith("/ForgeRealSaw/ForgeRealSaw.cpp"):
                    return SimpleNamespace(returncode=1, stdout="saw compiler error")
                return SimpleNamespace(returncode=0, stdout="")

            with (mock.patch.object(gate.sdk, "check_dependencies"),
                  mock.patch.object(gate.sdk, "render_linux_speex_types",
                                    return_value="#pragma once\\n"),
                  mock.patch.object(gate.sdk, "compiler_flags",
                                    return_value=["-std=gnu++17", "-DHEADLESS", "-fsyntax-only",
                                                  "-I", "/pinned/rack/include"]),
                  mock.patch.object(gate.shutil, "which", return_value="c++"),
                  mock.patch.object(gate.subprocess, "run", side_effect=fake_run)):
                output = io.StringIO()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(output):
                    result = gate.main(["--rack-root", str(rack),
                                        "--dpf-root", str(Path(temp) / "dpf")])

            self.assertEqual(result, 1)
            self.assertEqual(len(calls), 2)
            self.assertIn("FAIL: generated ForgeRealSaw", output.getvalue())
            self.assertIn("saw compiler error", output.getvalue())

    def test_pulse_compiler_failure_is_reported_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            rack = Path(temp) / "rack"
            template = rack / "dep/speexdsp/include/speex/speexdsp_config_types.h.in"
            template.parent.mkdir(parents=True)
            template.write_text("template", encoding="utf-8")
            calls = []

            def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
                calls.append(command)
                if command[-1].endswith("/ForgeRealPulse/ForgeRealPulse.cpp"):
                    return SimpleNamespace(returncode=1, stdout="pulse compiler error")
                return SimpleNamespace(returncode=0, stdout="")

            with (mock.patch.object(gate.sdk, "check_dependencies"),
                  mock.patch.object(gate.sdk, "render_linux_speex_types",
                                    return_value="#pragma once\n"),
                  mock.patch.object(gate.sdk, "compiler_flags",
                                    return_value=["-std=gnu++17", "-DHEADLESS", "-fsyntax-only",
                                                  "-I", "/pinned/rack/include"]),
                  mock.patch.object(gate.shutil, "which", return_value="c++"),
                  mock.patch.object(gate.subprocess, "run", side_effect=fake_run)):
                output = io.StringIO()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(output):
                    result = gate.main(["--rack-root", str(rack),
                                        "--dpf-root", str(Path(temp) / "dpf")])

            self.assertEqual(result, 1)
            self.assertEqual(len(calls), 3)
            self.assertIn("FAIL: generated ForgeRealPulse", output.getvalue())
            self.assertIn("pulse compiler error", output.getvalue())


if __name__ == "__main__":
    unittest.main()
