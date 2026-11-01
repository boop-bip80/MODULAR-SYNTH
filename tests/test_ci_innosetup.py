"""Offline regressions for Windows packaging's pinned Inno Setup fetch."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
FETCHER = ROOT / "utils" / "fetch-inno-setup.sh"
INSTALLER = ROOT / "utils" / "create-windows-installer.sh"
OFFICIAL_URL = (
    "https://github.com/jrsoftware/issrc/releases/download/"
    "is-6_0_5/innosetup-6.0.5.exe"
)
# GitHub's official jrsoftware/issrc release asset lists this digest.
OFFICIAL_SHA256 = "ae6823b523df87e9441789e51845434e4e0e70aac0b88afe80f94f20f4b98acb"


class InnoSetupSourceTests(unittest.TestCase):
    def test_immutable_official_url_and_published_digest(self) -> None:
        script = FETCHER.read_text(encoding="utf-8")
        self.assertIn("url=" + OFFICIAL_URL, script)
        self.assertIn("sha256=" + OFFICIAL_SHA256, script)
        self.assertRegex(script, r"sha256sum\s+--check\s+--status")
        self.assertRegex(script, r"curl\s+--fail\s+--location")
        self.assertNotIn("jrsoftware.org/download.php", script)

    def test_installer_invokes_fetcher_before_wine(self) -> None:
        script = INSTALLER.read_text(encoding="utf-8")
        self.assertTrue(INSTALLER.stat().st_mode & stat.S_IXUSR)
        self.assertIn('sh utils/fetch-inno-setup.sh "${dlfile}"', script)
        self.assertLess(script.index("sh utils/fetch-inno-setup.sh"), script.index("wineboot -u"))
        self.assertNotIn("jrsoftware.org/download.php", script)

    def test_shell_syntax(self) -> None:
        subprocess.run(["sh", "-n", str(FETCHER)], check=True)
        subprocess.run(["bash", "-n", str(INSTALLER)], check=True)


class InnoSetupOfflineFetcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="ci-inno-test-")
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        mockbin = self.root / "mockbin"
        mockbin.mkdir()
        (self.root / "bin").mkdir()
        self.target = self.root / "bin" / "innosetup-6.0.5.exe"
        self.curl_calls = self.root / "curl-calls"

        curl = mockbin / "curl"
        curl.write_text(
            textwrap.dedent(
                """\
                #!/bin/sh
                set -eu
                output=
                url=
                fail_flag=0
                location_flag=0
                while [ "$#" -gt 0 ]; do
                    case "$1" in
                        --output) shift; output=$1 ;;
                        --fail) fail_flag=1 ;;
                        --location) location_flag=1 ;;
                        --retry|--retry-delay) shift ;;
                        *) url=$1 ;;
                    esac
                    shift
                done
                [ "$fail_flag" = 1 ] && [ "$location_flag" = 1 ]
                [ "$url" = "$EXPECTED_INNO_URL" ] && [ -n "$output" ]
                printf 'called\\n' >> "$MOCK_CURL_CALLS"
                [ "${MOCK_DOWNLOAD_FAIL:-0}" != 1 ] || exit 22
                printf '%s' "${MOCK_CURL_BODY:-trusted}" > "$output"
                """
            ),
            encoding="utf-8",
        )

        sha256sum = mockbin / "sha256sum"
        sha256sum.write_text(
            textwrap.dedent(
                """\
                #!/bin/sh
                set -eu
                [ "$1" = --check ] && [ "$2" = --status ]
                read -r given_sha file
                [ "$given_sha" = "$EXPECTED_INNO_SHA256" ]
                [ -f "$file" ]
                [ "$(cat "$file")" = trusted ]
                """
            ),
            encoding="utf-8",
        )
        curl.chmod(0o755)
        sha256sum.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(mockbin) + os.pathsep + os.environ["PATH"],
            "EXPECTED_INNO_URL": OFFICIAL_URL,
            "EXPECTED_INNO_SHA256": OFFICIAL_SHA256,
            "MOCK_CURL_CALLS": str(self.curl_calls),
        }

    def run_fetcher(self, **env_overrides: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", str(FETCHER), str(self.target)],
            cwd=self.root,
            env={**self.env, **env_overrides},
            text=True,
            capture_output=True,
            check=False,
        )

    def assert_no_partial_files(self) -> None:
        self.assertEqual(list(self.target.parent.glob("*.tmp.*")), [])

    def test_first_download_populates_cache_atomically(self) -> None:
        result = self.run_fetcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_text(encoding="utf-8"), "trusted")
        self.assertEqual(self.curl_calls.read_text(encoding="utf-8"), "called\n")
        self.assert_no_partial_files()

    def test_valid_cached_asset_never_contacts_network(self) -> None:
        self.target.write_text("trusted", encoding="utf-8")
        result = self.run_fetcher(MOCK_DOWNLOAD_FAIL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.curl_calls.exists())
        self.assert_no_partial_files()

    def test_invalid_cached_html_is_replaced(self) -> None:
        self.target.write_text("<html>latest download</html>", encoding="utf-8")
        result = self.run_fetcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("wrong SHA-256", result.stderr)
        self.assertEqual(self.target.read_text(encoding="utf-8"), "trusted")
        self.assert_no_partial_files()

    def test_bad_download_checksum_fails_and_preserves_cached_file(self) -> None:
        self.target.write_text("prior invalid cache", encoding="utf-8")
        result = self.run_fetcher(MOCK_CURL_BODY="tampered")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("failed SHA-256", result.stderr)
        self.assertEqual(self.target.read_text(encoding="utf-8"), "prior invalid cache")
        self.assert_no_partial_files()

    def test_download_http_failure_cannot_replace_cached_file(self) -> None:
        self.target.write_text("prior invalid cache", encoding="utf-8")
        result = self.run_fetcher(MOCK_DOWNLOAD_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Failed to download", result.stderr)
        self.assertEqual(self.target.read_text(encoding="utf-8"), "prior invalid cache")
        self.assert_no_partial_files()

    def test_argument_validation(self) -> None:
        result = subprocess.run(
            ["sh", str(FETCHER)], text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)


if __name__ == "__main__":
    unittest.main()
