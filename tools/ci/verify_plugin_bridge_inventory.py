#!/usr/bin/env python3
"""Fail-closed inventory gate for the Ubuntu Cardinal plugin host-smoke job.

The subsequent Carla tests actually load these exact plugin formats under
Valgrind. This preflight checks *targets*, not DAW compatibility, audio output,
Rack model instantiation, state recall, or plugin runtime behavior by itself.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


LV2_VARIANTS = ("CardinalFX", "CardinalSynth")
VST2_VARIANTS = ("CardinalFX", "CardinalSynth")
VST3_VARIANTS = ("Cardinal", "CardinalFX", "CardinalSynth")
LV2_URIS = {
    "CardinalFX": "https://distrho.kx.studio/plugins/cardinal#fx",
    "CardinalSynth": "https://distrho.kx.studio/plugins/cardinal#synth",
}


class HostInventoryError(ValueError):
    """A required compiled plugin host-bridge target is missing or invalid."""


def require_file(path: Path, description: str) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise HostInventoryError(f"missing, empty or symlinked {description}: {path}")


def require_elf64_shared(path: Path, description: str) -> None:
    require_file(path, description)
    with path.open("rb") as stream:
        header = stream.read(64)
    if len(header) < 64 or header[:7] != b"\x7fELF\x02\x01\x01":
        raise HostInventoryError(f"expected Linux x86-64 ELF shared object for {description}: {path}")
    elf_type, elf_machine, elf_version = struct.unpack_from("<HHI", header, 16)
    if elf_type != 3 or elf_machine != 62 or elf_version != 1:
        raise HostInventoryError(f"wrong ELF type, machine or version for {description}: {path}")
    phoff = struct.unpack_from("<Q", header, 32)[0]
    ehsize, phentsize, phnum = struct.unpack_from("<HHH", header, 52)
    if ehsize < 64 or phentsize < 56 or not 0 < phnum <= 1024:
        raise HostInventoryError(f"invalid ELF program header table for {description}: {path}")
    file_size = path.stat().st_size
    if phoff < ehsize or phoff > file_size or phentsize * phnum > file_size - phoff:
        raise HostInventoryError(f"truncated ELF program header table for {description}: {path}")


def verify_targets(bin_dir: Path, lv2_dir: Path) -> tuple[str, ...]:
    checked: list[str] = []
    for variant in LV2_VARIANTS:
        bundle = lv2_dir / f"{variant}.lv2"
        if not bundle.is_dir() or bundle.is_symlink():
            raise HostInventoryError(f"missing LV2 bundle: {bundle}")
        manifest = bundle / "manifest.ttl"
        require_file(manifest, "LV2 manifest")
        try:
            text = manifest.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise HostInventoryError(f"invalid LV2 manifest encoding: {manifest}") from exc
        if f"<{LV2_URIS[variant]}>" not in text:
            raise HostInventoryError(f"LV2 manifest missing the expected URI {LV2_URIS[variant]}: {manifest}")
        require_elf64_shared(bundle / f"{variant}.so", f"LV2 {variant}")
        checked.append(f"LV2 {variant} ({LV2_URIS[variant]})")

    for variant in VST2_VARIANTS:
        binary = bin_dir / "Cardinal.vst" / f"{variant}.so"
        require_elf64_shared(binary, f"VST2 {variant}")
        checked.append(f"VST2 {variant}")

    for variant in VST3_VARIANTS:
        bundle = bin_dir / f"{variant}.vst3"
        if not bundle.is_dir() or bundle.is_symlink():
            raise HostInventoryError(f"missing VST3 bundle: {bundle}")
        binary = bundle / "Contents" / "x86_64-linux" / f"{variant}.so"
        require_elf64_shared(binary, f"VST3 {variant}")
        checked.append(f"VST3 {variant}")
    return tuple(checked)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", type=Path, default=Path("bin"))
    parser.add_argument("--lv2-dir", type=Path, default=Path("/tmp/lv2-path"))
    args = parser.parse_args(argv)
    try:
        targets = verify_targets(args.bin_dir, args.lv2_dir)
    except (HostInventoryError, OSError) as exc:
        print(f"plugin bridge preflight FAILED: {exc}", file=sys.stderr)
        return 1
    for target in targets:
        print(f"plugin bridge target OK: {target}")
    print(f"{len(targets)} required plugin targets present; Carla runtime tests must follow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
