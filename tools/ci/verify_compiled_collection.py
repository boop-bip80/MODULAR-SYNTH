#!/usr/bin/env python3
"""Narrow compiled-binary inventory gate for the built Cardinal Linux host.

This inspects the final ELF image, not just source registries or a Rack stub.
It cannot prove a module can instantiate, process sound or load in a DAW.
"""
from __future__ import annotations

import argparse
import json
import mmap
import re
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ORIGINALS = frozenset({
    "ChanceHold", "ClockedLFO", "DualVCA", "FMVoice", "FoldDrive",
    "Macro8", "MorphVCO", "StateFilter", "StereoEcho",
})
SLUG = re.compile(r"[A-Z][A-Za-z0-9]{1,39}\Z")


class InventoryError(ValueError):
    """A compiled first-party inventory precondition did not hold."""


def manifest_slugs(path: Path) -> tuple[str, ...]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InventoryError(f"cannot read first-party manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("slug") != "ModularSynth":
        raise InventoryError("first-party plugin.json must have slug ModularSynth")
    entries = manifest.get("modules")
    if not isinstance(entries, list) or not entries:
        raise InventoryError("first-party manifest has no module entries")
    slugs: list[str] = []
    for index, entry in enumerate(entries):
        slug = entry.get("slug") if isinstance(entry, dict) else None
        if not isinstance(slug, str) or not SLUG.fullmatch(slug):
            raise InventoryError(f"invalid module slug in manifest entry {index}: {slug!r}")
        slugs.append(slug)
    if len({slug.casefold() for slug in slugs}) != len(slugs):
        raise InventoryError("first-party manifest contains duplicate module slugs")
    if missing := ORIGINALS.difference(slugs):
        raise InventoryError("manifest is missing original modules: " + ", ".join(sorted(missing)))
    return tuple(slugs)


def _loadable_elf_ranges(image: mmap.mmap, binary: Path) -> tuple[tuple[int, int], ...]:
    """Return file-backed PT_LOAD bytes, excluding ELF debug/trailer data.

    A NUL-terminated identifier in an ELF section that is never mapped into
    memory (such as a debug section or an appended trailer) is not evidence of
    a model identifier in the compiled runtime image.
    """
    if image[:4] != b"\x7fELF" or image[4] not in (1, 2) or image[5] not in (1, 2):
        raise InventoryError(f"expected a Linux ELF host image: {binary}")
    if image[6] != 1:
        raise InventoryError(f"unsupported ELF identification version: {binary}")
    bits = image[4]
    endian = "<" if image[5] == 1 else ">"
    header_size = 64 if bits == 2 else 52
    program_header_size = 56 if bits == 2 else 32
    if len(image) < header_size:
        raise InventoryError(f"truncated ELF header: {binary}")
    elf_type, elf_machine, version = struct.unpack_from(endian + "HHI", image, 16)
    if elf_type not in (2, 3):
        raise InventoryError(f"expected linked executable/shared ELF, not an object file: {binary}")
    if elf_machine == 0 or version != 1:
        raise InventoryError(f"invalid ELF machine or header version: {binary}")
    if bits == 2:
        table_offset = struct.unpack_from(endian + "Q", image, 32)[0]
        declared_header_size, entry_size, entry_count = struct.unpack_from(
            endian + "HHH", image, 52)
    else:
        table_offset = struct.unpack_from(endian + "I", image, 28)[0]
        declared_header_size, entry_size, entry_count = struct.unpack_from(
            endian + "HHH", image, 40)
    if (declared_header_size < header_size or entry_size < program_header_size
            or not 0 < entry_count <= 1024 or table_offset < declared_header_size
            or table_offset + entry_count * entry_size > len(image)):
        raise InventoryError(f"missing or invalid ELF program header table: {binary}")
    ranges: list[tuple[int, int]] = []
    for index in range(entry_count):
        offset = table_offset + index * entry_size
        segment_type = struct.unpack_from(endian + "I", image, offset)[0]
        if segment_type != 1:  # PT_LOAD: file bytes mapped into the process.
            continue
        if bits == 2:
            file_offset = struct.unpack_from(endian + "Q", image, offset + 8)[0]
            file_size, memory_size = struct.unpack_from(endian + "QQ", image, offset + 32)
        else:
            file_offset = struct.unpack_from(endian + "I", image, offset + 4)[0]
            file_size, memory_size = struct.unpack_from(endian + "II", image, offset + 16)
        if (file_size > memory_size or file_offset > len(image)
                or file_size > len(image) - file_offset):
            raise InventoryError(f"invalid file-backed ELF load segment: {binary}")
        if file_size:
            ranges.append((file_offset, file_offset + file_size))
    if not ranges:
        raise InventoryError(f"ELF has no file-backed load segments: {binary}")
    return tuple(ranges)


def verify_elf_inventory(binary: Path, slugs: tuple[str, ...]) -> None:
    try:
        if not binary.is_file() or binary.stat().st_size < 64:
            raise InventoryError(f"missing, empty or truncated compiled host binary: {binary}")
        with binary.open("rb") as stream:
            # mmap avoids making large compiled host images into Python byte arrays.
            with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as image:
                ranges = _loadable_elf_ranges(image, binary)
                # createModel<T>("Slug") and StaticPluginLoader("ModularSynth")
                # require these NUL-terminated strings in loadable image bytes.
                # String presence still does not prove model registration.
                markers = ("ModularSynth", *slugs)
                absent = [
                    marker for marker in markers
                    if not any(
                        image.find(marker.encode("ascii") + b"\0", start, end) >= 0
                        for start, end in ranges
                    )
                ]
                if absent:
                    raise InventoryError(
                        f"compiled host {binary} lacks first-party model identifiers: "
                        + ", ".join(absent))
    except OSError as exc:
        raise InventoryError(f"cannot inspect compiled host {binary}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True,
                        help="Final linked Linux ELF host image (not object or source)")
    parser.add_argument("--manifest", type=Path,
                        default=REPO / "plugins/ModularSynth/plugin.json")
    args = parser.parse_args(argv)
    try:
        slugs = manifest_slugs(args.manifest)
        verify_elf_inventory(args.binary, slugs)
    except InventoryError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: linked ELF PT_LOAD segments contain ModularSynth and {len(slugs)} "
          "manifest-declared identifier strings "
          "(not proof of model registration or host loadability)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
