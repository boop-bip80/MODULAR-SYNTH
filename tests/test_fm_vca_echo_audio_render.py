#!/usr/bin/env python3
"""Real FMVoice -> DualVCA -> StereoEcho DSP rendered to deterministic WAV.

These are offline C++ source tests, not Cardinal/DAW or listening tests.
"""
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
SOURCE = ROOT / "tools" / "audio-render" / "fm_vca_echo_render.cpp"
RATES = (48000, 96000)
MUSIC_SECONDS = 4
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
FNV_MASK = (1 << 64) - 1


def pcm_fnv1a64(data: bytes) -> str:
    state = FNV_OFFSET
    for byte in data:
        state = ((state ^ byte) * FNV_PRIME) & FNV_MASK
    return f"{state:016x}"


def samples_from_pcm(data: bytes) -> array.array:
    values = array.array("h")
    values.frombytes(data)
    if sys.byteorder != "little":
        values.byteswap()
    return values


def rms(samples: array.array) -> float:
    return math.sqrt(sum(float(x) * x for x in samples) / len(samples)) / 32768.0


def inspect_wav(path: Path, rate: int, tail_seconds: int) -> dict:
    with wave.open(str(path), "rb") as wav:
        self_description = (wav.getnchannels(), wav.getsampwidth(),
                            wav.getframerate(), wav.getnframes(),
                            wav.getcomptype())
        expected_description = (2, 2, rate,
                                rate * (MUSIC_SECONDS + tail_seconds), "NONE")
        if self_description != expected_description:
            raise AssertionError((self_description, expected_description))
        payload = wav.readframes(wav.getnframes())
    if len(payload) != rate * (MUSIC_SECONDS + tail_seconds) * 4:
        raise AssertionError("truncated stereo PCM16 data")
    if path.stat().st_size != 44 + len(payload):
        raise AssertionError("noncanonical RIFF layout")
    samples = samples_from_pcm(payload)
    peak = max(abs(x) for x in samples) / 32768.0
    music = samples[:rate * MUSIC_SECONDS * 2]
    stereo_difference = sum(a != b for a, b in zip(music[::2], music[1::2]))
    note_rms = []
    boundary_jumps = []
    for note in range(16):
        begin = rate // 4 * note * 2
        end = rate // 4 * (note + 1) * 2
        note_rms.append(rms(music[begin:end]))
        if note:
            boundary_jumps.extend(
                abs(music[begin + channel] - music[begin + channel - 2]) / 32768.0
                for channel in (0, 1)
            )
    return {
        "payload": payload, "samples": samples,
        "hash": pcm_fnv1a64(payload), "peak": peak, "rms": rms(samples),
        "music": music, "stereo_difference": stereo_difference,
        "note_rms": note_rms, "boundary_jumps": boundary_jumps,
    }


class FMVCAEchoRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="fm-vca-echo-render-")
        cls.directory = Path(cls.temp.name)
        cls.binaries = {}
        compiler = shlex.split(os.environ.get("CXX", "c++"))
        if not compiler or not shutil.which(compiler[0]):
            raise AssertionError("C++17 compiler is required; set CXX")
        for profile, flags in {
            "normal": ("-O2",),
            "fastmath": ("-O3", "-ffast-math"),
        }.items():
            binary = cls.directory / f"fm-vca-echo-{profile}"
            command = [
                *compiler, "-std=c++17", *flags, "-Wall", "-Wextra",
                "-Werror", "-pedantic", "-I", str(ROOT), str(SOURCE),
                "-o", str(binary),
            ]
            result = subprocess.run(command, capture_output=True, text=True,
                                    check=False, timeout=120)
            if result.returncode != 0:
                raise AssertionError(result.stdout + result.stderr)
            cls.binaries[profile] = binary

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def render(self, profile: str, rate: int, filename: str,
               *, tail_seconds: int = 1,
               dry_reference: bool = False) -> tuple[Path, dict]:
        path = self.directory / filename
        cmd = [str(self.binaries[profile]), "--sample-rate", str(rate),
               "--output", str(path), "--tail-seconds", str(tail_seconds)]
        if dry_reference:
            cmd.append("--dry-reference")
        result = subprocess.run(cmd, capture_output=True, text=True,
                                check=False, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("chain=FMVoice+DualVCA+StereoEcho", result.stdout)
        self.assertIn(f"rate={rate}", result.stdout)
        self.assertIn(f"frames={rate * (4 + tail_seconds)}", result.stdout)
        self.assertIn("echo=off" if dry_reference else "echo=on",
                      result.stdout)
        self.assertIn(f"tail_seconds={tail_seconds}", result.stdout)
        match = re.search(r"pcm_fnv1a64=([0-9a-f]{16})", result.stdout)
        self.assertIsNotNone(match, result.stdout)
        result_stats = inspect_wav(path, rate, tail_seconds)
        self.assertEqual(match.group(1), result_stats["hash"])
        return path, result_stats

    def test_48k_96k_repeatable_and_musical_note_windows(self) -> None:
        digests = []
        for rate in RATES:
            with self.subTest(rate=rate):
                first, a = self.render("normal", rate, f"normal-{rate}-a.wav")
                second, b = self.render("normal", rate, f"normal-{rate}-b.wav")
                self.assertEqual(first.read_bytes(), second.read_bytes())
                self.assertEqual(a["hash"], b["hash"])
                self.assertEqual((a["peak"], a["rms"]),
                                 (b["peak"], b["rms"]))
                self.assertTrue(0.05 < a["peak"] < 0.60)
                self.assertTrue(0.012 < a["rms"] < 0.15)
                self.assertGreater(a["stereo_difference"], rate)
                self.assertGreater(min(a["note_rms"]), 0.007)
                self.assertLess(max(a["note_rms"]), 0.15)
                self.assertLess(max(a["boundary_jumps"]), 0.025)
                digests.append(a["hash"])
        self.assertEqual(len(set(digests)), len(RATES))

    def test_real_echo_delay_differs_from_dual_vca_dry_reference(self) -> None:
        rate = 48000
        _, dry = self.render("normal", rate, "dry-reference.wav",
                             tail_seconds=0, dry_reference=True)
        _, wet = self.render("normal", rate, "wet-reference.wav", tail_seconds=0)
        self.assertNotEqual(dry["hash"], wet["hash"])
        # Before 187.5 ms, 35% wet should be 65% of the VCA output,
        # modulo independent PCM16 rounding at the final output stage.
        early = rate * 16 // 100 * 2
        early_error = max(abs(w - 0.65 * d) for d, w in zip(
            dry["samples"][:early], wet["samples"][:early]))
        self.assertLess(early_error, 2.1)
        start, stop = rate // 4 * 2, rate * 3 // 4 * 2
        late_error = max(abs(w - 0.65 * d) for d, w in zip(
            dry["samples"][start:stop], wet["samples"][start:stop]))
        self.assertGreater(late_error, 80.0)

    def test_echo_tail_is_true_decay_without_extra_voice_output(self) -> None:
        for rate in RATES:
            with self.subTest(rate=rate):
                _, no_tail = self.render("normal", rate, f"base-{rate}.wav",
                                         tail_seconds=0)
                first, one = self.render("normal", rate, f"tail1-{rate}.wav",
                                         tail_seconds=1)
                second, two = self.render("normal", rate, f"tail2-{rate}.wav",
                                          tail_seconds=2)
                self.assertEqual(one["payload"][:len(no_tail["payload"])],
                                 no_tail["payload"])
                self.assertEqual(two["payload"][:len(one["payload"])],
                                 one["payload"])
                self.assertNotEqual(no_tail["hash"], one["hash"])
                self.assertNotEqual(one["hash"], two["hash"])
                tail = two["samples"][rate * MUSIC_SECONDS * 2:]
                early = tail[:rate // 4 * 2]
                late = tail[-rate // 4 * 2:]
                self.assertGreater(max(abs(x) for x in early), 8)
                self.assertLess(rms(late), rms(early) * 0.1)
                self.assertEqual(first.stat().st_size, 44 + rate * 5 * 4)
                self.assertEqual(second.stat().st_size, 44 + rate * 6 * 4)

    def test_aggressive_fastmath_is_finite_deterministic(self) -> None:
        for rate in RATES:
            with self.subTest(rate=rate):
                a, stats = self.render("fastmath", rate,
                                       f"fastmath-{rate}-a.wav")
                b, repeated = self.render("fastmath", rate,
                                          f"fastmath-{rate}-b.wav")
                self.assertEqual(a.read_bytes(), b.read_bytes())
                self.assertEqual(stats["hash"], repeated["hash"])
                self.assertTrue(0.05 < stats["peak"] < 0.60)
                self.assertGreater(min(stats["note_rms"]), 0.007)
                self.assertGreater(stats["stereo_difference"], rate)

    def test_cli_rejects_invalid_inputs_and_never_overwrites(self) -> None:
        binary = str(self.binaries["normal"])
        info = subprocess.run([binary, "--help"], capture_output=True,
                              text=True, timeout=10)
        self.assertEqual(info.returncode, 0)
        self.assertIn("Usage:", info.stdout)
        for args in (
            [], ["--output"], ["--bad-flag"], ["--tail-seconds", "3"],
            ["--sample-rate", "44100"],
            ["--dry-reference", "--output", "ignored.wav"],
        ):
            with self.subTest(args=args):
                result = subprocess.run([binary, *args], capture_output=True,
                                        text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
        source, _ = self.render("normal", 48000, "do-not-overwrite.wav")
        original = hashlib.sha256(source.read_bytes()).digest()
        result = subprocess.run([binary, "--output", str(source)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("will not overwrite", result.stderr)
        self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), original)
        link = self.directory / "dangling-output.wav"
        try:
            link.symlink_to(self.directory / "missing-target.wav")
        except (OSError, NotImplementedError):
            return
        result = subprocess.run([binary, "--output", str(link)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertTrue(link.is_symlink())


if __name__ == "__main__":
    unittest.main()
