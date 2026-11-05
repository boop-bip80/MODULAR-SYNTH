"""Sparse, source-only Macro8 scene performance timeline.

The saved Macro8 parameters establish initial control values and one fixed
one-pole smoothing time. Events change *targets* without assuming intermediate
scenes have settled. This is an analytical estimate, not a Rack/DAW render.
"""
from __future__ import annotations

import math

from morph_preview import (MAX_ELAPSED_SECONDS, MAX_SAMPLE_RATE,
                           MIN_SAMPLE_RATE, SCENES, SETTLE_LOG_FACTOR, SLOTS)


MAX_EVENTS = 128
MAX_QUERY_TIMES = 256
SCOPE = (
    "Analytical source-only saved Macro8 target sequence, starting at a fully "
    "settled scene and retaining partial transitions between events; "
    "NOT emitted CV, MIDI, DAW automation, or rendered audio."
)


class SequencePreviewError(ValueError):
    """Invalid source-only scene-sequencing request."""


def _finite_seconds(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SequencePreviewError(f"{field} must be a finite number of seconds")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise SequencePreviewError(f"{field} must be a finite number of seconds") from exc
    if not math.isfinite(number) or not 0.0 <= number <= MAX_ELAPSED_SECONDS:
        raise SequencePreviewError(f"{field} must be in the range 0..3600 seconds")
    return number


def _sample_index(seconds: float, sample_rate: int) -> int:
    return int(math.floor(seconds * sample_rate + 0.5))


def _tokens(raw: str, label: str, limit: int) -> list[str]:
    if not isinstance(raw, str) or not raw or len(raw) > 8192:
        raise SequencePreviewError(f"{label} must be a bounded comma-separated list")
    items = raw.split(",")
    if len(items) > limit or any(not item or len(item) > 80 for item in items):
        raise SequencePreviewError(f"{label} must contain 1..{limit} short entries")
    return items


def _timestamp_token(token: str, field: str) -> float:
    if token.strip() != token or not token.isascii():
        raise SequencePreviewError(f"{field} has invalid timestamp syntax")
    try:
        value = float(token)
    except ValueError as exc:
        raise SequencePreviewError(f"{field} has invalid timestamp syntax") from exc
    return _finite_seconds(value, field)


def parse_events(raw: str) -> list[tuple[float, str]]:
    """Parse ordered `seconds:SCENE` tokens; sample uniqueness checked later."""
    result = []
    for token in _tokens(raw, "scene events", MAX_EVENTS):
        time_part, sep, scene = token.partition(":")
        if not sep or scene not in SCENES:
            raise SequencePreviewError(
                "scene event must be TIME:LIVE, TIME:A, TIME:B, TIME:C or TIME:D")
        result.append((_timestamp_token(time_part, "scene event"), scene))
    return result


def parse_query_times(raw: str) -> list[float]:
    """Parse query timestamps with no implicit sortedness or deduplication."""
    return [_timestamp_token(token, "query time")
            for token in _tokens(raw, "query times", MAX_QUERY_TIMES)]


def _scene(macro: dict, scene: str) -> tuple[float, ...]:
    if scene == "LIVE":
        return tuple(macro["liveValues"])
    saved = macro["snapshots"][SLOTS.index(scene)]
    if saved is None:
        raise SequencePreviewError(
            f"Macro8 module {macro['moduleId']} has no stored snapshot {scene}")
    return tuple(saved)


def _select_macro(manifest: dict, module_id: int | None) -> dict:
    if module_id is not None and (
            type(module_id) is not int or not 0 <= module_id <= 0x7fffffffffffffff):
        raise SequencePreviewError("module id must be a nonnegative signed 64-bit integer")
    macros = manifest["performance"]["macro8"]
    if module_id is None:
        if len(macros) != 1:
            raise SequencePreviewError(
                "multiple Macro8 modules found; select one with --module-id")
        return macros[0]
    for item in macros:
        if item["moduleId"] == module_id:
            return item
    raise SequencePreviewError(f"no Macro8 module has id {module_id}")


def build_sequence_preview(manifest: dict, *, source: str,
                           events: list[tuple[float, str]],
                           query_times: list[float], sample_rate: int = 48000,
                           module_id: int | None = None) -> dict:
    """Estimate chronological snapshots of an unfinished multi-scene morph.

    Each event changes the target *at* its quantized sample boundary. A query
    at that exact boundary returns the state before processing the next sample.
    Between boundaries, exp(-ln(1000)*N/(T*rate)) analytically reproduces the
    one-pole recurrence without scanning millions of silent intermediate ticks.
    """
    if source not in SCENES:
        raise SequencePreviewError("initial scene must be LIVE, A, B, C or D")
    if type(sample_rate) is not int or not MIN_SAMPLE_RATE <= sample_rate <= MAX_SAMPLE_RATE:
        raise SequencePreviewError("sample rate must be an integer from 8000 to 384000 Hz")
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
        raise SequencePreviewError(f"expected 1..{MAX_EVENTS} scene events")
    if not isinstance(query_times, list) or not 1 <= len(query_times) <= MAX_QUERY_TIMES:
        raise SequencePreviewError(f"expected 1..{MAX_QUERY_TIMES} query times")

    macro = _select_macro(manifest, module_id)
    initial = _scene(macro, source)
    pending = []
    prev_event_index = -1
    for index, entry in enumerate(events):
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            raise SequencePreviewError(f"scene event {index} must be (seconds, scene)")
        seconds = _finite_seconds(entry[0], f"scene event {index}")
        if entry[1] not in SCENES:
            raise SequencePreviewError(f"scene event {index} has invalid scene")
        sample = _sample_index(seconds, sample_rate)
        if sample <= prev_event_index:
            raise SequencePreviewError("scene events must have distinct increasing sample times")
        prev_event_index = sample
        pending.append((sample, seconds, entry[1], _scene(macro, entry[1])))

    queries = []
    prev_query_index = -1
    for index, raw in enumerate(query_times):
        seconds = _finite_seconds(raw, f"query time {index}")
        sample = _sample_index(seconds, sample_rate)
        if sample <= prev_query_index:
            raise SequencePreviewError("query times must have distinct increasing sample times")
        prev_query_index = sample
        queries.append((sample, seconds))

    settle = macro["morphSeconds"]
    current = initial
    target = initial
    target_scene = source
    event_cursor = 0
    cursor = 0

    def advance(steps: int) -> None:
        nonlocal current
        if steps <= 0:
            return
        if settle <= 0.0:
            current = target
        else:
            remaining = math.exp(-SETTLE_LOG_FACTOR * (steps / sample_rate) / settle)
            current = tuple(dst + remaining * (src - dst)
                            for src, dst in zip(current, target))

    result = []
    for sample, requested in queries:
        while event_cursor < len(pending) and pending[event_cursor][0] <= sample:
            event_sample, _event_time, scene, values = pending[event_cursor]
            advance(event_sample - cursor)
            cursor = event_sample
            target, target_scene = values, scene
            event_cursor += 1
        advance(sample - cursor)
        cursor = sample
        result.append({
            "requestedSeconds": requested,
            "quantizedSeconds": sample / sample_rate,
            "sampleCount": sample,
            "activeTarget": target_scene,
            "controls": [{
                "number": i + 1,
                "name": macro["names"][i],
                "range": macro["ranges"][i],
                "predictedNormalized": value,
                "predictedNominalVolts": (
                    value * 10.0 - (5.0 if macro["ranges"][i] == "bipolar" else 0.0)),
            } for i, value in enumerate(current)],
        })

    selected = macro["selectedSlot"]
    return {
        "instrument": manifest["name"],
        "bundleFormatVersion": manifest["formatVersion"],
        "scope": SCOPE,
        "moduleId": macro["moduleId"],
        "savedSelectedSource": "LIVE" if selected == -1 else SLOTS[selected],
        "startScene": source,
        "sampleRate": sample_rate,
        "morphSeconds": settle,
        "events": [{"requestedSeconds": seconds, "sampleCount": sample,
                    "quantizedSeconds": sample / sample_rate, "scene": scene}
                   for sample, seconds, scene, _ in pending],
        "snapshots": result,
    }


def text_sequence_preview(report: dict) -> str:
    """Readable sparse CV timeline with host-evidence disclaimer."""
    lines = [
        f"Macro8 scene sequence estimate: {report['instrument']} "
        f"(source bundle v{report['bundleFormatVersion']})",
        f"Scope: {report['scope']}",
        f"Module {report['moduleId']}, settled {report['startScene']}, "
        f"saved morph {report['morphSeconds']:g} s, "
        f"sample rate {report['sampleRate']} Hz",
        "Scene target changes:",
    ]
    for event in report["events"]:
        lines.append(f"  {event['scene']} at sample {event['sampleCount']} "
                     f"({event['quantizedSeconds']:.6f} s)")
    lines.append("Estimated control-voltage snapshots:")
    for sample in report["snapshots"]:
        lines.append(f"  Sample {sample['sampleCount']} "
                     f"({sample['quantizedSeconds']:.6f} s), "
                     f"target {sample['activeTarget']}:")
        for control in sample["controls"]:
            lines.append(f"    {control['number']}. {control['name']!r} "
                         f"[{control['range']}]: "
                         f"{control['predictedNormalized']:.6f} "
                         f"({control['predictedNominalVolts']:+.6f} V nominal)")
    return "\n".join(lines) + "\n"
