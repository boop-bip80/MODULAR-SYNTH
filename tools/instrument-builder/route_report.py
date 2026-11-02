"""Human-readable, source-only Macro8 routing report for saved instruments.

A report never claims that the patch is loadable, produces audio, or exposes
host automation. Call only after instrument_builder.inspect() has verified the
bundle, patch SHA-256, and patch-derived performance manifest.
"""
from __future__ import annotations

from verified_routes import verified_routes_report


SCOPE = (
    "Saved direct Macro8 cables and source-declared input labels only; "
    "NOT a live Cardinal build, audio test, or DAW automation mapping."
)


def build_route_report(manifest: dict) -> dict:
    """Expand verified v2 mappings without reinterpreting legacy archives.

    This is an informational view, even if the optional strict-route gate
    would fail due to unknown ports. The original manifest remains untouched.
    """
    verification = verified_routes_report(manifest)
    version = manifest["formatVersion"]
    rows = []
    if version == 2:
        for mapping in manifest["performance"]["controlMappings"]:
            source = mapping["source"]
            target = mapping["destination"]
            rows.append({
                "cableId": mapping["cableId"],
                "macro": {
                    "moduleId": source["moduleId"],
                    "number": source["controlNumber"],
                    "name": source["name"],
                    "range": source["range"],
                },
                "destination": {
                    "moduleId": target["moduleId"],
                    "plugin": target["plugin"],
                    "model": target["model"],
                    "inputId": target["inputId"],
                    "kind": target["inputKind"],
                    "label": target["inputLabel"],
                    "relatedKnob": target["modulatesParameter"],
                },
                "status": (
                    "SOURCE_VERIFIED" if target["inputKind"] in ("cv", "audio")
                    else "UNVERIFIED"
                ),
            })
    return {
        "instrument": manifest["name"],
        "bundleFormatVersion": version,
        "mappingContract": (
            manifest["performance"].get("controlMappingContract")
            if version == 2 else None
        ),
        "scope": SCOPE,
        "verification": {
            "status": verification["status"],
            "reason": verification["reason"],
            "summary": verification["summary"],
        },
        "routes": rows,
    }


def text_route_report(report: dict) -> str:
    """Render musician-facing controls and ports in deterministic source order."""
    version = report["bundleFormatVersion"]
    lines = [
        f"Saved Macro8 routes: {report['instrument']} (source bundle v{version})",
        f"Scope: {report['scope']}",
    ]
    if version != 2:
        lines.append(
            "No route metadata in v1. Repack the original .vcv source with "
            "pack --format-version 2 to inspect saved direct Macro8 cables."
        )
        return "\n".join(lines) + "\n"

    rows = report["routes"]
    if not rows:
        lines.append("No direct Macro8 output cables were saved in this patch.")
    for row in rows:
        macro = row["macro"]
        target = row["destination"]
        line = (
            f"  cable {row['cableId']}: Macro8 module {macro['moduleId']} "
            f"control {macro['number']} {macro['name']!r} ({macro['range']}) "
            f"-> {target['plugin']}/{target['model']} module "
            f"{target['moduleId']} input {target['inputId']}"
        )
        if row["status"] == "SOURCE_VERIFIED":
            line += f" [{target['kind']}: {target['label']}; SOURCE_VERIFIED]"
            knob = target["relatedKnob"]
            if knob is not None:
                line += (
                    f" (source-related knob {knob['id']}: {knob['name']}; "
                    "not host automation)"
                )
        else:
            line += " [UNVERIFIED: input label and port semantics unknown]"
        lines.append(line)

    summary = report["verification"]["summary"]
    lines.append(
        f"Routes: {summary['total']} saved; "
        f"{summary['sourceVerified']} source-verified; "
        f"{summary['unverified']} unverified."
    )
    if summary["unverified"]:
        lines.append(
            "Unverified inputs are preserved as saved; they are not validated "
            "against third-party or older source port contracts."
        )
    lines.append(
        "For an optional CI gate, run check --require-verified-routes. "
        "This route view is informational and does not test sound."
    )
    return "\n".join(lines) + "\n"
