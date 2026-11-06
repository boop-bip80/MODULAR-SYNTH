"""Fixture-only tests: generated WAVs are NOT real-host audio evidence."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/ci"))
sys.path.insert(0, str(ROOT / "tests"))

import package_host_audio_capture as packager  # noqa: E402
from test_ci_host_audio_capture import valid_midi, write_wav  # noqa: E402


class PackageExternalCaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True)
        subprocess.run([
            "git", "-C", str(self.repo), "-c", "user.name=Fixture",
            "-c", "user.email=fixture@example.invalid", "commit", "-q",
            "--allow-empty", "-m", "source fixture",
        ], check=True)
        self.sha = subprocess.check_output(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True,
        ).strip()
        self.external = self.base / "operator-files"
        self.external.mkdir()
        elf = bytearray(64)
        elf[:6] = b"\x7fELF\x02\x01"
        elf[16:20] = (3).to_bytes(2, "little") + (62).to_bytes(2, "little")
        (self.external / "plugin.so").write_bytes(elf)
        (self.external / "patch.vcv").write_text('{"modules":[{"id":1}],"cables":[]}', encoding="utf-8")
        (self.external / "notes.mid").write_bytes(valid_midi())
        # Generated PCM exists ONLY inside unit-test fixtures, never in packages
        # advertised as real DAW recordings by this test suite.
        write_wav(self.external / "active.wav")
        write_wav(self.external / "idle.wav", amplitude=0)
        self.output = self.base / "upload-this-directory"
        self.plugin_sha = hashlib.sha256((self.external / "plugin.so").read_bytes()).hexdigest()

    def command(self, **overrides):
        values = {
            "repo": self.repo, "source-sha": self.sha,
            "plugin": self.external / "plugin.so", "plugin-sha256": self.plugin_sha,
            "patch": self.external / "patch.vcv", "stimulus": self.external / "notes.mid",
            "render": self.external / "active.wav", "baseline": self.external / "idle.wav",
            "output-dir": self.output, "mode": "synth", "plugin-format": "VST3",
            "host-name": "Operator attestation fixture", "host-version": "1",
            "capture-method": "fixture bytes only; no DAW capture claimed",
        }
        values.update(overrides)
        argv = [item for key, value in values.items() for item in (f"--{key}", str(value))]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return packager.main(argv)

    def test_packages_exact_supplied_bytes_and_manifest(self):
        self.assertEqual(self.command(), 0)
        manifest = json.loads((self.output / "capture.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["source_sha"], self.sha)
        self.assertEqual(manifest["plugin"]["sha256"], self.plugin_sha)
        for slot, original in (("plugin", "plugin.so"), ("patch", "patch.vcv"),
                               ("stimulus", "notes.mid"), ("render", "active.wav"),
                               ("baseline", "idle.wav")):
            self.assertEqual((self.output / manifest[slot]["path"]).read_bytes(),
                             (self.external / original).read_bytes())
        self.assertTrue(packager.verify(manifest, self.output, self.sha)["accepted"])
        self.assertEqual(self.command(), 1, "must never overwrite a published package")

    def test_wrong_source_or_plugin_sha_fails_without_artifact(self):
        self.assertEqual(self.command(**{"source-sha": "b" * 40}), 1)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.command(**{"plugin-sha256": "0" * 64}), 1)
        self.assertFalse(self.output.exists())

    def test_symlink_and_invalid_audio_fail_without_artifact(self):
        linked = self.base / "linked-render.wav"
        linked.symlink_to(self.external / "active.wav")
        self.assertEqual(self.command(render=linked), 1)
        self.assertFalse(self.output.exists())
        (self.external / "active.wav").write_bytes(b"not a WAV")
        self.assertEqual(self.command(), 1)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
