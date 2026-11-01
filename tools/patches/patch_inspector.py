#!/usr/bin/env python3
"""Inspect and validate plaintext VCV/Cardinal .vcv patch graphs offline.

The tool deliberately does not claim to load a patch or verify its sound.
Only first-party source-backed port bounds are authoritative; third-party
module ports and ranges are reported as unverified.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
FIRST_PARTY = ("Cardinal", "ModularSynth")
ENUM_MARKERS = {"ParamIds": "NUM_PARAMS", "InputIds": "NUM_INPUTS", "OutputIds": "NUM_OUTPUTS"}


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _strict_json(path: Path) -> object:
    def nonfinite(value: str) -> object:
        raise ValueError(f"Non-finite JSON literal: {value}")

    def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key!r}")
            result[key] = value
        return result

    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream, parse_constant=nonfinite, object_pairs_hook=unique_keys)


def _known_modules(root: Path) -> tuple[dict[tuple[str, str], dict], set[tuple[str, str]]]:
    """First-party manifests; stock-template references are weaker evidence."""
    first: dict[tuple[str, str], dict] = {}
    for slug in FIRST_PARTY:
        path = root / "plugins" / slug / "plugin.json"
        if not path.is_file():
            continue
        manifest = _strict_json(path)
        if not isinstance(manifest, dict) or manifest.get("slug") != slug:
            continue
        for entry in manifest.get("modules", []):
            if isinstance(entry, dict) and isinstance(entry.get("slug"), str):
                first[(slug, entry["slug"])] = entry

    bundled_reference: set[tuple[str, str]] = set()
    template_dir = root / "patches" / "templates"
    for path in sorted(template_dir.glob("*.vcv")):
        try:
            patch = _strict_json(path)
            if not isinstance(patch, dict):
                continue
            for module in patch.get("modules", []):
                if isinstance(module, dict):
                    plugin, model = module.get("plugin"), module.get("model")
                    if isinstance(plugin, str) and isinstance(model, str):
                        bundled_reference.add((plugin, model))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return first, bundled_reference


def _enum_members(source: str, enum_name: str, sentinel: str) -> list[str] | None:
    match = re.search(r"\benum\s+" + re.escape(enum_name) + r"\s*\{([^}]*)\}", source, re.S)
    if not match:
        return None
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", match.group(1), flags=re.S)
    members = [member.strip() for member in body.split(",") if member.strip()]
    if not members or members[-1] != sentinel:
        return None
    # Explicit assignments and aliases would invalidate simple ordinal counting.
    if any(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", member) is None for member in members):
        return None
    return members[:-1]


def _source_bounds(root: Path, plugin: str, model: str) -> dict | None:
    """Read numeric port counts and configParam ranges from our owned C++ module."""
    if plugin != "ModularSynth":
        return None
    source_file = root / "plugins" / plugin / "src" / f"{model}.cpp"
    if not source_file.is_file():
        return None
    source = source_file.read_text(encoding="utf-8")
    groups = {
        enum: _enum_members(source, enum, sentinel)
        for enum, sentinel in ENUM_MARKERS.items()
    }
    if any(members is None for members in groups.values()):
        return None

    params = groups["ParamIds"]
    assert params is not None
    ranges: dict[int, tuple[float, float]] = {}
    literal = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)[fF]?"

    # Literal-valued scalar Rack config calls (including switches).
    scalar = re.compile(
        r"\bconfig(?:Param|Switch)\s*\(\s*([A-Za-z_][A-Za-z_0-9]*)\s*,\s*"
        + literal + r"\s*,\s*" + literal + r"\s*,"
    )
    for name, lower, upper in scalar.findall(source):
        if name in params:
            ranges[params.index(name)] = (float(lower), float(upper))

    # Rack button parameters are binary 0..1. These have no explicit
    # configParam min/max but can be validated against the button contract.
    for name in re.findall(r"\bconfigButton\s*\(\s*([A-Za-z_][A-Za-z_0-9]*)\s*,", source):
        if name in params:
            ranges[params.index(name)] = (0.0, 1.0)

    # Source-backed expansion for the simple ordinal +i pattern used by
    # first-party control banks such as Macro8. Do not infer arbitrary C++.
    loops = re.compile(
        r"for\s*\(\s*int\s+i\s*=\s*0\s*;\s*i\s*<\s*(\d+)\s*;"
        r"\s*\+\+i\s*\)\s*\{(.*?)\n\s*\}", re.S
    )
    indexed = re.compile(
        r"\bconfig(?:Param|Switch)\s*\(\s*([A-Za-z_][A-Za-z_0-9]*)\s*\+\s*i\s*,\s*"
        + literal + r"\s*,\s*" + literal + r"\s*,"
    )
    for count_text, body in loops.findall(source):
        count = int(count_text)
        if count < 1 or count > 256:
            continue
        for base_name, lower, upper in indexed.findall(body):
            if base_name not in params:
                continue
            start = params.index(base_name)
            for offset in range(count):
                if start + offset < len(params):
                    ranges[start + offset] = (float(lower), float(upper))

    return {
        "params": len(params),
        "inputs": len(groups["InputIds"] or []),
        "outputs": len(groups["OutputIds"] or []),
        "ranges": ranges,
    }


def inspect_patch(path: str | Path, root: str | Path = ROOT, *, strict_unknown: bool = False) -> dict:
    """Return a serializable report. Errors mean structurally unsafe patch JSON."""
    path = Path(path)
    root = Path(root)
    report: dict[str, object] = {
        "path": str(path),
        "ok": False,
        "errors": [],
        "warnings": [],
        "module_inventory": {},
        "modules": [],
        "cables": [],
        "graph": [],
        "components": [],
    }
    errors: list[str] = report["errors"]  # type: ignore[assignment]
    warnings: list[str] = report["warnings"]  # type: ignore[assignment]
    try:
        patch = _strict_json(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Cannot decode patch as strict UTF-8 JSON: {exc}")
        return report
    if not isinstance(patch, dict):
        errors.append("Patch root must be a JSON object")
        return report
    if not isinstance(patch.get("version"), str):
        errors.append("Patch version must be a string")
    modules = patch.get("modules")
    cables = patch.get("cables")
    if not isinstance(modules, list) or not isinstance(cables, list):
        errors.append("Patch requires modules and cables arrays")
        return report

    try:
        first_party, template_references = _known_modules(root)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Cannot inspect local first-party manifests: {exc}")
        return report

    known_ids: dict[int, tuple[str, str]] = {}
    schemas: dict[int, dict | None] = {}
    inventory: Counter[str] = Counter()
    reported_unknown: set[tuple[str, str]] = set()
    for index, module in enumerate(modules):
        tag = f"module #{index}"
        if not isinstance(module, dict):
            errors.append(f"{tag}: must be an object")
            continue
        mid = module.get("id")
        if not _integer(mid) or mid < 0:
            errors.append(f"{tag}: id must be a non-negative integer")
            continue
        if mid in known_ids:
            errors.append(f"{tag}: duplicate module id {mid}")
            continue
        plugin, model = module.get("plugin"), module.get("model")
        if not isinstance(plugin, str) or not plugin or not isinstance(model, str) or not model:
            errors.append(f"{tag}: plugin and model must be nonempty strings")
            continue
        key = (plugin, model)
        known_ids[mid] = key
        inventory[f"{plugin}/{model}"] += 1
        schema = _source_bounds(root, plugin, model) if key in first_party else None
        schemas[mid] = schema
        if plugin in FIRST_PARTY and key not in first_party:
            errors.append(f"{plugin}/{model}: model absent from checked-in first-party manifest")
        elif key not in first_party and key not in reported_unknown:
            origin = "appears in a stock Cardinal patch template" if key in template_references else "is not in a checked-in first-party manifest"
            warning = f"{plugin}/{model}: {origin}; module availability and port/parameter bounds are unverified"
            (errors if strict_unknown else warnings).append(warning)
            reported_unknown.add(key)
        if key in first_party and schema is None:
            warnings.append(f"{plugin}/{model}: first-party manifest found but source-derived port/parameter bounds unavailable")
        elif schema is not None and len(schema["ranges"]) < schema["params"]:
            warnings.append(f"{plugin}/{model}: {schema['params'] - len(schema['ranges'])} parameter ranges were not determined from source")

        params = module.get("params", [])
        if not isinstance(params, list):
            errors.append(f"{tag} ({plugin}/{model}): params must be an array")
            continue
        seen_params: set[int] = set()
        for param_index, param in enumerate(params):
            label = f"{plugin}/{model}[{mid}] param #{param_index}"
            if not isinstance(param, dict):
                errors.append(f"{label}: must be an object")
                continue
            pid, value = param.get("id"), param.get("value")
            if not _integer(pid) or pid < 0:
                errors.append(f"{label}: id must be a non-negative integer")
                continue
            if pid in seen_params:
                errors.append(f"{label}: duplicate parameter index {pid}")
            seen_params.add(pid)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append(f"{label}: value must be a finite number")
                continue
            if schema is not None:
                if pid >= schema["params"]:
                    errors.append(f"{label}: index {pid} exceeds known parameter count {schema['params']}")
                elif pid in schema["ranges"]:
                    low, high = schema["ranges"][pid]
                    if not low <= value <= high:
                        errors.append(f"{label}: value {value} outside declared [{low}, {high}]")

    seen_cable_ids: set[int] = set()
    seen_inputs: dict[tuple[int, int], int] = {}
    graph: list[str] = []
    neighbors: dict[int, set[int]] = {mid: set() for mid in known_ids}
    for index, cable in enumerate(cables):
        tag = f"cable #{index}"
        if not isinstance(cable, dict):
            errors.append(f"{tag}: must be an object")
            continue
        cid = cable.get("id")
        if not _integer(cid) or cid < 0:
            errors.append(f"{tag}: id must be a non-negative integer")
            continue
        if cid in seen_cable_ids:
            errors.append(f"{tag}: duplicate cable id {cid}")
        seen_cable_ids.add(cid)
        parsed: dict[str, int] = {}
        for name in ("outputModuleId", "inputModuleId", "outputId", "inputId"):
            value = cable.get(name)
            if not _integer(value) or value < 0:
                errors.append(f"{tag}: {name} must be a non-negative integer")
            else:
                parsed[name] = value
        if len(parsed) != 4:
            continue
        source_id, target_id = parsed["outputModuleId"], parsed["inputModuleId"]
        for name, endpoint in (("outputModuleId", source_id), ("inputModuleId", target_id)):
            if endpoint not in known_ids:
                errors.append(f"{tag}: {name} {endpoint} does not exist")
        input_key = (target_id, parsed["inputId"])
        if input_key in seen_inputs:
            errors.append(
                f"{tag}: duplicate connection to input {target_id}:{parsed['inputId']} "
                f"(also cable {seen_inputs[input_key]})"
            )
        seen_inputs[input_key] = cid
        for endpoint_id, port_id, kind in (
            (source_id, parsed["outputId"], "outputs"),
            (target_id, parsed["inputId"], "inputs"),
        ):
            schema = schemas.get(endpoint_id)
            if schema is not None and port_id >= schema[kind]:
                errors.append(f"{tag}: {kind} index {port_id} exceeds known count {schema[kind]} for module {endpoint_id}")
        if source_id in known_ids and target_id in known_ids:
            src = known_ids[source_id]
            dst = known_ids[target_id]
            graph.append(
                f"{src[0]}/{src[1]}[{source_id}]:out{parsed['outputId']} -> "
                f"{dst[0]}/{dst[1]}[{target_id}]:in{parsed['inputId']}"
            )
            neighbors[source_id].add(target_id)
            neighbors[target_id].add(source_id)

    components: list[list[int]] = []
    remaining = set(known_ids)
    while remaining:
        start = min(remaining)
        component = {start}
        queue = [start]
        remaining.remove(start)
        while queue:
            for neighbor in sorted(neighbors[queue.pop()]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        components.append(sorted(component))
    report["module_inventory"] = dict(sorted(inventory.items()))
    report["modules"] = [f"{plugin}/{model}[{mid}]" for mid, (plugin, model) in sorted(known_ids.items())]
    report["cables"] = len(cables)
    report["graph"] = graph
    report["components"] = components
    report["ok"] = not errors
    return report


def _format_report(report: dict, *, show_graph: bool) -> str:
    state = "PASS" if report["ok"] else "FAIL"
    lines = [f"{state}  {report['path']}",
             f"  Modules: {sum(report['module_inventory'].values())}; cables: {report['cables']}; "
             f"connected groups: {len(report['components'])}"]
    for name, count in report["module_inventory"].items():
        lines.append(f"    {name}: {count}")
    if show_graph:
        lines.append("  Signal graph:")
        lines.extend(f"    {edge}" for edge in report["graph"])
    for issue in report["errors"]:
        lines.append(f"  ERROR: {issue}")
    for issue in report["warnings"]:
        lines.append(f"  WARNING: {issue}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "inspect"))
    parser.add_argument("patches", nargs="+", help="Plain-text .vcv files")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--strict-unknown", action="store_true",
                        help="Reject modules not present in checked-in first-party manifests")
    parser.add_argument("--json", action="store_true", help="Output structured JSON reports")
    args = parser.parse_args(argv)
    reports = [inspect_patch(path, args.repo_root, strict_unknown=args.strict_unknown)
               for path in args.patches]
    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        for result in reports:
            print(_format_report(result, show_graph=args.command == "inspect"))
    return 0 if all(result["ok"] for result in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
