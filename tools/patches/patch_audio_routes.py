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

from patch_inspector import ROOT, _enum_members, _source_bounds, _strict_json, inspect_patch


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


# These ordinal input/output names must match the pinned *source* exactly.
# A first-party CV input never silently becomes an audio path just because a
# cable graph connects its module to a HostAudio2 terminal. This is deliberately
# narrower than arbitrary Rack DSP routing and is not an audibility guarantee.
SIGNAL_PORT_CONTRACTS = {
    "MorphVCO": (
        ("PITCH_INPUT", "FM_INPUT", "MORPH_CV_INPUT", "PWM_CV_INPUT"),
        ("MORPH_OUTPUT", "SINE_OUTPUT"), (), (0, 1),
    ),
    "FMVoice": (
        ("PITCH_INPUT", "RATIO_CV_INPUT", "INDEX_CV_INPUT", "FEEDBACK_CV_INPUT"),
        ("CARRIER_OUTPUT", "MODULATOR_OUTPUT"), (), (0, 1),
    ),
    "StateFilter": (
        ("AUDIO_INPUT", "CUTOFF_CV_INPUT", "RESONANCE_CV_INPUT", "DRIVE_CV_INPUT"),
        ("LOWPASS_OUTPUT", "BANDPASS_OUTPUT", "HIGHPASS_OUTPUT"), (0,), (0, 1, 2),
    ),
    "FoldDrive": (
        ("AUDIO_INPUT", "DRIVE_CV_INPUT", "BIAS_CV_INPUT", "MIX_CV_INPUT"),
        ("AUDIO_OUTPUT",), (0,), (0,),
    ),
    "DualVCA": (
        ("AUDIO_A_INPUT", "CV_A_INPUT", "AUDIO_B_INPUT", "CV_B_INPUT"),
        ("AUDIO_A_OUTPUT", "AUDIO_B_OUTPUT", "SUM_OUTPUT"), (0, 2), (0, 1, 2),
    ),
    "StereoEcho": (
        ("LEFT_INPUT", "RIGHT_INPUT", "TIME_CV_INPUT", "FEEDBACK_CV_INPUT",
         "MIX_CV_INPUT"),
        ("LEFT_OUTPUT", "RIGHT_OUTPUT"), (0, 1), (0, 1),
    ),
}


# Only source-backed *signal input -> output* relationships are followed.
# In particular, DualVCA's A input cannot reach its B-only output, while
# either input may contribute to SUM. The CV inputs never qualify.
SIGNAL_PORT_TRANSFERS = {
    "StateFilter": {0: (0, 1, 2)},
    "FoldDrive": {0: (0,)},
    "StereoEcho": {0: (0, 1), 1: (0, 1)},
    "DualVCA": {0: (0, 2), 2: (1, 2)},
}


def _verified_signal_ports(root: Path, model: str) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
    """Guard semantic port indices with the exact checked-in ordinal enums."""
    contract = SIGNAL_PORT_CONTRACTS.get(model)
    if contract is None:
        return None
    path = root / "plugins" / "ModularSynth" / "src" / f"{model}.cpp"
    if not path.is_file():
        return None
    source = path.read_text(encoding="utf-8")
    inputs, outputs, signal_inputs, signal_outputs = contract
    if (_enum_members(source, "InputIds", "NUM_INPUTS") != list(inputs)
            or _enum_members(source, "OutputIds", "NUM_OUTPUTS") != list(outputs)):
        return None
    bounds = _source_bounds(root, "ModularSynth", model)
    if (bounds is None or bounds["inputs"] != len(inputs)
            or bounds["outputs"] != len(outputs)):
        return None
    return signal_inputs, signal_outputs


