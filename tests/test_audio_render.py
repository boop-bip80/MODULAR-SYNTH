#!/usr/bin/env python3
"""End-to-end deterministic PCM16 render tests for original first-party DSP."""
from __future__ import annotations

import array
import hashlib
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "audio-render" / "morph_filter_render.cpp"
RATES = (44100, 48000, 96000)
SECONDS = 4
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
FNV_MASK = (1 << 64) - 1


def fnv1a64(data: bytes) -> str:
    value = FNV_OFFSET
    for byte in data:
        value = ((value ^ byte) * FNV_PRIME) & FNV_MASK
    return f"{value:016x}"


def inspect_wav(path: Path, rate: int) -> tuple[str, float, float]:
    """Check PCM shape, amplitude, channel activity and return its digest."""
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 2 or wav.getsampwidth() != 2:
            raise AssertionError("render must be stereo PCM16")
        if wav.getframerate() != rate or wav.getnframes() != rate * SECONDS:
            raise AssertionError("sample rate or exact 4-second length is wrong")
        if wav.getcomptype() != "NONE":
            raise AssertionError("WAV must be uncompressed")
        frames = wav.readframes(wav.getnframes())

    expected_bytes = rate * SECONDS * 2 * 2
    if len(frames) != expected_bytes or path.stat().st_size != 44 + expected_bytes:
        raise AssertionError("RIFF/PCM data length mismatch")

    samples = array.array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max(abs(value) for value in samples) / 32768.0
    rms = math.sqrt(sum(float(value) * value for value in samples)
                    / len(samples)) / 32768.0
    left_energy = sum(float(v) * v for v in samples[::2])
    right_energy = sum(float(v) * v for v in samples[1::2])
    stereo_differences = sum(a != b for a, b in zip(samples[::2], samples[1::2]))

    if not (0.15 < peak < 0.75 and 0.02 < rms < 0.25):
        raise AssertionError(f"unexpected amplitude peak={peak} rms={rms}")
    if left_energy <= 0 or right_energy <= 0 or stereo_differences < rate:
        raise AssertionError("a channel is silent or stereo image is not evolving")
    return fnv1a64(frames), peak, rms


class AudioRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="modular-synth-audio-")
        cls.directory = Path(cls.temp.name)
        cls.binaries: dict[str, Path] = {}
        compiler = shlex.split(os.environ.get("CXX", "c++"))
        for profile, flags in {
            "normal": ("-O2",),
            "aggressive-fastmath": ("-O3", "-ffast-math"),
        }.items():
            override = os.environ.get(
                "MODULAR_SYNTH_AUDIO_RENDER_FASTMATH_BINARY"
                if profile == "aggressive-fastmath"
                else "MODULAR_SYNTH_AUDIO_RENDER_BINARY"
            )
            if override:
                cls.binaries[profile] = Path(override)
                continue
            if not compiler or not shutil.which(compiler[0]):
                raise AssertionError("C++17 compiler unavailable; set CXX")
            path = cls.directory / f"renderer-{profile}"
            command = [
                *compiler, "-std=c++17", *flags,
                "-Wall", "-Wextra", "-Werror", "-pedantic",
                "-I", str(ROOT), str(SOURCE), "-o", str(path),
            ]
            completed = subprocess.run(command, text=True, capture_output=True,
                                       check=False, timeout=120)
            if completed.returncode:
                raise AssertionError(
                    f"{profile} compile failed:\n{completed.stdout}{completed.stderr}"
                )
            cls.binaries[profile] = path

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def render(self, profile: str, rate: int, name: str) -> tuple[Path, str, float, float]:
        output = self.directory / name
        command = [
            str(self.binaries[profile]), "--sample-rate", str(rate),
            "--output", str(output),
        ]
        result = subprocess.run(command, text=True, capture_output=True,
                                check=False, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"rate={rate}", result.stdout)
        self.assertIn(f"frames={rate * SECONDS}", result.stdout)
        reported = re.search(r"pcm_fnv1a64=([0-9a-f]{16})", result.stdout)
        self.assertIsNotNone(reported, result.stdout)
        fnv, peak, rms = inspect_wav(output, rate)
        self.assertEqual(reported.group(1), fnv, "program/PCM checksum disagreement")
        return output, fnv, peak, rms

    def test_three_rates_byte_determinism_and_safety(self) -> None:
        rate_digests = []
        for rate in RATES:
            with self.subTest(sample_rate=rate):
                first, checksum, peak, rms = self.render(
                    "normal", rate, f"{rate}-first.wav")
                second, again, peak2, rms2 = self.render(
                    "normal", rate, f"{rate}-second.wav")
                self.assertEqual(hashlib.sha256(first.read_bytes()).digest(),
                                 hashlib.sha256(second.read_bytes()).digest())
                self.assertEqual(checksum, again)
                self.assertEqual((peak, rms), (peak2, rms2))
                rate_digests.append(checksum)
        self.assertEqual(len(set(rate_digests)), len(RATES))

    def test_aggressive_fastmath_render_is_finite(self) -> None:
        _, checksum, peak, rms = self.render(
            "aggressive-fastmath", 48000, "fastmath-48000.wav")
        self.assertRegex(checksum, r"^[0-9a-f]{16}$")
        self.assertGreater(peak, 0.15)
        self.assertGreater(rms, 0.02)

    def test_all_sixteen_notes_are_active_and_boundaries_click_safe(self) -> None:
        # A healthy whole-file RMS alone could pass a renderer that goes
        # silent halfway through the phrase. Check every original note.
        for rate in RATES:
            with self.subTest(sample_rate=rate):
                output, _, _, _ = self.render(
                    "normal", rate, f"note-windows-{rate}.wav")
                with wave.open(str(output), "rb") as wav:
                    samples = array.array("h", wav.readframes(wav.getnframes()))
                if sys.byteorder != "little":
                    samples.byteswap()
                frames_per_note = rate // 4
                note_rms = []
                boundary_jumps = []
                for note in range(16):
                    start = 2 * note * frames_per_note
                    end = 2 * (note + 1) * frames_per_note
                    block = samples[start:end]
                    energy = sum(float(value) * value for value in block)
                    note_rms.append(math.sqrt(energy / len(block)) / 32768.0)
                    if note:
                        boundary_jumps.extend(
                            abs(samples[start + channel] -
                                samples[start + channel - 2]) / 32768.0
                            for channel in (0, 1))
                self.assertGreater(min(note_rms), 0.015)
                self.assertLess(max(note_rms), 0.25)
                self.assertGreater(max(note_rms) - min(note_rms), 0.01)
                self.assertLess(max(boundary_jumps), 0.01)

    def test_dangling_symlink_does_not_create_target(self) -> None:
        # Without a file-entry check, an ifstream probe of a dangling
        # symlink fails and the subsequent ofstream follows it.
        target = self.directory / "should-never-be-created.wav"
        link = self.directory / "dangling-output-link.wav"
        try:
            link.symlink_to(target)
        except (NotImplementedError, OSError):
            self.skipTest("test system does not allow creating symlinks")
        result = subprocess.run(
            [str(self.binaries["normal"]), "--output", str(link)],
            capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("will not overwrite", result.stderr)
        self.assertTrue(link.is_symlink())
        self.assertFalse(target.exists())

    def test_help_validation_and_no_overwrite(self) -> None:
        binary = str(self.binaries["normal"])
        help_result = subprocess.run([binary, "--help"], capture_output=True,
                                     text=True, timeout=10)
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("Usage:", help_result.stdout)
        for args in ([], ["--sample-rate", "12345", "--output", "invalid.wav"],
                     ["--output"], ["--unknown"]):
            with self.subTest(args=args):
                result = subprocess.run([binary, *args], capture_output=True,
                                        text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
        existing, _, _, _ = self.render("normal", 44100, "must-preserve.wav")
        before = existing.read_bytes()
        result = subprocess.run([binary, "--output", str(existing)],
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("will not overwrite", result.stderr)
        self.assertEqual(before, existing.read_bytes())


if __name__ == "__main__":
    unittest.main()
