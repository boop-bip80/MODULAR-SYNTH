#!/usr/bin/env python3
"""Explain a failed linked-ELF inventory without relaxing its release gate.

This is a post-failure diagnostic, not proof of registration or host loading.
It distinguishes absent strings from strings present only in non-runtime ELF
bytes (e.g. debug sections, writable data or an appended trailer).
"""

from __future__ import annotations

import argparse
import json
import mmap
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.ci.verify_compiled_collection import (  # noqa: E402
    InventoryError,
    _has_standalone_literal,
    _loadable_elf_ranges,
    manifest_slugs,
    verify_elf_inventory,
)


def inspect_binary(binary: Path, names: tuple[str, ...]) -> dict:
    """Gather bounded evidence from the exact linked ELF selected by the CI gate."""
    result: dict = {"path": str(binary), "exists": binary.is_file()}
    if not binary.is_file():
        result["error"] = "compiled binary is missing"
        return result
    try:
        result["file_size_bytes"] = binary.stat().st_size
        if result["file_size_bytes"] < 64:
            raise InventoryError("compiled binary is smaller than an ELF header")
        with binary.open("rb") as stream:
            with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as image:
                result["elf_magic"] = image[:4] == b"\x7fELF"
                if len(image) >= 20:
                    result["elf_class"] = image[4]
                    result["elf_machine"] = int.from_bytes(image[18:20], "little" if image[5] == 1 else "big")
                # Record a cheap whole-file check even if the runtime range
                # parser cannot validate the ELF. The whole-file result is
                # *never* an alternative passing condition.
                anywhere = {
                    name: _has_standalone_literal(image, name.encode("ascii") + b"\0", 0, len(image))
                    for name in names
                }
                result["standalone_string_anywhere"] = anywhere
                try:
                    ranges = _loadable_elf_ranges(image, binary)
                except InventoryError as exc:
                    result["runtime_elf_error"] = str(exc)
                else:
                    result["readonly_mapped_literal_ranges"] = len(ranges)
                    runtime = {
                        name: any(_has_standalone_literal(image, name.encode("ascii") + b"\0", start, end)
                                  for start, end in ranges)
                        for name in names
                    }
                    result["standalone_runtime_literals"] = runtime
                    result["missing_runtime_identifiers"] = [name for name, present in runtime.items() if not present]
        try:
            verify_elf_inventory(binary, names[1:])
        except InventoryError as exc:
            result["gate_result"] = "failed"
            result["gate_error"] = str(exc)
        else:
            result["gate_result"] = "passed"
    except (OSError, InventoryError) as exc:
        result["gate_result"] = "failed"
        result["error"] = str(exc)
    return result


def diagnose(binary: Path, manifest: Path, candidates: list[Path]) -> dict:
    result: dict = {
        "schema": "modular-linked-elf-diagnostics-v1",
        "warning": "Diagnostic only: matching ELF string literals do not prove registration, plugin loadability or audio output.",
        "primary_binary": str(binary),
    }
    try:
        slugs = manifest_slugs(manifest)
    except InventoryError as exc:
        result["manifest_error"] = str(exc)
        return result
    names = ("ModularSynth", *slugs)
    result["required_identifiers"] = list(names)
    result["binaries"] = [inspect_binary(path, names) for path in (binary, *candidates)]
    result["primary_gate_passed"] = result["binaries"][0].get("gate_result") == "passed"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=REPO / "plugins/ModularSynth/plugin.json")
    parser.add_argument("--candidate", action="append", type=Path, default=[],
                        help="Additional linked ELF binary (informational only)")
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = diagnose(args.binary, args.manifest, args.candidate)
    # Avoid creating an accidental path outside the designated output directory
    # when this script is used in Actions with a fixed safe filename.
    args.json_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    # Intentional: the original verifier remains the release-failing gate;
    # diagnostic collection should run and upload even after that failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
