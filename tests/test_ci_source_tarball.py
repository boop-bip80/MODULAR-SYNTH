"""Offline regression coverage for the source-tarball release gate.

These checks validate archive completeness and workflow wiring; they are not
evidence of any completed hosted build or downloadable release.
"""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/workflows/scripts/verify-source-tarballs.sh"
WORKFLOW = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")
VERSION = re.search(r"(?m)^VERSION = (\S+)$", MAKEFILE).group(1)
ARCHIVES = (f"cardinal-{VERSION}.tar.xz", f"cardinal+deps-{VERSION}.tar.xz")


def source_job() -> str:
    match = re.search(
        r"(?ms)^  source-tarball:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)",
        WORKFLOW,
    )
    if match is None:
        raise AssertionError("Missing source-tarball job")
    return match.group(1)


class SourceReleaseWorkflowTests(unittest.TestCase):
    def test_makefile_contract_and_explicit_archive_gate(self) -> None:
        self.assertIn("tar -c --lzma", MAKEFILE)
        self.assertIn("../cardinal-$(VERSION).tar.xz", MAKEFILE)
        self.assertIn("../cardinal+deps-$(VERSION).tar.xz", MAKEFILE)

        job = source_job()
        create = job.index("- name: Create source tarball")
        verify = job.index("- name: Verify source release archives")
        upload = job.index("- uses: actions/upload-artifact@v4")
        self.assertLess(create, verify)
        self.assertLess(verify, upload)
        self.assertIn(
            'bash .github/workflows/scripts/verify-source-tarballs.sh "$(make -s version)"',
            job,
        )
        checker = SCRIPT.read_text(encoding="utf-8")
        for suffix in ("cardinal-${version}.tar.xz", "cardinal+deps-${version}.tar.xz"):
            self.assertIn(suffix, checker)
        self.assertIn('[[ ! -s "$archive" ]]', checker)
        self.assertIn('tar --lzma -tf "$archive"', checker)

    def test_tagged_upload_and_release_fail_on_unmatched_files(self) -> None:
        job = source_job()
        upload = job.split("      - uses: actions/upload-artifact@v4\n", 1)[1]
        upload = upload.split("      - uses:", 1)[0]
        release = job.split("      - uses: softprops/action-gh-release@v1\n", 1)[1]
        self.assertIn(
            "if-no-files-found: ${{ startsWith(github.ref, 'refs/tags/') "
            "&& 'error' || 'warn' }}",
            upload,
        )
        self.assertIn("fail_on_unmatched_files: true", release)

    @unittest.skipUnless(
        shutil.which("tar") and shutil.which("lzma") and shutil.which("bash"),
        "GNU tar/LZMA/Bash unavailable for archive smoke test",
    )
    def test_validator_accepts_both_valid_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "checkout"
            project.mkdir()
            (project / "payload.txt").write_text("A sample source entry", encoding="utf-8")
            self._create_archives(project)
            result = self._run(project, VERSION)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(
        shutil.which("tar") and shutil.which("lzma") and shutil.which("bash"),
        "GNU tar/LZMA/Bash unavailable for archive smoke test",
    )
    def test_validator_rejects_missing_empty_and_corrupt_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "checkout"
            project.mkdir()
            (project / "payload.txt").write_text("A sample source entry", encoding="utf-8")
            self._create_archives(project)
            with_deps = project.parent / ARCHIVES[1]
            with_deps.unlink()
            self.assertNotEqual(self._run(project, VERSION).returncode, 0)

            with_deps.touch()
            self.assertNotEqual(self._run(project, VERSION).returncode, 0)

            with_deps.write_bytes(b"not a compressed tar archive")
            self.assertNotEqual(self._run(project, VERSION).returncode, 0)

    def test_validator_rejects_path_like_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            result = self._run(project, "../untrusted")
            self.assertEqual(result.returncode, 2)

    @staticmethod
    def _run(project: Path, version: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), version],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def _create_archives(project: Path) -> None:
        for archive in ARCHIVES:
            subprocess.run(
                [
                    "tar", "--lzma", "-cf", str(project.parent / archive),
                    "-C", str(project), "payload.txt",
                ],
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()
