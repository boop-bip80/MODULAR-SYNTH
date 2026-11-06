"""Regression coverage for post-failure linked ELF diagnostics.

The ELF fixtures are synthetic; they are not real Cardinal host binaries.
"""

from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import test_ci_compiled_collection as fixtures


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("linked_diagnostics", ROOT / "tools/ci/diagnose_compiled_collection.py")
assert SPEC and SPEC.loader
diagnostics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostics)


class LinkedELFDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = fixtures.CompiledFirstPartyGateTests("test_accepts_current_manifest_marker_inventory")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture

    def report(self) -> dict:
        return diagnostics.diagnose(self.fixture.binary, self.fixture.manifest, [])

    def test_accepts_synthetic_linked_identifiers_for_diagnostic_only(self) -> None:
        self.fixture.write_image()
        report = self.report()
        self.assertTrue(report["primary_gate_passed"])
        self.assertEqual(report["binaries"][0]["missing_runtime_identifiers"], [])
        self.assertIn("not prove registration", report["warning"])

    def test_reports_marker_only_in_unmapped_elf_trailer(self) -> None:
        missing = self.fixture.data["modules"][-1]["slug"]
        self.fixture.write_image(markers=("ModularSynth", *(m["slug"] for m in self.fixture.data["modules"][:-1])),
                                 trailer_markers=(missing,))
        report = self.report()
        self.assertFalse(report["primary_gate_passed"])
        binary = report["binaries"][0]
        self.assertTrue(binary["standalone_string_anywhere"][missing])
        self.assertFalse(binary["standalone_runtime_literals"][missing])
        self.assertIn(missing, binary["missing_runtime_identifiers"])

    def test_writable_marker_segment_never_passes_gate(self) -> None:
        self.fixture.write_image(load_flags=6)
        report = self.report()
        self.assertFalse(report["primary_gate_passed"])
        self.assertIn("no read-only", report["binaries"][0]["runtime_elf_error"])
        self.assertIn("ModularSynth", report["binaries"][0]["standalone_string_anywhere"])

    def test_missing_primary_binary_and_optional_candidate_are_observable(self) -> None:
        report = diagnostics.diagnose(self.fixture.binary, self.fixture.manifest,
                                      [self.fixture.root / "missing-plugin.so"])
        self.assertFalse(report["primary_gate_passed"])
        self.assertEqual(len(report["binaries"]), 2)
        self.assertFalse(report["binaries"][1]["exists"])

    def test_cli_writes_inspectable_json_without_masking_original_failure(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "linked-diagnostics.json"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(diagnostics.main([
                    "--binary", str(self.fixture.binary),
                    "--manifest", str(self.fixture.manifest),
                    "--json-output", str(output),
                ]), 0)
            self.assertFalse(json.loads(output.read_text())["primary_gate_passed"])


if __name__ == "__main__":
    unittest.main()
