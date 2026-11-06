"""Source-only regression tests for the fail-closed external DAW audio gate."""

from __future__ import annotations

import hashlib
import importlib.util
import contextlib
import io
import json
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("host_capture", ROOT / "tools/ci/verify_host_audio_capture.py")
assert SPEC and SPEC.loader
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)
SOURCE_SHA = "a" * 40


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_wav(path: Path, *, rate: int = 48000, amplitude: float = .2,
              right: float = 1.0, phase: float = 0.0, seconds: float = 1.0) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        payload = bytearray()
        for i in range(round(rate * seconds)):
            v = math.sin(2 * math.pi * 220 * i / rate + phase) * amplitude
            payload.extend(struct.pack("<hh", round(32767 * v), round(32767 * v * right)))
        wf.writeframes(payload)


def valid_midi() -> bytes:
    track = bytes([0, 0x90, 60, 100, 0x60, 0x80, 60, 0, 0, 0xff, 0x2f, 0])
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, 96) + b"MTrk" + struct.pack(">I", len(track)) + track


class HostCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        # A header-shaped ELF fixture only, not a compiled/loadable plugin.
        elf = bytearray(64)
        elf[:4] = b"\x7fELF"
        elf[4:6] = bytes([2, 1])  # ELF64 little endian
        elf[16:20] = struct.pack("<HH", 3, 62)  # shared object, x86_64
        (self.base / "compiled-plugin.so").write_bytes(elf)
        (self.base / "source.vcv").write_bytes(b'{"modules":[{"id":1,"model":"Voice"}],"cables":[]}')
        (self.base / "notes.mid").write_bytes(valid_midi())
        write_wav(self.base / "active.wav")
        write_wav(self.base / "idle.wav", amplitude=0)
        self.manifest = {
            "schema": "modular-host-audio-v1", "source_sha": SOURCE_SHA,
            "host": {"name": "Test host", "version": "1.0", "os": "Linux x86_64",
                     "plugin_format": "VST3", "capture_method": "captured by operator after loading patch"},
            "plugin": self.record("compiled-plugin.so"),
            "patch": self.record("source.vcv"),
            "mode": "synth", "stimulus": self.record("notes.mid"),
            "render": self.record("active.wav"), "baseline": self.record("idle.wav"),
        }

    def record(self, name):
        return {"path": name, "sha256": digest(self.base / name)}

    def refresh(self, name, slot):
        self.manifest[slot] = self.record(name)

    def verify(self):
        return host.verify(self.manifest, self.base, SOURCE_SHA)

    def test_valid_synth_stereo_midi_and_negative_control(self):
        result = self.verify()
        self.assertTrue(result["accepted"])
        self.assertEqual(result["midi_note_on_events"], 1)
        self.assertGreater(result["control_rms_ratio_db"], 50)
        self.assertIn("operator-attested", result["scope_warning"])

    def test_valid_effect_requires_different_wet_pcm(self):
        write_wav(self.base / "dry.wav", amplitude=.18)
        self.manifest["mode"] = "effect"
        self.refresh("dry.wav", "stimulus")
        result = self.verify()
        self.assertTrue(result["accepted"])
        self.assertEqual(result["midi_note_on_events"], 0)

    def test_dry_pass_through_not_effect_proof(self):
        (self.base / "dry.wav").write_bytes((self.base / "active.wav").read_bytes())
        self.manifest["mode"] = "effect"
        self.refresh("dry.wav", "stimulus")
        with self.assertRaisesRegex(host.CaptureError, "exactly copies"):
            self.verify()

    def test_wrong_source_commit_rejected(self):
        self.manifest["source_sha"] = "b" * 40
        with self.assertRaisesRegex(host.CaptureError, "commit mismatch"):
            self.verify()

    def test_invalid_expected_commit_rejected(self):
        with self.assertRaisesRegex(host.CaptureError, "expected SHA"):
            host.verify(self.manifest, self.base, "not-a-commit")

    def test_tampered_render_digest_rejected(self):
        self.manifest["render"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(host.CaptureError, "digest does not match"):
            self.verify()

    def test_missing_capture_rejected(self):
        self.manifest["render"]["path"] = "missing.wav"
        with self.assertRaisesRegex(host.CaptureError, "cannot read evidence"):
            self.verify()

    def test_wav_trailing_undeclared_bytes_rejected_even_with_matching_sha256(self):
        with (self.base / "active.wav").open("ab") as stream:
            stream.write(b"unaccounted trailing payload")
        self.refresh("active.wav", "render")
        with self.assertRaisesRegex(host.CaptureError, "declared size or trailing bytes"):
            self.verify()

    def test_wav_malformed_chunk_after_audio_rejected(self):
        path = self.base / "active.wav"
        raw = bytearray(path.read_bytes())
        raw.extend(b"JUNK" + struct.pack("<I", 1000) + b"short")
        struct.pack_into("<I", raw, 4, len(raw) - 8)
        path.write_bytes(raw)
        self.refresh("active.wav", "render")
        with self.assertRaisesRegex(host.CaptureError, "oversized RIFF chunk"):
            self.verify()

    def test_wav_second_data_chunk_rejected(self):
        path = self.base / "active.wav"
        raw = bytearray(path.read_bytes())
        raw.extend(b"data" + struct.pack("<I", 4) + b"fake")
        struct.pack_into("<I", raw, 4, len(raw) - 8)
        path.write_bytes(raw)
        self.refresh("active.wav", "render")
        with self.assertRaisesRegex(host.CaptureError, "exactly one PCM data chunk"):
            self.verify()

    def test_absolute_path_and_traversal_rejected(self):
        for path in ("/tmp/capture.wav", "../capture.wav", "nested/../../escape.wav"):
            with self.subTest(path=path):
                self.manifest["render"]["path"] = path
                with self.assertRaisesRegex(host.CaptureError, "path"):
                    self.verify()
        self.manifest["render"]["path"] = "active.wav"

    def test_symlink_escape_rejected(self):
        (self.base / "active-link.wav").symlink_to(self.base / "active.wav")
        self.manifest["render"] = self.record("active.wav")
        self.manifest["render"]["path"] = "active-link.wav"
        with self.assertRaisesRegex(host.CaptureError, "symlink"):
            self.verify()

    def test_midi_without_note_on_fails(self):
        track = bytes([0, 0x80, 60, 0, 0, 0xff, 0x2f, 0])
        (self.base / "notes.mid").write_bytes(b"MThd" + struct.pack(">IHHH", 6, 0, 1, 96)
                                              + b"MTrk" + struct.pack(">I", len(track)) + track)
        self.refresh("notes.mid", "stimulus")
        with self.assertRaisesRegex(host.CaptureError, "no note-on"):
            self.verify()

    def test_truncated_midi_fails(self):
        (self.base / "notes.mid").write_bytes(valid_midi()[:-2])
        self.refresh("notes.mid", "stimulus")
        with self.assertRaisesRegex(host.CaptureError, "truncated MIDI"):
            self.verify()

    def test_mono_right_channel_fails_stereo_gate(self):
        write_wav(self.base / "active.wav", right=0)
        self.refresh("active.wav", "render")
        with self.assertRaisesRegex(host.CaptureError, "missing a stereo channel"):
            self.verify()

    def test_silent_render_fails(self):
        write_wav(self.base / "active.wav", amplitude=0)
        self.refresh("active.wav", "render")
        with self.assertRaisesRegex(host.CaptureError, "silent"):
            self.verify()

    def test_idle_and_played_equal_fails_midi_control(self):
        (self.base / "idle.wav").write_bytes((self.base / "active.wav").read_bytes())
        self.refresh("idle.wav", "baseline")
        with self.assertRaisesRegex(host.CaptureError, "no-input/no-MIDI control"):
            self.verify()

    def test_persistent_clipping_fails(self):
        with wave.open(str(self.base / "active.wav"), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            wf.writeframes(struct.pack("<hh", 32767, -32768) * 48000)
        self.refresh("active.wav", "render")
        with self.assertRaisesRegex(host.CaptureError, "clipping"):
            self.verify()

    def test_wrong_rate_and_duration_fails(self):
        for rate, seconds in ((22050, 1), (48000, .3), (48000, 46)):
            with self.subTest(rate=rate, seconds=seconds):
                write_wav(self.base / "active.wav", rate=rate, seconds=seconds)
                self.refresh("active.wav", "render")
                with self.assertRaisesRegex(host.CaptureError, "rate or duration"):
                    self.verify()

    def test_baseline_sample_format_mismatch_fails(self):
        write_wav(self.base / "idle.wav", rate=44100, amplitude=0)
        self.refresh("idle.wav", "baseline")
        with self.assertRaisesRegex(host.CaptureError, "share sample rate"):
            self.verify()

    def test_invalid_host_metadata_rejected(self):
        self.manifest["host"]["plugin_format"] = "unknown"
        with self.assertRaisesRegex(host.CaptureError, "unsupported host plugin"):
            self.verify()

    def test_non_linux_host_rejected(self):
        self.manifest["host"]["os"] = "macOS"
        with self.assertRaisesRegex(host.CaptureError, "Linux host"):
            self.verify()

    def test_non_elf_plugin_rejected(self):
        (self.base / "compiled-plugin.so").write_bytes(b"not a compiled ELF plugin")
        self.refresh("compiled-plugin.so", "plugin")
        with self.assertRaisesRegex(host.CaptureError, "Linux ELF64"):
            self.verify()

    def test_empty_or_invalid_patch_rejected(self):
        (self.base / "source.vcv").write_bytes(b'{"modules":[],"cables":[]}')
        self.refresh("source.vcv", "patch")
        with self.assertRaisesRegex(host.CaptureError, "nonempty modules"):
            self.verify()

    def test_duplicate_manifest_keys_fail_closed(self):
        manifest = self.base / "manifest.json"
        manifest.write_text('{"schema":"first","schema":"second"}')
        with contextlib.redirect_stdout(io.StringIO()):
            code = host.main(["--manifest", str(manifest), "--expected-sha", SOURCE_SHA])
        self.assertEqual(code, 1)

    def test_cli_json_exit_code_and_result(self):
        manifest = self.base / "manifest.json"
        manifest.write_text(json.dumps(self.manifest))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(host.main(["--manifest", str(manifest), "--expected-sha", SOURCE_SHA, "--json"]), 0)
            self.assertEqual(host.main(["--manifest", str(manifest), "--expected-sha", "b" * 40, "--json"]), 1)


if __name__ == "__main__":
    unittest.main()
