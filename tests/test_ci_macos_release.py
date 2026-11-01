"""Release asset guards for the non-matrix macOS packaging job."""

from pathlib import Path
import re
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "build.yml"
MACOS_JOB = re.compile(r"(?ms)^  macos:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)")


class MacosReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        match = MACOS_JOB.search(WORKFLOW.read_text(encoding="utf-8"))
        if match is None:
            raise AssertionError("macos job missing from full-build workflow")
        cls.job = match.group(1)

    def test_release_gate_references_no_nonexistent_matrix_property(self) -> None:
        self.assertNotIn("strategy:\n", self.job)
        self.assertNotIn("matrix.debug", self.job)
        self.assertIn(
            "      - uses: softprops/action-gh-release@v1\n"
            "        if: startsWith(github.ref, 'refs/tags/')\n",
            self.job,
        )

    def test_release_requires_package_and_main_cache_warmup_can_warn(self) -> None:
        upload = self.job.split("      - uses: actions/upload-artifact@v4\n", 1)[1]
        upload = upload.split("      - uses:", 1)[0]
        release = self.job.split("      - uses: softprops/action-gh-release@v1\n", 1)[1]
        self.assertIn(
            "if-no-files-found: ${{ startsWith(github.ref, 'refs/tags/') "
            "&& 'error' || 'warn' }}",
            upload,
        )
        self.assertIn("fail_on_unmatched_files: true", release)
        self.assertIn("${{ github.event.repository.name }}-*.pkg", upload)
        self.assertIn("${{ github.event.repository.name }}-*.pkg", release)


if __name__ == "__main__":
    unittest.main()
