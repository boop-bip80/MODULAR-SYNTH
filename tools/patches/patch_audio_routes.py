#!/usr/bin/env python3
"""Audit saved patch wiring toward Cardinal HostAudio2 without executing audio.

Port identity is sourced from the checked-in HostAudio2 implementation via
patch_inspector. Graph reachability alone cannot establish audible signal.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from patch_inspector import ROOT, _source_bounds, _strict_json, inspect_patch


# These models are designated as modulation/control sources in their checked-in
# implementation, not audio generators. A direct cable to HostAudio2 is only an
# advisory; creative audio-rate CV patching is valid.
CONTROL_SOURCE_MODELS = frozenset({
    ("ModularSynth", "Macro8"),
    ("ModularSynth", "ClockedLFO"),
    ("Cardinal", "HostMIDI"),
    ("Cardinal", "HostTime"),
})
# Narrow, first-party audio voices with source-defined output ports. Unknown
# bundled/third-party modules are deliberately omitted.
FIRST_PARTY_GENERATORS = frozenset({
    ("ModularSynth", "MorphVCO"),
    ("ModularSynth", "FMVoice"),
})


def _source_verified_output(root: Path, key: tuple[str, str], port: int) -> bool:
    schema = _source_bounds(root, *key)
    return schema is not None and 0 <= port < schema["outputs"]


def audit_output_routes(path: str | Path, root: str | Path = ROOT) -> dict:
    """Describe all wired HostAudio2 inputs and their upstream cable ancestry.

    A valid patch and source-verified HostAudio2 port counts are prerequisites
    to claiming even a *wired terminal input*. The result never claims sound.
    """
    path, root = Path(path), Path(root)
    inspection = inspect_patch(path, root)
    result: dict = {
        "path": str(path),
        "ok": inspection["ok"],
        "errors": list(inspection["errors"]),
        "warnings": list(inspection["warnings"]),
        "host_contract_verified": False,
        "has_wired_host_input": False,
        "sinks": [],
        "control_source_hints": [],
        "unrouted_first_party_generators": [],
        "advisories": [],
    }
    if not inspection["ok"]:
        result["advisories"].append("Invalid patch; audio-routing inspection skipped.")
        return result

    # inspect_patch already decoded strict JSON and checked duplicate IDs,
    # dangling endpoints and the source-known port ranges.
    patch = _strict_json(path)
    modules = {module["id"]: module for module in patch["modules"]}
    incoming: dict[int, list[dict]] = {mid: [] for mid in modules}
    outgoing: dict[int, list[dict]] = {mid: [] for mid in modules}
    for cable in patch["cables"]:
        incoming[cable["inputModuleId"]].append(cable)
        outgoing[cable["outputModuleId"]].append(cable)

    schema = _source_bounds(root, "Cardinal", "HostAudio2")
    result["host_contract_verified"] = (
        schema is not None and schema["inputs"] == 2 and schema["outputs"] == 2
    )
    hosts = sorted(
        (mid for mid, mod in modules.items()
         if (mod["plugin"], mod["model"]) == ("Cardinal", "HostAudio2"))
    )
    if not result["host_contract_verified"]:
        result["advisories"].append(
            "Checked-in HostAudio2 source port contract was not verified; "
            "terminal-input interpretation is unavailable."
        )
        return result
    if not hosts:
        result["advisories"].append(
            "No Cardinal/HostAudio2 module found; this audit does not assess "
            "alternative terminal modules or other plugin variants."
        )

    for host_id in hosts:
        endpoints = {cable["inputId"]: cable for cable in incoming[host_id]}
        inputs: list[dict] = []
        upstream: set[int] = set()
        for jack, name in ((0, "Left/M"), (1, "Right")):
            cable = endpoints.get(jack)
            if cable is None:
                inputs.append({"port": jack, "label": name, "connected": False,
                               "source": None})
                continue
            src_id = cable["outputModuleId"]
            source = modules[src_id]
            inputs.append({
                "port": jack, "label": name, "connected": True,
                "source": {
                    "module_id": src_id,
                    "model": f"{source['plugin']}/{source['model']}",
                    "output_port": cable["outputId"],
                },
            })
            source_key = (source["plugin"], source["model"])
            if (source_key in CONTROL_SOURCE_MODELS
                    and _source_verified_output(root, source_key, cable["outputId"])):
                result["control_source_hints"].append({
                    "host_module_id": host_id, "input_port": jack,
                    "module_id": src_id,
                    "model": f"{source_key[0]}/{source_key[1]}",
                    "output_port": cable["outputId"],
                })
                result["advisories"].append(
                    f"HostAudio2[{host_id}] {name} is fed directly by the "
                    f"control-oriented {source_key[0]}/{source_key[1]}[{src_id}] "
                    f"output {cable['outputId']}; check whether this is intentional."
                )
            # Reverse, module-level cable graph only. Includes CV and gates;
            # the traversal deliberately does not assert signal processing.
            todo = [src_id]
            while todo:
                current = todo.pop()
                if current in upstream:
                    continue
                upstream.add(current)
                todo.extend(edge["outputModuleId"] for edge in incoming[current])
        sink = {
            "module_id": host_id,
            "inputs": inputs,
            "connected_ports": sorted(endpoints),
            "upstream_modules": [
                {"module_id": mid,
                 "model": f"{modules[mid]['plugin']}/{modules[mid]['model']}"}
                for mid in sorted(upstream)
            ],
        }
        result["sinks"].append(sink)
        if endpoints:
            result["has_wired_host_input"] = True
        else:
            result["advisories"].append(
                f"HostAudio2[{host_id}] has neither terminal input wired."
            )
        if 1 in endpoints and 0 not in endpoints:
            result["advisories"].append(
                f"HostAudio2[{host_id}] has only Right wired; Left/M is unpatched."
            )
    if not result["has_wired_host_input"]:
        result["advisories"].append(
            "No HostAudio2 terminal input is wired; the checked graph has no "
            "direct cable route into this host output."
        )

    # A generator may be disconnected even when another voice reaches the
    # host. Track directed *module-level* cable reachability only; do not
    # treat CV paths, unknown processors or cycles as verified audio.
    wired_hosts = {mid for mid in hosts if incoming[mid]}
    for module_id, generator in sorted(modules.items()):
        key = (generator["plugin"], generator["model"])
        if key not in FIRST_PARTY_GENERATORS:
            continue
        schema = _source_bounds(root, *key)
        if schema is None or schema["outputs"] < 1:
            continue  # Source drift: no audio-generator claim without schema.
        seen = {module_id}
        stack = [module_id]
        reaches_host = False
        while stack:
            current = stack.pop()
            if current in wired_hosts:
                reaches_host = True
                break
            for cable in outgoing[current]:
                target = cable["inputModuleId"]
                if target not in seen:
                    seen.add(target)
                    stack.append(target)
        if reaches_host:
            continue
        item = {"module_id": module_id, "model": f"{key[0]}/{key[1]}"}
        result["unrouted_first_party_generators"].append(item)
        result["advisories"].append(
            f"{item['model']}[{module_id}] has no directed cable-graph route "
            "to a wired HostAudio2 terminal; this may be intentional."
        )
    return result


def format_output_routes(result: dict) -> str:
    lines = [f"{'PASS' if result['ok'] else 'FAIL'}  {result['path']}",
             "  HostAudio2 source contract: "
             + ("verified" if result["host_contract_verified"] else "unverified")]
    for sink in result["sinks"]:
        lines.append(f"  HostAudio2[{sink['module_id']}]")
        for port in sink["inputs"]:
            if port["source"] is None:
                lines.append(f"    {port['label']}: unpatched")
            else:
                src = port["source"]
                lines.append(
                    f"    {port['label']}: {src['model']}[{src['module_id']}]"
                    f":out{src['output_port']}"
                )
        lines.append(
            f"    Upstream graph nodes: {len(sink['upstream_modules'])}"
            " (includes CV/gate paths; not proof of audio)"
        )
    if result["unrouted_first_party_generators"]:
        lines.append(
            f"  First-party voices without a host cable-graph route: "
            f"{len(result['unrouted_first_party_generators'])}"
        )
    for issue in result["errors"]:
        lines.append(f"  ERROR: {issue}")
    for issue in result["warnings"]:
        lines.append(f"  WARNING: {issue}")
    for issue in result["advisories"]:
        lines.append(f"  ADVISORY: {issue}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patches", nargs="+", help="Plain-text .vcv files")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", help="Structured reports")
    parser.add_argument(
        "--require-host-input", action="store_true",
        help="Exit 1 if a structurally valid patch has no source-verified "
             "wired Cardinal/HostAudio2 input; not an audible-audio test",
    )
    parser.add_argument(
        "--require-generator-route", action="store_true",
        help="Exit 1 if a source-verified first-party MorphVCO/FMVoice lacks "
             "a directed cable-graph path to a wired HostAudio2 input; "
             "does not verify sound or audio-rate processing",
    )
    args = parser.parse_args(argv)
    reports = [audit_output_routes(path, args.repo_root) for path in args.patches]
    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        for report in reports:
            print(format_output_routes(report))
    if not all(report["ok"] for report in reports):
        return 2
    if args.require_host_input and not all(
        report["host_contract_verified"] and report["has_wired_host_input"]
        for report in reports
    ):
        return 1
    if args.require_generator_route and any(
        report["unrouted_first_party_generators"] for report in reports
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
