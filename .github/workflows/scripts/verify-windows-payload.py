#!/usr/bin/env python3
"""Inspect Windows release payloads before publishing a GitHub tag.

This is an archive/PE-architecture integrity gate, not a DAW load test,
installer execution test, or verification of first-party Rack registration.
"""

from __future__ import annotations

import argparse
import stat
import struct
import sys
import zipfile
from pathlib import Path


class ReleasePayloadError(ValueError):
    """A required release artifact is missing, malformed or inconsistent."""


MACHINES = {"win32": 0x014C, "win64": 0x8664}
VST3_MODULES = ("Cardinal", "CardinalFX", "CardinalSynth")


def _machine_from_pe(head: bytes, label: str) -> int:
    """Read COFF Machine from a bounded PE header, ignoring a large body."""
    if len(head) < 64 or head[:2] != b"MZ":
        raise ReleasePayloadError(f"{label}: missing DOS/PE executable header")
    pe_offset = struct.unpack_from("<I", head, 0x3C)[0]
    if pe_offset < 0x40 or pe_offset > 1024 * 1024:
        raise ReleasePayloadError(f"{label}: invalid PE header offset")
    if len(head) < pe_offset + 6 or head[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise ReleasePayloadError(f"{label}: missing PE signature")
    if len(head) < pe_offset + 24:
        raise ReleasePayloadError(f"{label}: truncated COFF header")
    machine, sections = struct.unpack_from("<HH", head, pe_offset + 4)
    optional_size = struct.unpack_from("<H", head, pe_offset + 20)[0]
    if not 1 <= sections <= 96 or optional_size < 96:
        raise ReleasePayloadError(f"{label}: invalid PE section or optional header")
    optional_offset = pe_offset + 24
    if len(head) < optional_offset + optional_size + 40 * sections:
        raise ReleasePayloadError(f"{label}: truncated PE optional/section headers")
    magic = struct.unpack_from("<H", head, optional_offset)[0]
    if (machine, magic) not in ((MACHINES["win32"], 0x10B),
                                (MACHINES["win64"], 0x20B)):
        raise ReleasePayloadError(f"{label}: invalid PE machine/optional-header pairing")
    return machine


def _check_machine(head: bytes, label: str, target: str) -> None:
    actual = _machine_from_pe(head, label)
    expected = MACHINES[target]
    if actual != expected:
        raise ReleasePayloadError(
            f"{label}: machine 0x{actual:04x} does not match {target} "
            f"(0x{expected:04x})")


def _read_pe_header(stream, label: str, target: str) -> None:
    # PE signature is only at e_lfanew. Read a bounded prefix; never load
    # multi-hundred-megabyte installers or plug-in binaries into memory.
    _check_machine(stream.read(1024 * 1024 + 6), label, target)


def verify_payload(archive: Path, installer: Path, target: str) -> None:
    if target not in MACHINES:
        raise ReleasePayloadError(f"invalid Windows target {target!r}")
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size == 0:
        raise ReleasePayloadError(f"missing, empty or linked ZIP: {archive}")
    if installer.is_symlink() or not installer.is_file() or installer.stat().st_size == 0:
        raise ReleasePayloadError(f"missing, empty or linked installer: {installer}")
    with installer.open("rb") as stream:
        _read_pe_header(stream, str(installer), target)

    archdir = "x86-win" if target == "win32" else "x86_64-win"
    required_pe = {
        "CardinalJACK.exe", "CardinalNative.exe",
        *(f"{name}.vst3/Contents/{archdir}/{name}.vst3" for name in VST3_MODULES),
        "Cardinal.clap/CardinalFX.clap", "Cardinal.clap/CardinalSynth.clap",
    }
    required_metadata = {
        "LICENSE", "README.md",
        *(f"{name}.lv2/manifest.ttl" for name in VST3_MODULES),
    }
    try:
        with zipfile.ZipFile(archive) as zf:
            names = set()
            for info in zf.infolist():
                components = info.filename.split("/")
                if info.is_dir():
                    components.pop()  # ZIP directory names terminate in '/'.
                if (info.filename.startswith("/") or "\\" in info.filename
                        or ":" in info.filename
                        or any(part in ("", ".", "..") for part in components)):
                    raise ReleasePayloadError(f"unsafe ZIP member: {info.filename!r}")
                # A ZIP symlink can point outside the archive even when the
                # member name itself has no traversal components.
                if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                    raise ReleasePayloadError(f"symlink ZIP member: {info.filename!r}")
                if info.filename in names:
                    raise ReleasePayloadError(f"duplicate ZIP member: {info.filename!r}")
                names.add(info.filename)

            missing = (required_pe | required_metadata) - names
            if missing:
                raise ReleasePayloadError(
                    "ZIP missing required release payload: " + ", ".join(sorted(missing)))
            for name in sorted(required_pe | required_metadata):
                info = zf.getinfo(name)
                if info.is_dir() or info.file_size == 0:
                    raise ReleasePayloadError(f"ZIP member is empty or directory: {name}")

            # zipfile validates the CRC of *every* archived member, rather
            # than trusting a nonempty archive and unverified central index.
            if corrupt := zf.testzip():
                raise ReleasePayloadError(f"ZIP member CRC/decompression failed: {corrupt}")

            for name in sorted(required_pe):
                with zf.open(name) as stream:
                    _read_pe_header(stream, name, target)
    except (OSError, EOFError, zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError) as exc:
        raise ReleasePayloadError(f"invalid Windows ZIP {archive}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--target", choices=tuple(MACHINES), required=True)
    args = parser.parse_args(argv)
    try:
        verify_payload(args.zip, args.installer, args.target)
    except ReleasePayloadError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: {args.target} ZIP CRC, plug-in inventory and PE architecture "
          "match installer (not DAW loadability proof)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
