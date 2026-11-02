#!/usr/bin/env python3
"""Syntax-check fresh Module Forge starters against pinned, real Rack headers.

This is a Linux HEADLESS *source* compatibility gate. It does not link a
Cardinal plugin, load its GUI, render host audio, or prove DAW compatibility.
In particular, tests/rack_stub is deliberately never on the include path.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from module_forge import check_module, generate


ROOT = Path(__file__).resolve().parents[2]
COLLECTION = ROOT / "plugins" / "ModularSynth" / "src"
sys.path.insert(0, str(ROOT / "tools" / "ci"))
import check_real_rack_headers as sdk  # noqa: E402 -- shared pinned SDK preflight


STARTERS = (
    ("ForgeRealOsc", "Forge Real Osc", "oscillator"),
    ("ForgeRealLP", "Forge Real LP", "effect"),
)


def generate_starters(directory: Path) -> list[Path]:
    """Generate fresh modules; reject any missing or tampered output."""
    paths = []
    for slug, name, kind in STARTERS:
        folder = generate(slug, name, directory, kind=kind)
        problems = check_module(folder)
        if problems:
            raise sdk.PreflightError(f"Generated {slug} invalid: {'; '.join(problems)}")
        paths.append(folder / f"{slug}.cpp")
    return paths


def syntax_commands(compiler: str, flags: list[str], sources: list[Path]) -> list[list[str]]:
    """Build exact translation-unit commands, using the real API include flags."""
    if not any(flag == "-DHEADLESS" for flag in flags):
        raise sdk.PreflightError("Pinned Rack compiler flags must use HEADLESS")
    if "-fsyntax-only" not in flags:
        raise sdk.PreflightError("Pinned Rack compiler flags must use syntax-only mode")
    if any("rack_stub" in flag for flag in flags):
        raise sdk.PreflightError("Test-only Rack shim is forbidden in real-header gate")
    return [
        [compiler, *flags, "-I", str(COLLECTION), "-I", str(source.parent), str(source)]
        for source in sources
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rack-root", type=Path, default=ROOT / "src" / "Rack")
    parser.add_argument("--dpf-root", type=Path, default=ROOT / "dpf")
    parser.add_argument("--jansson-include", type=Path, default=Path("/usr/include"))
    parser.add_argument("--compiler", default="c++")
    parser.add_argument("--preflight-only", action="store_true",
                        help="only check pinned SDK dependencies (no C++ compilation)")
    args = parser.parse_args(argv)

    try:
        rack, dpf, jansson = (
            path.resolve() for path in (args.rack_root, args.dpf_root, args.jansson_include)
        )
        sdk.check_dependencies(rack, dpf, jansson)
        if args.preflight_only:
            print("PASS: pinned real Rack/DPF/Jansson preflight (no compilation)")
            return 0
        compiler = shutil.which(args.compiler)
        if compiler is None:
            raise sdk.PreflightError(f"C++ compiler not found: {args.compiler}")

        template = (rack / "dep/speexdsp/include/speex/speexdsp_config_types.h.in").read_text()
        with tempfile.TemporaryDirectory(prefix="module-forge-real-rack-") as temp:
            output = Path(temp)
            types = output / "types"
            types.mkdir()
            (types / "speexdsp_config_types.h").write_text(
                sdk.render_linux_speex_types(template), encoding="utf-8"
            )
            sources = generate_starters(output)
            flags = sdk.compiler_flags(rack, dpf, jansson, types)
            for source, command in zip(sources, syntax_commands(compiler, flags, sources)):
                result = subprocess.run(
                    command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, check=False, timeout=120,
                )
                if result.returncode:
                    print(f"FAIL: generated {source.stem} against pinned real Rack headers\n"
                          f"{result.stdout}", file=sys.stderr)
                    return 1
                print(f"PASS: generated {source.stem} (real pinned Rack headers)")

        print(f"PASS: {len(STARTERS)}/{len(STARTERS)} generated HEADLESS translation units; "
              "syntax-only, no link/GUI/host audio")
        return 0
    except (sdk.PreflightError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"Generated real Rack header preflight unavailable: {exc}\n\n"
              f"{sdk.SETUP}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
