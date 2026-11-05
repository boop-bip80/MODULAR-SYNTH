#!/usr/bin/env python3
"""Fail-closed source-independent checks of the macOS universal build/package.

This checks bundle architecture and XAR package structure, not signing,
notarization, plug-in loadability, audio, MIDI or DAW host behaviour.
"""
from __future__ import annotations

import argparse
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path


EXPECTED_ARCHES = frozenset({0x01000007, 0x0100000C})  # x86_64, arm64
PACKAGE_COMPONENTS = frozenset({
    "dpf-cardinal-resources.pkg", "dpf-cardinal-jack.pkg",
    "dpf-cardinal-native.pkg", "dpf-cardinal-components.pkg",
    "dpf-cardinal-lv2bundles.pkg", "dpf-cardinal-vst2bundles.pkg",
    "dpf-cardinal-vst3bundles.pkg", "dpf-cardinal-clapbundles.pkg",
})
REQUIRED_BUNDLES = ("app", "component", "lv2", "vst", "vst3", "clap")
REQUIRED_STANDALONES = {
    "Cardinal.app": "Cardinal",
    "CardinalNative.app": "CardinalNative",
}


class VerificationError(ValueError):
    """One of the claimed release properties was not verified."""


def mach_arches(path: Path) -> frozenset[int]:
    """Extract all architectures from an intact universal Mach-O fat header.

    Unknown, thin or truncated files are deliberately rejected by callers.
    """
    try:
        with path.open("rb") as stream:
            header = stream.read(8)
            if len(header) < 8:
                return frozenset()
            magic = header[:4]
            if magic == b"\xca\xfe\xba\xbe":
                order = ">"
                entry_size = 20
            elif magic == b"\xbe\xba\xfe\xca":
                order = "<"
                entry_size = 20
            elif magic == b"\xca\xfe\xba\xbf":
                order = ">"
                entry_size = 32
            elif magic == b"\xbf\xba\xfe\xca":
                order = "<"
                entry_size = 32
            else:
                return frozenset()
            count = struct.unpack(order + "I", header[4:])[0]
            if not 2 <= count <= 16:
                return frozenset()
            entries = stream.read(count * entry_size)
            if len(entries) != count * entry_size:
                return frozenset()
            file_size = path.stat().st_size
            result: set[int] = set()
            ranges: list[tuple[int, int]] = []
            for index in range(count):
                chunk = entries[index * entry_size:(index + 1) * entry_size]
                if entry_size == 20:
                    cpu, _, offset, size, _ = struct.unpack(order + "IIIII", chunk)
                else:
                    cpu, _, offset, size, _, _ = struct.unpack(order + "IIQQII", chunk)
                if size < 32 or offset < 8 + count * entry_size or offset + size > file_size:
                    return frozenset()
                if any(offset < end and offset + size > begin for begin, end in ranges):
                    return frozenset()
                ranges.append((offset, offset + size))
                stream.seek(offset)
                slice_header = stream.read(32)
                if len(slice_header) != 32:
                    return frozenset()
                if slice_header[:4] == b"\xcf\xfa\xed\xfe":
                    slice_cpu = struct.unpack_from("<I", slice_header, 4)[0]
                    filetype = struct.unpack_from("<I", slice_header, 12)[0]
                elif slice_header[:4] == b"\xfe\xed\xfa\xcf":
                    slice_cpu = struct.unpack_from(">I", slice_header, 4)[0]
                    filetype = struct.unpack_from(">I", slice_header, 12)[0]
                else:
                    return frozenset()
                if slice_cpu != cpu or filetype not in (2, 6, 8):  # executable/dylib/bundle
                    return frozenset()
                result.add(cpu)
            return frozenset(result) if len(result) == count else frozenset()
    except OSError:
        return frozenset()


