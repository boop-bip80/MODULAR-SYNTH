"""Source-only .msinstrument compatibility preflight and deterministic reports.

A declared first-party slug is NOT proof that the plugin was compiled or that
Rack/DAW can load it. Other plugin/module references always remain UNKNOWN.
"""
from __future__ import annotations

import re

FIRST_PARTY = "ModularSynth"
COLLECTION_PATH = "plugins/ModularSynth/plugin.json"
REPORT_VERSION = 1
MAX_MODULES = 256
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CompatibilityError(ValueError):
    """Malformed first-party manifest or patch model reference."""


def _label(value: object, field: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise CompatibilityError(f"{field} must be a nonempty string <= 128 chars")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise CompatibilityError(f"{field} contains control characters")
    return value


def collection_slugs(collection: dict) -> set[str]:
    if not isinstance(collection, dict) or collection.get("slug") != FIRST_PARTY:
        raise CompatibilityError("expected a ModularSynth collection manifest")
    modules = collection.get("modules")
    if not isinstance(modules, list) or not 1 <= len(modules) <= MAX_MODULES:
        raise CompatibilityError("collection modules must be a nonempty list")
    slugs: set[str] = set()
    seen_casefold: set[str] = set()
    for module in modules:
        if not isinstance(module, dict):
            raise CompatibilityError("collection module must be an object")
        slug = module.get("slug")
        if not isinstance(slug, str) or not SLUG.fullmatch(slug):
            raise CompatibilityError("invalid first-party model slug")
        if slug.casefold() in seen_casefold:
            raise CompatibilityError(f"duplicate first-party model slug: {slug}")
        seen_casefold.add(slug.casefold())
        slugs.add(slug)
    return slugs


def patch_references(patch: dict) -> dict[tuple[str, str], list[int]]:
    """Extract stable model references from ordinary Rack patches.

    This can scan patches with or without Macro8. The .msinstrument checker
    separately verifies a source bundle, which currently requires Macro8.
    """
    if not isinstance(patch, dict):
        raise CompatibilityError("VCV patch must be a JSON object")
    _label(patch.get("version"), "VCV patch version")
    modules = patch.get("modules")
    if not isinstance(modules, list) or not 1 <= len(modules) <= MAX_MODULES:
        raise CompatibilityError("VCV patch modules must contain 1..256 entries")
    ids: set[int] = set()
    references: dict[tuple[str, str], list[int]] = {}
    for module in modules:
        if not isinstance(module, dict):
            raise CompatibilityError("VCV module must be an object")
        module_id = module.get("id")
        if (type(module_id) is not int or not 0 <= module_id <= 0x7fffffffffffffff
                or module_id in ids):
            raise CompatibilityError("invalid or duplicate Rack module ID")
        ids.add(module_id)
        plugin = _label(module.get("plugin"), "plugin slug")
        model = _label(module.get("model"), "model slug")
        references.setdefault((plugin, model), []).append(module_id)
    for group in references.values():
        group.sort()
    return references


def compatibility_report(patch: dict, collection: dict, *,
                         patch_sha256: str | None = None,
                         required_plugins: list[str] | None = None) -> dict:
    if patch_sha256 is not None and (
        not isinstance(patch_sha256, str) or not SHA256.fullmatch(patch_sha256)
    ):
        raise CompatibilityError("invalid source patch SHA-256")
    slugs = collection_slugs(collection)
    model_refs = patch_references(patch)
    plugins = sorted({plugin for plugin, _ in model_refs})
    if required_plugins is not None and required_plugins != plugins:
        raise CompatibilityError("source manifest requiredPlugins mismatch")

    references: list[dict] = []
    counts = {"declared": 0, "missing": 0, "unknown": 0}
    for (plugin, model), module_ids in sorted(
        model_refs.items(),
        key=lambda entry: (entry[0][0] != FIRST_PARTY,
                           entry[0][0].casefold(), entry[0][1].casefold(),
                           entry[0][0], entry[0][1]),
    ):
        if plugin != FIRST_PARTY:
            status = "UNKNOWN"
        else:
            status = "DECLARED" if model in slugs else "MISSING"
        counts[status.lower()] += 1
        references.append({
            "plugin": plugin,
            "model": model,
            "moduleIds": module_ids,
            "status": status,
        })
    return {
        "formatVersion": REPORT_VERSION,
        "scope": "source-only; not a host or plugin-availability check",
        "status": "FAIL" if counts["missing"] else "PASS",
        "bundleIntegrity": "VERIFIED" if patch_sha256 is not None else "NOT_CHECKED",
        "patchSha256": patch_sha256,
        "firstPartyCollection": COLLECTION_PATH,
        "requiredPlugins": plugins,
        "references": references,
        "summary": counts,
    }


def text_report(report: dict) -> str:
    """Stable, human-readable report with explicit UNKNOWN semantics."""
    lines = [
        "MODULAR-SYNTH source compatibility preflight v1",
        "Bundle integrity: " + report["bundleIntegrity"]
        + (" (source ZIP and manifest SHA-256)"
           if report["bundleIntegrity"] == "VERIFIED"
           else " (raw patch reference scan only)"),
        f"First-party collection: {report['firstPartyCollection']}",
        f"Source-level result: {report['status']}",
    ]
    for reference in report["references"]:
        module_ids = ", ".join(str(value) for value in reference["moduleIds"])
        lines.append(
            f"{reference['status']:8} {reference['plugin']}/{reference['model']}"
            f"  [Rack IDs: {module_ids}]"
        )
    counts = report["summary"]
    lines.append(
        "Summary: "
        f"{counts['declared']} first-party DECLARED, "
        f"{counts['missing']} first-party MISSING, "
        f"{counts['unknown']} external UNKNOWN"
    )
    lines.append(
        "UNKNOWN = external plugin/model not checked against an installed host."
    )
    lines.append(
        "DECLARED = listed in this source collection manifest; not build/load proof."
    )
    lines.append(
        "No DAW/Rack load, third-party availability, port-bounds, or DSP checks."
    )
    if "verifiedRoutes" in report:
        routes = report["verifiedRoutes"]
        counts = routes["summary"]
        lines.append("")
        lines.append(
            f"Strict Macro8 source route check: {routes['status']} "
            f"(bundle v{routes['bundleFormatVersion']})")
        if routes["reason"] == "V1_NO_ROUTE_CONTRACT":
            lines.append(
                "No stored cable mapping contract in v1; repack from source "
                "with --format-version 2.")
        elif routes["reason"] == "NO_DIRECT_MACRO8_ROUTES":
            lines.append("No saved direct Macro8 output cables; strict route check fails.")
        else:
            lines.append(
                f"Routes: {counts['sourceVerified']} source-verified, "
                f"{counts['unverified']} unverified of {counts['total']}.")
        for route in routes["routes"]:
            lines.append(
                f"{route['status']:15} cable {route['cableId']} "
                f"Macro8 {route['sourceModuleId']} output {route['sourceOutputId']} "
                f"-> {route['plugin']}/{route['model']} "
                f"module {route['destinationModuleId']} input {route['inputId']} "
                f"({route['inputKind']})")
        lines.append(
            "SOURCE_VERIFIED = saved cable targets a first-party input port "
            "described by this source revision; not DAW parameter automation.")
        lines.append(
            "Only v2 mapped first-party Macro8 destination indices are checked; "
            "other patch cables and host port availability are not validated.")
    return "\n".join(lines) + "\n"
