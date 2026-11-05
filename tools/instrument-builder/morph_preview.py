"""Deterministic, source-only Macro8 scene-transition estimates.

This does not render audio or query a running Rack engine. It models the
one-pole Macro8Smoother transition from a *settled* source scene to a new
target, assuming the saved morph-time knob is unchanged during the transition.
"""
from __future__ import annotations

import math


SLOTS = ("A", "B", "C", "D")
SCENES = ("LIVE",) + SLOTS
MIN_SAMPLE_RATE = 8000
MAX_SAMPLE_RATE = 384000
MAX_ELAPSED_SECONDS = 3600.0
SETTLE_LOG_FACTOR = math.log(1000.0)  # Macro8Smoother's 99.9% settling time.
SCOPE = (
    "Idealized saved Macro8 scene interpolation, assuming the starting scene "
    "was fully settled and the saved morph-time knob stays constant; "
    "NOT a live CV measurement, DAW automation, or rendered audio."
)


class MorphPreviewError(ValueError):
    """Invalid offline morph-preview request."""


def _scene_values(macro: dict, scene: str) -> list[float]:
    if scene == "LIVE":
        return macro["liveValues"]
    index = SLOTS.index(scene)
    values = macro["snapshots"][index]
    if values is None:
        raise MorphPreviewError(
            f"Macro8 module {macro['moduleId']} has no stored snapshot {scene}")
    return values


def _volts(normalized: float, mode: str) -> float:
    return normalized * 10.0 - (5.0 if mode == "bipolar" else 0.0)


def build_morph_preview(manifest: dict, *, source: str, destination: str,
                        elapsed_seconds: float, sample_rate: int = 48000,
                        module_id: int | None = None) -> dict:
    """Predict Macro8 normalized/nominal CV at a quantized time after recall.

    The numerical model mirrors the DSP's one-pole coefficient, with a settled
    starting scene and precisely one target change. No patch graph is executed.
    The caller must have validated the instrument using read_bundle()/inspect().
    """
    if source not in SCENES or destination not in SCENES:
        raise MorphPreviewError("scene names must be LIVE, A, B, C or D")
    if type(sample_rate) is not int or not MIN_SAMPLE_RATE <= sample_rate <= MAX_SAMPLE_RATE:
        raise MorphPreviewError("sample rate must be an integer from 8000 to 384000 Hz")
    if (isinstance(elapsed_seconds, bool)
            or not isinstance(elapsed_seconds, (int, float))):
        raise MorphPreviewError("elapsed time must be a finite number of seconds")
    try:
        elapsed = float(elapsed_seconds)
    except (ValueError, OverflowError) as exc:
        raise MorphPreviewError("elapsed time must be a finite number of seconds") from exc
    if not math.isfinite(elapsed) or not 0.0 <= elapsed <= MAX_ELAPSED_SECONDS:
        raise MorphPreviewError("elapsed time must be finite and between 0 and 3600 seconds")
    if module_id is not None and (type(module_id) is not int or
                                  not 0 <= module_id <= 0x7fffffffffffffff):
        raise MorphPreviewError("module id must be a nonnegative signed 64-bit integer")

    modules = manifest["performance"]["macro8"]
    if module_id is None:
        if len(modules) != 1:
            raise MorphPreviewError(
                "multiple Macro8 modules found; select one with --module-id")
        macro = modules[0]
    else:
        matches = [item for item in modules if item["moduleId"] == module_id]
        if not matches:
            raise MorphPreviewError(f"no Macro8 module has id {module_id}")
        macro = matches[0]

    start = _scene_values(macro, source)
    end = _scene_values(macro, destination)
    samples = int(math.floor(elapsed * sample_rate + 0.5))
    simulated_time = samples / sample_rate
    settle = macro["morphSeconds"]
    if samples == 0:
        fraction = 0.0
    elif settle <= 0.0:
        fraction = 1.0
    else:
        # Repeated C++ one-pole processing yields exp(-ln(1000) * N * dt/T).
        # expm1 avoids subtractive cancellation near the start of the morph.
        fraction = -math.expm1(-SETTLE_LOG_FACTOR * simulated_time / settle)

    controls = []
    for index, (from_value, to_value) in enumerate(zip(start, end)):
        value = from_value + fraction * (to_value - from_value)
        mode = macro["ranges"][index]
        controls.append({
            "number": index + 1,
            "name": macro["names"][index],
            "range": mode,
            "fromNormalized": from_value,
            "toNormalized": to_value,
            "predictedNormalized": value,
            "predictedNominalVolts": _volts(value, mode),
        })

    selected = macro["selectedSlot"]
    return {
        "instrument": manifest["name"],
        "bundleFormatVersion": manifest["formatVersion"],
        "scope": SCOPE,
        "moduleId": macro["moduleId"],
        "savedSelectedSource": "LIVE" if selected == -1 else SLOTS[selected],
        "fromScene": source,
        "toScene": destination,
        "morphSeconds": settle,
        "requestedElapsedSeconds": elapsed,
        "quantizedElapsedSeconds": simulated_time,
        "sampleRate": sample_rate,
        "sampleCount": samples,
        "completionFraction": fraction,
        "controls": controls,
    }


def text_morph_preview(report: dict) -> str:
    """Human-readable offline scene estimate with explicit qualifications."""
    lines = [
        f"Macro8 scene estimate: {report['instrument']} "
        f"(source bundle v{report['bundleFormatVersion']})",
        f"Scope: {report['scope']}",
        f"Module {report['moduleId']}: {report['fromScene']} -> "
        f"{report['toScene']} after {report['sampleCount']} samples at "
        f"{report['sampleRate']} Hz ({report['quantizedElapsedSeconds']:.6f} s); "
        f"saved morph setting {report['morphSeconds']:g} s; "
        f"progress {report['completionFraction'] * 100:.3f}%",
    ]
    for control in report["controls"]:
        lines.append(
            f"  {control['number']}. {control['name']!r} "
            f"[{control['range']}]: "
            f"{control['fromNormalized']:.6f} -> "
            f"{control['toNormalized']:.6f}; "
            f"estimated {control['predictedNormalized']:.6f} "
            f"({control['predictedNominalVolts']:+.6f} V nominal)"
        )
    return "\n".join(lines) + "\n"
