#!/usr/bin/env python3
"""Check original modules against the *pinned, real* Rack C++ API.

Default mode syntax-checks HEADLESS sources. Optional --link-smoke compiles
real SDK translation units and links a temporary ELF with unresolved host
imports; it is NOT a loadable Rack/Cardinal plugin, GUI/DAW/audio test or
proof of a releasable binary.
Dependencies are supplied as exact Gitlink checkouts; this tool never fetches
submodules or installs packages. See docs/CI.md for narrow setup commands.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = ROOT / "plugins" / "ModularSynth" / "src"
MODULES = ("MorphVCO", "StateFilter", "FoldDrive", "Macro8", "StereoEcho",
           "ClockedLFO", "FMVoice", "ChanceHold", "DualVCA", "SlewGlide",
           "ScaleQuantizer")
# Cardinal's production plugin builds still use gnu++11 on several targets.
# Keep the newer dialect as a second independent compatibility check: a
# successful gnu++17 syntax test alone does not demonstrate production ABI.
CXX_STANDARDS = ("gnu++11", "gnu++17")
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


def compiler_flags(
    rack: Path, dpf: Path, jansson: Path, temp_types: Path,
    standard: str = "gnu++11",
) -> list[str]:
    """Mirror the relevant Cardinal Linux HEADLESS module build definitions."""
    if standard not in CXX_STANDARDS:
        raise PreflightError(f"Unsupported real-Rack C++ dialect: {standard!r}")
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
        f"-std={standard}", "-fsyntax-only", "-pthread",
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



def module_sources(source_dir: Path = MODULE_DIR, modules: tuple[str, ...] = MODULES) -> list[Path]:
    """Collect exactly one source translation unit per registered model."""
    paths = [source_dir / f"{module}.cpp" for module in modules]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise PreflightError(f"Missing first-party wrapper translation units: {', '.join(missing)}")
    return paths


def model_symbol(module: str) -> str:
    """Strong exported Model* symbol for an original Rack slug.

    Model slugs are namespaced by plugin; global C++ symbols are not. Inherited
    AmalgamatedHarmonics also exports modelScaleQuantizer, so the first-party
    pointer must have a distinct identifier despite preserving the patch slug.
    """
    if module == "ScaleQuantizer":
        return "modelModularSynthScaleQuantizer"
    return f"model{module}"


def validate_registration_contract(
    manifest: dict, makefile: str, header: str, loader: str,
    modules: tuple[str, ...] = MODULES,
) -> None:
    """Narrow first-party manifest, compiled-source and static-loader parity.

    The existing repository unit tests additionally parse nested C++ source and
    panels; this is a fail-fast check before compiling expensive SDK objects.
    """
    entries = manifest.get("modules")
    if not isinstance(entries, list):
        raise PreflightError("ModularSynth manifest has no module entries")
    slugs = [entry.get("slug") if isinstance(entry, dict) else None for entry in entries]
    if collections.Counter(slugs) != collections.Counter(modules):
        raise PreflightError(f"First-party manifest mismatch: {slugs!r} versus {modules!r}")

    compiled = re.findall(
        r"(?m)^[ \t]*PLUGIN_FILES[ \t]*\+=[ \t]*ModularSynth/src/"
        r"([A-Za-z][A-Za-z0-9]*)\.cpp[ \t]*$",
        makefile,
    )
    if collections.Counter(compiled) != collections.Counter(modules):
        raise PreflightError(f"First-party compiled-source registry mismatch: {compiled!r}")

    declarations = re.findall(
        r"(?m)^[ \t]*extern[ \t]+(?:rack::)?Model[ \t]*\*[ \t]*"
        r"(model[A-Za-z][A-Za-z0-9]*)[ \t]*;",
        header,
    )
    expected_symbols = [model_symbol(module) for module in modules]
    if collections.Counter(declarations) != collections.Counter(expected_symbols):
        raise PreflightError("First-party model header declarations mismatch")

    function = re.search(
        r"(?ms)^static void initStatic__ModularSynth\(\)[ \t\r\n]*\{(.*?)^\}",
        loader,
    )
    if function is None:
        raise PreflightError("First-party static loader function unavailable")
    registered = re.findall(
        r"\bp[ \t]*->[ \t]*addModel[ \t]*\([ \t]*"
        r"(model[A-Za-z][A-Za-z0-9]*)[ \t]*\)[ \t]*;",
        function.group(1),
    )
    if collections.Counter(registered) != collections.Counter(expected_symbols):
        raise PreflightError(f"First-party static loader registrations mismatch: {registered!r}")
    if len(re.findall(r"(?m)^[ \t]*initStatic__ModularSynth\(\);[ \t]*$", loader)) != 1:
        raise PreflightError("First-party loader invocation must occur exactly once")


def check_registration_contract() -> None:
    collection = ROOT / "plugins" / "ModularSynth"
    try:
        manifest = json.loads((collection / "plugin.json").read_text(encoding="utf-8"))
        makefile = (ROOT / "plugins" / "Makefile").read_text(encoding="utf-8")
        header = (MODULE_DIR / "plugin.hpp").read_text(encoding="utf-8")
        loader = (ROOT / "plugins" / "plugins.cpp").read_text(encoding="utf-8")
    except (OSError, ValueError, TypeError) as exc:
        raise PreflightError(f"Cannot read first-party registration contract: {exc}") from exc
    validate_registration_contract(manifest, makefile, header, loader)


def validate_linked_model_symbols(
    defined_output: str, undefined_output: str, modules: tuple[str, ...] = MODULES,
) -> None:
    """Require one exported strong model pointer per original, no unresolved models.

    Other undefined C++ symbols are expected Rack/host imports in this narrow
    smoke library and are intentionally NOT treated as plugin-link success.
    """
    defined = collections.Counter(
        fields[-1] for line in defined_output.splitlines()
        if (fields := line.split())
    )
    undefined = {
        fields[-1] for line in undefined_output.splitlines()
        if (fields := line.split())
    }
    expected = {model_symbol(module) for module in modules}
    invalid = {symbol: defined[symbol] for symbol in expected if defined[symbol] != 1}
    if invalid:
        raise PreflightError(f"Missing or duplicate linked first-party model definitions: {invalid!r}")
    unresolved = sorted(expected & undefined)
    if unresolved:
        raise PreflightError(f"Unresolved first-party model symbols: {unresolved!r}")


def run_link_smoke(
    compiler: str, flags: list[str], output_dir: Path, standard: str,
) -> None:
    """Compile genuine SDK wrappers and link a temporary ELF with host imports.

    The result is NOT a loadable Cardinal/Rack plugin: no host library, entry
    point, GUI, audio runtime, or ABI is linked. Nothing is published.
    """
    if sys.platform != "linux":
        raise PreflightError("The first-party object-link smoke supports Linux only")
    if [flag for flag in flags if flag.startswith("-std=")] != [f"-std={standard}"]:
        raise PreflightError(f"Link smoke dialect/flags mismatch for {standard}")
    nm = shutil.which("nm")
    if nm is None:
        raise PreflightError("nm (binutils) is required to inspect linked model symbols")

    object_flags = [flag for flag in flags if flag != "-fsyntax-only"]
    object_flags.extend(("-fPIC", "-c"))
    objects: list[Path] = []
    for module, source in zip(MODULES, module_sources(), strict=True):
        output = output_dir / f"{module}.o"
        command = [compiler, *object_flags, str(source), "-o", str(output)]
        result = subprocess.run(
            command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )
        if result.returncode or not output.is_file():
            raise PreflightError(
                f"Cannot compile real-Rack object {module} ({standard}):\n{result.stdout}"
            )
        objects.append(output)
        print(f"PASS: compiled {module} real-Rack HEADLESS object ({standard})")

    library = output_dir / "libModularSynthFirstPartyLinkSmoke.so"
    result = subprocess.run(
        [compiler, "-shared", "-o", str(library), *(str(obj) for obj in objects)],
        cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False,
    )
    if result.returncode or not library.is_file() or library.stat().st_size < 4:
        raise PreflightError(f"Cannot link first-party HEADLESS smoke ELF ({standard}):\n{result.stdout}")
    if library.read_bytes()[:4] != b"\x7fELF":
        raise PreflightError("First-party link smoke did not produce an ELF file")

    results = []
    for selector in ("--defined-only", "--undefined-only"):
        symbols = subprocess.run(
            [nm, "-D", selector, str(library)], cwd=ROOT,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if symbols.returncode:
            raise PreflightError(f"nm {selector} failed: {symbols.stderr}")
        results.append(symbols.stdout)
    validate_linked_model_symbols(*results)
    print(
        f"PASS: {len(objects)} pinned-Rack HEADLESS objects ({standard}) "
        f"linked into one temporary ELF, with {len(MODULES)} defined first-party models; "
        "Rack/host imports intentionally unresolved. NOT a Cardinal plugin."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rack-root", type=Path, default=ROOT / "src" / "Rack")
    parser.add_argument("--dpf-root", type=Path, default=ROOT / "dpf")
    parser.add_argument("--jansson-include", type=Path, default=Path("/usr/include"))
    parser.add_argument("--compiler", default="c++")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight-only", action="store_true", help="verify pinned SDK headers; skip C++ parsing")
    mode.add_argument(
        "--link-smoke", action="store_true",
        help="compile all first-party real-Rack HEADLESS objects and link a temporary ELF (NOT a host plugin)",
    )
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
            if args.link_smoke:
                check_registration_contract()
                for standard in CXX_STANDARDS:
                    objects = types / standard
                    objects.mkdir()
                    flags = compiler_flags(rack, dpf, jansson, types, standard)
                    run_link_smoke(compiler, flags, objects, standard)
                print(
                    f"PASS: {len(MODULES)} originals linked separately under "
                    f"both {', '.join(CXX_STANDARDS)}; temporary ELF only, not a host plugin"
                )
                return 0
            for standard in CXX_STANDARDS:
                flags = compiler_flags(rack, dpf, jansson, types, standard)
                for module in MODULES:
                    source = MODULE_DIR / f"{module}.cpp"
                    completed = subprocess.run(
                        [compiler, *flags, str(source)], cwd=ROOT, text=True,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
                    )
                    if completed.returncode:
                        print(
                            f"FAIL: {module} ({standard}; real pinned Rack headers)\n"
                            f"{completed.stdout}", file=sys.stderr,
                        )
                        return 1
                    print(f"PASS: {module} ({standard}; real pinned Rack headers)")
        print(
            f"PASS: {len(MODULES)} original HEADLESS translation units under "
            f"both {', '.join(CXX_STANDARDS)}; syntax only, no link/host test"
        )
        return 0
    except (PreflightError, OSError) as exc:
        print(f"Real Rack header preflight unavailable: {exc}\n\n{SETUP}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
