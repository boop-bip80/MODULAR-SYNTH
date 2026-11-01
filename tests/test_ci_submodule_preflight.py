"""Offline tests for the Gitlink/SpeexDSP CI preflight command.

Every fixture uses only local temporary Git repositories with synthetic Gitlinks;
no submodules are fetched and no network requests are made.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "tools" / "ci" / "preflight_submodules.py"
FAKE_PIN = "a" * 40
SPEEX_PIN = "b" * 40
SOURCE_URL = "https://gitlab.xiph.org/xiph/speexdsp.git"
MIRROR_URL = "https://github.com/xiph/speexdsp.git"


class SubmodulePreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="submodule-ci-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.git(self.repo, "init", "-q")
        self.configure_author(self.repo)
        (self.repo / ".gitmodules").write_text(
            '[submodule "example"]\n'
            '\tpath = deps/example\n'
            '\turl = https://github.com/example/example.git\n',
            encoding="utf-8",
        )
        workflow = self.repo / ".github" / "workflows" / "build.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text(
            "name: build\n"
            "env:\n"
            "  GIT_CONFIG_COUNT: '1'\n"
            f"  GIT_CONFIG_KEY_0: url.{MIRROR_URL}.insteadOf\n"
            f"  GIT_CONFIG_VALUE_0: {SOURCE_URL}\n",
            encoding="utf-8",
        )
        self.git(self.repo, "add", ".gitmodules", ".github/workflows/build.yml")
        self.pin(self.repo, "deps/example", FAKE_PIN)
        self.git(self.repo, "commit", "-qm", "synthetic pinned submodule")

    @staticmethod
    def git(repo: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def configure_author(self, repo: Path) -> None:
        self.git(repo, "config", "user.name", "CI Test")
        self.git(repo, "config", "user.email", "ci-test@example.invalid")

    def pin(self, repo: Path, path: str, sha: str) -> None:
        self.git(repo, "update-index", "--add", "--cacheinfo", f"160000,{sha},{path}")

    def run_preflight(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(PREFLIGHT), "--repo", str(self.repo), *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def populate_example(self) -> str:
        sub = self.repo / "deps" / "example"
        sub.mkdir(parents=True)
        self.git(sub, "init", "-q")
        self.configure_author(sub)
        (sub / "README").write_text("local source\n", encoding="utf-8")
        self.git(sub, "add", "README")
        self.git(sub, "commit", "-qm", "local pinned commit")
        return self.git(sub, "rev-parse", "HEAD")

    def populate_rack(self, speex_url: str = SOURCE_URL, include_gitlink: bool = True) -> None:
        rack = self.repo / "src" / "Rack"
        rack.mkdir(parents=True)
        self.git(rack, "init", "-q")
        self.configure_author(rack)
        (rack / ".gitmodules").write_text(
            '[submodule "dep/speexdsp"]\n'
            '\tpath = dep/speexdsp\n'
            f'\turl = {speex_url}\n',
            encoding="utf-8",
        )
        self.git(rack, "add", ".gitmodules")
        if include_gitlink:
            self.pin(rack, "dep/speexdsp", SPEEX_PIN)
        self.git(rack, "commit", "-qm", "Rack with SpeexDSP Gitlink")
        with (self.repo / ".gitmodules").open("a", encoding="utf-8") as stream:
            stream.write(
                '[submodule "Rack"]\n'
                '\tpath = src/Rack\n'
                '\turl = https://github.com/VCVRack/Rack.git\n'
            )
        self.git(self.repo, "add", ".gitmodules")
        self.pin(self.repo, "src/Rack", self.git(rack, "rev-parse", "HEAD"))
        self.git(self.repo, "commit", "-qm", "pin Rack")

    def test_unpopulated_submodule_is_an_actionable_warning_by_default(self) -> None:
        result = self.run_preflight()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("1 root Gitlinks", result.stdout)
        self.assertIn("1 uninitialized submodule", result.stdout)
        self.assertIn(f"resolves to {MIRROR_URL}", result.stdout)

    def test_strict_mode_requires_initialized_checkout(self) -> None:
        result = self.run_preflight("--require-populated")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("deps/example is not initialized", result.stderr)

    def test_manifest_entry_without_gitlink_fails(self) -> None:
        manifest = self.repo / ".gitmodules"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace("deps/example", "deps/absent"),
            encoding="utf-8",
        )
        result = self.run_preflight()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("entries lack pinned Gitlinks", result.stderr)

    def test_invalid_mirror_configuration_fails_offline(self) -> None:
        workflow = self.repo / ".github" / "workflows" / "build.yml"
        workflow.write_text(
            workflow.read_text(encoding="utf-8").replace(
                "https://gitlab.xiph.org/xiph/speexdsp.git",
                "https://example.invalid/wrong.git",
            ),
            encoding="utf-8",
        )
        result = self.run_preflight()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("GIT_CONFIG_VALUE_0 must equal", result.stderr)

    def test_initialized_submodule_must_match_pinned_head(self) -> None:
        actual = self.populate_example()
        self.assertNotEqual(actual, FAKE_PIN)
        result = self.run_preflight()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("does not match pinned Gitlink", result.stderr)

        self.pin(self.repo, "deps/example", actual)
        self.git(self.repo, "commit", "-qm", "fix pinned Gitlink")
        strict_result = self.run_preflight("--require-populated")
        self.assertEqual(0, strict_result.returncode, strict_result.stderr)

    def test_nested_rack_speex_gitlink_is_checked_when_rack_populated(self) -> None:
        self.populate_rack()
        result = self.run_preflight()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("2 uninitialized submodule", result.stdout)
        strict_result = self.run_preflight("--require-populated")
        self.assertNotEqual(0, strict_result.returncode)
        self.assertIn("dep/speexdsp is not initialized", strict_result.stderr)

    def test_nested_rack_missing_speex_gitlink_is_rejected(self) -> None:
        self.populate_rack(include_gitlink=False)
        result = self.run_preflight()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("lacks pinned dep/speexdsp Gitlink", result.stderr)

    def test_nested_rack_uncovered_speex_url_is_rejected(self) -> None:
        self.populate_rack(speex_url="https://example.invalid/other-speex.git")
        result = self.run_preflight()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("URL is not covered by CI mirror", result.stderr)


if __name__ == "__main__":
    unittest.main()
