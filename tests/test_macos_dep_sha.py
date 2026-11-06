"""Regression coverage for macOS dependency archive SHA-256 validation."""

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MacOSDependencyChecksumTest(unittest.TestCase):
    def test_darwin_uses_portable_sha256_command_in_both_modes(self):
        # Exercise the actual Darwin branch independently of uninitialized submodules.
        source = (ROOT / "deps" / "Makefile").read_text()
        blocks = [match.group(0) for match in re.finditer(
            r"(?ms)^ifeq \(\$\(shell uname -s\),Darwin\)\n.*?^endif\s*$",
            source,
        ) if "SHA256SUM" in match.group(0)]
        self.assertEqual(len(blocks), 1, "Darwin SHA256SUM configuration must be unique")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            uname = directory / "uname"
            uname.write_text("#!/bin/sh\ncase \"$1\" in -s) echo Darwin ;; *) exit 1 ;; esac\n")
            uname.chmod(0o755)
            probe = directory / "probe.mk"
            probe.write_text(
                "DEP_MAKE :=\n" + blocks[0] + "\n"
                ".PHONY: print-dep-make\nprint-dep-make:\n"
                "\t@printf '%s\\n' '$(DEP_MAKE)'\n"
            )
            env = os.environ.copy()
            env["PATH"] = str(directory) + os.pathsep + env.get("PATH", "")

            for cibuild in ("true", "false"):
                with self.subTest(CIBUILD=cibuild):
                    result = subprocess.run(
                        ["make", "--no-print-directory", "-s", "-f", str(probe),
                         "print-dep-make", f"CIBUILD={cibuild}"],
                        cwd=ROOT / "deps", env=env, text=True,
                        capture_output=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('SHA256SUM="shasum -a 256"', result.stdout)
                    self.assertNotIn("shasum5.", result.stdout)

    @unittest.skipUnless(shutil.which("shasum"), "unversioned shasum unavailable")
    def test_command_rejects_tampered_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "archive.tar.gz"
            archive.write_bytes(b"original fixture archive")
            pinned = hashlib.sha256(archive.read_bytes()).hexdigest()
            check_line = f"{pinned}  {archive}\n"

            def verify():
                return subprocess.run(
                    ["shasum", "-a", "256", "-c"], input=check_line,
                    capture_output=True, text=True,
                )

            self.assertEqual(verify().returncode, 0)
            archive.write_bytes(b"modified fixture archive")
            self.assertNotEqual(verify().returncode, 0)


if __name__ == "__main__":
    unittest.main()
