"""Offline, musician-facing inventory of every saved Macro8 performance control.

Only call after read_bundle()/inspect() has re-derived the source manifest.
No reported voltage is a runtime measurement or a DAW automation assignment.
"""
from __future__ import annotations


SLOTS = ("A", "B", "C", "D")
SCOPE = (
    "Saved Macro8 knob/snapshot targets and direct cable metadata only; "
    "nominal voltages are calculated from stored normalized values, NOT live "
    "CV measurements, host automation, or proof of audio playback."
)


def _saved_value(normalized: float, range_mode: str) -> dict:
    """Interpret the Macro8 source's 0..10 V / -5..5 V output scaling."""
    voltage = 10.0 * normalized
    if range_mode == "bipolar":
        voltage -= 5.0
    return {"normalized": normalized, "nominalVolts": voltage}


def build_control_report(manifest: dict) -> dict:
    """Summarize all 8 controls per Macro8, including unpatched controls.

    Unlike a routing-only report, this also works with v1 source bundles.
    v1 route counts are deliberately unknown, not falsely zero. For v2, the
    counts reflect saved direct cables, including conservatively unverified
    historical or third-party destination ports.
    """
    version = manifest["formatVersion"]
    route_counts: dict[tuple[int, int], dict] = {}
    if version == 2:
        for mapping in manifest["performance"]["controlMappings"]:
            source = mapping["source"]
            target = mapping["destination"]
            key = (source["moduleId"], source["controlNumber"])
            counts = route_counts.setdefault(
                key, {"total": 0, "sourceVerified": 0, "unverified": 0})
            counts["total"] += 1
            if target["inputKind"] in ("cv", "audio"):
                counts["sourceVerified"] += 1
            else:
                counts["unverified"] += 1

    controllers = []
    for macro in manifest["performance"]["macro8"]:
        selected = macro["selectedSlot"]
        selected_source = "LIVE" if selected == -1 else SLOTS[selected]
        controls = []
        for index, name in enumerate(macro["names"]):
            range_mode = macro["ranges"][index]
            live = macro["liveValues"][index]
            scene_values = {
                slot: (
                    None if macro["snapshots"][slot_index] is None
                    else _saved_value(
                        macro["snapshots"][slot_index][index], range_mode)
                )
                for slot_index, slot in enumerate(SLOTS)
            }
            target = (live if selected == -1
                      else macro["snapshots"][selected][index])
            controls.append({
                "number": index + 1,
                "name": name,
                "range": range_mode,
                "live": _saved_value(live, range_mode),
                "savedTarget": {
                    "source": selected_source,
                    **_saved_value(target, range_mode),
                },
                "snapshots": scene_values,
                "routes": (
                    None if version == 1
                    else dict(route_counts.get(
                        (macro["moduleId"], index + 1),
                        {"total": 0, "sourceVerified": 0, "unverified": 0}))
                ),
            })
        controllers.append({
            "moduleId": macro["moduleId"],
            "snapshotAction": macro["snapshotAction"],
            "selectedSource": selected_source,
            "morphSeconds": macro["morphSeconds"],
            "storedSlots": [
                slot for slot, row in zip(SLOTS, macro["snapshots"])
                if row is not None
            ],
            "controls": controls,
        })
    return {
        "instrument": manifest["name"],
        "bundleFormatVersion": version,
        "scope": SCOPE,
        "controllers": controllers,
    }


def text_control_report(report: dict) -> str:
    """Deterministic report with saved values and *nominal* output voltages."""
    lines = [
        f"Saved Macro8 controls: {report['instrument']} "
        f"(source bundle v{report['bundleFormatVersion']})",
        f"Scope: {report['scope']}",
    ]
    for controller in report["controllers"]:
        scenes = ", ".join(controller["storedSlots"]) or "none"
        lines.append(
            f"Macro8 module {controller['moduleId']}: saved source "
            f"{controller['selectedSource']}; "
            f"{controller['snapshotAction'].upper()} mode; "
            f"{controller['morphSeconds']:g} s morph; stored scenes {scenes}"
        )
        for control in controller["controls"]:
            live = control["live"]
            target = control["savedTarget"]
            scenes = ", ".join(
                f"{slot}="
                + ("empty" if value is None else f"{value['normalized']:.3f}")
                for slot, value in control["snapshots"].items()
            )
            counts = control["routes"]
            routing = (
                "routes unknown (v1)" if counts is None
                else f"{counts['total']} saved routes "
                     f"({counts['sourceVerified']} source-verified, "
                     f"{counts['unverified']} unverified)"
            )
            lines.append(
                f"  {control['number']}. {control['name']!r} "
                f"[{control['range']}]: LIVE {live['normalized']:.3f} "
                f"({live['nominalVolts']:+.3f} V); "
                f"saved {target['source']} target "
                f"{target['normalized']:.3f} "
                f"({target['nominalVolts']:+.3f} V); "
                f"{scenes}; {routing}"
            )
    lines.append(
        "Saved targets may be smoothed in Rack; this report does not "
        "measure emitted CV, sound, or DAW automation."
    )
    return "\n".join(lines) + "\n"
