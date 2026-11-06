"""Opt-in, fail-closed saved-patch stereo HostAudio2 preflight.

The existing patch inspector and audio-route auditor are the source of truth.
The temporary plaintext patch is private, short-lived and never an exported
artifact; no source ZIP or its historical manifest is rewritten.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile


_PATCH_TOOLS = Path(__file__).resolve().parents[1] / "patches"
if str(_PATCH_TOOLS) not in sys.path:
    sys.path.insert(0, str(_PATCH_TOOLS))

from patch_audio_routes import audit_output_routes  # noqa: E402


SCOPE = (
    "saved HostAudio2 Left/M and Right input cables, checked-in HostAudio2 "
    "port bounds and conservative first-party generator-to-terminal signal "
    "chains; NOT a test of audible audio, channel independence, installed "
    "third-party modules or DAW/plugin execution"
)
PORTS = (0, 1)


def stereo_host_route_report(patch_bytes: bytes, root: Path) -> dict:
    """Audit the exact validated ZIP patch bytes without modifying the ZIP.

    Existing patch_audio_routes always calls patch_inspector first and refuses
    to promote opaque/third-party or CV-only hops to verified signal paths.
    """
    if not isinstance(patch_bytes, bytes):
        raise ValueError("source patch must be bytes")
    # audit_output_routes consumes a pathname; isolate it from the user output
    # directory and strip its transient path from all published diagnostics.
    try:
        with tempfile.TemporaryDirectory(prefix="msinstrument-host-routes-") as temp:
            candidate = Path(temp) / "source.vcv"
            candidate.write_bytes(patch_bytes)
            audit = audit_output_routes(candidate, root)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        return {
            "scope": SCOPE, "status": "FAIL",
            "reason": "ROUTING_INSPECTION_UNAVAILABLE",
            "hostContractVerified": False,
            "summary": {"hostModules": 0, "verifiedStereoHosts": 0,
                        "sourceVerifiedTerminalInputs": 0,
                        "missingTerminalInputs": 0,
                        "unverifiedWiredTerminalInputs": 0},
            "hosts": [],
            "errors": [f"Cannot complete source-routing audit: {type(exc).__name__}"],
        }

    inspected = bool(audit["ok"])
    contract = bool(audit["host_contract_verified"])
    proven = {
        (route["host_module_id"], route["host_input_port"])
        for route in audit["source_verified_host_inputs"]
    }
    hosts = []
    for sink in sorted(audit["sinks"], key=lambda item: item["module_id"]):
        host_id = sink["module_id"]
        wired = sorted(set(sink["connected_ports"]))
        verified = [port for port in PORTS if (host_id, port) in proven]
        missing = [port for port in PORTS if port not in wired]
        unverified = [port for port in wired if port not in verified]
        traces = sorted(({
            "generatorModuleId": trace["module_id"],
            "generatorModel": trace["model"],
            "hostInputPort": trace["host_input_port"],
            "cables": [hop["cable_id"] for hop in trace["cable_hops"]],
        } for trace in audit["source_verified_host_input_traces"]
            if trace["host_module_id"] == host_id),
            key=lambda trace: (trace["hostInputPort"],
                               trace["generatorModuleId"], trace["cables"]))
        hosts.append({
            "moduleId": host_id,
            "status": "PASS" if len(verified) == 2 and contract and inspected else "FAIL",
            "wiredInputs": wired,
            "sourceVerifiedInputs": verified,
            "missingInputs": missing,
            "unverifiedWiredInputs": unverified,
            "generatorTraces": traces,
        })

    if not inspected:
        reason = "PATCH_INSPECTION_FAILED"
    elif not contract:
        reason = "HOST_CONTRACT_UNVERIFIED"
    elif not hosts:
        reason = "NO_HOST_AUDIO2"
    elif any(host["status"] == "FAIL" for host in hosts):
        reason = "UNVERIFIED_STEREO_HOST_INPUTS"
    else:
        reason = None

    return {
        "scope": SCOPE,
        "status": "PASS" if reason is None else "FAIL",
        "reason": reason,
        "hostContractVerified": contract,
        "summary": {
            "hostModules": len(hosts),
            "verifiedStereoHosts": sum(host["status"] == "PASS" for host in hosts),
            "sourceVerifiedTerminalInputs": sum(len(host["sourceVerifiedInputs"])
                                                for host in hosts),
            "missingTerminalInputs": sum(len(host["missingInputs"])
                                         for host in hosts),
            "unverifiedWiredTerminalInputs": sum(len(host["unverifiedWiredInputs"])
                                                 for host in hosts),
        },
        "hosts": hosts,
        # Never disclose or nondeterministically persist the private temp path
        # in the public JSON report, even on unexpected parser/file failures.
        "errors": [error.replace(str(candidate), "<saved-patch>")
                   for error in audit["errors"]],
    }


def text_stereo_host_route_report(report: dict) -> str:
    """Compact deterministic, performer-facing explanation of the strict gate."""
    lines = [
        f"Strict stereo HostAudio2 source route check: {report['status']}",
        "  Checked-in HostAudio2 port contract: "
        + ("verified" if report["hostContractVerified"] else "unverified"),
        f"  Reason: {report['reason'] or 'NONE'}",
    ]
    for host in report["hosts"]:
        lines.append(f"  HostAudio2[{host['moduleId']}]: {host['status']}")
        for port, label in ((0, "Left/M"), (1, "Right")):
            if port in host["sourceVerifiedInputs"]:
                state = "SOURCE_VERIFIED"
            elif port in host["missingInputs"]:
                state = "UNPATCHED"
            else:
                state = "WIRED_BUT_UNVERIFIED"
            lines.append(f"    {label}: {state}")
        for trace in host["generatorTraces"]:
            lines.append(
                f"    Signal chain to input {trace['hostInputPort']}: "
                f"{trace['generatorModel']}[{trace['generatorModuleId']}], "
                f"cables {trace['cables']}")
    for error in report["errors"]:
        lines.append(f"  ERROR: {error}")
    lines.append(
        "  Source-verified wiring is NOT evidence of sound, stereo separation, "
        "third-party DSP behavior or host execution.")
    return "\n".join(lines) + "\n"
