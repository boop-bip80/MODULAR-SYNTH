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
    """Return file-backed, read-only literal ranges of a linked ELF image.

    A NUL-terminated identifier in an ELF section that is never mapped into
    memory (such as a debug section or an appended trailer) is not evidence of
    a model identifier in the compiled runtime image. Writable data and ELF
    note/metadata sections are not acceptable substitutes for string literals.
    Section headers are optional for a valid executable; if present, they
    narrow the ranges further to allocated, read-only PROGBITS sections.
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
    # Reject impossible ELF class/machine combinations as well as the generic
    # EM_NONE. These are the Linux targets built by this repository.
    machines = {3: (1,), 40: (1,), 62: (2,), 183: (2,), 243: (1, 2)}
    if elf_machine not in machines or bits not in machines[elf_machine] or version != 1:
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
    saw_load = False
    for index in range(entry_count):
        offset = table_offset + index * entry_size
        segment_type = struct.unpack_from(endian + "I", image, offset)[0]
        if segment_type != 1:  # PT_LOAD: file bytes mapped into the process.
            continue
        saw_load = True
        if bits == 2:
            flags = struct.unpack_from(endian + "I", image, offset + 4)[0]
            file_offset = struct.unpack_from(endian + "Q", image, offset + 8)[0]
            address = struct.unpack_from(endian + "Q", image, offset + 16)[0]
            file_size, memory_size = struct.unpack_from(endian + "QQ", image, offset + 32)
            alignment = struct.unpack_from(endian + "Q", image, offset + 48)[0]
        else:
            file_offset = struct.unpack_from(endian + "I", image, offset + 4)[0]
            address = struct.unpack_from(endian + "I", image, offset + 8)[0]
            file_size, memory_size = struct.unpack_from(endian + "II", image, offset + 16)
            flags, alignment = struct.unpack_from(endian + "II", image, offset + 24)
        if (file_size > memory_size or file_offset > len(image)
                or file_size > len(image) - file_offset):
            raise InventoryError(f"invalid file-backed ELF load segment: {binary}")
        if (alignment not in (0, 1) and
                (alignment & (alignment - 1) or file_offset % alignment != address % alignment)):
            raise InventoryError(f"invalid ELF load segment alignment: {binary}")
        # ELF reserves upper permission bits for OS/architecture extensions;
        # only the standard low PF_R/PF_W bits determine literal eligibility.
        if file_size and flags & 4 and not flags & 2:  # PF_R and not PF_W.
            ranges.append((file_offset, file_offset + file_size))
    if not saw_load:
        raise InventoryError(f"ELF has no file-backed load segments: {binary}")
    if not ranges:
        raise InventoryError(f"ELF has no read-only file-backed load segments: {binary}")

    if bits == 2:
        section_offset = struct.unpack_from(endian + "Q", image, 40)[0]
        section_entry_size, section_count = struct.unpack_from(endian + "HH", image, 58)
        minimum_section_size = 64
    else:
        section_offset = struct.unpack_from(endian + "I", image, 32)[0]
        section_entry_size, section_count = struct.unpack_from(endian + "HH", image, 46)
        minimum_section_size = 40
    if section_count:
        if (not section_offset or section_entry_size < minimum_section_size or
                section_offset > len(image) or
                section_count * section_entry_size > len(image) - section_offset):
            raise InventoryError(f"invalid ELF section header table: {binary}")
        literal_sections: list[tuple[int, int]] = []
        for index in range(section_count):
            offset = section_offset + index * section_entry_size
            section_type = struct.unpack_from(endian + "I", image, offset + 4)[0]
            if bits == 2:
                flags = struct.unpack_from(endian + "Q", image, offset + 8)[0]
                start, size = struct.unpack_from(endian + "QQ", image, offset + 24)
            else:
                flags = struct.unpack_from(endian + "I", image, offset + 8)[0]
                start, size = struct.unpack_from(endian + "II", image, offset + 16)
            # SHT_PROGBITS, SHF_ALLOC, !SHF_WRITE, !SHF_EXECINSTR.
            # This excludes .note, .comment, and executable instructions.
            if section_type != 1 or not flags & 2 or flags & (1 | 4) or not size:
                continue
            if start > len(image) or size > len(image) - start:
                raise InventoryError(f"invalid ELF allocated literal section: {binary}")
            literal_sections.append((start, start + size))
        ranges = [
            (max(load_start, section_start), min(load_end, section_end))
            for load_start, load_end in ranges
            for section_start, section_end in literal_sections
            if max(load_start, section_start) < min(load_end, section_end)
        ]
        if not ranges:
            raise InventoryError(f"ELF has no read-only allocated literal sections: {binary}")
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
                # require standalone NUL-terminated literals within mapped,
                # nonwritable bytes. A suffix of "NotFMVoice\0" is not evidence
                # of an independent "FMVoice\0" literal. String presence still
                # does not prove that a model was registered or instantiated.
                markers = ("ModularSynth", *slugs)
                absent = [
                    marker for marker in markers
                    if not any(
                        _has_standalone_literal(image, marker.encode("ascii") + b"\0", start, end)
                        for start, end in ranges
                    )
                ]
                if absent:
                    raise InventoryError(
                        f"compiled host {binary} lacks first-party model identifiers: "
                        + ", ".join(absent))
    except OSError as exc:
        raise InventoryError(f"cannot inspect compiled host {binary}: {exc}") from exc


def _has_standalone_literal(image: mmap.mmap, marker: bytes, start: int, end: int) -> bool:
    offset = image.find(marker, start, end)
    while offset >= 0:
        if offset == 0 or image[offset - 1] not in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_":
            return True
        offset = image.find(marker, offset + 1, end)
    return False


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
    print(f"PASS: linked ELF read-only runtime literals contain ModularSynth and {len(slugs)} "
          "manifest-declared standalone identifier strings "
          "(not proof of model registration or host loadability)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