def verify_binaries(bin_dir: Path) -> None:
    if not bin_dir.is_dir() or bin_dir.is_symlink():
        raise VerificationError(f"macOS binary directory missing: {bin_dir}")
    # Info_{JACK,Native}.plist declare these executable names.  A random
    # universal helper inside the app cannot substitute for the actual entry.
    for standalone, executable_name in REQUIRED_STANDALONES.items():
        app = bin_dir / standalone
        if not app.is_dir() or app.is_symlink():
            raise VerificationError(f"required macOS standalone missing: {standalone}")
        executable = app / "Contents" / "MacOS" / executable_name
        if not executable.is_file() or executable.is_symlink() or mach_arches(executable) != EXPECTED_ARCHES:
            raise VerificationError(f"required macOS standalone executable is not universal: {executable}")
    for suffix in REQUIRED_BUNDLES:
        bundles = sorted(bin_dir.glob("*." + suffix))
        if not bundles:
            raise VerificationError(f"no macOS .{suffix} bundle in {bin_dir}")
        for bundle in bundles:
            if not bundle.is_dir() or bundle.is_symlink():
                raise VerificationError(f"macOS .{suffix} bundle is not a directory: {bundle}")
            # Inspect only executable image candidates, not arbitrary resource
            # strings or Info.plist; nested helpers may be present too.
            candidates = [p for p in bundle.rglob("*")
                          if p.is_file() and not p.is_symlink()
                          and (p.suffix in (".dylib", ".so") or "MacOS" in p.parts)]
            # At least one healthy image is not sufficient: the actual plugin
            # executable (or a nested binary helper) could still be thin or
            # corrupted while an unrelated universal dylib masks the issue.
            if not candidates:
                raise VerificationError(
                    f"no universal macOS executable image candidates in {bundle}")
            for path in candidates:
                if mach_arches(path) != EXPECTED_ARCHES:
                    raise VerificationError(
                        f"macOS executable image is not intact universal x86_64+arm64: {path}")


def parse_xar(path: Path) -> tuple[ET.Element, int, int]:
    try:
        with path.open("rb") as stream:
            header = stream.read(28)
            if len(header) != 28:
                raise VerificationError("truncated XAR package header")
            magic, header_size, version, compressed_len, uncompressed_len, _ = struct.unpack(
                ">IHHQQI", header)
            if magic != 0x78617221 or header_size != 28 or version != 1:
                raise VerificationError("invalid XAR package magic/header/version")
            if not 0 < compressed_len <= 16 * 1024 * 1024:
                raise VerificationError("XAR TOC has implausible compressed size")
            if not 0 < uncompressed_len <= 32 * 1024 * 1024:
                raise VerificationError("XAR TOC has implausible expanded size")
            # A bounded output prevents a malicious zlib bomb in a build asset.
            decoded = zlib.decompressobj()
            toc = decoded.decompress(stream.read(compressed_len), uncompressed_len + 1)
            if len(toc) != uncompressed_len or not decoded.eof or decoded.unused_data:
                raise VerificationError("XAR TOC is corrupt or has incorrect length")
            root = ET.fromstring(toc)
            if root.tag != "xar":
                raise VerificationError("XAR TOC root must be xar")
            return root, header_size + compressed_len, path.stat().st_size
    except (OSError, zlib.error, ET.ParseError) as exc:
        raise VerificationError(f"cannot decode XAR package {path}: {exc}") from exc


def verify_package(pkg: Path, expected_name: str) -> None:
    if pkg.name != expected_name or not expected_name.startswith("MODULAR-SYNTH-macOS-universal-") \
            or not expected_name.endswith(".pkg"):
        raise VerificationError("macOS package name does not match the fork artifact pattern")
    root, heap_start, archive_size = parse_xar(pkg)
    toc = root.find("toc")
    if toc is None:
        raise VerificationError("XAR has no TOC")
    entries: dict[str, ET.Element] = {}
    for entry in toc.findall("file"):
        name = entry.findtext("name")
        if not name or "/" in name or name in entries:
            raise VerificationError("XAR root entries have ambiguous or unsafe names")
        entries[name] = entry
    expected = PACKAGE_COMPONENTS | {"Distribution"}
    missing = expected.difference(entries)
    if missing:
        raise VerificationError("installer is missing components: " + ", ".join(sorted(missing)))
    for name in expected:
        entry = entries[name]
        if entry.findtext("type") != "file":
            raise VerificationError(f"installer member {name} is not a file")
        data = entry.find("data")
        try:
            offset = int(data.findtext("offset")) if data is not None else -1
            length = int(data.findtext("length")) if data is not None else -1
            size = int(data.findtext("size")) if data is not None else -1
        except (TypeError, ValueError) as exc:
            raise VerificationError(f"installer member {name} has invalid lengths") from exc
        if offset < 0 or length < 1 or size < 1 or heap_start + offset + length > archive_size:
            raise VerificationError(f"installer member {name} is empty or truncated")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--binaries", type=Path, help="unpackaged bin/ source tree")
    group.add_argument("--package", type=Path, help="final XAR macOS installer")
    parser.add_argument("--expected-name", help="exact fork-owned package filename")
    args = parser.parse_args(argv)
    try:
        if args.binaries is not None:
            verify_binaries(args.binaries)
            print("PASS macOS universal source bundle architecture gate")
        else:
            if not args.expected_name:
                parser.error("--expected-name is required with --package")
            verify_package(args.package, args.expected_name)
            print("PASS macOS XAR installer component integrity gate")
    except VerificationError as exc:
        print(f"FAIL macOS release validation: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
