"""Offline regression checks for Windows tag assets and their upload/release paths."""

from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
VERIFIER = ROOT / ".github" / "workflows" / "scripts" / "verify-windows-release-artifacts.sh"
WINDOWS_JOB = re.compile(r"(?ms)^  windows:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)")


class WindowsReleaseAssetsTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cwd = Path(temporary.name)

    def verify(self, target: str = "win64", slug: str = "v26.02", repository: str = "MODULAR-SYNTH") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(VERIFIER), repository, target, slug],
            cwd=self.cwd,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_release_gate_requires_both_actual_nonempty_assets(self) -> None:
        self.assertNotEqual(0, self.verify().returncode)
        (self.cwd / "MODULAR-SYNTH-win64-v26.02.zip").write_bytes(b"zip")
        self.assertNotEqual(0, self.verify().returncode)
        (self.cwd / "Cardinal-win64-26.02-installer.exe").write_bytes(b"installer")
        self.assertEqual(0, self.verify().returncode)

    def test_release_gate_rejects_wrong_ref_target_and_empty_file(self) -> None:
        (self.cwd / "MODULAR-SYNTH-win64-v26.02.zip").write_bytes(b"zip")
        (self.cwd / "Cardinal-win32-26.02-installer.exe").write_bytes(b"installer")
        self.assertNotEqual(0, self.verify().returncode)
        (self.cwd / "Cardinal-win64-26.02-installer.exe").touch()
        self.assertNotEqual(0, self.verify().returncode)
        (self.cwd / "Cardinal-win64-26.02-installer.exe").write_bytes(b"installer")
        self.assertNotEqual(0, self.verify(slug="different-tag").returncode)
        self.assertNotEqual(0, self.verify(target="win32").returncode)

    def test_release_gate_rejects_ambiguous_installer_or_invalid_arguments(self) -> None:
        (self.cwd / "MODULAR-SYNTH-win64-v26.02.zip").write_bytes(b"zip")
        (self.cwd / "Cardinal-win64-26.02-installer.exe").write_bytes(b"installer")
        (self.cwd / "Cardinal-win64-old-installer.exe").write_bytes(b"installer")
        self.assertNotEqual(0, self.verify().returncode)
        self.assertEqual(2, self.verify(target="linux").returncode)
        self.assertEqual(2, self.verify(repository="bad/repository").returncode)

    def test_workflow_upload_and_release_match_actual_fork_names(self) -> None:
        match = WINDOWS_JOB.search(WORKFLOW.read_text(encoding="utf-8"))
        self.assertIsNotNone(match, "Windows matrix job missing from full build")
        job = match.group(1)

        self.assertIn("${{ github.event.repository.name }}-${{ matrix.target }}-${{ github.event.pull_request.number || env.SHA8 }}.zip", job)
        self.assertIn("      - name: Verify Windows release installer and ZIP\n        if: startsWith(github.ref, 'refs/tags/')", job)
        self.assertIn("bash .github/workflows/scripts/verify-windows-release-artifacts.sh", job)
        upload = job.split("      - uses: actions/upload-artifact@v4\n", 1)[1].split("      - uses:", 1)[0]
        release = job.split("      - uses: softprops/action-gh-release@v1\n", 1)[1]
        for step in (upload, release):
            self.assertIn("Cardinal-${{ matrix.target }}-*-installer.exe", step)
            self.assertIn("${{ github.event.repository.name }}-${{ matrix.target }}-*.zip", step)
            self.assertNotIn("Cardinal-*.zip", step)
        self.assertIn("if-no-files-found: ${{ startsWith(github.ref, 'refs/tags/') && 'error' || 'warn' }}", upload)
        self.assertIn("fail_on_unmatched_files: true", release)
        self.assertIn("if: startsWith(github.ref, 'refs/tags/')", release)

    def test_installer_source_matches_its_target_specific_release_pattern(self) -> None:
        for target in ("win32", "win64"):
            with self.subTest(target=target):
                installer_script = (ROOT / "utils" / "inno" / f"{target}.iss").read_text(encoding="utf-8")
                self.assertIn(f"OutputBaseFilename=Cardinal-{target}-{{#VERSION}}-installer", installer_script)
        create_installer = (ROOT / "utils" / "create-windows-installer.sh").read_text(encoding="utf-8")
        self.assertIn("mv utils/inno/*.exe .", create_installer)


if __name__ == "__main__":
    unittest.main()
