"""Fail-closed orchestration tests for Module Forge's real-Rack source gate.

These unit tests mock the compiler; only the separate hosted job with pinned
Gitlinks is allowed to claim actual real-header C++ syntax compatibility.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import check_real_generated_headers as gate


class GeneratedRealHeaderGateTests(unittest.TestCase):
    def test_both_generated_sources_are_valid_and_have_distinct_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            sources = gate.generate_starters(Path(temp))
            self.assertEqual([path.name for path in sources],
                             ["ForgeRealOsc.cpp", "ForgeRealLP.cpp"])
            for source in sources:
                self.assertTrue(source.is_file())
                self.assertIn("#include \"plugin.hpp\"", source.read_text())
            self.assertFalse((Path(temp) / "ForgeRealOsc" / "ForgeRealOsc.dsp.hpp").exists())
            self.assertTrue((Path(temp) / "ForgeRealLP" / "ForgeRealLP.dsp.hpp").exists())

    def test_gate_uses_headless_real_header_flags_not_test_shim(self) -> None:
        paths = [Path("/tmp/a/ForgeRealOsc.cpp"), Path("/tmp/b/ForgeRealLP.cpp")]
        flags = ["-DHEADLESS", "-fsyntax-only", "-I", "/real/rack/include"]
        commands = gate.syntax_commands("c++", flags, paths)
        self.assertEqual(len(commands), 2)
        for command, source in zip(commands, paths):
            self.assertEqual(command[0], "c++")
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

    def test_sdk_preflight_failure_is_not_treated_as_success(self) -> None:
        with mock.patch.object(gate.sdk, "check_dependencies",
                               side_effect=gate.sdk.PreflightError("wrong pinned gitlink")):
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                result = gate.main(["--preflight-only"])
            self.assertEqual(result, 2)
            self.assertIn("wrong pinned gitlink", output.getvalue())

    def test_compiler_invokes_both_real_header_translation_units(self) -> None:
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
                                    return_value=["-DHEADLESS", "-fsyntax-only",
                                                  "-I", "/pinned/rack/include"]),
                  mock.patch.object(gate.shutil, "which", return_value="c++"),
                  mock.patch.object(gate.subprocess, "run", side_effect=fake_run)):
                # A mocked compiler must not print misleading real-SDK PASS lines.
                with contextlib.redirect_stdout(io.StringIO()):
                    result = gate.main(["--rack-root", str(rack),
                                        "--dpf-root", str(Path(temp) / "dpf")])
            self.assertEqual(result, 0)
            self.assertEqual(len(calls), 2)
            self.assertTrue(calls[0][-1].endswith("/ForgeRealOsc/ForgeRealOsc.cpp"))
            self.assertTrue(calls[1][-1].endswith("/ForgeRealLP/ForgeRealLP.cpp"))
            self.assertTrue(all("rack_stub" not in " ".join(c) for c in calls))


if __name__ == "__main__":
    unittest.main()
