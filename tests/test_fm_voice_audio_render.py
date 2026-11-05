#!/usr/bin/env python3
"""Deterministic FMVoice C++ DSP-to-stereo-WAV regression (not host audio)."""
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
SOURCE = ROOT / "tools" / "audio-render" / "fm_voice_render.cpp"
RATES = (44100, 48000, 96000)
SECONDS = 4
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
FNV_MASK = (1 << 64) - 1


def pcm_hash(payload: bytes) -> str:
    state = FNV_OFFSET
    for octet in payload:
        state = ((state ^ octet) * FNV_PRIME) & FNV_MASK
    return f"{state:016x}"


def wav_metrics(path: Path, rate: int) -> dict:
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(),
                wav.getnframes(), wav.getcomptype()) != (
                    2, 2, rate, rate * SECONDS, "NONE"):
            raise AssertionError("unexpected stereo PCM16 WAV format")
        payload = wav.readframes(wav.getnframes())
    if len(payload) != rate * SECONDS * 4 or path.stat().st_size != 44 + len(payload):
        raise AssertionError("incorrect RIFF or PCM data length")
    samples = array.array("h")
    samples.frombytes(payload)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max(abs(v) for v in samples) / 32768.0
    rms = math.sqrt(sum(float(v) * v for v in samples)
                    / len(samples)) / 32768.0
    left = samples[::2]
    right = samples[1::2]
    stereo_diff = sum(a != b for a, b in zip(left, right))
    note_rms: list[float] = []
    boundary_jumps: list[float] = []
    frames_per_note = rate // 4
    note_hashes = []
    for n in range(16):
        a, b = 2 * n * frames_per_note, 2 * (n + 1) * frames_per_note
        note = samples[a:b]
        note_hashes.append(hashlib.sha256(note.tobytes()).digest())
        note_rms.append(math.sqrt(sum(float(x) * x for x in note)
                                  / len(note)) / 32768.0)
        if n:
            boundary_jumps.extend(
                abs(samples[a + channel] - samples[a + channel - 2]) / 32768.0
                for channel in (0, 1)
            )
    return {
        "hash": pcm_hash(payload), "peak": peak, "rms": rms,
        "samples": samples, "stereo_diff": stereo_diff,
        "note_rms": note_rms, "boundary_jumps": boundary_jumps,
        "distinct_note_windows": len(set(note_hashes)),
    }


class FMVoiceWavTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="fmvoice-audio-")
        cls.directory = Path(cls.temp.name)
        cls.binaries: dict[str, Path] = {}
        compiler = shlex.split(os.environ.get("CXX", "c++"))
        if not compiler or not shutil.which(compiler[0]):
            raise AssertionError("C++17 compiler unavailable; set CXX")
        for name, flags in {
            "normal": ("-O2",),
            "fastmath": ("-O3", "-ffast-math"),
        }.items():
            binary = cls.directory / f"fm-voice-{name}"
            command = [
                *compiler, "-std=c++17", *flags, "-Wall", "-Wextra",
                "-Werror", "-pedantic", "-I", str(ROOT), str(SOURCE),
                "-o", str(binary),
            ]
            finished = subprocess.run(command, capture_output=True, text=True,
                                      check=False, timeout=120)
            if finished.returncode:
                raise AssertionError(
                    f"{name} compiler failure:\n{finished.stdout}{finished.stderr}"
                )
            cls.binaries[name] = binary

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def render(self, name: str, rate: int, filename: str,
               *, reference: bool = False, unison: int = 1,
               harmony: str | None = None) -> tuple[Path, dict]:
        path = self.directory / filename
        cmd = [str(self.binaries[name]), "--sample-rate", str(rate),
               "--output", str(path)]
        if reference:
            cmd.append("--sine-reference")
        if unison != 1:
            cmd.extend(("--unison", str(unison)))
        if harmony is not None:
            cmd.extend(("--harmony", harmony))
        finished = subprocess.run(cmd, capture_output=True, text=True,
                                  check=False, timeout=60)
        self.assertEqual(finished.returncode, 0,
                         finished.stdout + finished.stderr)
        self.assertIn(f"mode={'sine' if reference else 'fm'}", finished.stdout)
        self.assertIn(f"unison={unison}", finished.stdout)
        self.assertIn(f"harmony={harmony or 'off'}", finished.stdout)
        self.assertIn(f"rate={rate}", finished.stdout)
        self.assertIn(f"frames={rate * SECONDS}", finished.stdout)
        match = re.search(r"pcm_fnv1a64=([0-9a-f]{16})", finished.stdout)
        self.assertIsNotNone(match, finished.stdout)
        measurements = wav_metrics(path, rate)
        self.assertEqual(match.group(1), measurements["hash"])
        return path, measurements

    def test_multirate_repeatability_per_note_energy_and_headroom(self) -> None:
        hashes = []
        for rate in RATES:
            with self.subTest(rate=rate):
                first, a = self.render("normal", rate, f"fm-{rate}-first.wav")
                second, b = self.render("normal", rate, f"fm-{rate}-repeat.wav")
                self.assertEqual(hashlib.sha256(first.read_bytes()).digest(),
                                 hashlib.sha256(second.read_bytes()).digest())
                self.assertEqual(a["hash"], b["hash"])
                self.assertEqual((a["peak"], a["rms"]), (b["peak"], b["rms"]))
                self.assertTrue(0.1 < a["peak"] < 0.75)
                self.assertTrue(0.03 < a["rms"] < 0.3)
                self.assertGreater(a["stereo_diff"], rate // 2)
                self.assertGreater(min(a["note_rms"]), 0.03)
                self.assertLess(max(a["note_rms"]), 0.3)
                self.assertLess(max(a["boundary_jumps"]), 0.02)
                self.assertGreaterEqual(a["distinct_note_windows"], 12)
                hashes.append(a["hash"])
        self.assertEqual(len(set(hashes)), len(RATES))

    def test_fm_is_audibly_distinct_in_samples_from_sine_reference(self) -> None:
        # This checks PCM difference, not human listening or hearing thresholds.
        _, fm = self.render("normal", 48000, "fm-compare.wav")
        _, sine = self.render("normal", 48000, "sine-compare.wav", reference=True)
        self.assertNotEqual(fm["hash"], sine["hash"])
        self.assertGreater(sine["stereo_diff"], 24000)
        diffs = [float(a) - b for a, b in zip(
            fm["samples"], sine["samples"])]
        difference_rms = math.sqrt(sum(v * v for v in diffs)
                                   / len(diffs)) / 32768.0
        self.assertGreater(difference_rms, 0.04)
        self.assertLess(sine["peak"], 0.75)
        self.assertGreater(min(sine["note_rms"]), 0.03)

    def test_aggressive_fastmath_finite_and_active(self) -> None:
        _, metrics = self.render("fastmath", 48000, "fm-fastmath.wav")
        self.assertTrue(0.1 < metrics["peak"] < 0.75)
        self.assertTrue(0.03 < metrics["rms"] < 0.3)
        self.assertGreater(min(metrics["note_rms"]), 0.03)

    def test_unison_layers_are_deterministic_distinct_and_bounded(self) -> None:
        for rate in RATES:
            with self.subTest(rate=rate):
                _, single = self.render("normal", rate,
                                        f"unison-single-{rate}.wav")
                layer_hashes = [single["hash"]]
                for voices in (2, 4):
                    first, a = self.render(
                        "normal", rate, f"unison-{voices}-{rate}.wav",
                        unison=voices)
                    second, b = self.render(
                        "normal", rate, f"unison-{voices}-{rate}-repeat.wav",
                        unison=voices)
                    self.assertEqual(first.read_bytes(), second.read_bytes())
                    self.assertEqual(a["hash"], b["hash"])
                    self.assertGreater(a["stereo_diff"], rate // 4)
                    self.assertTrue(0.02 < a["peak"] < 0.75)
                    self.assertTrue(0.008 < a["rms"] < 0.3)
                    self.assertGreater(min(a["note_rms"]), 0.006)
                    self.assertLess(max(a["boundary_jumps"]), 0.04)
                    layer_hashes.append(a["hash"])
                self.assertEqual(len(set(layer_hashes)), 3)

    def test_sine_reference_unison_and_explicit_one_layer(self) -> None:
        rate = 48000
        single, _ = self.render("normal", rate, "unison-default.wav")
        explicit = self.directory / "unison-explicit-one.wav"
        result = subprocess.run([
            str(self.binaries["normal"]), "--sample-rate", str(rate),
            "--output", str(explicit), "--unison", "1"
        ], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(single.read_bytes(), explicit.read_bytes())
        _, sine_one = self.render("normal", rate, "unison-sine-one.wav",
                                  reference=True)
        _, sine_four = self.render("normal", rate, "unison-sine-four.wav",
                                   reference=True, unison=4)
        self.assertNotEqual(sine_one["hash"], sine_four["hash"])
        self.assertGreater(sine_four["stereo_diff"], rate // 4)
        self.assertTrue(0.008 < sine_four["rms"] < 0.3)

    def test_unison_fastmath_is_finite(self) -> None:
        _, metrics = self.render("fastmath", 48000, "unison-fastmath.wav",
                                 unison=4)
        self.assertTrue(0.02 < metrics["peak"] < 0.75)
        self.assertTrue(0.008 < metrics["rms"] < 0.3)

    def test_harmony_off_is_exactly_backward_compatible(self) -> None:
        for unison in (1, 2, 4):
            with self.subTest(unison=unison):
                implicit, original = self.render(
                    "normal", 48000, f"harmony-default-{unison}.wav",
                    unison=unison)
                explicit, inactive = self.render(
                    "normal", 48000, f"harmony-off-{unison}.wav",
                    harmony="off", unison=unison)
                self.assertEqual(implicit.read_bytes(), explicit.read_bytes())
                self.assertEqual(original["hash"], inactive["hash"])

    def test_four_tone_chords_have_distinct_deterministic_stereo_audio(self) -> None:
        for rate in RATES:
            with self.subTest(rate=rate):
                fingerprints = []
                for harmony in ("minor7", "quartal"):
                    for unison in (1, 4):
                        with self.subTest(harmony=harmony, unison=unison):
                            first, a = self.render(
                                "normal", rate,
                                f"harmony-{harmony}-{unison}-{rate}.wav",
                                harmony=harmony, unison=unison)
                            second, b = self.render(
                                "normal", rate,
                                f"harmony-{harmony}-{unison}-{rate}-again.wav",
                                harmony=harmony, unison=unison)
                            self.assertEqual(first.read_bytes(), second.read_bytes())
                            self.assertEqual(a["hash"], b["hash"])
                            self.assertGreater(a["stereo_diff"], rate // 3)
                            self.assertTrue(0.015 < a["peak"] < 0.75)
                            self.assertTrue(0.008 < a["rms"] < 0.3)
                            self.assertGreater(min(a["note_rms"]), 0.005)
                            self.assertLess(max(a["boundary_jumps"]), 0.05)
                            self.assertGreaterEqual(a["distinct_note_windows"], 12)
                            fingerprints.append(a["hash"])
                self.assertEqual(len(set(fingerprints)), 4)

    def test_harmony_sine_reference_contains_expected_chord_tones(self) -> None:
        # Verify audible-frequency content from the actual four independent
        # FMVoice sine cores, not just different PCM hashes or file sizes.
        rate = 48000
        _, off = self.render("normal", rate, "harmony-sine-off.wav",
                             reference=True)
        _, minor7 = self.render("normal", rate, "harmony-sine-minor7.wav",
                                reference=True, harmony="minor7")
        _, quartal = self.render("normal", rate, "harmony-sine-quartal.wav",
                                reference=True, harmony="quartal")

        def tone_strength(measurements: dict, semitones: int) -> float:
            # Hann window avoids leakage from the base C3 note. The 120-ms
            # window starts after all four 15-ms-staggered attacks finish.
            left = measurements["samples"][::2]
            start = int(0.095 * rate)
            frames = int(0.12 * rate)
            frequency = 130.81278265 * (2 ** (semitones / 12))
            angular = 2 * math.pi * frequency / rate
            real = 0.0
            imaginary = 0.0
            for n in range(frames):
                window = 0.5 - 0.5 * math.cos(2 * math.pi * n / (frames - 1))
                value = left[start + n] * window
                real += value * math.cos(angular * n)
                imaginary += value * math.sin(angular * n)
            return 4 * math.hypot(real, imaginary) / (frames * 32768.0)

        for semitones in (3, 7):
            self.assertGreater(tone_strength(minor7, semitones), 0.018)
            self.assertGreater(
                tone_strength(minor7, semitones),
                4 * tone_strength(off, semitones))
        for semitones in (5, 15):
            self.assertGreater(tone_strength(quartal, semitones), 0.014)
            self.assertGreater(
                tone_strength(quartal, semitones),
                4 * tone_strength(off, semitones))
        self.assertNotEqual(minor7["hash"], quartal["hash"])

    def test_harmony_fastmath_is_finite_with_full_unison(self) -> None:
        for harmony in ("minor7", "quartal"):
            with self.subTest(harmony=harmony):
                _, measurements = self.render(
                    "fastmath", 48000,
                    f"harmony-{harmony}-fastmath.wav",
                    harmony=harmony, unison=4)
                self.assertTrue(0.015 < measurements["peak"] < 0.75)
                self.assertTrue(0.008 < measurements["rms"] < 0.3)
                self.assertGreater(min(measurements["note_rms"]), 0.005)

    def test_cli_validation_existing_file_and_dangling_symlink(self) -> None:
        binary = str(self.binaries["normal"])
        help_result = subprocess.run([binary, "--help"], capture_output=True,
                                     text=True, timeout=10)
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("Usage:", help_result.stdout)
        for args in (
            [], ["--output"], ["--unknown"],
            ["--sample-rate", "12345", "--output", "invalid.wav"],
            ["--unison"], ["--unison", "0"],
            ["--unison", "3"], ["--unison", "-1"],
            ["--harmony"], ["--harmony", "major"],
            ["--harmony", "MINOR7"],
        ):
            with self.subTest(args=args):
                finished = subprocess.run([binary, *args], capture_output=True,
                                          text=True, timeout=10)
                self.assertNotEqual(finished.returncode, 0)
        original, _ = self.render("normal", 44100, "do-not-overwrite.wav")
        before = original.read_bytes()
        finished = subprocess.run([binary, "--output", str(original)],
                                  capture_output=True, text=True, timeout=10)
        self.assertEqual(finished.returncode, 2)
        self.assertIn("will not overwrite", finished.stderr)
        self.assertEqual(original.read_bytes(), before)
        dangling = self.directory / "dangling.wav"
        try:
            dangling.symlink_to(self.directory / "missing-target.wav")
        except (NotImplementedError, OSError):
            return  # Symlinks may be disabled, especially on Windows.
        finished = subprocess.run([binary, "--output", str(dangling)],
                                  capture_output=True, text=True, timeout=10)
        self.assertEqual(finished.returncode, 2)
        self.assertTrue(dangling.is_symlink())
        self.assertFalse(dangling.exists())


if __name__ == "__main__":
    unittest.main()
