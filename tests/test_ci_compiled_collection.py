"""Synthetic negative-case tests for the compiled first-party ELF inventory gate.

Fake ELF fixtures only exercise parser and workflow contracts. They are *not*
actual linked Cardinal objects or a substitute for CI host execution.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools/ci/verify_compiled_collection.py"
MANIFEST = REPO / "plugins/ModularSynth/plugin.json"
WORKFLOW = (REPO / ".github/workflows/build.yml").read_text(encoding="utf-8")


class CompiledFirstPartyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "Cardinal"
        self.manifest = self.root / "plugin.json"
        self.data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.write_manifest()

    def write_manifest(self) -> None:
        self.manifest.write_text(json.dumps(self.data), encoding="utf-8")

    def write_image(self, *, markers: tuple[str, ...] | None = None,
                    header: bytes | None = None) -> None:
        marker_names = markers if markers is not None else (
            "ModularSynth",
            *(entry["slug"] for entry in self.data["modules"]),
        )
        # A minimal fixture: plausible ELF header and test-only marker bytes.
        # No fake image ever claims to be executable or plugin-loadable.
        elf = bytearray(64)
        elf[:6] = b"\x7fELF\x02\x01"
        elf[16:18] = (3).to_bytes(2, "little")
        payload = bytes(elf if header is None else header)
        payload += b"\0".join(m.encode("ascii") for m in marker_names) + b"\0"
        self.binary.write_bytes(payload)

    def run_gate(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--binary", str(self.binary),
             "--manifest", str(self.manifest)],
            text=True, capture_output=True, check=False,
        )

    def test_accepts_current_manifest_marker_inventory(self) -> None:
        self.write_image()
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not host loadability", result.stdout)

    def test_rejects_missing_original_or_new_manifest_identifier(self) -> None:
        markers = ("ModularSynth", *(
            entry["slug"] for entry in self.data["modules"][:-1]
        ))
        self.write_image(markers=markers)
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn(self.data["modules"][-1]["slug"], result.stderr)
        # A future module is required automatically, with no hand-edited list.
        self.data["modules"].append({"slug": "NewFutureModule"})
        self.write_manifest()
        self.write_image(markers=("ModularSynth", *(
            entry["slug"] for entry in self.data["modules"][:-1]
        )))
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("NewFutureModule", result.stderr)

    def test_rejects_missing_or_non_elf_or_unlinked_object(self) -> None:
        self.assertEqual(self.run_gate().returncode, 1)
        self.write_image(header=b"not an ELF")
        self.assertEqual(self.run_gate().returncode, 1)
        self.write_image()
        payload = bytearray(self.binary.read_bytes())
        payload[16:18] = (1).to_bytes(2, "little")  # ET_REL object, not linked
        self.binary.write_bytes(payload)
        self.assertEqual(self.run_gate().returncode, 1)

    def test_rejects_bad_manifest_identity_duplicate_or_invalid_slugs(self) -> None:
        self.write_image()
        self.data["slug"] = "DifferentPlugin"
        self.write_manifest()
        self.assertEqual(self.run_gate().returncode, 1)
        self.data["slug"] = "ModularSynth"
        self.data["modules"].append({"slug": self.data["modules"][0]["slug"].lower()})
        self.write_manifest()
        self.assertEqual(self.run_gate().returncode, 1)
        self.data["modules"][-1]["slug"] = "../Escape"
        self.write_manifest()
        self.assertEqual(self.run_gate().returncode, 1)

    def test_plugin_validation_invokes_gate_after_link_before_runtime_selftest(self) -> None:
        job = WORKFLOW.split("\n  plugin-validation:\n", 1)[1]
        compile_done = job.index("- name: Build Cardinal (final build stage)")
        gate = job.index("- name: Verify linked first-party collection")
        selftest = job.index("- name: Run Cardinal self-tests")
        self.assertLess(compile_done, gate)
        self.assertLess(gate, selftest)
        self.assertIn("python3 -B tools/ci/verify_compiled_collection.py --binary bin/Cardinal", job)


if __name__ == "__main__":
    unittest.main()
