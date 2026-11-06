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
from urllib.error import HTTPError, URLError
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
SEEDER_PATH = ROOT / "tools/ci/seed_mod_toolchain_source.py"
spec = importlib.util.spec_from_file_location("mod_toolchain_source", SEEDER_PATH)
seeder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seeder)


def sample_source_archive(names=None, *, links=(), extra_types=()):
    if names is None:
        root = "gcc-linaro-7.5-2019.12"
        names = (
            f"{root}/", f"{root}/configure", f"{root}/gcc/",
            f"{root}/gcc/config.gcc", f"{root}/libgcc/",
            f"{root}/libgcc/config.host",
        )
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
        for name, target, typecode in links:
            info = tarfile.TarInfo(name)
            info.type = typecode
            info.linkname = target
            archive.addfile(info)
        for name, typecode in extra_types:
            info = tarfile.TarInfo(name)
            info.type = typecode
            archive.addfile(info)
    return stream.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, content, *, target="https://arm.example.test/gcc-linaro-7.5-2019.12.tar.xz", mime="application/x-xz"):
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
    def test_transport_failures_are_actionable_and_do_not_disclose_signed_urls(self) -> None:
        digest = hashlib.sha256(sample_source_archive()).hexdigest()
        failures = (
            (HTTPError("https://mirror.example.test/archive?token=not-for-logs", 404, "Not Found", None, None), "HTTP 404"),
            (URLError("download failed; token=not-for-logs"), "unreachable or timed out"),
            (TimeoutError("download timeout; token=not-for-logs"), "unreachable or timed out"),
        )
        for failure, expected in failures:
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as temp:
                cache = Path(temp)
                with mock.patch.object(seeder, "urlopen", side_effect=failure):
                    with self.assertRaises(seeder.SourceArchiveError) as caught:
                        seeder.seed_archive(
                            "https://mirror.example.test/" + seeder.ARCHIVE_NAME,
                            digest, cache,
                        )
                self.assertIn(expected, str(caught.exception))
                self.assertNotIn("not-for-logs", str(caught.exception))
                self.assertEqual(tuple(cache.iterdir()), (), "Failed downloads must remove staged archives")

    def test_good_https_download_verified_and_reused_from_cache(self) -> None:
        content = sample_source_archive()
        digest = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            with mock.patch.object(seeder, "urlopen", return_value=FakeResponse(content)) as fetch:
                self.assertEqual(
                    seeder.seed_archive("https://arm.example.test/gcc-linaro-7.5-2019.12.tar.xz", digest, cache),
                    "downloaded and verified source",
                )
            fetch.assert_called_once()
            self.assertEqual((cache / seeder.ARCHIVE_NAME).read_bytes(), content)
            with mock.patch.object(seeder, "urlopen", side_effect=AssertionError("unexpected download")):
                self.assertEqual(
                    seeder.seed_archive("https://arm.example.test/gcc-linaro-7.5-2019.12.tar.xz", digest, cache),
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
                    seeder.seed_archive("https://releases.linaro.org/gcc-linaro-7.5-2019.12.tar.xz", digest, cache)
            self.assertFalse((cache / seeder.ARCHIVE_NAME).exists())
            self.assertFalse(tuple(cache.iterdir()), "Staging archives must be cleaned up")

    def test_archive_name_is_required_before_fetch_and_after_redirect(self) -> None:
        archive = sample_source_archive()
        digest = hashlib.sha256(archive).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / "cache"
            with mock.patch.object(seeder, "urlopen", side_effect=AssertionError("must not fetch")):
                with self.assertRaisesRegex(seeder.SourceArchiveError, seeder.ARCHIVE_NAME):
                    seeder.seed_archive("https://mirror.example.test/download.html", digest, cache)
            renamed_local = Path(temp) / "renamed-source.tar.xz"
            renamed_local.write_bytes(archive)
            with self.assertRaisesRegex(seeder.SourceArchiveError, seeder.ARCHIVE_NAME):
                seeder.seed_local_archive(renamed_local, digest, cache)
            with mock.patch.object(
                seeder, "urlopen", return_value=FakeResponse(
                    archive, target="https://mirror.example.test/contact.html",
                    mime="application/octet-stream",
                ),
            ):
                with self.assertRaisesRegex(seeder.SourceArchiveError, seeder.ARCHIVE_NAME):
                    seeder.seed_archive(
                        "https://mirror.example.test/" + seeder.ARCHIVE_NAME, digest, cache,
                    )
            self.assertFalse((cache / seeder.ARCHIVE_NAME).exists())
            self.assertFalse(tuple(cache.iterdir()), "Redirect rejection must remove staging files")

    def test_html_payload_is_rejected_even_when_hash_matches_and_mime_is_generic(self) -> None:
        html = b"<!doctype html><html><body>Download discontinued</body></html>"
        digest = hashlib.sha256(html).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            with mock.patch.object(
                seeder, "urlopen", return_value=FakeResponse(
                    html, target="https://mirror.example.test/" + seeder.ARCHIVE_NAME,
                    mime="application/octet-stream",
                ),
            ):
                with self.assertRaisesRegex(seeder.SourceArchiveError, "not XZ data"):
                    seeder.seed_archive(
                        "https://mirror.example.test/" + seeder.ARCHIVE_NAME, digest, cache,
                    )
            self.assertFalse(tuple(cache.iterdir()), "Spoofed archive must not reach cache")

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
                    seeder.seed_archive("https://arm.example.test/gcc-linaro-7.5-2019.12.tar.xz", digest, Path(temp))

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
                        seeder.seed_archive("https://arm.example.test/gcc-linaro-7.5-2019.12.tar.xz", digest, Path(temp))
                self.assertFalse((Path(temp) / seeder.ARCHIVE_NAME).exists())

    def test_canonical_gcc_source_files_are_required(self) -> None:
        # A two-entry XZ/tar with a convincing basename and a matching digest
        # must not be mistaken for the full GCC source release.
        fake = sample_source_archive(("gcc-linaro-7.5-2019.12/", "gcc-linaro-7.5-2019.12/README"))
        digest = hashlib.sha256(fake).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(seeder, "urlopen", return_value=FakeResponse(fake)):
                with self.assertRaisesRegex(seeder.SourceArchiveError, "canonical GCC 7 source"):
                    seeder.seed_archive("https://arm.example.test/gcc-linaro-7.5-2019.12.tar.xz", digest, Path(temp))
            self.assertFalse((Path(temp) / seeder.ARCHIVE_NAME).exists())

    def test_archive_links_must_resolve_inside_source_root(self) -> None:
        root = seeder.ROOT_NAME
        for links, problem in (
            (((f"{root}/gcc/escape", "../../../outside", tarfile.SYMTYPE),), "escaping link"),
            (((f"{root}/gcc/absolute", "/etc/passwd", tarfile.SYMTYPE),), "unsafe link"),
            (((f"{root}/gcc/hard", "../../outside", tarfile.LNKTYPE),), "escaping link"),
        ):
            with self.subTest(links=links):
                archive = sample_source_archive(links=links)
                digest = hashlib.sha256(archive).hexdigest()
                with tempfile.TemporaryDirectory() as temp:
                    with mock.patch.object(seeder, "urlopen", return_value=FakeResponse(archive)):
                        with self.assertRaisesRegex(seeder.SourceArchiveError, problem):
                            seeder.seed_archive("https://arm.example.test/gcc-linaro-7.5-2019.12.tar.xz", digest, Path(temp))

    def test_safe_relative_symlink_is_accepted(self) -> None:
        archive = sample_source_archive(links=(
            (f"{seeder.ROOT_NAME}/gcc/config-link", "config.gcc", tarfile.SYMTYPE),
        ))
        digest = hashlib.sha256(archive).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(seeder, "urlopen", return_value=FakeResponse(archive)):
                self.assertEqual(
                    seeder.seed_archive("https://arm.example.test/gcc-linaro-7.5-2019.12.tar.xz", digest, Path(temp)),
                    "downloaded and verified source",
                )

    def test_duplicate_files_and_special_members_fail_closed(self) -> None:
        root = seeder.ROOT_NAME
        for archive, problem in (
            (sample_source_archive(names=(
                f"{root}/", f"{root}/configure", f"{root}/configure",
                f"{root}/gcc/config.gcc", f"{root}/libgcc/config.host",
            )), "duplicate member path"),
            (sample_source_archive(names=(
                f"{root}/", f"{root}/configure", f"{root}/gcc/config.gcc",
                f"{root}/gcc/./config.gcc", f"{root}/libgcc/config.host",
            )), "duplicate member path"),
            (sample_source_archive(extra_types=((f"{root}/fifo", tarfile.FIFOTYPE),)), "special member"),
        ):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as temp:
                digest = hashlib.sha256(archive).hexdigest()
                with mock.patch.object(seeder, "urlopen", return_value=FakeResponse(archive)):
                    with self.assertRaisesRegex(seeder.SourceArchiveError, problem):
                        seeder.seed_archive("https://arm.example.test/gcc-linaro-7.5-2019.12.tar.xz", digest, Path(temp))

    def test_local_source_seed_requires_digest_and_never_uses_network(self) -> None:
        archive = sample_source_archive()
        digest = hashlib.sha256(archive).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / seeder.ARCHIVE_NAME
            source.write_bytes(archive)
            cache = root / "download"
            with mock.patch.object(seeder, "urlopen", side_effect=AssertionError("no network allowed")):
                self.assertEqual(seeder.seed_local_archive(source, digest, cache), "verified local source")
                self.assertEqual(seeder.seed_local_archive(source, digest, cache), "verified cached source")
            self.assertEqual(source.read_bytes(), archive)
            self.assertEqual((cache / seeder.ARCHIVE_NAME).read_bytes(), archive)
            source.write_bytes(b"replaced by unrelated content")
            self.assertEqual(seeder.seed_local_archive(source, digest, cache), "verified cached source")

    def test_local_source_rejects_bad_digest_without_mutating_cache(self) -> None:
        archive = sample_source_archive()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / seeder.ARCHIVE_NAME
            source.write_bytes(archive)
            cache = root / "download"
            cache.mkdir()
            cached = cache / seeder.ARCHIVE_NAME
            cached.write_bytes(b"uncertain prior download")
            with self.assertRaisesRegex(seeder.SourceArchiveError, "SHA-256 mismatch"):
                seeder.seed_local_archive(source, "0" * 64, cache)
            self.assertEqual(cached.read_bytes(), b"uncertain prior download")
            self.assertEqual(tuple(cache.iterdir()), (cached,))

    def test_local_source_cli_runs_without_url_and_requires_authenticity_pin(self) -> None:
        archive = sample_source_archive()
        digest = hashlib.sha256(archive).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / seeder.ARCHIVE_NAME
            source.write_bytes(archive)
            base_command = [
                sys.executable, str(SEEDER_PATH), "--source-url", "", "--source-file", str(source),
                "--cache-dir", str(root / "cache"),
            ]
            missing_pin = subprocess.run(
                base_command + ["--sha256", ""], check=False, capture_output=True, text=True,
            )
            self.assertEqual(missing_pin.returncode, 1)
            self.assertIn("requires a verified --sha256", missing_pin.stderr)
            seeded = subprocess.run(
                base_command + ["--sha256", digest], check=False, capture_output=True, text=True,
            )
            self.assertEqual(seeded.returncode, 0, seeded.stderr)
            self.assertIn("verified local source", seeded.stdout)
            self.assertEqual((root / "cache" / seeder.ARCHIVE_NAME).read_bytes(), archive)

    def test_compressed_member_and_unpacked_size_limits_fail_closed(self) -> None:
        archive = sample_source_archive()
        digest = hashlib.sha256(archive).hexdigest()
        for limit, value, problem in (
            ("MAX_SOURCE_BYTES", len(archive) - 1, "compressed size bound"),
            ("MAX_ARCHIVE_MEMBERS", 5, "member limit"),
            ("MAX_UNPACKED_BYTES", 12, "unpacked size limit"),
        ):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as temp:
                candidate = Path(temp) / "candidate.tar.xz"
                candidate.write_bytes(archive)
                with mock.patch.object(seeder, limit, value):
                    with self.assertRaisesRegex(seeder.SourceArchiveError, problem):
                        seeder.validate_archive(candidate, digest)
                self.assertFalse((Path(temp) / seeder.ARCHIVE_NAME).exists())

    def test_bad_cached_download_is_replaced_only_after_new_archive_verifies(self) -> None:
        content = sample_source_archive()
        digest = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            destination = cache / seeder.ARCHIVE_NAME
            destination.write_bytes(b"<html>stale cache</html>")
            with mock.patch.object(seeder, "urlopen", return_value=FakeResponse(content)):
                seeder.seed_archive("https://arm.example.test/gcc-linaro-7.5-2019.12.tar.xz", digest, cache)
            self.assertEqual(destination.read_bytes(), content)

    def test_missing_configuration_fails_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, str(SEEDER_PATH), "--source-url", "", "--sha256", "", "--cache-dir", temp],
                check=False, capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("MOD_LINARO_SOURCE_URL", result.stderr)
        self.assertIn("MOD_LINARO_SOURCE_SHA256", result.stderr)
        self.assertIn(seeder.ARCHIVE_NAME, result.stderr)
        self.assertIn("--source-file", result.stderr)
        self.assertIn("MOD hardware builds remain blocked", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
