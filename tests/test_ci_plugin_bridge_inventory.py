"""Negative-fixture coverage for the exact Ubuntu Carla bridge target set.

The tiny synthetic ELF files test inventory validation only; they are not
loadable plugins and do not constitute audio/DAW integration evidence.
"""
from __future__ import annotations

import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools/ci/verify_plugin_bridge_inventory.py"
WORKFLOW = (REPO / ".github/workflows/build.yml").read_text(encoding="utf-8")
NAMES = ("Cardinal", "CardinalFX", "CardinalSynth")
URIS = {
    "CardinalFX": "https://distrho.kx.studio/plugins/cardinal#fx",
    "CardinalSynth": "https://distrho.kx.studio/plugins/cardinal#synth",
}


def simulated_elf64_shared() -> bytes:
    """Make only an ELF header/table fixture; not a runnable shared object."""
    data = bytearray(256)
    data[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", data, 16, 3, 62, 1)
    struct.pack_into("<Q", data, 32, 64)
    struct.pack_into("<HHH", data, 52, 64, 56, 1)
    struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, 0, 0, 0, len(data), len(data), 4096)
    return bytes(data)


def workflow_script(name: str) -> str:
    match = re.search(
        rf"^      - name: {re.escape(name)}\n        run: \|\n"
        rf"(?P<body>.*?)(?=^      - name: |^      - uses: |\Z)",
        WORKFLOW, re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"missing workflow step: {name}")
    return "\n".join(line[10:] if line.startswith("          ") else line
                     for line in match.group("body").splitlines()) + "\n"


class PluginBridgeInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.lv2 = self.root / "lv2-path"
        self.bin.mkdir()
        self.lv2.mkdir()

    def seed_targets(self) -> None:
        for variant, uri in URIS.items():
            bundle = self.lv2 / f"{variant}.lv2"
            bundle.mkdir()
            (bundle / "manifest.ttl").write_text(f"<{uri}> a <urn:fixture> .\n", encoding="utf-8")
            (bundle / f"{variant}.so").write_bytes(simulated_elf64_shared())
            vst2 = self.bin / "Cardinal.vst"
            vst2.mkdir(exist_ok=True)
            (vst2 / f"{variant}.so").write_bytes(simulated_elf64_shared())
        for variant in NAMES:
            binary = self.bin / f"{variant}.vst3" / "Contents" / "x86_64-linux" / f"{variant}.so"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(simulated_elf64_shared())

    def check_inventory(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--bin-dir", str(self.bin),
             "--lv2-dir", str(self.lv2)],
            text=True, capture_output=True, check=False,
        )

    def test_accepts_complete_seven_target_inventory(self) -> None:
        self.seed_targets()
        result = self.check_inventory()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("plugin bridge target OK"), 7)
        self.assertIn("Carla runtime tests must follow", result.stdout)

    def test_empty_inventory_is_not_an_implicit_pass(self) -> None:
        self.assertNotEqual(self.check_inventory().returncode, 0)

    def test_all_seven_missing_variants_are_rejected_individually(self) -> None:
        self.seed_targets()
        targets = [
            self.lv2 / f"{name}.lv2" / f"{name}.so" for name in URIS
        ] + [
            self.bin / "Cardinal.vst" / f"{name}.so" for name in URIS
        ] + [
            self.bin / f"{name}.vst3" / "Contents" / "x86_64-linux" / f"{name}.so"
            for name in NAMES
        ]
        for target in targets:
            with self.subTest(target=target):
                original = target.read_bytes()
                target.unlink()
                result = self.check_inventory()
                self.assertEqual(result.returncode, 1)
                self.assertIn(str(target), result.stderr)
                target.write_bytes(original)

    def test_rejects_invalid_lv2_uri_and_missing_manifest(self) -> None:
        self.seed_targets()
        manifest = self.lv2 / "CardinalFX.lv2" / "manifest.ttl"
        manifest.write_text("<urn:unrelated> a <urn:fixture> .", encoding="utf-8")
        self.assertIn("expected URI", self.check_inventory().stderr)
        manifest.unlink()
        self.assertIn("LV2 manifest", self.check_inventory().stderr)

    def test_rejects_truncated_wrong_machine_and_object_files(self) -> None:
        self.seed_targets()
        binary = self.bin / "Cardinal.vst3" / "Contents" / "x86_64-linux" / "Cardinal.so"
        original = binary.read_bytes()
        binary.write_bytes(b"\x7fELF")
        self.assertIn("expected Linux x86-64", self.check_inventory().stderr)
        changed = bytearray(original)
        struct.pack_into("<H", changed, 18, 183)  # AArch64, not x86-64.
        binary.write_bytes(changed)
        self.assertIn("wrong ELF type", self.check_inventory().stderr)
        changed = bytearray(original)
        struct.pack_into("<H", changed, 16, 1)  # Relocatable object, not linked shared library.
        binary.write_bytes(changed)
        self.assertIn("wrong ELF type", self.check_inventory().stderr)
        changed = bytearray(original)
        struct.pack_into("<Q", changed, 32, 4096)  # Out-of-bounds program table.
        binary.write_bytes(changed)
        self.assertIn("truncated ELF program header table", self.check_inventory().stderr)

    def test_rejects_symlinked_plugin_binary(self) -> None:
        self.seed_targets()
        binary = self.bin / "Cardinal.vst" / "CardinalFX.so"
        copied = self.root / "fake.so"
        binary.rename(copied)
        binary.symlink_to(copied)
        self.assertIn("symlinked", self.check_inventory().stderr)

    def test_rejects_missing_bundle_even_with_correct_shared_object_elsewhere(self) -> None:
        self.seed_targets()
        bundle = self.bin / "CardinalFX.vst3"
        bundle.rename(self.bin / "other.vst3")
        self.assertIn("missing VST3 bundle", self.check_inventory().stderr)

    def run_bridge_step(self, name: str, *, prelude: str = "") -> subprocess.CompletedProcess[str]:
        script = f"{prelude}\n{workflow_script(name)}"
        return subprocess.run(["bash", "-c", script], cwd=self.root,
                              text=True, capture_output=True, check=False)

    def test_workflow_targets_match_preflight_without_glob_or_discovery_loops(self) -> None:
        self.assertIn("- name: Verify all plugin host-bridge targets exist\n"
                      "        run: python3 -B tools/ci/verify_plugin_bridge_inventory.py", WORKFLOW)
        lv2 = workflow_script("Test LV2 plugin")
        vst2 = workflow_script("Test VST2 plugin")
        vst3 = workflow_script("Test VST3 plugin")
        for script in (lv2, vst2, vst3):
            self.assertIn("set -euo pipefail", script)
            self.assertNotIn("for p in $(", script)
            self.assertIn("/usr/lib/carla/carla-bridge-native", script)
        for uri in URIS.values():
            self.assertIn(uri, lv2)
        self.assertIn("CardinalFX CardinalSynth", vst2)
        self.assertIn("Cardinal CardinalFX CardinalSynth", vst3)

    def test_bridge_steps_fail_if_no_plugins_are_found(self) -> None:
        lv2 = self.run_bridge_step("Test LV2 plugin", prelude="lv2ls() { :; }")
        self.assertNotEqual(lv2.returncode, 0, lv2.stdout)
        self.assertNotEqual(self.run_bridge_step("Test VST2 plugin").returncode, 0)
        self.assertNotEqual(self.run_bridge_step("Test VST3 plugin").returncode, 0)

    def test_all_bridge_invocations_are_reached_with_mock_commands(self) -> None:
        self.seed_targets()
        # Never start Carla or Valgrind during these script-logic tests. The
        # real CI job runs both against compiled binaries after preflight.
        fake_env = 'env() { printf "BRIDGE %s\\n" "$*"; }'
        lv2_list = 'lv2ls() { printf "%s\\n" ' + ' '.join(f'"{uri}"' for uri in URIS.values()) + '; }'
        result = self.run_bridge_step("Test LV2 plugin", prelude=f"{fake_env}\n{lv2_list}")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("BRIDGE "), 2)
        result = self.run_bridge_step("Test VST2 plugin", prelude=fake_env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("BRIDGE "), 2)
        result = self.run_bridge_step("Test VST3 plugin", prelude=fake_env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("BRIDGE "), 3)


if __name__ == "__main__":
    unittest.main()
