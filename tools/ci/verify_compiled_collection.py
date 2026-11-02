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
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ORIGINALS = frozenset({
    "ChanceHold", "ClockedLFO", "FMVoice", "FoldDrive",
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


def verify_elf_inventory(binary: Path, slugs: tuple[str, ...]) -> None:
    try:
        if not binary.is_file() or binary.stat().st_size < 64:
            raise InventoryError(f"missing, empty or truncated compiled host binary: {binary}")
        with binary.open("rb") as stream:
            header = stream.read(64)
            if header[:4] != b"\x7fELF" or header[4] not in (1, 2) or header[5] not in (1, 2):
                raise InventoryError(f"expected a Linux ELF host image: {binary}")
            byteorder = "little" if header[5] == 1 else "big"
            if int.from_bytes(header[16:18], byteorder=byteorder) not in (2, 3):
                raise InventoryError(f"expected linked executable/shared ELF, not an object file: {binary}")
            # mmap avoids making large compiled host images into Python byte arrays.
            with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as image:
                # createModel<T>("Slug") and StaticPluginLoader("ModularSynth")
                # require these NUL-terminated identifiers in the linked host.
                markers = ("ModularSynth", *slugs)
                absent = [marker for marker in markers if image.find(marker.encode("ascii") + b"\0") < 0]
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
    print(f"PASS: linked ELF contains ModularSynth collection and {len(slugs)} "
          "manifest-declared model identifiers (not host loadability)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
