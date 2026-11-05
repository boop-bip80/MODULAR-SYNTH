"""Source-verified, sparse Macro8 CV route estimates, never DAW automation.

No new bundle format is introduced. Call this only with a manifest re-derived
by ``instrument_builder.inspect``, which checks archive bytes and saved patch.
"""
from __future__ import annotations

import csv
from io import StringIO

from sequence_preview import (SequencePreviewError, build_sequence_preview)


MAX_EXPORT_ROWS = 8192
SCOPE = (
    "Offline estimate of saved Macro8 source-controlled nominal CV at requested "
    "sample boundaries and direct source-verified cable destinations; "
    "NOT measured Rack voltages, parameter automation, MIDI or audio."
)


class AutomationExportError(ValueError):
    """Invalid or untrustworthy source-only CV export request."""


CSV_FIELDS = (
    "sampleCount", "quantizedSeconds", "activeTarget", "macroModuleId",
    "controlNumber", "controlName", "controlRange", "predictedNormalized",
    "predictedNominalVolts", "cableId", "destinationModuleId", "destinationPlugin",
    "destinationModel", "destinationInputId", "destinationInputKind",
    "destinationInputLabel", "relatedKnobId", "relatedKnobName",
)


def build_automation_export(manifest: dict, *, source: str,
                            events: list[tuple[float, str]],
                            query_times: list[float], sample_rate: int = 48000,
                            module_id: int | None = None) -> dict:
    """Return sorted CV/cable rows estimated from a saved v2 source bundle.

    This emits only sparse requested sample boundaries; it neither samples a
    continuous CV stream nor exports host-loadable parameter automation.
    Unknown destination ports are not permitted because the column labels
    could otherwise falsely imply verified routing semantics.
    """
    if manifest.get("formatVersion") != 2:
        raise AutomationExportError(
            "verified CV route export requires a v2 source bundle; "
            "repack the original .vcv with pack --format-version 2")
    try:
        preview = build_sequence_preview(
            manifest, source=source, events=events, query_times=query_times,
            sample_rate=sample_rate, module_id=module_id)
    except SequencePreviewError as exc:
        raise AutomationExportError(str(exc)) from exc

    selected = preview["moduleId"]
    mapping = [m for m in manifest["performance"]["controlMappings"]
               if m["source"]["moduleId"] == selected]
    if not mapping:
        raise AutomationExportError(
            f"Macro8 module {selected} has no direct saved routes; "
            "a source-only CV destination cannot be inferred")
    for item in mapping:
        target = item["destination"]
        if target["inputKind"] not in ("cv", "audio"):
            raise AutomationExportError(
                f"cable {item['cableId']} destination "
                f"{target['plugin']}/{target['model']} input {target['inputId']} "
                "is not source-verified; refusing labelled CV export")
    if len(mapping) * len(preview["snapshots"]) > MAX_EXPORT_ROWS:
        raise AutomationExportError(
            f"CV export exceeds {MAX_EXPORT_ROWS} rows; "
            "reduce query samples or cable fan-out")

    mapping.sort(key=lambda m: (
        m["cableId"], m["source"]["outputId"],
        m["destination"]["moduleId"], m["destination"]["inputId"]))
    rows = []
    for sample in preview["snapshots"]:
        for item in mapping:
            src, target = item["source"], item["destination"]
            control = sample["controls"][src["outputId"]]
            knob = target["modulatesParameter"]
            rows.append({
                "sampleCount": sample["sampleCount"],
                "quantizedSeconds": sample["quantizedSeconds"],
                "activeTarget": sample["activeTarget"],
                "macroModuleId": selected,
                "controlNumber": src["controlNumber"],
                "controlName": control["name"],
                "controlRange": control["range"],
                "predictedNormalized": control["predictedNormalized"],
                "predictedNominalVolts": control["predictedNominalVolts"],
                "cableId": item["cableId"],
                "destinationModuleId": target["moduleId"],
                "destinationPlugin": target["plugin"],
                "destinationModel": target["model"],
                "destinationInputId": target["inputId"],
                "destinationInputKind": target["inputKind"],
                "destinationInputLabel": target["inputLabel"],
                "relatedKnobId": None if knob is None else knob["id"],
                "relatedKnobName": None if knob is None else knob["name"],
            })

    return {
        "instrument": preview["instrument"],
        "bundleFormatVersion": 2,
        "scope": SCOPE,
        "moduleId": selected,
        "startScene": source,
        "sampleRate": sample_rate,
        "morphSeconds": preview["morphSeconds"],
        "events": preview["events"],
        "routeCount": len(mapping),
        "sampleCount": len(preview["snapshots"]),
        "rowCount": len(rows),
        "rows": rows,
    }


def text_automation_csv(report: dict) -> str:
    """Deterministic, formula-safe CSV; no executable spreadsheet formulas."""
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in report["rows"]:
        safe = {}
        for field in CSV_FIELDS:
            value = row[field]
            if isinstance(value, str) and value and value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            safe[field] = "" if value is None else value
        writer.writerow(safe)
    return stream.getvalue()
