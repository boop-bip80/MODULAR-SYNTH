#!/usr/bin/env python3
"""Offline, deterministic MODULAR-SYNTH source instrument bundles.

A .msinstrument is a small source ZIP containing ONLY a validated .vcv patch
and a verified Macro8 performance manifest. No DSP compilation or plugin export.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

from panel_preview import PreviewError, render_svg
from compatibility import CompatibilityError, compatibility_report, text_report
from control_mapping import (
    CHANCE_HOLD_CONTRACT, CLOCKED_LFO_CONTRACT, FOLD_DRIVE_CONTRACT,
    FM_VOICE_CONTRACT, MappingError,
    derive_control_mappings)
from verified_routes import verified_routes_report
from route_report import build_route_report, text_route_report
from control_report import build_control_report, text_control_report
from instrument_diff import compare_verified_bundles, text_diff_report

FORMAT = "modular-synth-source-instrument"
FORMAT_VERSION = 1
MAPPING_FORMAT_VERSION = 2
SUPPORTED_FORMAT_VERSIONS = (FORMAT_VERSION, MAPPING_FORMAT_VERSION)
PATCH_MEMBER = "patch/main.vcv"
MANIFEST_MEMBER = "manifest.json"
MEMBERS = (MANIFEST_MEMBER, PATCH_MEMBER)
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MAX_PATCH_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
MAX_BUNDLE_BYTES = MAX_PATCH_BYTES + MAX_MANIFEST_BYTES + 65536
MAX_MODULES = 256
MAX_CABLES = 4096
MAX_MACRO8 = 8
SLOT_NAMES = ("A", "B", "C", "D")
DISPLAY_NAME = re.compile(r"[\x20-\x7e]{1,64}\Z")


class InstrumentError(ValueError):
    """Invalid patch, manifest, archive, or unsafe destination."""


def _is_int(value: object) -> bool:
    return type(value) is int


def _number(value: object, minimum: float, maximum: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InstrumentError(f"{field} must be a number")
    numeric = float(value)
    if not math.isfinite(numeric) or not minimum <= numeric <= maximum:
        raise InstrumentError(f"{field} outside {minimum:g}..{maximum:g}")
    return numeric


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise InstrumentError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _finite_json_float(source: str) -> float:
    value = float(source)
    if not math.isfinite(value):
        raise InstrumentError("nonfinite JSON number")
    return value


def _reject_json_constant(value: str) -> None:
    raise InstrumentError(f"invalid JSON constant: {value}")


def _decode_json(blob: bytes, description: str) -> dict:
    try:
        value = json.loads(
            blob.decode("utf-8"), object_pairs_hook=_pairs_without_duplicates,
            parse_float=_finite_json_float, parse_constant=_reject_json_constant)
    except (UnicodeError, ValueError, RecursionError, OverflowError) as exc:
        raise InstrumentError(f"invalid {description}: {exc}") from exc
    if not isinstance(value, dict):
        raise InstrumentError(f"{description} must be a JSON object")
    return value


def _valid_module_id(value: object, field: str) -> int:
    if not _is_int(value) or not 0 <= value <= 0x7fffffffffffffff:
        raise InstrumentError(f"{field} must be a nonnegative signed 64-bit integer")
    return value


def _valid_name(value: object, field: str, limit: int = 128) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= limit:
        raise InstrumentError(f"{field} must be a nonempty string of at most {limit} chars")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise InstrumentError(f"{field} contains control characters")
    return value


def _macro8_performance(module: dict) -> dict:
    module_id = module["id"]
    data = module.get("data")
    if not isinstance(data, dict):
        raise InstrumentError(f"Macro8 {module_id}: missing versioned data object")
    if not _is_int(data.get("macro8Version")) or data["macro8Version"] != 1:
        raise InstrumentError(f"Macro8 {module_id}: unsupported macro8Version")

    names = data.get("names")
    if not isinstance(names, list) or len(names) != 8:
        raise InstrumentError(f"Macro8 {module_id}: names must contain eight labels")
    for index, name in enumerate(names):
        if not isinstance(name, str) or not 1 <= len(name) <= 12 or any(
            ord(character) < 32 or ord(character) > 126 for character in name
        ):
            raise InstrumentError(f"Macro8 {module_id}: invalid name {index + 1}")

    raw_slots = data.get("snapshots")
    if not isinstance(raw_slots, list) or len(raw_slots) != 4:
        raise InstrumentError(f"Macro8 {module_id}: snapshots must have four slots")
    snapshots: list[list[float] | None] = []
    for slot, row in zip(SLOT_NAMES, raw_slots):
        if row is None:
            snapshots.append(None)
        elif isinstance(row, list) and len(row) == 8:
            snapshots.append([
                _number(value, 0, 1, f"Macro8 {module_id} snapshot {slot}")
                for value in row
            ])
        else:
            raise InstrumentError(f"Macro8 {module_id}: malformed snapshot {slot}")
    selected = data.get("selectedSlot")
    if not _is_int(selected) or selected not in (-1, 0, 1, 2, 3):
        raise InstrumentError(f"Macro8 {module_id}: invalid selectedSlot")
    if selected >= 0 and snapshots[selected] is None:
        raise InstrumentError(f"Macro8 {module_id}: selected snapshot is empty")

    params = module.get("params")
    if not isinstance(params, list):
        raise InstrumentError(f"Macro8 {module_id}: params must be a list")
    by_id: dict[int, float] = {}
    for entry in params:
        if not isinstance(entry, dict) or not _is_int(entry.get("id")):
            raise InstrumentError(f"Macro8 {module_id}: invalid parameter entry")
        param_id = entry["id"]
        if not 0 <= param_id <= 22 or param_id in by_id:
            raise InstrumentError(f"Macro8 {module_id}: unknown/duplicate parameter id")
        by_id[param_id] = _number(
            entry.get("value"), 0, 5 if param_id == 8 else 1,
            f"Macro8 {module_id} param {param_id}")

    live = [by_id.get(i, 0.0) for i in range(8)]
    range_modes = [
        "bipolar" if by_id.get(15 + i, 0.0) >= 0.5 else "unipolar"
        for i in range(8)
    ]
    return {
        "moduleId": module_id,
        "stateVersion": 1,
        "names": list(names),
        "ranges": range_modes,
        "liveValues": live,
        "morphSeconds": by_id.get(8, 0.25),
        "snapshotAction": "store" if by_id.get(9, 0.0) >= 0.5 else "recall",
        "snapshots": snapshots,
        "selectedSlot": selected,
    }


def patch_performance(patch_bytes: bytes) -> tuple[list[dict], list[str]]:
    """Validate a JSON Rack patch and derive real Macro8 performance state."""
    if not isinstance(patch_bytes, bytes) or len(patch_bytes) > MAX_PATCH_BYTES:
        raise InstrumentError("patch must be bytes and at most 8 MiB")
    patch = _decode_json(patch_bytes, "VCV patch")
    _valid_name(patch.get("version"), "patch version", 64)
    modules = patch.get("modules")
    if not isinstance(modules, list) or not 1 <= len(modules) <= MAX_MODULES:
        raise InstrumentError("patch modules must contain 1..256 entries")

    seen_ids: set[int] = set()
    performance: list[dict] = []
    plugins: set[str] = set()
    for entry in modules:
        if not isinstance(entry, dict):
            raise InstrumentError("patch module must be an object")
        module_id = _valid_module_id(entry.get("id"), "module id")
        if module_id in seen_ids:
            raise InstrumentError(f"duplicate module id: {module_id}")
        seen_ids.add(module_id)
        plugin = _valid_name(entry.get("plugin"), "plugin slug")
        model = _valid_name(entry.get("model"), "module model")
        plugins.add(plugin)
        if plugin == "ModularSynth" and model == "Macro8":
            performance.append(_macro8_performance(entry))
            if len(performance) > MAX_MACRO8:
                raise InstrumentError("patch has more than eight Macro8 modules")
    if not performance:
        raise InstrumentError("patch must contain at least one ModularSynth/Macro8")

    cables = patch.get("cables", [])
    if not isinstance(cables, list) or len(cables) > MAX_CABLES:
        raise InstrumentError("patch cables must be an array of at most 4096 entries")
    seen_cable_ids: set[int] = set()
    for index, cable in enumerate(cables):
        if not isinstance(cable, dict):
            raise InstrumentError(f"cable {index} must be an object")
        cable_id = _valid_module_id(cable.get("id"), f"cable {index} id")
        if cable_id in seen_cable_ids:
            raise InstrumentError(f"duplicate cable id: {cable_id}")
        seen_cable_ids.add(cable_id)
        for endpoint in ("input", "output"):
            module_id = _valid_module_id(
                cable.get(f"{endpoint}ModuleId"), f"cable {index} {endpoint} module")
            if module_id not in seen_ids:
                raise InstrumentError(f"cable {index} references missing module")
            port = cable.get(f"{endpoint}Id")
            if not _is_int(port) or not 0 <= port <= 4096:
                raise InstrumentError(f"cable {index} has invalid {endpoint} port")

    performance.sort(key=lambda item: item["moduleId"])
    return performance, sorted(plugins)


def _validate_display_name(name: object) -> str:
    if not isinstance(name, str) or not DISPLAY_NAME.fullmatch(name):
        raise InstrumentError("instrument name must be 1..64 printable ASCII characters")
    return name


def build_manifest(patch_bytes: bytes, name: str, *,
                   format_version: int = FORMAT_VERSION,
                   legacy_v2_mapping: bool = False,
                   legacy_fold_drive_mapping: bool | None = None,
                   legacy_fm_voice_mapping: bool | None = None,
                   legacy_chance_hold_mapping: bool | None = None) -> dict:
    name = _validate_display_name(name)
    if not _is_int(format_version) or format_version not in SUPPORTED_FORMAT_VERSIONS:
        raise InstrumentError("unsupported instrument manifest format/version")
    # Historical v2 contracts are cumulative, not mutable. An old unmarked
    # bundle predates ClockedLFO, FoldDrive, FMVoice and ChanceHold; older
    # markers never inherit later source-port labels on read.
    if legacy_fold_drive_mapping is None:
        legacy_fold_drive_mapping = legacy_v2_mapping
    elif legacy_v2_mapping and not legacy_fold_drive_mapping:
        raise InstrumentError("incompatible historical v2 mapping contracts")
    if legacy_fm_voice_mapping is None:
        legacy_fm_voice_mapping = legacy_fold_drive_mapping
    elif legacy_fold_drive_mapping and not legacy_fm_voice_mapping:
        raise InstrumentError("incompatible historical v2 mapping contracts")
    if legacy_chance_hold_mapping is None:
        legacy_chance_hold_mapping = legacy_fm_voice_mapping
    elif legacy_fm_voice_mapping and not legacy_chance_hold_mapping:
        raise InstrumentError("incompatible historical v2 mapping contracts")
    performance, plugins = patch_performance(patch_bytes)
    manifest = {
        "format": FORMAT,
        "formatVersion": format_version,
        "name": name,
        "patch": {
            "file": PATCH_MEMBER,
            "sha256": hashlib.sha256(patch_bytes).hexdigest(),
            "size": len(patch_bytes),
        },
        "performance": {"macro8": performance},
        "requiredPlugins": plugins,
    }
    if format_version == MAPPING_FORMAT_VERSION:
        # No source repository is required at pack/read time. First-party port
        # descriptors are a versioned contract tested against our C++ source;
        # all third-party ports remain explicitly unverified.
        try:
            mappings = derive_control_mappings(
                _decode_json(patch_bytes, "VCV patch"), performance,
                clocked_lfo_known=not legacy_v2_mapping,
                fold_drive_known=not legacy_fold_drive_mapping,
                fm_voice_known=not legacy_fm_voice_mapping,
                chance_hold_known=not legacy_chance_hold_mapping)
        except MappingError as exc:
            raise InstrumentError(f"Macro8 control mapping: {exc}") from exc
        manifest["performance"]["controlMappings"] = mappings
        if not legacy_chance_hold_mapping and any(
            route["destination"]["plugin"] == "ModularSynth"
            and route["destination"]["model"] == "ChanceHold"
            for route in mappings
        ):
            # Only newly packed ChanceHold destinations opt into the eighth
            # model's labels. All historical v2 port contracts are immutable.
            manifest["performance"]["controlMappingContract"] = CHANCE_HOLD_CONTRACT
        elif not legacy_fm_voice_mapping and any(
            route["destination"]["plugin"] == "ModularSynth"
            and route["destination"]["model"] == "FMVoice"
            for route in mappings
        ):
            # The new seven-model contract implies the prior FoldDrive and
            # ClockedLFO port mappings without changing archived v2 claims.
            manifest["performance"]["controlMappingContract"] = FM_VOICE_CONTRACT
        elif not legacy_fold_drive_mapping and any(
            route["destination"]["plugin"] == "ModularSynth"
            and route["destination"]["model"] == "FoldDrive"
            for route in mappings
        ):
            # The six-model contract includes the previous ClockedLFO inputs.
            # Old unmarked and ClockedLFO-marked v2 archives continue to
            # interpret FoldDrive as unverified; never reinterpret them.
            manifest["performance"]["controlMappingContract"] = FOLD_DRIVE_CONTRACT
        elif not legacy_v2_mapping and any(
            route["destination"]["plugin"] == "ModularSynth"
            and route["destination"]["model"] == "ClockedLFO"
            for route in mappings
        ):
            # Original v2 had four verified models; this marker added a fifth.
            manifest["performance"]["controlMappingContract"] = CLOCKED_LFO_CONTRACT
    return manifest


def _canonical_json(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, ensure_ascii=True,
                       allow_nan=False, indent=2) + "\n").encode("utf-8")


def create_bundle(patch_bytes: bytes, name: str, *,
                  format_version: int = FORMAT_VERSION) -> bytes:
    """Build a deterministic, two-entry, uncompressed source archive."""
    manifest = _canonical_json(build_manifest(
        patch_bytes, name, format_version=format_version))
    if len(manifest) > MAX_MANIFEST_BYTES:
        raise InstrumentError("performance manifest exceeds 128 KiB")
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for filename, content in (
            (MANIFEST_MEMBER, manifest), (PATCH_MEMBER, patch_bytes)
        ):
            info = zipfile.ZipInfo(filename, date_time=ZIP_TIMESTAMP)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, content)
    result = stream.getvalue()
    if len(result) > MAX_BUNDLE_BYTES:
        raise InstrumentError("instrument archive exceeds size limit")
    return result


def _safe_member(name: str) -> None:
    if ("\\" in name or "\x00" in name or name.startswith("/")
            or re.match(r"^[A-Za-z]:", name)
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise InstrumentError(f"unsafe archive path: {name!r}")
    if name not in MEMBERS:
        raise InstrumentError(f"unexpected archive entry: {name!r}")


def read_bundle(bundle_bytes: bytes) -> tuple[dict, bytes]:
    """Validate all archive members and manifest-to-patch consistency."""
    if not isinstance(bundle_bytes, bytes) or len(bundle_bytes) > MAX_BUNDLE_BYTES:
        raise InstrumentError("bundle must be bytes and within the size limit")
    try:
        with zipfile.ZipFile(BytesIO(bundle_bytes), "r") as archive:
            entries = archive.infolist()
            if len(entries) != len(MEMBERS):
                raise InstrumentError("archive must contain exactly two files")
            if archive.comment:
                raise InstrumentError("archive comments are not supported")
            seen: set[str] = set()
            for info in entries:
                _safe_member(info.filename)
                key = info.filename.casefold()
                if key in seen:
                    raise InstrumentError("duplicate archive entry")
                seen.add(key)
                mode = (info.external_attr >> 16) & 0xffff
                if (info.is_dir() or info.compress_type != zipfile.ZIP_STORED
                        or info.flag_bits & 1 or info.extra or info.comment
                        or info.create_system != 3
                        or stat.S_IFMT(mode) != stat.S_IFREG):
                    raise InstrumentError(f"unsupported archive entry: {info.filename}")
                maximum = (MAX_PATCH_BYTES if info.filename == PATCH_MEMBER
                           else MAX_MANIFEST_BYTES)
                if info.file_size > maximum or info.compress_size > maximum:
                    raise InstrumentError(f"oversized archive member: {info.filename}")
            if seen != {member.casefold() for member in MEMBERS}:
                raise InstrumentError("archive is missing required members")
            raw_manifest = archive.read(MANIFEST_MEMBER)
            patch = archive.read(PATCH_MEMBER)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError) as exc:
        raise InstrumentError(f"invalid ZIP archive: {exc}") from exc

    if len(raw_manifest) > MAX_MANIFEST_BYTES or len(patch) > MAX_PATCH_BYTES:
        raise InstrumentError("archive extraction exceeds size limit")
    manifest = _decode_json(raw_manifest, "instrument manifest")
    if (manifest.get("format") != FORMAT
            or not _is_int(manifest.get("formatVersion"))
            or manifest["formatVersion"] not in SUPPORTED_FORMAT_VERSIONS):
        raise InstrumentError("unsupported instrument manifest format/version")
    performance = manifest.get("performance")
    contract = (performance.get("controlMappingContract")
                if isinstance(performance, dict) else None)
    if contract is not None and contract not in (
            CLOCKED_LFO_CONTRACT, FOLD_DRIVE_CONTRACT,
            FM_VOICE_CONTRACT, CHANCE_HOLD_CONTRACT):
        raise InstrumentError("unsupported control mapping contract")
    expected = build_manifest(
        patch, manifest.get("name"), format_version=manifest["formatVersion"],
        legacy_v2_mapping=(manifest["formatVersion"] == MAPPING_FORMAT_VERSION
                           and contract is None),
        legacy_fold_drive_mapping=(
            manifest["formatVersion"] == MAPPING_FORMAT_VERSION
            and contract not in (FOLD_DRIVE_CONTRACT, FM_VOICE_CONTRACT,
                                 CHANCE_HOLD_CONTRACT)),
        legacy_fm_voice_mapping=(
            manifest["formatVersion"] == MAPPING_FORMAT_VERSION
            and contract not in (FM_VOICE_CONTRACT, CHANCE_HOLD_CONTRACT)),
        legacy_chance_hold_mapping=(
            manifest["formatVersion"] == MAPPING_FORMAT_VERSION
            and contract != CHANCE_HOLD_CONTRACT))
    if manifest != expected:
        raise InstrumentError("instrument manifest does not match its patch")
    return manifest, patch


def _read_limited(path: Path, maximum: int, description: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise InstrumentError(f"{description} must be a regular non-symlink file")
    with path.open("rb") as source:
        data = source.read(maximum + 1)
    if len(data) > maximum:
        raise InstrumentError(f"{description} exceeds size limit")
    return data


@contextmanager
def _safe_directory_fd(directory: Path):
    """Hold component-wise no-follow directory handles on POSIX.

    Other platforms reject known ancestor symlinks but cannot promise
    protection against hostile concurrent filesystem changes.
    """
    absolute = Path(os.path.abspath(os.fspath(directory)))
    if os.name != "posix" or not all(
        hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW")
    ):
        for component in (absolute, *absolute.parents):
            if component.is_symlink():
                raise InstrumentError(f"symlink destination directory: {component}")
        if not absolute.is_dir():
            raise InstrumentError(f"destination parent does not exist: {absolute}")
        yield None
        return
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in absolute.parts[1:]:
            next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def _mkdir_new(parent: Path, name: str, parent_fd: int | None) -> None:
    if parent_fd is None:
        (parent / name).mkdir(mode=0o755, exist_ok=False)
    else:
        os.mkdir(name, mode=0o755, dir_fd=parent_fd)


def _write_new(parent: Path, name: str, content: bytes,
               parent_fd: int | None) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if parent_fd is None:
        fd = os.open(parent / name, flags, 0o644)
    else:
        fd = os.open(name, flags, 0o644, dir_fd=parent_fd)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)


def pack(patch_path: Path, bundle_path: Path, name: str | None = None, *,
         format_version: int = FORMAT_VERSION) -> dict:
    if patch_path.suffix.lower() != ".vcv":
        raise InstrumentError("source patch must have a .vcv extension")
    if bundle_path.suffix.lower() != ".msinstrument":
        raise InstrumentError("output bundle must end with .msinstrument")
    patch = _read_limited(patch_path, MAX_PATCH_BYTES, "VCV patch")
    manifest = build_manifest(
        patch, name if name is not None else patch_path.stem,
        format_version=format_version)
    bundle = create_bundle(
        patch, manifest["name"], format_version=format_version)
    with _safe_directory_fd(bundle_path.parent) as fd:
        _write_new(bundle_path.parent, bundle_path.name, bundle, fd)
    return manifest


def unpack(bundle_path: Path, destination: Path) -> dict:
    if bundle_path.suffix.lower() != ".msinstrument":
        raise InstrumentError("source bundle must end with .msinstrument")
    blob = _read_limited(bundle_path, MAX_BUNDLE_BYTES, "instrument bundle")
    manifest, patch = read_bundle(blob)  # All hostile input checked before writing.
    with _safe_directory_fd(destination.parent) as parent_fd:
        _mkdir_new(destination.parent, destination.name, parent_fd)
        with _safe_directory_fd(destination) as root_fd:
            _write_new(destination, MANIFEST_MEMBER, _canonical_json(manifest), root_fd)
            _mkdir_new(destination, "patch", root_fd)
            with _safe_directory_fd(destination / "patch") as patch_fd:
                _write_new(destination / "patch", "main.vcv", patch, patch_fd)
    return manifest


def inspect(bundle_path: Path) -> dict:
    if bundle_path.suffix.lower() != ".msinstrument":
        raise InstrumentError("source bundle must end with .msinstrument")
    blob = _read_limited(bundle_path, MAX_BUNDLE_BYTES, "instrument bundle")
    return read_bundle(blob)[0]


def preview(bundle_path: Path, svg_path: Path, *,
            show_routes: bool = False) -> dict:
    """Create a static SVG; optionally display verified saved v2 cable metadata."""
    if svg_path.suffix.lower() != ".svg":
        raise InstrumentError("preview output must end with .svg")
    manifest = inspect(bundle_path)  # Validate ZIP and source-derived state first.
    if show_routes and manifest["formatVersion"] != MAPPING_FORMAT_VERSION:
        raise InstrumentError(
            "route-aware SVG preview requires v2 source mapping metadata; "
            "repack the trusted .vcv with --format-version 2")
    # Keep the original panel pixels and v1 display schema unchanged. The
    # optional route appendix is derived only after full bundle validation;
    # archived v2 port contracts retain their historical interpretation.
    view = (manifest if manifest["formatVersion"] == FORMAT_VERSION else {
        **manifest, "formatVersion": FORMAT_VERSION,
        "performance": {"macro8": manifest["performance"]["macro8"]},
    })
    try:
        image = render_svg(
            view, route_map=build_route_report(manifest) if show_routes else None)
    except PreviewError as exc:
        raise InstrumentError(f"cannot preview instrument: {exc}") from exc
    with _safe_directory_fd(svg_path.parent) as fd:
        _write_new(svg_path.parent, svg_path.name, image, fd)
    return manifest


def check(bundle_path: Path, repo_root: Path | None = None, *,
          require_verified_routes: bool = False) -> dict:
    """Verify a source bundle, then check only first-party model declarations.

    External plugin/model availability is intentionally never inferred. The
    optional route gate requires a v2 source mapping contract and at least one
    direct Macro8 cable, then checks every destination's source port descriptor.
    It never checks a DAW's automatable parameter or audio behavior.
    """
    if bundle_path.suffix.lower() != ".msinstrument":
        raise InstrumentError("source bundle must end with .msinstrument")
    blob = _read_limited(bundle_path, MAX_BUNDLE_BYTES, "instrument bundle")
    manifest, source_patch = read_bundle(blob)  # Includes SHA/schema checks.
    root = repo_root if repo_root is not None else Path(__file__).resolve().parents[2]
    collection_path = root / "plugins" / "ModularSynth" / "plugin.json"
    registry = _decode_json(
        _read_limited(collection_path, MAX_MANIFEST_BYTES,
                      "first-party collection manifest"),
        "first-party collection manifest")
    patch = _decode_json(source_patch, "VCV patch")
    try:
        report = compatibility_report(
            patch, registry,
            patch_sha256=manifest["patch"]["sha256"],
            required_plugins=manifest["requiredPlugins"])
        if require_verified_routes:
            routes = verified_routes_report(manifest)
            report["verifiedRoutes"] = routes
            if routes["status"] == "FAIL":
                report["status"] = "FAIL"
        return report
    except CompatibilityError as exc:
        raise InstrumentError(f"compatibility preflight: {exc}") from exc


def compare_bundles(previous_path: Path, current_path: Path) -> dict:
    """Compare two independently validated saved instruments without writing."""
    verified = []
    for path in (previous_path, current_path):
        if path.suffix.lower() != ".msinstrument":
            raise InstrumentError("source bundle must end with .msinstrument")
        blob = _read_limited(path, MAX_BUNDLE_BYTES, "instrument bundle")
        verified.append(read_bundle(blob))
    (old_manifest, old_patch), (new_manifest, new_patch) = verified
    return compare_verified_bundles(
        old_manifest, old_patch, new_manifest, new_patch)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    create = subs.add_parser("pack", help="package a validated VCV patch and Macro8")
    create.add_argument("patch", type=Path)
    create.add_argument("--out", required=True, type=Path)
    create.add_argument("--name", help="instrument display name (default: patch stem)")
    create.add_argument(
        "--format-version", type=int, choices=SUPPORTED_FORMAT_VERSIONS,
        default=FORMAT_VERSION,
        help="source manifest v1 (default) or v2 with verified Macro8 cable mappings")
    info = subs.add_parser("inspect", help="validate and print an instrument manifest")
    info.add_argument("bundle", type=Path)
    routes = subs.add_parser(
        "routes", help="explain saved direct Macro8 cable routes in musician terms")
    routes.add_argument("bundle", type=Path)
    routes.add_argument(
        "--json", action="store_true",
        help="machine-readable source-only route report")
    controls = subs.add_parser(
        "controls", help="inventory all saved Macro8 knobs, snapshots and routes")
    controls.add_argument("bundle", type=Path)
    controls.add_argument(
        "--json", action="store_true",
        help="deterministic source-only saved performance inventory")
    difference = subs.add_parser(
        "diff", help="compare validated saved patch, Macro8 and routing state")
    difference.add_argument("old_bundle", type=Path)
    difference.add_argument("new_bundle", type=Path)
    difference.add_argument("--json", action="store_true",
                            help="deterministic structured source-only comparison")
    difference.add_argument("--fail-on-change", action="store_true",
                            help="exit 1 on saved semantic changes (for CI)")
    extract = subs.add_parser("unpack", help="extract into a NEW directory only")
    extract.add_argument("bundle", type=Path)
    extract.add_argument("--out", required=True, type=Path)
    panel = subs.add_parser("preview", help="create an offline SVG concept panel")
    panel.add_argument("bundle", type=Path)
    panel.add_argument("--out", required=True, type=Path)
    panel.add_argument(
        "--show-routes", action="store_true",
        help="append source-only direct Macro8 routing map (requires v2)")
    compatibility = subs.add_parser(
        "check", help="preflight source model references against ModularSynth")
    compatibility.add_argument("bundle", type=Path)
    compatibility.add_argument(
        "--repo-root", type=Path, default=None,
        help="repository containing plugins/ModularSynth/plugin.json")
    compatibility.add_argument(
        "--format", choices=("text", "json"), default="text")
    compatibility.add_argument(
        "--json", action="store_true", help="alias for --format json")
    compatibility.add_argument(
        "--require-verified-routes", action="store_true",
        help=("fail unless a v2 bundle has at least one direct Macro8 cable "
              "and every destination input port is source-verified"))
    args = parser.parse_args(argv)
    try:
        if args.command == "pack":
            manifest = pack(
                args.patch, args.out, args.name, format_version=args.format_version)
            print(f"Packed {args.out} ({len(manifest['performance']['macro8'])} Macro8)")
        elif args.command == "unpack":
            unpack(args.bundle, args.out)
            print(f"Unpacked to {args.out} (manifest.json, patch/main.vcv)")
        elif args.command == "preview":
            preview(args.bundle, args.out, show_routes=args.show_routes)
            if args.show_routes:
                print(f"Generated static route-aware SVG preview {args.out}")
            else:
                print(f"Generated static SVG preview {args.out}")
        elif args.command == "routes":
            report = build_route_report(inspect(args.bundle))
            if args.json:
                print(_canonical_json(report).decode("utf-8"), end="")
            else:
                print(text_route_report(report), end="")
        elif args.command == "controls":
            report = build_control_report(inspect(args.bundle))
            if args.json:
                print(_canonical_json(report).decode("utf-8"), end="")
            else:
                print(text_control_report(report), end="")
        elif args.command == "diff":
            report = compare_bundles(args.old_bundle, args.new_bundle)
            if args.json:
                print(_canonical_json(report).decode("utf-8"), end="")
            else:
                print(text_diff_report(report), end="")
            return 1 if args.fail_on_change and report["changed"] else 0
        elif args.command == "check":
            report = check(
                args.bundle, args.repo_root,
                require_verified_routes=args.require_verified_routes)
            if args.json or args.format == "json":
                print(_canonical_json(report).decode("utf-8"), end="")
            else:
                print(text_report(report), end="")
            return 1 if report["status"] == "FAIL" else 0
        else:
            print(_canonical_json(inspect(args.bundle)).decode("utf-8"), end="")
        return 0
    except (InstrumentError, OSError, zipfile.BadZipFile) as exc:
        print(f"Instrument Builder: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
