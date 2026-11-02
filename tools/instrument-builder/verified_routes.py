"""Opt-in, source-only verification of saved Macro8 cable destinations.

Only call this after read_bundle() has validated the archive and re-derived the
manifest. A source-verified input name/port is not a functioning host mapping.
"""
from __future__ import annotations


SOURCE_SCOPE = (
    "saved direct Macro8 cables and source-declared input ports only; "
    "not host automation, installed-plugin availability or audio behavior"
)


def verified_routes_report(manifest: dict) -> dict:
    """Describe all Macro8 routes; fail closed on missing/unknown contracts.

    Legacy v1 contains no mapping contract, so it must not report an empty
    verified route set. Old unmarked v2 bundles retain their original
    conservative ``unverified`` destination records after read_bundle().
    """
    version = manifest["formatVersion"]
    report = {
        "scope": SOURCE_SCOPE,
        "bundleFormatVersion": version,
        "status": "FAIL",
        "reason": None,
        "summary": {"total": None, "sourceVerified": None, "unverified": None},
        "routes": [],
    }
    if version != 2:
        report["reason"] = "V1_NO_ROUTE_CONTRACT"
        return report

    mappings = manifest["performance"]["controlMappings"]
    routes = []
    for mapping in mappings:
        destination = mapping["destination"]
        verified = destination["inputKind"] in ("cv", "audio")
        routes.append({
            "cableId": mapping["cableId"],
            "sourceModuleId": mapping["source"]["moduleId"],
            "sourceOutputId": mapping["source"]["outputId"],
            "destinationModuleId": destination["moduleId"],
            "plugin": destination["plugin"],
            "model": destination["model"],
            "inputId": destination["inputId"],
            "inputKind": destination["inputKind"],
            "status": "SOURCE_VERIFIED" if verified else "UNVERIFIED",
        })
    # Source patch ordering and the route derivation's grouping by source
    # output must not affect how diagnostics appear to callers.
    routes.sort(key=lambda item: (
        item["cableId"], item["sourceModuleId"], item["sourceOutputId"],
        item["destinationModuleId"], item["inputId"],
    ))
    verified_count = sum(route["status"] == "SOURCE_VERIFIED" for route in routes)
    unknown_count = len(routes) - verified_count
    report["routes"] = routes
    report["summary"] = {
        "total": len(routes),
        "sourceVerified": verified_count,
        "unverified": unknown_count,
    }
    if not routes:
        report["reason"] = "NO_DIRECT_MACRO8_ROUTES"
    elif unknown_count:
        report["reason"] = "UNVERIFIED_DESTINATIONS"
    else:
        report["status"] = "PASS"
    return report
