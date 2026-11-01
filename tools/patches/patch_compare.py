#!/usr/bin/env python3
"""Semantic, order-independent comparison of plain-text Cardinal/VCV patches.

Offline only: this does not load plugins, render audio, or verify a DAW session.
Rack layout, cable colors/IDs and JSON array ordering are not musical changes.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import sys
from typing import Any


class PatchComparisonError(ValueError):
    """The input is unsuitable for a reliable semantic comparison."""


MISSING = object()
SLOTS = ("A", "B", "C", "D")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PatchComparisonError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _no_constants(token: str) -> Any:
    raise PatchComparisonError(f"non-finite JSON literal: {token}")


def load_patch(path: Path) -> dict[str, Any]:
    """Strict UTF-8 JSON, including duplicate-key and NaN/Infinity rejection."""
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(
                stream, object_pairs_hook=_unique_object, parse_constant=_no_constants
            )
    except (OSError, UnicodeError, ValueError) as exc:
        raise PatchComparisonError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PatchComparisonError(f"{path}: patch root must be an object")
    return value


def _natural_id(value: Any, description: str) -> int:
    if type(value) is not int or value < 0:
        raise PatchComparisonError(f"{description} must be a non-negative integer")
    return value


def _finite_recursive(value: Any, path: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise PatchComparisonError(f"{path}: non-finite number")
    if isinstance(value, dict):
        for key, item in value.items():
            _finite_recursive(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _finite_recursive(item, f"{path}[{index}]")


def _parse_patch(patch: dict[str, Any]) -> tuple[dict[int, dict[str, Any]], list[dict[str, int]]]:
    if not isinstance(patch, dict):
        raise PatchComparisonError("patch root must be an object")
    _finite_recursive(patch, "patch")
    raw_modules, raw_cables = patch.get("modules"), patch.get("cables")
    if not isinstance(raw_modules, list) or not isinstance(raw_cables, list):
        raise PatchComparisonError("patch requires modules and cables arrays")

    modules: dict[int, dict[str, Any]] = {}
    for index, raw in enumerate(raw_modules):
        context = f"modules[{index}]"
        if not isinstance(raw, dict):
            raise PatchComparisonError(f"{context} must be an object")
        mid = _natural_id(raw.get("id"), f"{context}.id")
        if mid in modules:
            raise PatchComparisonError(f"duplicate module ID {mid}")
        plugin, model = raw.get("plugin"), raw.get("model")
        if not isinstance(plugin, str) or not plugin or not isinstance(model, str) or not model:
            raise PatchComparisonError(f"{context}: plugin/model must be non-empty strings")
        entries = raw.get("params", [])
        if not isinstance(entries, list):
            raise PatchComparisonError(f"{context}.params must be an array")
        params: dict[int, int | float] = {}
        for pindex, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise PatchComparisonError(f"{context}.params[{pindex}] must be an object")
            pid = _natural_id(entry.get("id"), f"{context}.params[{pindex}].id")
            val = entry.get("value")
            if type(val) not in (int, float) or not math.isfinite(val):
                raise PatchComparisonError(f"{context}.params[{pindex}].value must be finite numeric")
            if pid in params:
                raise PatchComparisonError(f"{context}: duplicate parameter ID {pid}")
            params[pid] = val
        data = raw.get("data", {})
        if data is None:
            data = {}
        if (plugin, model) == ("ModularSynth", "Macro8") and not isinstance(data, dict):
            raise PatchComparisonError(f"{context}.data for Macro8 must be an object")
        modules[mid] = {"plugin": plugin, "model": model, "params": params, "data": data}

    cables: list[dict[str, int]] = []
    seen: set[int] = set()
    for index, raw in enumerate(raw_cables):
        context = f"cables[{index}]"
        if not isinstance(raw, dict):
            raise PatchComparisonError(f"{context} must be an object")
        cid = _natural_id(raw.get("id"), f"{context}.id")
        if cid in seen:
            raise PatchComparisonError(f"duplicate cable ID {cid}")
        seen.add(cid)
        cable: dict[str, int] = {}
        for key in ("outputModuleId", "outputId", "inputModuleId", "inputId"):
            cable[key] = _natural_id(raw.get(key), f"{context}.{key}")
        for key in ("outputModuleId", "inputModuleId"):
            if cable[key] not in modules:
                raise PatchComparisonError(f"{context}.{key}: missing module {cable[key]}")
        cables.append(cable)
    return modules, cables


def _kind(module: dict[str, Any]) -> tuple[str, str]:
    return module["plugin"], module["model"]


def _slug(module: dict[str, Any]) -> str:
    return f"{module['plugin']}/{module['model']}"


def _match(
    old: dict[int, dict[str, Any]], new: dict[int, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[int, str], dict[int, str]]:
    """Stable IDs first; otherwise pair only the unique remaining instance of a type."""
    old_left, new_left = set(old), set(new)
    pairs: list[tuple[int, int]] = []
    for mid in sorted(old_left & new_left):
        if _kind(old[mid]) == _kind(new[mid]):
            pairs.append((mid, mid))
            old_left.remove(mid)
            new_left.remove(mid)
    old_types: dict[tuple[str, str], list[int]] = defaultdict(list)
    new_types: dict[tuple[str, str], list[int]] = defaultdict(list)
    for mid in sorted(old_left):
        old_types[_kind(old[mid])].append(mid)
    for mid in sorted(new_left):
        new_types[_kind(new[mid])].append(mid)
    for kind in sorted(set(old_types) & set(new_types)):
        if len(old_types[kind]) == len(new_types[kind]) == 1:
            lhs, rhs = old_types[kind][0], new_types[kind][0]
            pairs.append((lhs, rhs))
            old_left.remove(lhs)
            new_left.remove(rhs)

    old_count = Counter(_kind(m) for m in old.values())
    new_count = Counter(_kind(m) for m in new.values())
    paired: list[dict[str, Any]] = []
    old_refs: dict[int, str] = {}
    new_refs: dict[int, str] = {}
    for lhs, rhs in sorted(pairs, key=lambda ids: (_kind(old[ids[0]]), ids[0], ids[1])):
        kind = _kind(old[lhs])
        slug = _slug(old[lhs])
        ref = slug if old_count[kind] == new_count[kind] == 1 else f"{slug}#{lhs}"
        paired.append({"module": slug, "ref": ref, "before_id": lhs, "after_id": rhs})
        old_refs[lhs] = new_refs[rhs] = ref

    removed: list[dict[str, Any]] = []
    added: list[dict[str, Any]] = []
    for mid in sorted(old_left, key=lambda ident: (_kind(old[ident]), ident)):
        ref = f"{_slug(old[mid])}#{mid}"
        old_refs[mid] = ref
        removed.append({"module": _slug(old[mid]), "id": mid, "ref": ref})
    for mid in sorted(new_left, key=lambda ident: (_kind(new[ident]), ident)):
        ref = f"{_slug(new[mid])}#{mid}"
        new_refs[mid] = ref
        added.append({"module": _slug(new[mid]), "id": mid, "ref": ref})
    return paired, removed, added, old_refs, new_refs


def _field_change(field: str, lhs: Any, rhs: Any) -> dict[str, Any] | None:
    if lhs is MISSING and rhs is MISSING:
        return None
    if lhs is not MISSING and rhs is not MISSING and lhs == rhs:
        return None
    change = "added" if lhs is MISSING else "removed" if rhs is MISSING else "changed"
    return {
        "field": field, "change": change,
        "before": None if lhs is MISSING else lhs,
        "after": None if rhs is MISSING else rhs,
    }


def _macro8_changes(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for field in ("macro8Version", "selectedSlot"):
        entry = _field_change(field, old.get(field, MISSING), new.get(field, MISSING))
        if entry:
            changes.append(entry)
    left_names, right_names = old.get("names", MISSING), new.get("names", MISSING)
    if isinstance(left_names, list) and isinstance(right_names, list):
        for index in range(max(len(left_names), len(right_names))):
            lhs = left_names[index] if index < len(left_names) else MISSING
            rhs = right_names[index] if index < len(right_names) else MISSING
            entry = _field_change(f"name[{index + 1}]", lhs, rhs)
            if entry:
                changes.append(entry)
    else:
        entry = _field_change("names", left_names, right_names)
        if entry:
            changes.append(entry)
    left_slots, right_slots = old.get("snapshots", MISSING), new.get("snapshots", MISSING)
    if isinstance(left_slots, list) and isinstance(right_slots, list):
        for index in range(max(len(left_slots), len(right_slots))):
            name = SLOTS[index] if index < len(SLOTS) else str(index + 1)
            lhs = left_slots[index] if index < len(left_slots) else MISSING
            rhs = right_slots[index] if index < len(right_slots) else MISSING
            if isinstance(lhs, list) and isinstance(rhs, list):
                for knob in range(max(len(lhs), len(rhs))):
                    before = lhs[knob] if knob < len(lhs) else MISSING
                    after = rhs[knob] if knob < len(rhs) else MISSING
                    entry = _field_change(f"snapshot[{name}].macro{knob + 1}", before, after)
                    if entry:
                        changes.append(entry)
            else:
                entry = _field_change(f"snapshot[{name}]", lhs, rhs)
                if entry:
                    changes.append(entry)
    else:
        entry = _field_change("snapshots", left_slots, right_slots)
        if entry:
            changes.append(entry)
    return changes


def _edges(cables: list[dict[str, int]], refs: dict[int, str]) -> Counter[tuple[str, int, str, int]]:
    return Counter(
        (refs[c["outputModuleId"]], c["outputId"], refs[c["inputModuleId"]], c["inputId"])
        for c in cables
    )


def _edge_record(edge: tuple[str, int, str, int], count: int) -> dict[str, Any]:
    return {
        "source": edge[0], "output": edge[1],
        "destination": edge[2], "input": edge[3], "count": count,
    }


def compare_patches(
    before: dict[str, Any], after: dict[str, Any],
    *, before_label: str = "before", after_label: str = "after",
) -> dict[str, Any]:
    """Return a deterministic, JSON-serializable semantic report."""
    old, old_cables = _parse_patch(before)
    new, new_cables = _parse_patch(after)
    paired, removed, added, old_refs, new_refs = _match(old, new)
    parameters: list[dict[str, Any]] = []
    macros: list[dict[str, Any]] = []
    remaps: list[dict[str, Any]] = []
    for pair in paired:
        lhs, rhs = pair["before_id"], pair["after_id"]
        if lhs != rhs:
            remaps.append(pair)
        for pid in sorted(set(old[lhs]["params"]) | set(new[rhs]["params"])):
            entry = _field_change(
                str(pid), old[lhs]["params"].get(pid, MISSING),
                new[rhs]["params"].get(pid, MISSING),
            )
            if entry:
                parameters.append({
                    **pair, "parameter_id": pid, "change": entry["change"],
                    "before": entry["before"], "after": entry["after"],
                })
        if _kind(old[lhs]) == ("ModularSynth", "Macro8"):
            macros.extend({**pair, **entry} for entry in _macro8_changes(old[lhs]["data"], new[rhs]["data"]))
    before_edges, after_edges = _edges(old_cables, old_refs), _edges(new_cables, new_refs)
    cable_added: list[dict[str, Any]] = []
    cable_removed: list[dict[str, Any]] = []
    for edge in sorted(set(before_edges) | set(after_edges)):
        delta = after_edges[edge] - before_edges[edge]
        if delta > 0:
            cable_added.append(_edge_record(edge, delta))
        elif delta < 0:
            cable_removed.append(_edge_record(edge, -delta))
    summary = {
        "matched_modules": len(paired),
        "modules_added": len(added),
        "modules_removed": len(removed),
        "id_remaps_ignored": len(remaps),
        "parameters_changed": len(parameters),
        "macro8_state_changed": len(macros),
        "cables_added": sum(c["count"] for c in cable_added),
        "cables_removed": sum(c["count"] for c in cable_removed),
    }
    summary["changed"] = any(summary[key] for key in (
        "modules_added", "modules_removed", "parameters_changed",
        "macro8_state_changed", "cables_added", "cables_removed",
    ))
    return {
        "before": before_label, "after": after_label, "summary": summary,
        "modules": {
            "added": added, "removed": removed, "id_remaps": remaps,
            "parameters": parameters, "macro8_state": macros,
        },
        "cables": {"added": cable_added, "removed": cable_removed},
    }


def _display_value(item: dict[str, Any], side: str) -> str:
    absent = (side == "before" and item["change"] == "added") or (
        side == "after" and item["change"] == "removed"
    )
    return "(missing)" if absent else json.dumps(item[side], ensure_ascii=False, sort_keys=True)


def format_report(report: dict[str, Any]) -> str:
    """Display the same stable ordering used by the JSON report."""
    stats = report["summary"]
    lines = [f"Patch comparison: {report['before']} -> {report['after']}"]
    lines.append(
        f"  Modules: {stats['matched_modules']} matched, {stats['modules_added']} added, "
        f"{stats['modules_removed']} removed; {stats['id_remaps_ignored']} ID remaps ignored"
    )
    lines.append(
        f"  Changes: {stats['parameters_changed']} parameters, "
        f"{stats['macro8_state_changed']} Macro8 state fields, "
        f"{stats['cables_added']} cables added, {stats['cables_removed']} cables removed"
    )
    for heading, items, prefix in (
        ("Modules added", report["modules"]["added"], "+"),
        ("Modules removed", report["modules"]["removed"], "-"),
    ):
        if items:
            lines.append(f"{heading}:")
            lines.extend(f"  {prefix} {item['ref']}" for item in items)
    for heading, items in (
        ("Parameter changes", report["modules"]["parameters"]),
        ("Macro8 state changes", report["modules"]["macro8_state"]),
    ):
        if items:
            lines.append(f"{heading}:")
            for item in items:
                field = f"param {item['parameter_id']}" if "parameter_id" in item else item["field"]
                lines.append(
                    f"  {item['ref']} {field}: "
                    f"{_display_value(item, 'before')} -> {_display_value(item, 'after')}"
                )
    for heading, items, prefix in (
        ("Cables added", report["cables"]["added"], "+"),
        ("Cables removed", report["cables"]["removed"], "-"),
    ):
        if items:
            lines.append(f"{heading}:")
            for item in items:
                lines.append(
                    f"  {prefix} {item['source']}:out{item['output']} -> "
                    f"{item['destination']}:in{item['input']} (x{item['count']})"
                )
    if not stats["changed"]:
        lines.append("No semantic changes.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path, help="Original plain-text .vcv patch")
    parser.add_argument("after", type=Path, help="Modified plain-text .vcv patch")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON report")
    args = parser.parse_args(argv)
    try:
        report = compare_patches(
            load_patch(args.before), load_patch(args.after),
            before_label=str(args.before), after_label=str(args.after),
        )
    except PatchComparisonError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        if args.json else format_report(report)
    )
    return 1 if report["summary"]["changed"] else 0


if __name__ == "__main__":
    sys.exit(main())
