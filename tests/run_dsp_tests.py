#!/usr/bin/env python3
"""Discover, compile, and run dependency-free DSP smoke tests.

Only tests/*_dsp_smoke.cpp and tests/*_dsp_test.cpp are standalone entrypoints.
VCV Rack/DPF wrapper tests belong in the full plugin build, not this runner.
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "tests"
PATTERNS = ("*_dsp_smoke.cpp", "*_dsp_test.cpp")
COMPILER_PROFILES = {
    "strict": ("-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror"),
    "production": (
        "-std=c++17", "-O3", "-ffast-math", "-fno-finite-math-only",
        "-Wall", "-Wextra", "-Werror",
    ),
    "aggressive-fastmath": (
        "-std=c++17", "-O3", "-ffast-math", "-Wall", "-Wextra", "-Werror",
    ),
}
COMPILE_TIMEOUT_SECONDS = 120
RUN_TIMEOUT_SECONDS = 30


def discover_tests(directory: Path = TEST_DIR) -> list[Path]:
    """Find explicitly named standalone DSP C++ test entrypoints only."""
    files = {path for pattern in PATTERNS for path in directory.glob(pattern)}
    # Wrapper tests are not standalone and generally need VCV Rack/DPF headers.
    return sorted(
        path for path in files
        if path.is_file()
        and not ({"rack", "wrapper"} & set(path.stem.lower().split("_")))
    )


def compiler_command() -> list[str]:
    compiler = shlex.split(os.environ.get("CXX", "c++"))
    if not compiler or not shutil.which(compiler[0]):
        raise RuntimeError(
            "No C++ compiler found. Set CXX to an available C++17 compiler."
        )
    return compiler


def run_checked(command: list[str], description: str, timeout: int) -> None:
    print(f"\n[{description}] $ {shlex.join(map(str, command))}", flush=True)
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{description}: exceeded {timeout}s timeout") from exc
    except OSError as exc:
        raise RuntimeError(f"{description}: could not execute: {exc}") from exc

    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.returncode < 0:
        raise RuntimeError(
            f"{description}: terminated by signal {-completed.returncode}"
        )
    if completed.returncode != 0:
        raise RuntimeError(f"{description}: failed with exit code {completed.returncode}")


def run_suite(tests: list[Path], compiler: list[str]) -> bool:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="modular-synth-dsp-") as tmp:
        tmp_path = Path(tmp)
        for test in tests:
            for profile, flags in COMPILER_PROFILES.items():
                output = tmp_path / f"{test.stem}-{profile}"
                compile_command = [
                    *compiler, *flags, "-I", str(ROOT),
                    str(test), "-o", str(output),
                ]
                label = f"{test.name} / {profile}"
                try:
                    run_checked(compile_command, f"compile {label}", COMPILE_TIMEOUT_SECONDS)
                    run_checked([str(output)], f"run {label}", RUN_TIMEOUT_SECONDS)
                except RuntimeError as exc:
                    print(f"FAIL: {exc}", file=sys.stderr, flush=True)
                    failures.append(label)

    if failures:
        print(f"\nFAIL: {len(failures)} DSP profile(s): {', '.join(failures)}",
              file=sys.stderr)
        return False
    print(
        f"\nPASS: {len(tests)} standalone DSP test(s) x "
        f"{len(COMPILER_PROFILES)} compiler profiles"
    )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list", action="store_true",
        help="Show discovered standalone tests without compiling",
    )
    args = parser.parse_args(argv)

    tests = discover_tests()
    if not tests:
        print(
            f"No standalone DSP tests found in {TEST_DIR} "
            f"({', '.join(PATTERNS)}).",
            file=sys.stderr,
        )
        return 1

    if args.list:
        for test in tests:
            print(test.relative_to(ROOT))
        return 0

    try:
        return 0 if run_suite(tests, compiler_command()) else 1
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
