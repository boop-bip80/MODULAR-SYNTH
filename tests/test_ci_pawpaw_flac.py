"""Network-free regression checks for the pinned PawPaw FLAC CI workaround."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "workflows" / "scripts" / "seed-pawpaw-flac.sh"
BUILD = ROOT / ".github" / "workflows" / "build.yml"


class PawPawFlacBootstrapTests(unittest.TestCase):
    def test_official_release_checksum_and_pawpaw_cache_path_are_pinned(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('FLAC_VERSION="1.5.0"', script)
        self.assertIn('FLAC_ARCHIVE="flac-${FLAC_VERSION}.tar.xz"', script)
        self.assertIn(
            'FLAC_SHA256="f2c1c76592a82ffff8413ba3c4a1299b6c7ab06c734dee03fd88630485c2b920"',
            script,
        )
        self.assertIn(
            'https://github.com/xiph/flac/releases/download/${FLAC_VERSION}/${FLAC_ARCHIVE}',
            script,
        )
        self.assertIn('PAWPAW_DOWNLOAD_DIR="${HOME}/PawPawBuilds/downloads"', script)
        self.assertIn('check_sha256 "${DESTINATION}"', script)
        self.assertIn('check_sha256 "${temp_file}"', script)
        self.assertNotIn("--insecure", script)
        self.assertNotIn("--no-check-certificate", script)
        if shutil.which("bash"):
            subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_all_pawpaw_cardinal_bootstraps_seed_archive_first(self) -> None:
        workflow = BUILD.read_text(encoding="utf-8")
        steps = re.split(r"(?m)^\s+- name: ", workflow)
        bootstraps = [step for step in steps if "./deps/PawPaw/bootstrap-cardinal.sh" in step]
        self.assertEqual(4, len(bootstraps), "New PawPaw jobs need the checksum guard")
        seed = "bash .github/workflows/scripts/seed-pawpaw-flac.sh"
        for step in bootstraps:
            with self.subTest(job=step.splitlines()[0]):
                self.assertIn(seed, step)
                self.assertLess(step.index(seed), step.index("./deps/PawPaw/bootstrap-cardinal.sh"))

    @unittest.skipUnless(
        shutil.which("bash") and (shutil.which("sha256sum") or shutil.which("shasum")),
        "Requires Bash and a SHA-256 command",
    )
    def test_corrupt_download_is_rejected_without_network(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pawpaw-flac-test-") as temp:
            root = Path(temp)
            home = root / "home"
            home.mkdir()
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_curl = fake_bin / "curl"
            fake_curl.write_text(
                '#!/bin/sh\n'
                'while [ "$#" -gt 0 ]; do\n'
                '  if [ "$1" = "--output" ]; then\n'
                '    shift\n'
                '    printf "corrupted" > "$1"\n'
                '    exit 0\n'
                '  fi\n'
                '  shift\n'
                'done\n'
                'exit 2\n',
                encoding="utf-8",
            )
            fake_curl.chmod(0o755)
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("SHA-256 mismatch", result.stderr)
            cache_dir = home / "PawPawBuilds" / "downloads"
            self.assertFalse((cache_dir / "flac-1.5.0.tar.xz").exists())
            self.assertEqual([], list(cache_dir.glob(".flac-1.5.0.*")))


if __name__ == "__main__":
    unittest.main()
