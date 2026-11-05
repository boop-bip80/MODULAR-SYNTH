#!/usr/bin/env python3
"""Fail-closed *offline* verification of a claimed real-host stereo audio capture.

The operator must supply actual plugin, patch, stimulus and two rendered WAVs.
This checks hashes, sample-level audio and a negative control; it does NOT prove
that the files came from the named DAW or that a musician approved the sound.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import wave
from pathlib import Path


SHA = re.compile(r"[0-9a-f]{40}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
MAX_MANIFEST = 64 * 1024
MAX_MIDI = 2 * 1024 * 1024
MAX_AUDIO = 128 * 1024 * 1024
MAX_PLUGIN = 512 * 1024 * 1024
MIN_DURATION = 0.75
MAX_DURATION = 45.0
MIN_RMS = 0.001  # -60 dBFS; this is an explicit smoke-test floor
MIN_STEREO_RMS = 0.00025
MIN_ACTIVE_FRACTION = 0.01
MAX_CLIPPED_FRACTION = 0.01
MIN_CONTROL_RATIO = 4.0  # >=12 dB louder than the no-note/no-input control


class CaptureError(ValueError):
    """A capture package is absent, malformed or fails an acceptance check."""


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for k, v in pairs:
        if k in result:
            raise CaptureError(f"duplicate JSON key: {k}")
        result[k] = v
    return result


def _keys(obj: object, expected: set[str], label: str) -> dict:
    if not isinstance(obj, dict) or set(obj) != expected:
        raise CaptureError(f"{label} must contain exactly {sorted(expected)}")
    return obj


def _file(root: Path, entry: object, limit: int, label: str) -> tuple[Path, str]:
    obj = _keys(entry, {"path", "sha256"}, label)
    rel, expected = obj["path"], obj["sha256"]
    if not isinstance(expected, str) or not HASH.fullmatch(expected):
        raise CaptureError(f"{label}: invalid SHA-256 digest")
    if not isinstance(rel, str) or not rel or "\\" in rel:
        raise CaptureError(f"{label}: invalid relative path")
    fragment = Path(rel)
    if fragment.is_absolute() or any(p in ("..", ".", "") for p in fragment.parts):
        raise CaptureError(f"{label}: path must remain inside evidence directory")
    path = root / fragment
    if path.resolve(strict=False).is_relative_to(root.resolve()) is False:
        raise CaptureError(f"{label}: path escapes evidence directory")
    # Refuse symlinks at any level, including final path, to avoid following a
    # supposedly immutable evidence package into a mutable external location.
    parent = root
    for part in fragment.parts:
        parent = parent / part
        if parent.is_symlink():
            raise CaptureError(f"{label}: evidence path contains a symlink")
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            file_stat = os.fstat(handle.fileno())
            if not stat.S_ISREG(file_stat.st_mode) or not 0 < file_stat.st_size <= limit:
                raise CaptureError(f"{label}: missing, empty or oversized regular file")
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CaptureError(f"{label}: cannot read evidence: {exc}") from exc
    if digest.hexdigest() != expected:
        raise CaptureError(f"{label}: file digest does not match manifest")
    return path, expected


def _vlq(data: bytes, cursor: int, end: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if cursor >= end:
            raise CaptureError("truncated MIDI variable-length quantity")
        b = data[cursor]
        cursor += 1
        value = (value << 7) | (b & 0x7f)
        if b & 0x80 == 0:
            return value, cursor
    raise CaptureError("oversized MIDI variable-length quantity")


def _midi_note_ons(path: Path) -> int:
    data = path.read_bytes()
    if (len(data) < 14 or data[:4] != b"MThd"
            or int.from_bytes(data[4:8], "big") != 6):
        raise CaptureError("MIDI stimulus needs standard six-byte SMF header")
    form = int.from_bytes(data[8:10], "big")
    tracks = int.from_bytes(data[10:12], "big")
    division = int.from_bytes(data[12:14], "big")
    if form not in (0, 1) or not 1 <= tracks <= 64 or not 0 < division < 0x8000:
        raise CaptureError("unsupported MIDI format, track count or timing")
    cursor, notes = 14, 0
    for _ in range(tracks):
        if cursor + 8 > len(data) or data[cursor:cursor + 4] != b"MTrk":
            raise CaptureError("missing or truncated MIDI track")
        size = int.from_bytes(data[cursor + 4:cursor + 8], "big")
        cursor += 8
        end = cursor + size
        if end > len(data):
            raise CaptureError("truncated MIDI track contents")
        running = None
        while cursor < end:
            _, cursor = _vlq(data, cursor, end)
            if cursor >= end:
                raise CaptureError("truncated MIDI event")
            status = data[cursor]
            if status & 0x80:
                cursor += 1
                if 0x80 <= status < 0xf0:
                    running = status
                else:
                    running = None
            elif running is None:
                raise CaptureError("invalid MIDI running status")
            else:
                status = running
            if status == 0xff:
                if cursor >= end:
                    raise CaptureError("truncated MIDI meta-event")
                cursor += 1
                length, cursor = _vlq(data, cursor, end)
                cursor += length
            elif status in (0xf0, 0xf7):
                length, cursor = _vlq(data, cursor, end)
                cursor += length
            elif 0x80 <= status < 0xf0:
                count = 1 if status & 0xf0 in (0xc0, 0xd0) else 2
                if cursor + count > end or any(b & 0x80 for b in data[cursor:cursor + count]):
                    raise CaptureError("invalid MIDI channel message")
                if status & 0xf0 == 0x90 and data[cursor + 1] > 0:
                    notes += 1
                cursor += count
            else:
                raise CaptureError("unsupported MIDI system event")
            if cursor > end:
                raise CaptureError("MIDI event extends past track boundary")
    if cursor != len(data):
        raise CaptureError("trailing data after declared MIDI tracks")
    if notes == 0:
        raise CaptureError("MIDI stimulus has no note-on with positive velocity")
    return notes


def _wave_stats(path: Path) -> dict:
    try:
        with wave.open(str(path), "rb") as stream:
            nch, width, rate, nframes, comp, _ = stream.getparams()
            if nch != 2 or width not in (2, 3, 4) or comp != "NONE":
                raise CaptureError("capture must be uncompressed stereo 16/24/32-bit PCM WAV")
            if not 32000 <= rate <= 192000 or not MIN_DURATION <= nframes / rate <= MAX_DURATION:
                raise CaptureError("capture sample rate or duration outside declared smoke limits")
            width_bits = width * 8
            scale = float(1 << (width_bits - 1))
            squared = [0.0, 0.0]
            peak = [0.0, 0.0]
            active = [0, 0]
            clipped = [0, 0]
            pcm_digest = hashlib.sha256()
            consumed = 0
            while consumed < nframes:
                chunk = stream.readframes(min(8192, nframes - consumed))
                if not chunk or len(chunk) % (nch * width):
                    raise CaptureError("truncated or unaligned PCM frames")
                pcm_digest.update(chunk)
                for i in range(0, len(chunk), width):
                    channel = (i // width) % nch
                    v = int.from_bytes(chunk[i:i + width], "little", signed=True) / scale
                    a = abs(v)
                    squared[channel] += v * v
                    peak[channel] = max(peak[channel], a)
                    active[channel] += a >= 1e-3
                    clipped[channel] += a >= 0.99997
                consumed += len(chunk) // (nch * width)
            if consumed != nframes:
                raise CaptureError("WAV payload has fewer samples than declared")
    except (OSError, EOFError, wave.Error) as exc:
        raise CaptureError(f"cannot parse PCM WAV: {exc}") from exc
    return {
        "sample_rate": rate,
        "frames": nframes,
        "duration_seconds": round(nframes / rate, 6),
        "rms": [math.sqrt(q / nframes) for q in squared],
        "peak": peak,
        "active_fraction": [q / nframes for q in active],
        "clipped_fraction": [q / nframes for q in clipped],
        "pcm_sha256": pcm_digest.hexdigest(),
        "bits_per_sample": width_bits,
    }


def verify(manifest: dict, root: Path, expected_sha: str) -> dict:
    if not SHA.fullmatch(expected_sha):
        raise CaptureError("expected SHA must be exact lowercase forty-character Git commit")
    _keys(manifest, {"schema", "source_sha", "host", "plugin", "patch", "mode", "stimulus", "render", "baseline"}, "manifest")
    if manifest["schema"] != "modular-host-audio-v1" or manifest["source_sha"] != expected_sha:
        raise CaptureError("manifest schema or exact source commit mismatch")
    host = _keys(manifest["host"], {"name", "version", "os", "plugin_format", "capture_method"}, "host")
    for k, v in host.items():
        if not isinstance(v, str) or not 1 <= len(v) <= 160 or any(ord(c) < 32 for c in v):
            raise CaptureError(f"host {k} must be nonempty printable metadata")
    if host["plugin_format"] not in ("LV2", "VST2", "VST3"):
        raise CaptureError("unsupported host plugin format for this capture contract")
    if not host["os"].lower().startswith("linux"):
        raise CaptureError("this acceptance contract currently requires a Linux host")
    mode = manifest["mode"]
    if mode not in ("synth", "effect"):
        raise CaptureError("capture mode must be synth or effect")
    plugin_path, _ = _file(root, manifest["plugin"], MAX_PLUGIN, "plugin binary")
    patch_path, _ = _file(root, manifest["patch"], 4 * 1024 * 1024, "source patch")
    try:
        with plugin_path.open("rb") as handle:
            header = handle.read(64)
        if (len(header) < 20 or header[:4] != b"\x7fELF"
                or header[4] != 2 or header[5] != 1
                or int.from_bytes(header[16:18], "little") != 3
                or int.from_bytes(header[18:20], "little") not in (62, 183, 243)):
            raise CaptureError("plugin evidence is not a supported Linux ELF64 shared object")
        if patch_path.suffix != ".vcv":
            raise CaptureError("source patch must be a saved .vcv file")
        patch = json.loads(patch_path.read_text(encoding="utf-8"), object_pairs_hook=_unique,
                           parse_constant=lambda v: (_ for _ in ()).throw(CaptureError(f"invalid patch number: {v}")))
        if (not isinstance(patch, dict) or not isinstance(patch.get("modules"), list)
                or not patch["modules"] or not isinstance(patch.get("cables"), list)):
            raise CaptureError("source patch needs nonempty modules and a cable list")
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CaptureError(f"plugin or patch evidence is malformed: {exc}") from exc
    stimulus_path, _ = _file(root, manifest["stimulus"], MAX_AUDIO if mode == "effect" else MAX_MIDI, "stimulus")
    rendered_path, _ = _file(root, manifest["render"], MAX_AUDIO, "MIDI/input-on render")
    idle_path, _ = _file(root, manifest["baseline"], MAX_AUDIO, "no-MIDI/no-input render")
    if len({plugin_path, patch_path, stimulus_path, rendered_path, idle_path}) != 5:
        raise CaptureError("plugin, patch, stimulus, active and idle evidence must be different files")
    note_ons = _midi_note_ons(stimulus_path) if mode == "synth" else 0
    rendered = _wave_stats(rendered_path)
    baseline = _wave_stats(idle_path)
    for key in ("sample_rate", "frames", "bits_per_sample"):
        if rendered[key] != baseline[key]:
            raise CaptureError("active and control captures must share sample rate, bit depth and duration")
    if mode == "effect":
        dry = _wave_stats(stimulus_path)
        for key in ("sample_rate", "frames", "bits_per_sample"):
            if rendered[key] != dry[key]:
                raise CaptureError("effect stimulus and wet render must have matched PCM format/duration")
        if min(dry["rms"]) < MIN_STEREO_RMS:
            raise CaptureError("stereo effect input does not contain measurable stimulus on both channels")
        if dry["pcm_sha256"] == rendered["pcm_sha256"]:
            raise CaptureError("effect output exactly copies dry input; no effect processing demonstrated")
    if min(rendered["rms"]) < MIN_STEREO_RMS or max(rendered["rms"]) < MIN_RMS:
        raise CaptureError("active render is silent or missing a stereo channel")
    if min(rendered["active_fraction"]) < MIN_ACTIVE_FRACTION:
        raise CaptureError("active render lacks sustained measurable stereo output")
    if max(rendered["clipped_fraction"]) > MAX_CLIPPED_FRACTION:
        raise CaptureError("active render exhibits persistent hard clipping")
    loudness = math.sqrt(sum(v * v for v in rendered["rms"]) / 2)
    control = math.sqrt(sum(v * v for v in baseline["rms"]) / 2)
    if control * MIN_CONTROL_RATIO >= loudness:
        raise CaptureError("active output is not at least 12 dB above no-input/no-MIDI control")
    return {
        "accepted": True,
        "expected_sha": expected_sha,
        "mode": mode,
        "host_claim": host,
        "midi_note_on_events": note_ons,
        "active_audio": rendered,
        "negative_control_audio": baseline,
        "control_rms_ratio_db": round(20 * math.log10(loudness / max(control, 1e-12)), 2),
        "scope_warning": (
            "Hashes, ELF header and audio samples are verified; plugin loadability and DAW provenance remain unproved/operator-attested. "
            "This does not prove user listening, automation/save-reopen, sound quality or release readiness."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--json", action="store_true", help="print machine-readable acceptance result")
    args = parser.parse_args(argv)
    try:
        if not args.manifest.is_file() or args.manifest.stat().st_size > MAX_MANIFEST:
            raise CaptureError("missing or oversized capture manifest")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"), object_pairs_hook=_unique,
                              parse_constant=lambda v: (_ for _ in ()).throw(CaptureError(f"invalid JSON number: {v}")))
        result = verify(manifest, args.manifest.parent.resolve(), args.expected_sha)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, CaptureError) as exc:
        result = {"accepted": False, "error": str(exc)}
    if args.json:
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        print("PASS: bounded stereo host-capture audio evidence" if result["accepted"]
              else f"FAIL: host audio evidence: {result['error']}")
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
