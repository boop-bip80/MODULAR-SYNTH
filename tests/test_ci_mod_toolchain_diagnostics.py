"""Static safety gate for MOD's uncached crosstool-NG bootstrap diagnostics.

This does not build the MOD target or verify its external source archive.
"""

import re
import hashlib
import importlib.util
import io
from email.message import Message
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
SEEDER_PATH = ROOT / "tools/ci/seed_mod_toolchain_source.py"
spec = importlib.util.spec_from_file_location("mod_toolchain_source", SEEDER_PATH)
seeder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seeder)


def sample_source_archive(names=("gcc-linaro-7.5-2019.12/", "gcc-linaro-7.5-2019.12/README")):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:xz") as archive:
        for name in names:
            info = tarfile.TarInfo(name)
            if name.endswith("/"):
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
            else:
                contents = b"source stub"
                info.size = len(contents)
                archive.addfile(info, io.BytesIO(contents))
    return stream.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, content, *, target="https://arm.example.test/source.tar.xz", mime="application/x-xz"):
        super().__init__(content)
        self.target = target
        self.headers = Message()
        self.headers["Content-Type"] = mime

    def geturl(self):
        return self.target


class ModToolchainDiagnosticsTests(unittest.TestCase):
    def test_diagnostics_run_only_after_failed_uncached_bootstrap(self) -> None:
        job = re.search(
            r"(?ms)^  mod-plugin-builder:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)",
            WORKFLOW,
        )
        self.assertIsNotNone(job)
        section = job.group(1)
        bootstrap = section.index("- name: Bootstrap toolchain")
        diagnostics = section.index("- name: Diagnose failed toolchain bootstrap")
        build = section.index("- name: Build for modaudio")
        self.assertLess(bootstrap, diagnostics)
        self.assertLess(diagnostics, build)
        self.assertIn("id: mpb_bootstrap", section[bootstrap:diagnostics])
        self.assertIn("if: steps.mpb-cache.outputs.cache-hit != 'true'", section)
        self.assertIn(
            "if: ${{ failure() && steps.mpb_bootstrap.outcome == 'failure' }}",
            section[diagnostics:build],
        )
        self.assertNotIn("continue-on-error:", section)

    def test_diagnostic_script_is_bounded_and_bash_syntax_valid(self) -> None:
        step = WORKFLOW.split("      - name: Diagnose failed toolchain bootstrap\n", 1)[1]
        step = step.split("      - name: Build for modaudio\n", 1)[0]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])
        for required in (
            '"$HOME/mod-workdir"',
            '"$GITHUB_WORKSPACE/deps/mod-plugin-builder"',
            "-type f -name build.log -print0",
            "tail -n 200",
            "tail -n 40",
            "grep -Eiv 'token|password|secret|credential|authorization|api[_-]?key|https?://|@'",
            "-name 'gcc-linaro-7.5-2019.12.tar.xz'",
            'xz -t -- "$archive"',
            'tar -tJf "$archive"',
            "exit 0",
        ):
            with self.subTest(required=required):
                self.assertIn(required, script)
        self.assertNotIn("set -x", script)
        self.assertNotIn("cat \"$build_log\"", script)
        result = subprocess.run(
            ["bash", "-n"], input=script, capture_output=True, text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bootstrap_requires_verified_legacy_source_preflight(self) -> None:
        section = WORKFLOW.split("      - name: Bootstrap toolchain\n", 1)[1]
        section = section.split("      - name: Diagnose failed toolchain bootstrap\n", 1)[0]
        self.assertIn("MOD_LINARO_SOURCE_URL: ${{ vars.MOD_LINARO_SOURCE_URL }}", section)
        self.assertIn("MOD_LINARO_SOURCE_SHA256: ${{ vars.MOD_LINARO_SOURCE_SHA256 }}", section)
        self.assertLess(
            section.index("python3 tools/ci/seed_mod_toolchain_source.py"),
            section.index("deps/mod-plugin-builder/bootstrap.sh"),
        )


class ModToolchainSourceArchiveTests(unittest.TestCase):
    def test_good_https_download_verified_and_reused_from_cache(self) -> None:
        content = sample_source_archive()
        digest = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            with mock.patch.object(seeder, "urlopen", return_value=FakeResponse(content)) as fetch:
                self.assertEqual(
                    seeder.seed_archive("https://arm.example.test/source.tar.xz", digest, cache),
                    "downloaded and verified source",
                )
            fetch.assert_called_once()
            self.assertEqual((cache / seeder.ARCHIVE_NAME).read_bytes(), content)
            with mock.patch.object(seeder, "urlopen", side_effect=AssertionError("unexpected download")):
                self.assertEqual(
                    seeder.seed_archive("https://arm.example.test/source.tar.xz", digest, cache),
                    "verified cached source",
                )

    def test_rejected_html_redirect_does_not_poison_cache(self) -> None:
        content = b"<html>The Linaro site moved</html>"
        digest = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            with mock.patch.object(
                seeder, "urlopen",
                return_value=FakeResponse(content, target="https://www.linaro.org/contact/", mime="text/html"),
            ):
                with self.assertRaisesRegex(seeder.SourceArchiveError, "HTML"):
                    seeder.seed_archive("https://releases.linaro.org/source.tar.xz", digest, cache)
            self.assertFalse((cache / seeder.ARCHIVE_NAME).exists())
            self.assertFalse(tuple(cache.iterdir()), "Staging archives must be cleaned up")

    def test_rejects_downgrade_and_credential_urls(self) -> None:
        digest = hashlib.sha256(sample_source_archive()).hexdigest()
        for url in (
            "http://arm.example.test/source.tar.xz",
            "https://user:password@arm.example.test/source.tar.xz",
            "ftp://arm.example.test/source.tar.xz",
        ):
            with self.subTest(url=url), tempfile.TemporaryDirectory() as temp:
                with self.assertRaisesRegex(seeder.SourceArchiveError, "HTTPS URL"):
                    seeder.seed_archive(url, digest, Path(temp))
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(
                seeder, "urlopen",
                return_value=FakeResponse(sample_source_archive(), target="http://arm.example.test/archive"),
            ):
                with self.assertRaisesRegex(seeder.SourceArchiveError, "HTTPS URL"):
                    seeder.seed_archive("https://arm.example.test/source.tar.xz", digest, Path(temp))

    def test_wrong_digest_or_wrong_archive_members_are_rejected(self) -> None:
        correct = sample_source_archive()
        wrong_members = sample_source_archive(("other/", "other/README"))
        traversal = sample_source_archive(("gcc-linaro-7.5-2019.12/", "gcc-linaro-7.5-2019.12/../outside"))
        for content, digest, problem in (
            (correct, "0" * 64, "SHA-256 mismatch"),
            (wrong_members, hashlib.sha256(wrong_members).hexdigest(), "not GCC Linaro"),
            (traversal, hashlib.sha256(traversal).hexdigest(), "unsafe member"),
            (b"\xfd7zXZ\x00invalid", hashlib.sha256(b"\xfd7zXZ\x00invalid").hexdigest(), "integrity check"),
        ):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as temp:
                with mock.patch.object(seeder, "urlopen", return_value=FakeResponse(content)):
                    with self.assertRaisesRegex(seeder.SourceArchiveError, problem):
                        seeder.seed_archive("https://arm.example.test/source.tar.xz", digest, Path(temp))
                self.assertFalse((Path(temp) / seeder.ARCHIVE_NAME).exists())

    def test_bad_cached_download_is_replaced_only_after_new_archive_verifies(self) -> None:
        content = sample_source_archive()
        digest = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            destination = cache / seeder.ARCHIVE_NAME
            destination.write_bytes(b"<html>stale cache</html>")
            with mock.patch.object(seeder, "urlopen", return_value=FakeResponse(content)):
                seeder.seed_archive("https://arm.example.test/source.tar.xz", digest, cache)
            self.assertEqual(destination.read_bytes(), content)

    def test_missing_configuration_fails_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, str(SEEDER_PATH), "--source-url", "", "--sha256", "", "--cache-dir", temp],
                check=False, capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("MOD hardware builds remain blocked", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
