#!/usr/bin/env python3
"""Deterministic, source-only index of original MODULAR-SYNTH .vcv patches.

Uses patch_inspector for all structural/first-party-port validation. A catalog
row is metadata from saved patch JSON, NOT a playback or sound-quality claim.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import quote

import patch_inspector

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "MODULAR_-_"


def _display_name(filename: str) -> str:
    stem = Path(filename).stem
    if stem.startswith(PREFIX):
        stem = stem[len(PREFIX):]
    return stem.replace("_", " ")


def _relative_file(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        # Temp fixture paths should produce the same portable catalog labels.
        return f"patches/examples/{path.name}"


def _routed_source(modules: list[dict], cables: list[dict],
                   model: str) -> bool:
    ids = {
        module["id"] for module in modules
        if module.get("plugin") == "Cardinal" and module.get("model") == model
    }
    return any(cable["outputModuleId"] in ids for cable in cables)


def _midi_channels(modules: list[dict]) -> int | None:
    values = []
    for module in modules:
        if module.get("plugin") != "Cardinal" or module.get("model") != "HostMIDI":
            continue
        data = module.get("data")
        channels = data.get("channels") if isinstance(data, dict) else None
        if type(channels) is int and 1 <= channels <= 16:
            values.append(channels)
    # One unambiguous saved host MIDI channel setting is useful to display.
    return values[0] if len(values) == 1 else None


def _macro_scenes(modules: list[dict]) -> tuple[int | None, int, list[str]]:
    total = 0
    instances = 0
    warnings: list[str] = []
    for module in modules:
        if module.get("plugin") != "ModularSynth" or module.get("model") != "Macro8":
            continue
        instances += 1
        data = module.get("data")
        slots = data.get("snapshots") if isinstance(data, dict) else None
        if slots is None:
            continue
        if not isinstance(slots, list):
            warnings.append(
                f"Macro8 module {module['id']}: snapshots not an array; "
                "saved scene count unknown"
            )
            return None, instances, warnings
        # Count only serialized non-null slots. This does not duplicate
        # Macro8's saved-array semantic validation in the coverage suite.
        total += sum(slot is not None for slot in slots)
    return total, instances, warnings


def collect(root: Path = ROOT, examples_dir: Path | None = None) -> dict:
    """Collect sorted metadata from whatever original patches exist today."""
    root = Path(root)
    examples_dir = (Path(examples_dir) if examples_dir is not None
                    else root / "patches" / "examples")
    paths = sorted(examples_dir.glob("MODULAR_-_*.vcv"),
                   key=lambda path: (path.name.casefold(), path.name))
    entries: list[dict] = []
    errors: list[str] = []

    for path in paths:
        structural = patch_inspector.inspect_patch(path, root)
        inventory = structural["module_inventory"]
        entry = {
            "file": _relative_file(path, root),
            "title": _display_name(path.name),
            "structurally_valid": bool(structural["ok"]),
            "module_count": sum(inventory.values()),
            "cable_count": structural["cables"],
            "module_inventory": inventory,
            "original_modules": sorted(
                name.removeprefix("ModularSynth/")
                for name in inventory if name.startswith("ModularSynth/")
            ),
            "midi_routed": None,
            "host_transport_routed": None,
            "midi_channels_saved": None,
            "macro8_instances": inventory.get("ModularSynth/Macro8", 0),
            "macro8_stored_scenes": None,
            "inspector_has_warnings": bool(structural["warnings"]),
            "inspector_warning_count": len(structural["warnings"]),
            "inspector_warnings": structural["warnings"],
            "catalog_warnings": [],
            "errors": structural["errors"],
        }
        entries.append(entry)
        if not structural["ok"]:
            errors.extend(f"{path.name}: {issue}" for issue in structural["errors"])
            continue

        # Source is already strictly validated by patch_inspector, including
        # duplicate JSON keys, cable endpoints and first-party port bounds.
        patch = patch_inspector._strict_json(path)
        modules = patch["modules"]
        cables = patch["cables"]
        entry["midi_routed"] = _routed_source(modules, cables, "HostMIDI")
        entry["host_transport_routed"] = _routed_source(modules, cables, "HostTime")
        entry["midi_channels_saved"] = _midi_channels(modules)
        stored, units, extra_warnings = _macro_scenes(modules)
        entry["macro8_instances"] = units
        entry["macro8_stored_scenes"] = stored
        entry["catalog_warnings"] = extra_warnings

    if not paths:
        errors.append("No MODULAR_-_*.vcv examples found")
    return {
        "schema_version": 1,
        "ok": not errors,
        "patch_count": len(entries),
        "patches": entries,
        "errors": errors,
    }


def markdown(catalog: dict) -> str:
    """Render a reproducible index with links relative to docs/."""
    lines = [
        "# MODULAR-SYNTH original patch index",
        "",
        "Source-only saved-patch metadata. This does not prove playable audio, "
        "third-party module availability, or sonic character.",
        "",
        "| Patch | Modules | MIDI / host transport routes | Macro8 stored slots | Inspector |",
        "| --- | --- | --- | --- | --- |",
    ]
    for entry in catalog["patches"]:
        url = "../" + quote(entry["file"], safe="/")
        title = entry["title"].replace("|", r"\|")
        link = f"[{title}]({url})"
        originals = ", ".join(entry["original_modules"]) or "none"
        modules = f"{entry['module_count']} total; originals: {originals}"
        control = []
        if entry["midi_routed"]:
            midi = "MIDI"
            if entry["midi_channels_saved"] is not None:
                midi += f" ({entry['midi_channels_saved']} saved lanes)"
            control.append(midi)
        if entry["host_transport_routed"]:
            control.append("Host transport")
        routes = ", ".join(control) if control else (
            "none observed" if entry["structurally_valid"] else "unverified"
        )
        if entry["macro8_instances"]:
            count = entry["macro8_stored_scenes"]
            scenes = f"{count} non-null slots" if count is not None else "unknown"
        else:
            scenes = "none"
        status = ("PASS" if entry["structurally_valid"] else "FAIL")
        status += f"; {entry['inspector_warning_count']} inspector warnings"
        if entry["catalog_warnings"]:
            status += f"; {len(entry['catalog_warnings'])} metadata warnings"
        lines.append(f"| {link} | {modules} | {routes} | {scenes} | {status} |")
    lines += ["", "## Saved module inventories", ""]
    for entry in catalog["patches"]:
        modules = ", ".join(
            f"`{name}`" + (f" ×{count}" if count > 1 else "")
            for name, count in entry["module_inventory"].items()
        ) or "none"
        lines.append(f"- **{entry['title']}**: {modules}")
    lines += [
        "",
        f"{catalog['patch_count']} matching original examples; "
        f"{'no structural errors' if catalog['ok'] else 'structural errors present'}.",
        "",
        "Warning counts are preserved from the offline inspector. MIDI/transport "
        "flags mean a saved HostMIDI/HostTime output is **cabled**, not that "
        "the plugin was executed. Scene counts are non-null saved entries, "
        "not verified recall/audio.",
    ]
    if catalog["errors"]:
        lines += ["", "## Source inspection errors", ""]
        lines.extend(f"- {error}" for error in catalog["errors"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--examples-dir", type=Path)
    args = parser.parse_args(argv)

    try:
        catalog = collect(args.repo_root, args.examples_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: cannot read source catalog: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(catalog, indent=2, sort_keys=True))
    else:
        print(markdown(catalog), end="")
    return 0 if catalog["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
