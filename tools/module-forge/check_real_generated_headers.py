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
    # Keep the default sine and effect starters; compile all opt-in
    # polyBLEP/polyBLAMP waveforms (including PWM control ports) against real API.
    ("ForgeRealOsc", "Forge Real Osc", "oscillator", "sine"),
    ("ForgeRealSaw", "Forge Real Saw", "oscillator", "saw"),
    ("ForgeRealPulse", "Forge Real Pulse", "oscillator", "pulse"),
    ("ForgeRealPWM", "Forge Real PWM", "oscillator", "pwm"),
    ("ForgeRealTriangle", "Forge Real Triangle", "oscillator", "triangle"),
    ("ForgeRealLP", "Forge Real LP", "effect", "sine"),
)


def generate_starters(directory: Path) -> list[Path]:
    """Generate fresh modules; reject any missing or tampered output."""
    paths = []
    for slug, name, kind, waveform in STARTERS:
        folder = generate(slug, name, directory, kind=kind, waveform=waveform)
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
    # The generated source lives in a temp directory. Unlike an installed
    # plugin source, it cannot find our adjacent collection plugin.hpp first.
    # Rack also has include/plugin.hpp; -iquote takes precedence over all
    # ordinary SDK -I directories for quoted includes, mirroring the
    # production source-local header resolution without a test shim.
    return [
        [compiler, "-iquote", str(COLLECTION), *flags,
         "-I", str(source.parent), str(source)]
        for source in sources
    ]


def dialect_flags(flags: list[str], dialect: str) -> list[str]:
    """Select one generated-module dialect from exactly one known SDK standard.

    The shared genuine-Rack checker may default to Cardinal's C++11 or
    C++17. Reject missing, duplicate, or unknown standards; otherwise swap
    only that single -std option, retaining every pinned include/definition.
    """
    if dialect not in ("gnu++11", "gnu++17"):
        raise sdk.PreflightError(f"unsupported generated module dialect: {dialect}")
    standards = [flag for flag in flags if flag.startswith("-std=")]
    if len(standards) != 1 or standards[0] not in ("-std=gnu++11", "-std=gnu++17"):
        raise sdk.PreflightError(f"unexpected shared SDK dialect flags: {standards}")
    return [f"-std={dialect}" if flag == standards[0] else flag for flag in flags]


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
            for dialect in ("gnu++11", "gnu++17"):
                commands = syntax_commands(compiler, dialect_flags(flags, dialect), sources)
                for source, command in zip(sources, commands):
                    result = subprocess.run(
                        command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, check=False, timeout=120,
                    )
                    if result.returncode:
                        print(f"FAIL: generated {source.stem} ({dialect}) against "
                              f"pinned real Rack headers\n{result.stdout}", file=sys.stderr)
                        return 1
                    print(f"PASS: generated {source.stem} ({dialect}, real pinned Rack headers)")

        print(f"PASS: {len(STARTERS) * 2}/{len(STARTERS) * 2} generated HEADLESS "
              "translation units across C++11/C++17; syntax-only, "
              "no link/GUI/host audio")
        return 0
    except (sdk.PreflightError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"Generated real Rack header preflight unavailable: {exc}\n\n"
              f"{sdk.SETUP}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
