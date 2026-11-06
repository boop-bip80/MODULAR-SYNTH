#!/usr/bin/env python3
"""Fail-closed inventory of ModularSynth modules actually exercised by Cardinal.

Run after a successful ``bin/Cardinal selftest`` compiled with
``DPF_RUNTIME_TESTING``. This checks runtime registration and successful module
and widget creation up to engine insertion; it does not measure DSP quality or
prove that every LV2 variant has been loaded by a DAW.
"""
from __future__ import annotations

import argparse
from collections import Counter
import re
import sys
from pathlib import Path

from verify_compiled_collection import InventoryError, REPO, manifest_slugs


# CardinalUI.cpp writes these records only while iterating real registered
# rack::plugin::plugins and creating each corresponding runtime module/widget.
# Anchoring on the debug marker avoids matching a source snippet or prose.
EVENT = re.compile(
    r"^\s*>+\s+(LOADING module|ADDING TO ENGINE)\s+ModularSynth\s*:\s*(\S+)\s*$"
)
VALGRIND_ERRORS = re.compile(r"\bERROR SUMMARY:\s*(\d+)\s+errors?\b")
SELFTEST_FAILURE = re.compile(r"\b(?:assertion failed|assert failed|fatal error)\b", re.I)


def verify_runtime_inventory(log: Path, slugs: tuple[str, ...]) -> None:
    try:
        lines = log.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise InventoryError(f"cannot read Cardinal selftest log {log}: {exc}") from exc

    expected = set(slugs)
    loaded: Counter[str] = Counter()
    added: Counter[str] = Counter()
    for line_number, line in enumerate(lines, start=1):
        if match := VALGRIND_ERRORS.search(line):
            if int(match.group(1)):
                raise InventoryError(f"selftest reports Valgrind errors at line {line_number}")
        if SELFTEST_FAILURE.search(line):
            raise InventoryError(f"selftest reports a failure at line {line_number}")
        match = EVENT.fullmatch(line)
        if not match:
            continue
        event, slug = match.groups()
        if slug not in expected:
            raise InventoryError(f"unexpected ModularSynth runtime slug {slug!r} at line {line_number}")
        if event == "LOADING module":
            loaded[slug] += 1
            if loaded[slug] != 1:
                raise InventoryError(f"duplicate module load for ModularSynth/{slug}")
        else:
            added[slug] += 1
            if added[slug] != 1:
                raise InventoryError(f"duplicate engine insertion for ModularSynth/{slug}")
            if loaded[slug] != 1:
                raise InventoryError(f"engine insertion before module load for ModularSynth/{slug}")

    missing_load = expected - loaded.keys()
    missing_add = expected - added.keys()
    if missing_load or missing_add:
        details = []
        if missing_load:
            details.append("missing module loads: " + ", ".join(sorted(missing_load)))
        if missing_add:
            details.append("missing engine insertions: " + ", ".join(sorted(missing_add)))
        raise InventoryError("incomplete ModularSynth runtime inventory (" + "; ".join(details) + ")")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest-log", type=Path, required=True,
                        help="Captured stdout/stderr of successful Cardinal selftest")
    parser.add_argument("--manifest", type=Path,
                        default=REPO / "plugins/ModularSynth/plugin.json")
    args = parser.parse_args(argv)
    try:
        slugs = manifest_slugs(args.manifest)
        verify_runtime_inventory(args.selftest_log, slugs)
    except InventoryError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: Cardinal runtime selftest loaded and inserted all {len(slugs)} "
          "manifest-declared ModularSynth modules exactly once")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
