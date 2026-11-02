"""Deterministic semantic comparison of two validated .msinstrument source bundles.

This module deliberately does not read ZIPs itself. The caller MUST validate
both archives through instrument_builder.read_bundle() before invoking it.
It compares saved Rack JSON, not running engines, MIDI or DAW host state.
"""
from __future__ import annotations

import json

SLOTS = ("A", "B", "C", "D")
SCOPE = (
    "Saved patch JSON and source-derived Macro8 metadata only; "
    "NOT plugin loadability, emitted CV/audio, or DAW automation. "
    "Historical mapping contracts are never upgraded."
)


def _by_id(entries: list[dict]) -> dict[int, dict]:
    """The validated patch/manifest guarantees unique integer IDs."""
    return {entry["id"] if "id" in entry else entry["moduleId"]: entry
            for entry in entries}


def _delta(before: dict[int, dict], after: dict[int, dict]) -> dict:
    prior, current = set(before), set(after)
    return {
        "added": sorted(current - prior),
        "removed": sorted(prior - current),
        "modified": sorted(
            key for key in prior & current if before[key] != after[key]),
    }


def _macro_changes(before: dict, after: dict) -> dict:
    changed_fields = sorted(
        field for field in before.keys() | after.keys()
        if before.get(field) != after.get(field))
    affected_controls = []
    for index in range(8):
        if any(before[field][index] != after[field][index]
               for field in ("names", "ranges", "liveValues")) or any(
            (old_row is None) != (new_row is None) or (
                old_row is not None and new_row is not None
                and old_row[index] != new_row[index])
            for old_row, new_row in zip(
                before["snapshots"], after["snapshots"])
        ):
            affected_controls.append(index + 1)
    changed_slots = [
        slot for slot, old, new in zip(
            SLOTS, before["snapshots"], after["snapshots"])
        if old != new
    ]
    return {
        "moduleId": before["moduleId"],
        "fields": changed_fields,
        "controlNumbers": affected_controls,
        "snapshotSlots": changed_slots,
    }


def compare_verified_bundles(
    old_manifest: dict, old_patch: bytes,
    new_manifest: dict, new_patch: bytes,
) -> dict:
    """Compare independently validated sources, ignoring JSON formatting.

    A change to Rack module/cable array order alone does not count as a
    semantic difference. All top-level patch fields and each module/cable
    object DO count. A whitespace-only source rewrite is reported separately.
    """
    before = json.loads(old_patch)
    after = json.loads(new_patch)
    modules = _delta(_by_id(before["modules"]), _by_id(after["modules"]))
    cables = _delta(
        _by_id(before.get("cables", [])), _by_id(after.get("cables", [])))
    patch_metadata_changed = sorted(
        field for field in before.keys() | after.keys()
        if field not in ("modules", "cables")
        and before.get(field) != after.get(field))
    old_macros = _by_id(old_manifest["performance"]["macro8"])
    new_macros = _by_id(new_manifest["performance"]["macro8"])
    macro_ids = _delta(old_macros, new_macros)
    macro_details = [
        _macro_changes(old_macros[key], new_macros[key])
        for key in macro_ids["modified"]
    ]
    old_contract = old_manifest["performance"].get("controlMappingContract")
    new_contract = new_manifest["performance"].get("controlMappingContract")
    name_changed = old_manifest["name"] != new_manifest["name"]
    version_changed = (
        old_manifest["formatVersion"] != new_manifest["formatVersion"])
    contract_changed = old_contract != new_contract
    graph_changed = bool(
        patch_metadata_changed
        or any(modules.values()) or any(cables.values()))
    changed = (
        name_changed or version_changed or contract_changed or graph_changed
        or any(macro_ids.values()))
    return {
        "scope": SCOPE,
        "from": {
            "name": old_manifest["name"],
            "formatVersion": old_manifest["formatVersion"],
            "mappingContract": old_contract,
            "patchSha256": old_manifest["patch"]["sha256"],
        },
        "to": {
            "name": new_manifest["name"],
            "formatVersion": new_manifest["formatVersion"],
            "mappingContract": new_contract,
            "patchSha256": new_manifest["patch"]["sha256"],
        },
        "changed": bool(changed),
        "sourcePatchBytesChanged": old_patch != new_patch,
        "changes": {
            "name": name_changed,
            "formatVersion": version_changed,
            "mappingContract": contract_changed,
            "patchMetadataFields": patch_metadata_changed,
            "modules": modules,
            "cables": cables,
            "macro8": {
                "added": macro_ids["added"],
                "removed": macro_ids["removed"],
                "modified": macro_details,
            },
        },
    }


def text_diff_report(report: dict) -> str:
    """Stable plain-text presentation; useful without JSON diff tooling."""
    previous, current = report["from"], report["to"]
    changes = report["changes"]
    lines = [
        f"Saved instrument difference: {previous['name']} -> {current['name']}",
        f"Scope: {report['scope']}",
        f"Semantic saved-state changes: {'YES' if report['changed'] else 'NO'}",
        "Source patch bytes differ: "
        + ("YES" if report["sourcePatchBytesChanged"] else "NO"),
    ]
    if changes["name"]:
        lines.append("Instrument display name changed.")
    if changes["formatVersion"] or changes["mappingContract"]:
        lines.append(
            "Saved mapping interpretation changed: "
            f"v{previous['formatVersion']} / "
            f"{previous['mappingContract'] or 'unmarked'} -> "
            f"v{current['formatVersion']} / "
            f"{current['mappingContract'] or 'unmarked'} "
            "(historical routes are never reclassified in-place)."
        )
    if changes["patchMetadataFields"]:
        lines.append(
            "Patch-level fields changed: "
            + ", ".join(changes["patchMetadataFields"]))
    for kind in ("modules", "cables"):
        delta = changes[kind]
        lines.append(
            f"Saved {kind}: +{len(delta['added'])} "
            f"-{len(delta['removed'])} ~{len(delta['modified'])} "
            "(IDs in JSON report)"
        )
    macro = changes["macro8"]
    lines.append(
        f"Macro8 controllers: +{len(macro['added'])} "
        f"-{len(macro['removed'])} ~{len(macro['modified'])}"
    )
    for item in macro["modified"]:
        changed_controls = ",".join(map(str, item["controlNumbers"])) or "none"
        changed_slots = ",".join(item["snapshotSlots"]) or "none"
        lines.append(
            f"  Macro8 {item['moduleId']}: "
            f"fields {','.join(item['fields'])}; "
            f"controls {changed_controls}; scenes {changed_slots}"
        )
    if not report["changed"] and report["sourcePatchBytesChanged"]:
        lines.append(
            "Only source JSON serialization/order changed; "
            "saved module/cable/metadata content is equivalent."
        )
    lines.append(
        "This comparison does not test that either patch loads, sounds, "
        "automates or restores inside a DAW."
    )
    return "\n".join(lines) + "\n"
