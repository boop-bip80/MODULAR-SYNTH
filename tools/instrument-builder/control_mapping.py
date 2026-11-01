"""Source-derived Macro8 cable destinations for optional instrument manifest v2.

The static first-party port contract is pinned to this source revision and
checked against Rack's C++ enum/config declarations by test_control_mapping.
All other plugin/model ports remain unverified, never guessed.
"""
from __future__ import annotations

from typing import NamedTuple


class MappingError(ValueError):
    """A Macro8 source cable conflicts with a known source port contract."""


CLOCKED_LFO_CONTRACT = "modular-synth-v2-clockedlfo-inputs-v1"


class InputSpec(NamedTuple):
    enum: str
    label: str
    kind: str
    parameter: tuple[int, str] | None = None


# Rack inputId is the zero-based position in each module's InputIds enum.
# parameter records a knob influenced by the CV input; it does NOT describe
# automation or a direct cable to a Rack ParamId.
FIRST_PARTY_INPUTS: dict[str, tuple[InputSpec, ...]] = {
    "Macro8": (),
    "ClockedLFO": (
        InputSpec("RATE_CV_INPUT", "Free-rate CV (1 V/oct)",
                  "cv", (0, "Free-run frequency")),
        InputSpec("CLOCK_INPUT", "External tempo pulse (2 V rising threshold)",
                  "cv"),
        InputSpec("RESET_INPUT", "Phase reset trigger (2 V rising threshold)",
                  "cv"),
        InputSpec("PHASE_CV_INPUT", "Output phase CV (10 V per cycle)",
                  "cv", (2, "Output phase offset")),
        InputSpec("WIDTH_CV_INPUT", "Pulse width CV (10 V full range)",
                  "cv", (3, "Pulse width")),
    ),
    "MorphVCO": (
        InputSpec("PITCH_INPUT", "Pitch CV (1 V/oct)", "cv"),
        InputSpec("FM_INPUT", "Exponential FM CV (5 V/oct at 100% depth)", "cv"),
        InputSpec("MORPH_CV_INPUT", "Wave morph CV (10 V full span; adds to knob)",
                  "cv", (2, "Wave morph position")),
        InputSpec("PWM_CV_INPUT", "Pulse width CV (10 V full span; adds to knob)",
                  "cv", (3, "Pulse width")),
    ),
    "StateFilter": (
        InputSpec("AUDIO_INPUT", "Audio signal input", "audio"),
        InputSpec("CUTOFF_CV_INPUT", "Cutoff CV (1 V/oct; adds to knob)",
                  "cv", (0, "Cutoff")),
        InputSpec("RESONANCE_CV_INPUT", "Resonance CV (10 V full span; adds to knob)",
                  "cv", (1, "Resonance amount")),
        InputSpec("DRIVE_CV_INPUT", "Drive CV (10 V full span; adds to knob)",
                  "cv", (2, "Input drive amount")),
    ),
    "StereoEcho": (
        InputSpec("LEFT_INPUT", "Left audio input", "audio"),
        InputSpec("RIGHT_INPUT", "Right audio input (uses left when unplugged)",
                  "audio"),
        InputSpec("TIME_CV_INPUT", "Echo time CV (additive 100 ms/V; accepts negative CV)",
                  "cv", (0, "Echo time")),
        InputSpec("FEEDBACK_CV_INPUT", "Feedback CV (adds 10 percentage points/V)",
                  "cv", (1, "Feedback")),
        InputSpec("MIX_CV_INPUT", "Wet mix CV (adds 10 percentage points/V)",
                  "cv", (2, "Wet mix")),
    ),
}


def _destination(module: dict, input_id: int, *,
                 clocked_lfo_known: bool) -> dict:
    plugin, model = module["plugin"], module["model"]
    result = {
        "moduleId": module["id"],
        "plugin": plugin,
        "model": model,
        "inputId": input_id,
        "inputKind": "unverified",
        "inputLabel": None,
        "modulatesParameter": None,
    }
    if (plugin != "ModularSynth" or model not in FIRST_PARTY_INPUTS
            or (model == "ClockedLFO" and not clocked_lfo_known)):
        return result
    ports = FIRST_PARTY_INPUTS[model]
    if input_id >= len(ports):
        raise MappingError(
            f"{plugin}/{model} inputId {input_id} outside verified 0..{len(ports) - 1}")
    spec = ports[input_id]
    result["inputKind"] = spec.kind
    result["inputLabel"] = spec.label
    if spec.parameter is not None:
        result["modulatesParameter"] = {
            "id": spec.parameter[0], "name": spec.parameter[1]
        }
    return result


def derive_control_mappings(patch: dict, macro8: list[dict], *,
                            clocked_lfo_known: bool = True) -> list[dict]:
    """Map only direct saved Macro8 output cables to input ports.

    Call after the patch/module/cable graph and Macro8 state are validated.
    Source patch order does not determine the order of the returned records.
    """
    modules = {module["id"]: module for module in patch["modules"]}
    controllers = {entry["moduleId"]: entry for entry in macro8}
    routes: list[dict] = []
    seen_endpoints: set[tuple[int, int, int, int]] = set()
    for cable in patch.get("cables", []):
        source_id = cable["outputModuleId"]
        controller = controllers.get(source_id)
        if controller is None:
            continue
        output_id = cable["outputId"]
        if output_id >= 8:
            raise MappingError(f"Macro8 {source_id} outputId {output_id} outside 0..7")
        endpoints = (source_id, output_id, cable["inputModuleId"], cable["inputId"])
        if endpoints in seen_endpoints:
            raise MappingError(
                f"duplicate Macro8 route to module {cable['inputModuleId']}"
                f" inputId {cable['inputId']}")
        seen_endpoints.add(endpoints)
        routes.append({
            "cableId": cable["id"],
            "source": {
                "moduleId": source_id,
                "outputId": output_id,
                "controlNumber": output_id + 1,
                "name": controller["names"][output_id],
                "range": controller["ranges"][output_id],
            },
            "destination": _destination(
                modules[cable["inputModuleId"]], cable["inputId"],
                clocked_lfo_known=clocked_lfo_known),
        })
    routes.sort(key=lambda route: (
        route["source"]["moduleId"], route["source"]["outputId"],
        route["destination"]["moduleId"], route["destination"]["inputId"],
        route["cableId"],
    ))
    return routes