def _source_verified_signal_route(
    root: Path, generator_id: int, modules: dict[int, dict],
    outgoing: dict[int, list[dict]], wired_hosts: set[int],
    target_terminal: tuple[int, int] | None = None,
    *, include_cable_hops: bool = False,
) -> dict | None:
    """Find a conservative first-party signal-port chain (never infer sound).

    Any third-party module, CV-only hop or drifted first-party source contract
    breaks this strict path. The separate graph-level route remains available.
    """
    from collections import deque

    model = modules[generator_id]["model"]
    source_ports = _verified_signal_ports(root, model)
    if source_ports is None:
        return None
    queue = deque((generator_id, port, (generator_id,), ())
                  for port in source_ports[1])
    visited: set[tuple[int, int]] = set()
    while queue:
        current, output_port, ancestry, cable_hops = queue.popleft()
        if (current, output_port) in visited:
            continue
        visited.add((current, output_port))
        edges = sorted(outgoing[current], key=lambda c: (
            c["inputModuleId"], c["inputId"], c["id"]))
        for edge in edges:
            if edge["outputId"] != output_port:
                continue
            target_id, target_port = edge["inputModuleId"], edge["inputId"]
            hop = {
                "cable_id": edge["id"],
                "output_module_id": current,
                "output_port": output_port,
                "input_module_id": target_id,
                "input_port": target_port,
            }
            target = modules[target_id]
            if (target["plugin"], target["model"]) == ("Cardinal", "HostAudio2"):
                if (target_id in wired_hosts and target_port in (0, 1)
                        and (target_terminal is None
                             or (target_id, target_port) == target_terminal)):
                    result = {
                        "module_id": generator_id,
                        "model": f"ModularSynth/{model}",
                        "host_module_id": target_id,
                        "host_input_port": target_port,
                        "via_module_ids": list(ancestry),
                    }
                    if include_cable_hops:
                        result["cable_hops"] = [*cable_hops, hop]
                    return result
                continue
            if target["plugin"] != "ModularSynth":
                continue  # Opaque or control/host modules are not audio evidence.
            signal_ports = _verified_signal_ports(root, target["model"])
            if signal_ports is None or target_port not in signal_ports[0]:
                continue
            outputs = SIGNAL_PORT_TRANSFERS.get(target["model"], {}).get(
                target_port, ())
            for next_port in outputs:
                if next_port in signal_ports[1]:
                    queue.append((target_id, next_port, ancestry + (target_id,),
                                  cable_hops + (hop,)))
    return None


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
        "source_verified_signal_routes": [],
        "unverified_first_party_signal_routes": [],
        # A voice reaching *one* host jack says nothing about other wired
        # jacks. Terminal-level evidence is tracked separately to avoid a
        # misleading stereo/complete-output interpretation.
        "source_verified_host_inputs": [],
        # Unlike source_verified_host_inputs (one proof per terminal), this
        # enumerates every first-party generator with a typed path to each
        # terminal. Each hop records the exact cable and jack ordinals so a
        # patch author can trace why a voice is counted or excluded.
        "source_verified_host_input_traces": [],
        "unverified_wired_host_inputs": [],
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
        item = {"module_id": module_id, "model": f"{key[0]}/{key[1]}"}
        if reaches_host:
            signal_route = _source_verified_signal_route(
                root, module_id, modules, outgoing, wired_hosts)
            if signal_route is not None:
                result["source_verified_signal_routes"].append(signal_route)
            else:
                result["unverified_first_party_signal_routes"].append(item)
                result["advisories"].append(
                    f"{item['model']}[{module_id}] has a directed host cable "
                    "route, but no source-verified signal-port chain. A CV-only "
                    "or opaque third-party processing hop may be involved."
                )
            continue
        result["unrouted_first_party_generators"].append(item)
        result["advisories"].append(
            f"{item['model']}[{module_id}] has no directed cable-graph route "
            "to a wired HostAudio2 terminal; this may be intentional."
        )

    # Classify every *wired* terminal independently. A generator's verified
    # path to HostAudio2 Left must not be reused as proof for a separate Right
    # cable that may carry CV, unknown bundled DSP or only opaque third-party
    # processing. We require a complete typed source-to-exact-terminal chain.
    generators = [mid for mid, generator in sorted(modules.items())
                  if (generator["plugin"], generator["model"])
                  in FIRST_PARTY_GENERATORS]
    for host_id in hosts:
        for cable in sorted(incoming[host_id], key=lambda c: c["inputId"]):
            terminal = (host_id, cable["inputId"])
            verified = None
            for generator_id in generators:
                trace = _source_verified_signal_route(
                    root, generator_id, modules, outgoing, wired_hosts,
                    target_terminal=terminal, include_cable_hops=True)
                if trace is not None:
                    result["source_verified_host_input_traces"].append(trace)
                    if verified is None:
                        # Retain the original one-route-per-terminal API;
                        # cable provenance lives in the separate all-sources
                        # report, without changing existing consumers.
                        verified = {key: value for key, value in trace.items()
                                    if key != "cable_hops"}
            if verified is not None:
                result["source_verified_host_inputs"].append(verified)
                continue
            source = modules[cable["outputModuleId"]]
            result["unverified_wired_host_inputs"].append({
                "host_module_id": host_id,
                "host_input_port": cable["inputId"],
                "source_module_id": cable["outputModuleId"],
                "source_model": f"{source['plugin']}/{source['model']}",
                "source_output_port": cable["outputId"],
            })
            result["advisories"].append(
                f"HostAudio2[{host_id}] input {cable['inputId']} is wired "
                "but has no source-verified first-party signal-port chain; "
                "CV-only paths and opaque third-party processing remain "
                "unverified."
            )
    return result


