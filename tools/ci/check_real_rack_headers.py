#!/usr/bin/env python3
"""Syntax-check original modules against the *pinned, real* Rack C++ API.

This is a Linux HEADLESS compilation check, NOT a Rack/Cardinal link, GUI
build, plugin ABI check, audio-host test, or proof of a releasable binary.
Dependencies are supplied as exact Gitlink checkouts; this tool never fetches
submodules or installs packages. See docs/CI.md for narrow setup commands.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = ROOT / "plugins" / "ModularSynth" / "src"
MODULES = ("MorphVCO", "StateFilter", "Macro8", "StereoEcho", "ClockedLFO")
RACK_SUBMODULE_HEADERS = {
    "dep/glfw": "include/GLFW/glfw3.h",
    "dep/nanosvg": "src/nanosvg.h",
    "dep/oui-blendish": "blendish.h",
    "dep/pffft": "pffft.h",
    "dep/simde": "simde/x86/sse4.2.h",
    "dep/speexdsp": "include/speex/speex_resampler.h",
}
SETUP = (
    "Initialize only the required pinned Gitlinks:\n"
    "  git submodule update --init --depth 1 src/Rack dpf\n"
    "  git -C src/Rack submodule update --init --depth 1 "
    "dep/glfw dep/nanosvg dep/oui-blendish dep/pffft dep/simde dep/speexdsp\n"
    "Install libjansson-dev, or pass --jansson-include PATH to its unpacked headers."
)


class PreflightError(Exception):
    """Required real SDK source, header, or commit is unavailable."""


def git_output(working_dir: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(working_dir), *args], capture_output=True,
        text=True, check=False,
    )
    if result.returncode:
        raise PreflightError(
            f"Cannot inspect Git checkout {working_dir}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def parse_gitlink(tree_entry: str, path: str) -> str:
    """Require an exact Git mode 160000 entry, never a branch or tag name."""
    match = re.fullmatch(r"160000 commit ([0-9a-f]{40})\t" + re.escape(path), tree_entry)
    if match is None:
        raise PreflightError(f"Pinned Gitlink missing for {path!r}: {tree_entry!r}")
    return match.group(1)


def check_pinned(parent: Path, child: Path, relative_path: str) -> None:
    expected = parse_gitlink(git_output(parent, "ls-tree", "HEAD", "--", relative_path), relative_path)
    if not child.is_dir() or not (child / ".git").exists():
        # Git worktrees/submodules can have a .git *file*; Path.exists covers both.
        raise PreflightError(f"Uninitialized pinned submodule {relative_path}: {child}")
    actual = git_output(child, "rev-parse", "HEAD")
    if actual != expected:
        raise PreflightError(
            f"Wrong {relative_path} revision: actual {actual}, pinned {expected}"
        )


def require_header(path: Path) -> None:
    if not path.is_file():
        raise PreflightError(f"Required real dependency header missing: {path}")


def render_linux_speex_types(template: str) -> str:
    """Generate only the platform substitutions from SpeexDSP's pinned .in.

    The generated header lives in a Python TemporaryDirectory, never the repo.
    stdint.h provides exact-width int16_t/int32_t on supported Linux systems.
    """
    replacements = {
        "@INCLUDE_STDINT@": "#include <stdint.h>",
        "@SIZE16@": "int16_t",
        "@USIZE16@": "uint16_t",
        "@SIZE32@": "int32_t",
        "@USIZE32@": "uint32_t",
    }
    for marker, value in replacements.items():
        if template.count(marker) != 1:
            raise PreflightError(f"Unexpected pinned SpeexDSP template marker {marker}")
        template = template.replace(marker, value)
    if re.search(r"@[A-Z_0-9]+@", template):
        raise PreflightError("Unexpected unexpanded SpeexDSP configure marker")
    return template


def check_dependencies(rack: Path, dpf: Path, jansson: Path) -> None:
    if sys.platform != "linux":
        raise PreflightError("This narrow real-Rack HEADLESS preflight supports Linux only")
    if shutil.which("git") is None:
        raise PreflightError("git is required to validate exact SDK Gitlink revisions")

    check_pinned(ROOT, rack, "src/Rack")
    check_pinned(ROOT, dpf, "dpf")

    require_header(rack / "include" / "rack.hpp")
    require_header(dpf / "dgl" / "src" / "nanovg" / "nanovg.h")
    require_header(dpf / "distrho" / "DistrhoUtils.hpp")
    require_header(jansson / "jansson.h")
    require_header(jansson / "jansson_config.h")
    for submodule, header in RACK_SUBMODULE_HEADERS.items():
        check_pinned(rack, rack / submodule, submodule)
        require_header(rack / submodule / header)
    require_header(rack / "dep" / "speexdsp" / "include" / "speex" / "speexdsp_config_types.h.in")


def compiler_flags(rack: Path, dpf: Path, jansson: Path, temp_types: Path) -> list[str]:
    """Mirror the relevant Cardinal Linux HEADLESS module build definitions."""
    include_dirs = (
        jansson,
        temp_types,  # pinned SpeexDSP generated config types, not a fake Rack API
        ROOT / "include", ROOT / "include" / "simd-compat",
        ROOT / "src", rack / "include", rack / "include" / "dsp",
        rack / "dep" / "simde", rack / "dep" / "include",
        rack / "dep" / "filesystem" / "include",
        rack / "dep" / "fuzzysearchdatabase" / "src",
        rack / "dep" / "glfw" / "include",
        rack / "dep" / "nanosvg" / "src",
        rack / "dep" / "oui-blendish",
        rack / "dep" / "pffft",
        rack / "dep" / "speexdsp" / "include",
        rack / "dep" / "tinyexpr",
        dpf / "dgl" / "src" / "nanovg", dpf / "distrho",
    )
    flags = [
        "-std=gnu++17", "-fsyntax-only", "-pthread",
        "-DHEADLESS", "-DARCH_LIN", "-DUSING_CARDINAL_NOT_RACK",
        "-DpluginInstance=pluginInstance__ModularSynth",
        "-DSIMDE_ACCURACY_PREFERENCE=0", "-DSIMDE_FAST_CONVERSION_RANGE",
        "-DSIMDE_FAST_MATH", "-DSIMDE_FAST_NANS", "-DSIMDE_FAST_ROUND_MODE",
        "-DSIMDE_FAST_ROUND_TIES", "-DZSTDLIB_VISIBILITY=",
        "-fno-finite-math-only", "-fno-strict-aliasing",
    ]
    for directory in include_dirs:
        flags.extend(("-I", str(directory)))
    return flags


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rack-root", type=Path, default=ROOT / "src" / "Rack")
    parser.add_argument("--dpf-root", type=Path, default=ROOT / "dpf")
    parser.add_argument("--jansson-include", type=Path, default=Path("/usr/include"))
    parser.add_argument("--compiler", default="c++")
    parser.add_argument("--preflight-only", action="store_true", help="verify pinned SDK headers; skip C++ parsing")
    args = parser.parse_args()

    try:
        rack, dpf, jansson = (p.resolve() for p in (
            args.rack_root, args.dpf_root, args.jansson_include,
        ))
        check_dependencies(rack, dpf, jansson)
        if args.preflight_only:
            print("PASS: real pinned Rack/DPF/Jansson headers preflight (no compilation)")
            return 0
        compiler = shutil.which(args.compiler)
        if compiler is None:
            raise PreflightError(f"C++ compiler not found: {args.compiler}")
        template = (rack / "dep/speexdsp/include/speex/speexdsp_config_types.h.in").read_text()
        with tempfile.TemporaryDirectory(prefix="modular-real-rack-types-") as temporary:
            types = Path(temporary)
            (types / "speexdsp_config_types.h").write_text(render_linux_speex_types(template))
            flags = compiler_flags(rack, dpf, jansson, types)
            for module in MODULES:
                source = MODULE_DIR / f"{module}.cpp"
                completed = subprocess.run(
                    [compiler, *flags, str(source)], cwd=ROOT, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
                )
                if completed.returncode:
                    print(f"FAIL: {module} (real pinned Rack headers)\n{completed.stdout}", file=sys.stderr)
                    return 1
                print(f"PASS: {module} (real pinned Rack headers)")
        print("PASS: 5/5 original HEADLESS translation units; syntax only, no link/host test")
        return 0
    except (PreflightError, OSError) as exc:
        print(f"Real Rack header preflight unavailable: {exc}\n\n{SETUP}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
