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
# Optional fourth profile; only standalone DSP cores, never Rack wrappers.
SANITIZER_PROFILES = {
    "asan-ubsan": (
        "-std=c++17", "-O1", "-g", "-fno-omit-frame-pointer",
        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
        "-Wall", "-Wextra", "-Werror",
    ),
    "ubsan": (
        "-std=c++17", "-O1", "-g", "-fno-omit-frame-pointer",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-Wall", "-Wextra", "-Werror",
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


def run_checked(
    command: list[str], description: str, timeout: int,
    env: dict[str, str] | None = None,
) -> None:
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
            env=env,
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


def sanitizer_environment(name: str) -> dict[str, str]:
    """Turn sanitizer diagnostics into nonzero test failures."""
    env = os.environ.copy()
    env["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
    if name == "asan-ubsan":
        env["ASAN_OPTIONS"] = "halt_on_error=1:detect_leaks=1"
    return env


def probe_sanitizer(
    compiler: list[str], name: str, workspace: Path,
) -> None:
    """Compile and execute a tiny binary to check runtime support, offline."""
    source = workspace / f"sanitizer-probe-{name}.cpp"
    executable = workspace / f"sanitizer-probe-{name}"
    source.write_text("int main() { return 0; }\n", encoding="utf-8")
    flags = SANITIZER_PROFILES[name]
    run_checked(
        [*compiler, *flags, str(source), "-o", str(executable)],
        f"sanitizer probe compile {name}",
        COMPILE_TIMEOUT_SECONDS,
    )
    # ASan may fail to map shadow memory in constrained runners. Check the
    # runtime before selecting it; real DSP failures must NOT trigger fallback.
    run_checked(
        [str(executable)],
        f"sanitizer probe run {name}",
        RUN_TIMEOUT_SECONDS,
        env=sanitizer_environment(name),
    )


def select_sanitizer_profile(
    compiler: list[str], requested: str, workspace: Path,
) -> tuple[str, tuple[str, ...]]:
    """Prefer ASan+UBSan, fallback to UBSan only when the probe fails."""
    choices = ("asan-ubsan", "ubsan") if requested == "auto" else (requested,)
    for name in choices:
        try:
            probe_sanitizer(compiler, name, workspace)
        except RuntimeError as exc:
            print(f"NOTE: sanitizer {name} unavailable: {exc}", file=sys.stderr)
            continue
        if requested == "auto" and name == "ubsan":
            print("NOTE: ASan+UBSan probe failed; using UBSan-only sanitizer", flush=True)
        print(f"SANITIZER: {name} compile/runtime probe passed", flush=True)
        return name, SANITIZER_PROFILES[name]
    raise RuntimeError(
        f"Requested sanitizer '{requested}' unavailable: no compile/runtime "
        "probe passed; no sanitizer test results can be claimed"
    )


def run_suite(
    tests: list[Path], compiler: list[str], sanitizer: str | None = None,
) -> bool:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="modular-synth-dsp-") as tmp:
        tmp_path = Path(tmp)
        profiles = dict(COMPILER_PROFILES)
        sanitizer_name: str | None = None
        if sanitizer is not None:
            sanitizer_name, flags = select_sanitizer_profile(
                compiler, sanitizer, tmp_path
            )
            profiles[f"sanitizer-{sanitizer_name}"] = flags

        for test in tests:
            for profile, flags in profiles.items():
                output = tmp_path / f"{test.stem}-{profile}"
                compile_command = [
                    *compiler, *flags, "-I", str(ROOT),
                    str(test), "-o", str(output),
                ]
                label = f"{test.name} / {profile}"
                runtime_env = (
                    sanitizer_environment(sanitizer_name)
                    if sanitizer_name and profile == f"sanitizer-{sanitizer_name}"
                    else None
                )
                try:
                    run_checked(compile_command, f"compile {label}", COMPILE_TIMEOUT_SECONDS)
                    run_checked(
                        [str(output)], f"run {label}", RUN_TIMEOUT_SECONDS,
                        env=runtime_env,
                    )
                except RuntimeError as exc:
                    print(f"FAIL: {exc}", file=sys.stderr, flush=True)
                    failures.append(label)

    if failures:
        print(f"\nFAIL: {len(failures)} DSP profile(s): {', '.join(failures)}",
              file=sys.stderr)
        return False
    suffix = f" (sanitizer: {sanitizer_name})" if sanitizer_name else ""
    print(
        f"\nPASS: {len(tests)} standalone DSP test(s) x "
        f"{len(profiles)} compiler profiles{suffix}"
    )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list", action="store_true",
        help="Show discovered standalone tests without compiling",
    )
    parser.add_argument(
        "--sanitize", nargs="?", const="auto", default=None,
        choices=("auto", "asan-ubsan", "ubsan"),
        help=(
            "Add a fourth profile: probe ASan+UBSan then UBSan fallback (auto), "
            "or require one specific sanitizer. Fail if no runtime is available."
        ),
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
        return 0 if run_suite(tests, compiler_command(), sanitizer=args.sanitize) else 1
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