def format_output_routes(result: dict, *, show_signal_traces: bool = False) -> str:
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
    if result["source_verified_signal_routes"]:
        lines.append(
            "  First-party voices with source-verified signal-port chains: "
            f"{len(result['source_verified_signal_routes'])}"
            " (not proof of audible output)"
        )
    if result["sinks"]:
        wired = sum(len(sink["connected_ports"]) for sink in result["sinks"])
        lines.append(
            "  Wired HostAudio2 inputs with a source-verified first-party "
            "signal chain: "
            f"{len(result['source_verified_host_inputs'])}/{wired}"
            " (not proof of audio or stereo width)"
        )
        lines.append(
            "  Source-verified first-party generator-to-terminal traces: "
            f"{len(result['source_verified_host_input_traces'])}"
            " (includes distinct generators mixed onto one jack)"
        )
        if show_signal_traces:
            for trace in result["source_verified_host_input_traces"]:
                lines.append(
                    f"    {trace['model']}[{trace['module_id']}] -> "
                    f"HostAudio2[{trace['host_module_id']}]:in"
                    f"{trace['host_input_port']}"
                )
                for hop in trace["cable_hops"]:
                    lines.append(
                        f"      cable #{hop['cable_id']}: "
                        f"{hop['output_module_id']}:out{hop['output_port']} -> "
                        f"{hop['input_module_id']}:in{hop['input_port']}"
                    )
    if result["unverified_first_party_signal_routes"]:
        lines.append(
            "  First-party voices with host graph routes but no verified "
            f"signal-port chains: {len(result['unverified_first_party_signal_routes'])}"
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
        "--show-signal-traces", action="store_true",
        help="Include source-verified cable-by-cable provenance for every "
             "first-party generator feeding each HostAudio2 jack. Use "
             "--json for structured traces. Not an audibility test.",
    )
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
    parser.add_argument(
        "--require-source-verified-signal-route", action="store_true",
        help="Exit 1 if a first-party MorphVCO/FMVoice lacks a conservative "
             "source-verified signal-port chain to HostAudio2. Third-party "
             "processors remain opaque; this is NOT an audible-audio test.",
    )
    parser.add_argument(
        "--require-source-verified-host-inputs", action="store_true",
        help="Exit 1 unless at least one HostAudio2 jack is wired and every "
             "wired HostAudio2 jack has a first-party source-verified "
             "signal-port chain. This is not an audible-audio test; "
             "third-party-only routes remain unverified.",
    )
    parser.add_argument(
        "--require-source-verified-stereo", action="store_true",
        help="Exit 1 unless every saved HostAudio2 module has both Left/M "
             "and Right jacks connected through source-verified first-party "
             "generator-to-terminal signal-port chains. Does NOT prove "
             "different stereo content or audible output.",
    )
    args = parser.parse_args(argv)
    reports = [audit_output_routes(path, args.repo_root) for path in args.patches]
    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        for report in reports:
            print(format_output_routes(report, show_signal_traces=args.show_signal_traces))
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
    if args.require_source_verified_signal_route and any(
        not report["host_contract_verified"]
        or report["unrouted_first_party_generators"]
        or report["unverified_first_party_signal_routes"]
        for report in reports
    ):
        return 1
    if args.require_source_verified_host_inputs and any(
        not report["host_contract_verified"]
        or not report["has_wired_host_input"]
        or report["unverified_wired_host_inputs"]
        for report in reports
    ):
        return 1
    if args.require_source_verified_stereo and any(
        not report["host_contract_verified"]
        or not report["sinks"]
        or any(
            {route["host_input_port"] for route in report["source_verified_host_inputs"]
             if route["host_module_id"] == sink["module_id"]} != {0, 1}
            for sink in report["sinks"]
        )
        for report in reports
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
