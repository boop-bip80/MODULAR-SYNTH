#!/usr/bin/env python3
"""Conservative, order-independent comparison of plain-text Cardinal/VCV patches.

Offline only: this does not load plugins, render audio, or verify a DAW session.
Rack layout, cable colors/IDs and top-level module/cable array order are ignored.
Unclassified persisted data is compared rather than silently assumed cosmetic.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re
import sys
from typing import Any


class PatchComparisonError(ValueError):
    """The input is unsuitable for a reliable semantic comparison."""


MISSING = object()
SLOTS = ("A", "B", "C", "D")
MACRO8_DOCUMENTED_FIELDS = frozenset(("macro8Version", "selectedSlot", "names", "snapshots"))
# These view-only fields are explicitly exempted; unknown saved fields are
# conservatively treated as potential state, because Rack/module formats vary.
VIEW_ONLY_PATCH_FIELDS = frozenset(("zoom", "offset"))
VIEW_ONLY_MODULE_FIELDS = frozenset(("pos",))


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
        param_metadata: dict[int, dict[str, Any]] = {}
        for pindex, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise PatchComparisonError(f"{context}.params[{pindex}] must be an object")
            pid = _natural_id(entry.get("id"), f"{context}.params[{pindex}].id")
            val = entry.get("value")
            # Python's math.isfinite() converts integers to double and raises
            # OverflowError for a valid JSON integer beyond float range.
            # Such a parameter cannot represent a Rack control value; reject
            # it with our stable API error instead of a raw CLI traceback.
            try:
                finite = type(val) in (int, float) and math.isfinite(val)
            except OverflowError:
                finite = False
            if not finite:
                raise PatchComparisonError(f"{context}.params[{pindex}].value must be finite numeric")
            if pid in params:
                raise PatchComparisonError(f"{context}: duplicate parameter ID {pid}")
            params[pid] = val
            param_metadata[pid] = {key: value for key, value in entry.items()
                                   if key not in {"id", "value"}}
        data = raw.get("data", {})
        if data is None:
            data = {}
        if (plugin, model) == ("ModularSynth", "Macro8") and not isinstance(data, dict):
            raise PatchComparisonError(f"{context}.data for Macro8 must be an object")
        metadata = {key: value for key, value in raw.items()
                    if key not in {"id", "plugin", "model", "params", "data"}
                    and key not in VIEW_ONLY_MODULE_FIELDS}
        modules[mid] = {"plugin": plugin, "model": model, "params": params,
                        "param_metadata": param_metadata, "data": data,
                        "metadata": metadata}

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
        cable: dict[str, Any] = {}
        for key in ("outputModuleId", "outputId", "inputModuleId", "inputId"):
            cable[key] = _natural_id(raw.get(key), f"{context}.{key}")
        for key in ("outputModuleId", "inputModuleId"):
            if cable[key] not in modules:
                raise PatchComparisonError(f"{context}.{key}: missing module {cable[key]}")
        # Cable IDs and colors are presentation/bookkeeping fields; unknown
        # fields might be serialized routing state and must not be discarded.
        cable["metadata"] = {key: value for key, value in raw.items()
                             if key not in {"id", "color", "outputModuleId",
                                            "outputId", "inputModuleId", "inputId"}}
        cables.append(cable)
    return modules, cables


def _kind(module: dict[str, Any]) -> tuple[str, str]:
    return module["plugin"], module["model"]


def _slug(module: dict[str, Any]) -> str:
    return f"{module['plugin']}/{module['model']}"


def _match(
    old: dict[int, dict[str, Any]], new: dict[int, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[int, str], dict[int, str]]:
    """Pair stable IDs, unambiguous model instances, then unique saved states."""
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

    # Rack may regenerate IDs for a patch with multiple instances of the
    # *same* model. Recover only uniquely identifiable exact saved states;
    # this can distinguish two differently configured VCAs without inferring
    # identity from their canvas position or an arbitrary numeric ID. A state
    # fingerprint occurring twice on either side is ambiguous and deliberately
    # stays added/removed. Route rewires are checked after safe pairing.
    old_fingerprints: dict[tuple, list[int]] = defaultdict(list)
    new_fingerprints: dict[tuple, list[int]] = defaultdict(list)
    for mid in sorted(old_left):
        old_fingerprints[(_kind(old[mid]), _saved_identity(old[mid]))].append(mid)
    for mid in sorted(new_left):
        new_fingerprints[(_kind(new[mid]), _saved_identity(new[mid]))].append(mid)
    for mids in old_fingerprints.values():
        if len(mids) != 1:
            continue
        lhs = mids[0]
        fingerprint = (_kind(old[lhs]), _saved_identity(old[lhs]))
        right = new_fingerprints.get(fingerprint, ())
        if len(right) == 1:
            rhs = right[0]
            pairs.append((lhs, rhs))
            old_left.remove(lhs)
            new_left.remove(rhs)

    # A duplicate set may now have one unmatched instance per side, with the
    # other instances positively identified by their saved state. Apply the
    # same singleton-model policy used above to expose genuine edits to the
    # last remaining module instead of misreporting it as a replacement.
    old_types.clear()
    new_types.clear()
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
    # JSON booleans and numbers are distinct saved types even though Python
    # compares True == 1 and False == 0. Numeric 1 and 1.0 remain equivalent.
    same_type_or_numeric = (type(lhs) is type(rhs) or
                            (type(lhs) in (int, float) and type(rhs) in (int, float)))
    if lhs is not MISSING and rhs is not MISSING and same_type_or_numeric and lhs == rhs:
        return None
    change = "added" if lhs is MISSING else "removed" if rhs is MISSING else "changed"
    return {
        "field": field, "change": change,
        "before": None if lhs is MISSING else lhs,
        "after": None if rhs is MISSING else rhs,
    }


def _child_path(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]"
    if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", key):
        return f"{parent}.{key}" if parent else key
    return f"{parent}[{json.dumps(key, ensure_ascii=False)}]"


def _nested_changes(field: str, lhs: Any, rhs: Any) -> list[dict[str, Any]]:
    """Compare saved state deeply, preserving list order and ignoring dict order.

    This intentionally does not guess which unknown plugin keys are UI-only:
    treating a saved knob mapping or bypass flag as cosmetic is much worse than
    reporting an extra conservative state difference.
    """
    if isinstance(lhs, dict) and isinstance(rhs, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(lhs.keys() | rhs.keys()):
            changes.extend(_nested_changes(_child_path(field, key),
                                           lhs.get(key, MISSING), rhs.get(key, MISSING)))
        return changes
    if isinstance(lhs, list) and isinstance(rhs, list):
        changes = []
        for index in range(max(len(lhs), len(rhs))):
            changes.extend(_nested_changes(_child_path(field, index),
                                           lhs[index] if index < len(lhs) else MISSING,
                                           rhs[index] if index < len(rhs) else MISSING))
        return changes
    entry = _field_change(field, lhs, rhs)
    return [entry] if entry else []


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


def _edges(cables: list[dict[str, Any]], refs: dict[int, str]) -> Counter[tuple[str, int, str, int]]:
    return Counter(
        (refs[c["outputModuleId"]], c["outputId"], refs[c["inputModuleId"]], c["inputId"])
        for c in cables
    )


def _saved_identity(value: Any) -> tuple:
    """Hashable saved JSON identity: numeric 1/1.0 equal, boolean 1 distinct."""
    if isinstance(value, dict):
        return ("dict", tuple((key, _saved_identity(item))
                              for key, item in sorted(value.items())))
    if isinstance(value, list):
        return ("list", tuple(_saved_identity(item) for item in value))
    if type(value) in (int, float):
        return ("number", value)
    return (type(value).__name__, value)


def _cable_saved_state(
    before: list[dict[str, Any]], after: list[dict[str, Any]],
    old_refs: dict[int, str], new_refs: dict[int, str],
) -> list[dict[str, Any]]:
    """Compare extra cable fields independent of cable IDs and array order."""
    def group(cables: list[dict[str, Any]], refs: dict[int, str]) -> dict[tuple, list[dict[str, Any]]]:
        result: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
        for cable in cables:
            edge = (refs[cable["outputModuleId"]], cable["outputId"],
                    refs[cable["inputModuleId"]], cable["inputId"])
            result[edge].append(cable["metadata"])
        return result

    old_groups, new_groups = group(before, old_refs), group(after, new_refs)
    changes: list[dict[str, Any]] = []
    for edge in sorted(old_groups.keys() & new_groups.keys()):
        old_items, new_items = old_groups[edge], new_groups[edge]
        # Endpoint additions/removals are reported separately. Without equal
        # multiplicity there is no unambiguous existing cable to compare.
        if len(old_items) != len(new_items):
            continue
        record = {"source": edge[0], "output": edge[1],
                  "destination": edge[2], "input": edge[3]}
        if len(old_items) == 1:
            changes.extend({**record, **entry} for entry in
                           _nested_changes("cable", old_items[0], new_items[0]))
        elif Counter(map(_saved_identity, old_items)) != Counter(map(_saved_identity, new_items)):
            # Duplicate same-endpoint cables have no stable identity: avoid
            # pairing arbitrary IDs and report a deterministic group-level diff.
            order = lambda metadata: json.dumps(metadata, sort_keys=True, ensure_ascii=True)
            changes.append({**record, "field": "cable.metadata", "change": "changed",
                            "before": sorted(old_items, key=order),
                            "after": sorted(new_items, key=order)})
    return changes


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
    persisted_state: list[dict[str, Any]] = []
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
            if pid in old[lhs]["params"] and pid in new[rhs]["params"]:
                persisted_state.extend({**pair, **detail} for detail in
                                       _nested_changes(f"param[{pid}]",
                                                       old[lhs]["param_metadata"][pid],
                                                       new[rhs]["param_metadata"][pid]))
        if _kind(old[lhs]) == ("ModularSynth", "Macro8"):
            macros.extend({**pair, **entry} for entry in _macro8_changes(old[lhs]["data"], new[rhs]["data"]))
            # Known Macro8 fields retain the existing fine-grained report;
            # unknown future Macro8 fields must not disappear from the diff.
            old_data = {k: v for k, v in old[lhs]["data"].items()
                        if k not in MACRO8_DOCUMENTED_FIELDS}
            new_data = {k: v for k, v in new[rhs]["data"].items()
                        if k not in MACRO8_DOCUMENTED_FIELDS}
        else:
            old_data, new_data = old[lhs]["data"], new[rhs]["data"]
        persisted_state.extend({**pair, **entry} for entry in
                               _nested_changes("data", old_data, new_data))
        persisted_state.extend({**pair, **entry} for entry in
                               _nested_changes("module", old[lhs]["metadata"], new[rhs]["metadata"]))
    patch_state = _nested_changes(
        "patch",
        {k: v for k, v in before.items()
         if k not in {"modules", "cables"} and k not in VIEW_ONLY_PATCH_FIELDS},
        {k: v for k, v in after.items()
         if k not in {"modules", "cables"} and k not in VIEW_ONLY_PATCH_FIELDS},
    )
    before_edges, after_edges = _edges(old_cables, old_refs), _edges(new_cables, new_refs)
    cable_state = _cable_saved_state(old_cables, new_cables, old_refs, new_refs)
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
        "persisted_state_changed": len(persisted_state),
        "patch_state_changed": len(patch_state),
        "cable_state_changed": len(cable_state),
        "cables_added": sum(c["count"] for c in cable_added),
        "cables_removed": sum(c["count"] for c in cable_removed),
    }
    summary["changed"] = any(summary[key] for key in (
        "modules_added", "modules_removed", "parameters_changed",
        "macro8_state_changed", "persisted_state_changed", "patch_state_changed",
        "cable_state_changed", "cables_added", "cables_removed",
    ))
    return {
        "before": before_label, "after": after_label, "summary": summary,
        "modules": {
            "added": added, "removed": removed, "id_remaps": remaps,
            "parameters": parameters, "macro8_state": macros,
            "persisted_state": persisted_state,
        },
        "patch_state": patch_state,
        "cables": {"added": cable_added, "removed": cable_removed,
                   "saved_state": cable_state},
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
        f"{stats['persisted_state_changed']} other saved module fields, "
        f"{stats['patch_state_changed']} patch fields, "
        f"{stats['cable_state_changed']} saved cable fields, "
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
        ("Other saved module state changes", report["modules"]["persisted_state"]),
    ):
        if items:
            lines.append(f"{heading}:")
            for item in items:
                field = f"param {item['parameter_id']}" if "parameter_id" in item else item["field"]
                lines.append(
                    f"  {item['ref']} {field}: "
                    f"{_display_value(item, 'before')} -> {_display_value(item, 'after')}"
                )
    if report["patch_state"]:
        lines.append("Saved patch-level state changes:")
        for item in report["patch_state"]:
            lines.append(
                f"  {item['field']}: "
                f"{_display_value(item, 'before')} -> {_display_value(item, 'after')}"
            )
    if report["cables"]["saved_state"]:
        lines.append("Saved cable state changes:")
        for item in report["cables"]["saved_state"]:
            lines.append(
                f"  {item['source']}:out{item['output']} -> "
                f"{item['destination']}:in{item['input']} {item['field']}: "
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
