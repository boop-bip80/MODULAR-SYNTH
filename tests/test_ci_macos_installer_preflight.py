"""Non-destructive inventory preflight for the inherited macOS pkg builder.

These tests run on Linux.  They do not create, sign or install a .pkg.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "utils" / "create-macos-installer.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"


class MacInstallerInputPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="modular-macos-preflight-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "Makefile").write_text("VERSION = test\n", encoding="utf-8")
        package = self.root / "utils" / "macOS" / "package.xml.in"
        package.parent.mkdir(parents=True)
        package.write_text("<installer/>\n", encoding="utf-8")
        self.bin = self.root / "bin"
        for directory in (
            "Cardinal.app", "CardinalNative.app", "Cardinal.lv2/resources",
            "Cardinal.component", "Cardinal.vst", "Cardinal.vst3", "Cardinal.clap",
        ):
            (self.bin / directory).mkdir(parents=True)

    def run_preflight(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, check=False, timeout=15,
        )

    def test_complete_inventory_passes_without_modifying_anything(self) -> None:
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        completed = self.run_preflight("--preflight")
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("no files modified", completed.stdout)
        after = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        self.assertEqual(before, after)

    def test_missing_bundle_rejected_before_existing_data_is_touched(self) -> None:
        (self.bin / "CardinalNative.app").rmdir()
        sentinel = self.bin / "res" / "user-sentinel.txt"
        sentinel.parent.mkdir()
        sentinel.write_text("preserve me", encoding="utf-8")
        completed = self.run_preflight("--preflight")
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("CardinalNative.app", completed.stderr)
        self.assertEqual("preserve me", sentinel.read_text(encoding="utf-8"))

    def test_missing_format_and_resources_are_explicit(self) -> None:
        (self.bin / "Cardinal.clap").rmdir()
        completed = self.run_preflight("--preflight")
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("clap", completed.stderr)
        (self.bin / "Cardinal.clap").mkdir()
        (self.bin / "Cardinal.lv2" / "resources").rmdir()
        completed = self.run_preflight("--preflight")
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("resources", completed.stderr)

    def test_symlinked_app_directory_is_rejected(self) -> None:
        (self.bin / "Cardinal.app").rmdir()
        (self.bin / "CardinalReal.app").mkdir()
        (self.bin / "Cardinal.app").symlink_to("CardinalReal.app", target_is_directory=True)
        completed = self.run_preflight("--preflight")
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("Cardinal.app", completed.stderr)

    def test_wrong_working_directory_and_unknown_flag_fail(self) -> None:
        (self.root / "Makefile").unlink()
        completed = self.run_preflight("--preflight")
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("source root", completed.stderr)
        completed = self.run_preflight("--skip-safety")
        self.assertEqual(2, completed.returncode)
        self.assertIn("Usage", completed.stderr)

    def test_ci_preflight_runs_after_architecture_gate_before_pkgbuild(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        macos = workflow.split("\n  macos:\n", 1)[1].split("\n  windows:", 1)[0]
        architecture = macos.index("Verify universal macOS build products")
        inventory = macos.index("Verify macOS installer inputs without modifying bundles")
        packaging = macos.index("Build macOS (packaging)")
        self.assertLess(architecture, inventory)
        self.assertLess(inventory, packaging)
        self.assertIn("bash utils/create-macos-installer.sh --preflight", macos)


if __name__ == "__main__":
    unittest.main()
