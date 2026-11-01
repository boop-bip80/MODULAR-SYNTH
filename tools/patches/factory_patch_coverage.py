#!/usr/bin/env python3
"""Source-only coverage/claim checks for MODULAR_-_ factory patch examples.

Reuses patch_inspector for structural validity; additionally verifies the
published signal-flow claims and first-party module coverage. Does not execute
Rack/Cardinal, inspect DSP sound, or attest third-party module port schemas.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys

import patch_inspector

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Route:
    label: str
    source: str
    target: str
    output: int | None = None
    input: int | None = None


@dataclass(frozen=True)
class Example:
    summary: str
    models: tuple[str, ...]
    routes: tuple[Route, ...]
    stereo: bool = False
    two_oscillators: bool = False
    snapshot_names: tuple[str, ...] = ()
    morph_seconds: float | None = None
    bipolar_cutoff: bool = False
    bipolar_width: bool = False
    unipolar_macro_outputs: tuple[int, ...] = ()
    snapshot_count: int = 2
    midi_channels: int | None = None
    midi_poly_mode: int | None = None


EXAMPLES: dict[str, Example] = {
    "MODULAR_-_Pulse_Bass.vcv": Example(
        "MIDI-controlled oscillator, filter and envelope/VCA bass voice",
        ("Cardinal/HostMIDI", "Fundamental/VCO", "Bogaudio/Bogaudio-VCF",
         "Fundamental/ADSR", "Fundamental/VCA-1", "Cardinal/HostAudio2"),
        (
            Route("MIDI pitch to oscillator", "Cardinal/HostMIDI", "Fundamental/VCO"),
            Route("MIDI gate to envelope", "Cardinal/HostMIDI", "Fundamental/ADSR"),
            Route("oscillator to filter", "Fundamental/VCO", "Bogaudio/Bogaudio-VCF"),
            Route("filter to VCA", "Bogaudio/Bogaudio-VCF", "Fundamental/VCA-1"),
            Route("ADSR to VCA", "Fundamental/ADSR", "Fundamental/VCA-1"),
            Route("VCA to host", "Fundamental/VCA-1", "Cardinal/HostAudio2"),
        ),
        stereo=True,
    ),
    "MODULAR_-_Granular_Veil.vcv": Example(
        "MIDI-driven dual oscillators, mixer, envelope/VCA and Clouds texture",
        ("Cardinal/HostMIDI", "Bogaudio/Bogaudio-VCO", "Bogaudio/Bogaudio-VCM",
         "Fundamental/ADSR", "Fundamental/VCA-1", "AudibleInstruments/Clouds",
         "Cardinal/HostAudio2"),
        (
            Route("MIDI gate to envelope", "Cardinal/HostMIDI", "Fundamental/ADSR"),
            Route("oscillators to mixer", "Bogaudio/Bogaudio-VCO", "Bogaudio/Bogaudio-VCM"),
            Route("mixer to VCA", "Bogaudio/Bogaudio-VCM", "Fundamental/VCA-1"),
            Route("envelope to VCA", "Fundamental/ADSR", "Fundamental/VCA-1"),
            Route("VCA into Clouds", "Fundamental/VCA-1", "AudibleInstruments/Clouds"),
            Route("Clouds to host", "AudibleInstruments/Clouds", "Cardinal/HostAudio2"),
        ),
        stereo=True,
        two_oscillators=True,
    ),
    "MODULAR_-_Clockwork_Pulses.vcv": Example(
        "Host-clocked sequencer, Plaits, LFO modulation and Plateau reverb",
        ("Cardinal/HostTime", "JW-Modules/GridSeq", "AudibleInstruments/Plaits",
         "Bogaudio/Bogaudio-LFO", "Valley/Plateau", "Cardinal/HostAudio2"),
        (
            Route("host transport to sequencer", "Cardinal/HostTime", "JW-Modules/GridSeq"),
            Route("sequencer to Plaits", "JW-Modules/GridSeq", "AudibleInstruments/Plaits"),
            Route("host transport to Plaits", "Cardinal/HostTime", "AudibleInstruments/Plaits"),
            Route("LFO modulation to Plaits", "Bogaudio/Bogaudio-LFO", "AudibleInstruments/Plaits"),
            Route("Plaits to reverb", "AudibleInstruments/Plaits", "Valley/Plateau"),
            Route("reverb to host", "Valley/Plateau", "Cardinal/HostAudio2"),
        ),
        stereo=True,
    ),
    "MODULAR_-_Morph_VCO_Performance.vcv": Example(
        "First-party Morph VCO, MIDI pitch/gate and enveloped output",
        ("Cardinal/HostMIDI", "ModularSynth/MorphVCO",
         "Fundamental/ADSR", "Fundamental/VCA-1", "Cardinal/HostAudio2"),
        (
            Route("MIDI pitch to Morph VCO", "Cardinal/HostMIDI",
                  "ModularSynth/MorphVCO", input=0),
            Route("MIDI gate to envelope", "Cardinal/HostMIDI", "Fundamental/ADSR"),
            Route("Morph VCO audio to VCA", "ModularSynth/MorphVCO",
                  "Fundamental/VCA-1", output=0),
            Route("envelope to VCA", "Fundamental/ADSR", "Fundamental/VCA-1"),
            Route("VCA to host", "Fundamental/VCA-1", "Cardinal/HostAudio2"),
        ),
    ),
    "MODULAR_-_Morphing_State_Pad.vcv": Example(
        "First-party Morph VCO, StateFilter, Macro8 snapshots and MIDI-controlled VCA",
        ("Cardinal/HostMIDI", "ModularSynth/MorphVCO", "ModularSynth/StateFilter",
         "ModularSynth/Macro8", "Fundamental/ADSR",
         "Fundamental/VCA-1", "Cardinal/HostAudio2"),
        (
            Route("MIDI pitch to Morph VCO", "Cardinal/HostMIDI",
                  "ModularSynth/MorphVCO", input=0),
            Route("MIDI gate to envelope", "Cardinal/HostMIDI", "Fundamental/ADSR"),
            Route("macro shape CV", "ModularSynth/Macro8",
                  "ModularSynth/MorphVCO", output=0, input=2),
            Route("macro resonance CV", "ModularSynth/Macro8",
                  "ModularSynth/StateFilter", output=1, input=2),
            Route("macro drive CV", "ModularSynth/Macro8",
                  "ModularSynth/StateFilter", output=2, input=3),
            Route("oscillator into filter", "ModularSynth/MorphVCO",
                  "ModularSynth/StateFilter", output=0, input=0),
            Route("filter lowpass to VCA", "ModularSynth/StateFilter",
                  "Fundamental/VCA-1", output=0),
            Route("envelope to VCA", "Fundamental/ADSR", "Fundamental/VCA-1"),
            Route("VCA to host", "Fundamental/VCA-1", "Cardinal/HostAudio2"),
        ),
        snapshot_names=("Shape", "Resonance", "Drive"),
    ),
    "MODULAR_-_Cinematic_Drift_Pad.vcv": Example(
        "Slow Macro8 snapshot morphs across a MIDI pad voice and filter cutoff",
        ("Cardinal/HostMIDI", "ModularSynth/MorphVCO", "ModularSynth/StateFilter",
         "ModularSynth/Macro8", "Fundamental/ADSR",
         "Fundamental/VCA-1", "Cardinal/HostAudio2"),
        (
            Route("MIDI pitch to oscillator", "Cardinal/HostMIDI",
                  "ModularSynth/MorphVCO", input=0),
            Route("MIDI gate to envelope", "Cardinal/HostMIDI", "Fundamental/ADSR"),
            Route("macro texture CV", "ModularSynth/Macro8",
                  "ModularSynth/MorphVCO", output=0, input=2),
            Route("macro resonance CV", "ModularSynth/Macro8",
                  "ModularSynth/StateFilter", output=1, input=2),
            Route("macro warmth CV", "ModularSynth/Macro8",
                  "ModularSynth/StateFilter", output=2, input=3),
            Route("macro bipolar cutoff CV", "ModularSynth/Macro8",
                  "ModularSynth/StateFilter", output=3, input=1),
            Route("oscillator into filter", "ModularSynth/MorphVCO",
                  "ModularSynth/StateFilter", output=0, input=0),
            Route("filter lowpass to VCA", "ModularSynth/StateFilter",
                  "Fundamental/VCA-1", output=0),
            Route("envelope to VCA", "Fundamental/ADSR", "Fundamental/VCA-1"),
            Route("VCA to host", "Fundamental/VCA-1", "Cardinal/HostAudio2"),
        ),
        snapshot_names=("Texture", "Resonance", "Warmth", "Cutoff"),
        morph_seconds=4.0,
        bipolar_cutoff=True,
    ),
    "MODULAR_-_Rhythmic_Grit_Bass.vcv": Example(
        "Short-ADSR MIDI bass with 0.20-second Macro8 transitions and cutoff CV",
        ("Cardinal/HostMIDI", "ModularSynth/MorphVCO", "ModularSynth/StateFilter",
         "ModularSynth/Macro8", "Fundamental/ADSR",
         "Fundamental/VCA-1", "Cardinal/HostAudio2"),
        (
            Route("MIDI pitch to oscillator", "Cardinal/HostMIDI",
                  "ModularSynth/MorphVCO", input=0),
            Route("MIDI gate to envelope", "Cardinal/HostMIDI", "Fundamental/ADSR"),
            Route("macro growl CV", "ModularSynth/Macro8",
                  "ModularSynth/MorphVCO", output=0, input=2),
            Route("macro resonance CV", "ModularSynth/Macro8",
                  "ModularSynth/StateFilter", output=1, input=2),
            Route("macro drive CV", "ModularSynth/Macro8",
                  "ModularSynth/StateFilter", output=2, input=3),
            Route("macro bipolar cutoff CV", "ModularSynth/Macro8",
                  "ModularSynth/StateFilter", output=3, input=1),
            Route("oscillator into filter", "ModularSynth/MorphVCO",
                  "ModularSynth/StateFilter", output=0, input=0),
            Route("filter lowpass to VCA", "ModularSynth/StateFilter",
                  "Fundamental/VCA-1", output=0),
            Route("envelope to VCA", "Fundamental/ADSR", "Fundamental/VCA-1"),
            Route("VCA to host", "Fundamental/VCA-1", "Cardinal/HostAudio2"),
        ),
        snapshot_names=("Growl", "Resonance", "Drive", "Cutoff"),
        morph_seconds=0.2,
        bipolar_cutoff=True,
    ),

    "MODULAR_-_Polyphonic_Motion_Pad.vcv": Example(
        "Eight-lane MIDI poly pad with per-note filter keytracking and four Macro8 snapshots",
        ("Cardinal/HostMIDI", "ModularSynth/MorphVCO", "ModularSynth/StateFilter",
         "ModularSynth/Macro8", "Fundamental/ADSR",
         "Fundamental/VCA-1", "Cardinal/HostAudio2"),
        (
            Route("MIDI pitch to oscillator", "Cardinal/HostMIDI",
                  "ModularSynth/MorphVCO", output=0, input=0),
            Route("per-voice MIDI pitch to filter cutoff", "Cardinal/HostMIDI",
                  "ModularSynth/StateFilter", output=0, input=1),
            Route("MIDI poly gate to envelope", "Cardinal/HostMIDI",
                  "Fundamental/ADSR", output=1, input=4),
            Route("MIDI poly retrigger to envelope", "Cardinal/HostMIDI",
                  "Fundamental/ADSR", output=6, input=5),
            Route("macro color CV", "ModularSynth/Macro8",
                  "ModularSynth/MorphVCO", output=0, input=2),
            Route("macro resonance CV", "ModularSynth/Macro8",
                  "ModularSynth/StateFilter", output=1, input=2),
            Route("macro warmth CV", "ModularSynth/Macro8",
                  "ModularSynth/StateFilter", output=2, input=3),
            Route("macro bipolar width CV", "ModularSynth/Macro8",
                  "ModularSynth/MorphVCO", output=3, input=3),
            Route("poly oscillator into poly filter", "ModularSynth/MorphVCO",
                  "ModularSynth/StateFilter", output=0, input=0),
            Route("poly filter into VCA audio", "ModularSynth/StateFilter",
                  "Fundamental/VCA-1", output=0, input=1),
            Route("poly envelope into VCA CV", "Fundamental/ADSR",
                  "Fundamental/VCA-1", output=0, input=0),
            Route("poly VCA to host left", "Fundamental/VCA-1",
                  "Cardinal/HostAudio2", output=0, input=0),
            Route("poly VCA to host right", "Fundamental/VCA-1",
                  "Cardinal/HostAudio2", output=0, input=1),
        ),
        stereo=True,
        snapshot_names=("Color", "Resonance", "Warmth", "Width"),
        snapshot_count=4,
        morph_seconds=1.8,
        bipolar_width=True,
        midi_channels=8,
        midi_poly_mode=1,
    ),

    "MODULAR_-_Stereo_Echo_Showcase.vcv": Example(
        "First-party MorphVCO, gated StateFilter LP/HP stereo split and StereoEcho ping-pong delay",
        ("Cardinal/HostMIDI", "ModularSynth/MorphVCO",
         "Fundamental/ADSR", "Fundamental/VCA-1",
         "ModularSynth/StateFilter", "ModularSynth/StereoEcho",
         "Cardinal/HostAudio2"),
        (
            Route("MIDI pitch to Morph VCO", "Cardinal/HostMIDI",
                  "ModularSynth/MorphVCO", output=0, input=0),
            Route("MIDI gate to ADSR", "Cardinal/HostMIDI",
                  "Fundamental/ADSR", output=1, input=4),
            Route("oscillator to gated VCA", "ModularSynth/MorphVCO",
                  "Fundamental/VCA-1", output=0, input=1),
            Route("envelope to VCA CV", "Fundamental/ADSR",
                  "Fundamental/VCA-1", output=0, input=0),
            Route("gated VCA to filter", "Fundamental/VCA-1",
                  "ModularSynth/StateFilter", output=0, input=0),
            Route("filter LP to StereoEcho left", "ModularSynth/StateFilter",
                  "ModularSynth/StereoEcho", output=0, input=0),
            Route("filter HP to StereoEcho right", "ModularSynth/StateFilter",
                  "ModularSynth/StereoEcho", output=2, input=1),
            Route("StereoEcho left to host left", "ModularSynth/StereoEcho",
                  "Cardinal/HostAudio2", output=0, input=0),
            Route("StereoEcho right to host right", "ModularSynth/StereoEcho",
                  "Cardinal/HostAudio2", output=1, input=1),
        ),
        stereo=True,
    ),
    "MODULAR_-_Echo_Motion_Performance.vcv": Example(
        "MIDI-gated first-party LP/HP stereo echo with four Macro8 delay-motion snapshots",
        ("Cardinal/HostMIDI", "ModularSynth/MorphVCO",
         "Fundamental/ADSR", "Fundamental/VCA-1",
         "ModularSynth/StateFilter", "ModularSynth/StereoEcho",
         "ModularSynth/Macro8", "Cardinal/HostAudio2"),
        (
            Route("MIDI pitch to Morph VCO", "Cardinal/HostMIDI",
                  "ModularSynth/MorphVCO", output=0, input=0),
            Route("MIDI gate to ADSR", "Cardinal/HostMIDI",
                  "Fundamental/ADSR", output=1, input=4),
            Route("oscillator into gated VCA", "ModularSynth/MorphVCO",
                  "Fundamental/VCA-1", output=0, input=1),
            Route("ADSR envelope into VCA", "Fundamental/ADSR",
                  "Fundamental/VCA-1", output=0, input=0),
            Route("gated VCA into StateFilter", "Fundamental/VCA-1",
                  "ModularSynth/StateFilter", output=0, input=0),
            Route("lowpass to StereoEcho left", "ModularSynth/StateFilter",
                  "ModularSynth/StereoEcho", output=0, input=0),
            Route("highpass to StereoEcho right", "ModularSynth/StateFilter",
                  "ModularSynth/StereoEcho", output=2, input=1),
            Route("Macro8 time CV to Echo input 2", "ModularSynth/Macro8",
                  "ModularSynth/StereoEcho", output=0, input=2),
            Route("Macro8 feedback CV to Echo input 3", "ModularSynth/Macro8",
                  "ModularSynth/StereoEcho", output=1, input=3),
            Route("Macro8 wet CV to Echo input 4", "ModularSynth/Macro8",
                  "ModularSynth/StereoEcho", output=2, input=4),
            Route("Macro8 wave CV to oscillator", "ModularSynth/Macro8",
                  "ModularSynth/MorphVCO", output=3, input=2),
            Route("StereoEcho left into host left", "ModularSynth/StereoEcho",
                  "Cardinal/HostAudio2", output=0, input=0),
            Route("StereoEcho right into host right", "ModularSynth/StereoEcho",
                  "Cardinal/HostAudio2", output=1, input=1),
        ),
        stereo=True,
        snapshot_names=("Time", "Feedback", "Wet", "Wave"),
        snapshot_count=4,
        morph_seconds=1.2,
        unipolar_macro_outputs=(0, 1, 2, 3),
    ),

}


def _key(module: dict) -> str:
    return f"{module['plugin']}/{module['model']}"


def _routes_for(patch: dict, modules_by_id: dict[int, dict]) -> list[tuple[dict, dict, dict]]:
    return [
        (modules_by_id[cable["outputModuleId"]],
         modules_by_id[cable["inputModuleId"]], cable)
        for cable in patch["cables"]
    ]


def _claim_present(route: Route, routes: list[tuple[dict, dict, dict]]) -> bool:
    return any(
        _key(source) == route.source
        and _key(target) == route.target
        and (route.output is None or cable["outputId"] == route.output)
        and (route.input is None or cable["inputId"] == route.input)
        for source, target, cable in routes
    )


def _check_stereo(routes: list[tuple[dict, dict, dict]]) -> bool:
    host_ids: dict[int, set[int]] = {}
    for _source, target, cable in routes:
        if _key(target) == "Cardinal/HostAudio2":
            host_ids.setdefault(target["id"], set()).add(cable["inputId"])
    # A patch routes both jack indices of one stored HostAudio2 instance.
    # Whether an installed host exposes those exact jacks is NOT tested here.
    return any({0, 1}.issubset(inputs) for inputs in host_ids.values())


def _check_dual_oscillators(modules_by_id: dict[int, dict],
                            routes: list[tuple[dict, dict, dict]]) -> bool:
    oscillators = {
        mid for mid, module in modules_by_id.items()
        if _key(module) == "Bogaudio/Bogaudio-VCO"
    }
    mixers = {
        mid for mid, module in modules_by_id.items()
        if _key(module) == "Bogaudio/Bogaudio-VCM"
    }
    if len(oscillators) < 2 or not mixers:
        return False
    # Check every oscillator receives host MIDI and both arrive at a
    # common mixer, not just that these models happen to be in the patch.
    midi_fed = {
        target["id"] for source, target, _ in routes
        if _key(source) == "Cardinal/HostMIDI" and target["id"] in oscillators
    }
    if not oscillators.issubset(midi_fed):
        return False
    return any(all(
        any(source["id"] == osc and target["id"] == mixer
            for source, target, _ in routes)
        for osc in oscillators
    ) for mixer in mixers)


def _check_macro_snapshots(modules_by_id: dict[int, dict],
                           names_prefix: tuple[str, ...],
                           populated_count: int) -> bool:
    macros = [
        module for module in modules_by_id.values()
        if _key(module) == "ModularSynth/Macro8"
    ]
    if len(macros) != 1:
        return False
    data = macros[0].get("data")
    if not isinstance(data, dict) or data.get("macro8Version") != 1:
        return False
    names = data.get("names")
    snapshots = data.get("snapshots")
    if not isinstance(names, list) or len(names) != 8:
        return False
    if names[:len(names_prefix)] != list(names_prefix) or not all(
        isinstance(name, str) and name.strip() for name in names
    ):
        return False
    if not isinstance(snapshots, list) or len(snapshots) != 4:
        return False
    if not 0 <= populated_count <= len(snapshots):
        return False
    if not all(isinstance(slot, list) and len(slot) == 8
               for slot in snapshots[:populated_count]):
        return False
    if any(slot is not None for slot in snapshots[populated_count:]):
        return False
    return all(
        isinstance(value, (float, int)) and not isinstance(value, bool)
        and math.isfinite(value) and 0.0 <= value <= 1.0
        for slot in snapshots[:populated_count] for value in slot
    )


def analyze(root: Path = ROOT, examples_dir: Path | None = None) -> dict:
    """Return explicit coverage report; errors indicate unmet source claims."""
    root = Path(root)
    examples_dir = Path(examples_dir) if examples_dir else root / "patches" / "examples"
    manifest = patch_inspector._strict_json(root / "plugins/ModularSynth/plugin.json")
    if not isinstance(manifest, dict) or manifest.get("slug") != "ModularSynth":
        raise ValueError("Expected ModularSynth source manifest")
    entries = manifest.get("modules")
    if not isinstance(entries, list) or not all(
        isinstance(entry, dict) and isinstance(entry.get("slug"), str)
        for entry in entries
    ):
        raise ValueError("Invalid ModularSynth modules manifest")
    manifest_slugs = sorted({entry["slug"] for entry in entries})
    coverage: dict[str, list[str]] = {slug: [] for slug in manifest_slugs}
    files = sorted(examples_dir.glob("MODULAR_-_*.vcv"))
    errors: list[str] = []
    example_reports: list[dict] = []
    available = {path.name for path in files}

    for missing in sorted(set(EXAMPLES) - available):
        errors.append(f"{missing}: advertised example patch is missing")
    for unreviewed in sorted(available - set(EXAMPLES)):
        errors.append(f"{unreviewed}: no source-grounded capability claims reviewed")

    for path in files:
        spec = EXAMPLES.get(path.name)
        structural = patch_inspector.inspect_patch(path, root)
        result = {
            "patch": path.name, "ok": False, "modules": {},
            "capabilities": [], "warning_count": len(structural["warnings"]),
            "errors": list(structural["errors"]),
        }
        example_reports.append(result)
        if not structural["ok"]:
            errors.extend(f"{path.name}: {err}" for err in structural["errors"])
            continue

        patch = patch_inspector._strict_json(path)
        modules_by_id = {module["id"]: module for module in patch["modules"]}
        inventory = Counter(_key(module) for module in modules_by_id.values())
        result["modules"] = dict(sorted(inventory.items()))
        for slug in manifest_slugs:
            if inventory.get(f"ModularSynth/{slug}", 0):
                coverage[slug].append(path.name)

        if spec is None:
            continue
        local_errors = result["errors"]
        for model in spec.models:
            if inventory.get(model, 0) < 1:
                local_errors.append(f"missing required advertised model {model}")
        routes = _routes_for(patch, modules_by_id)
        for claim in spec.routes:
            if not _claim_present(claim, routes):
                local_errors.append(f"missing advertised route: {claim.label} "
                                    f"({claim.source} -> {claim.target})")
            else:
                result["capabilities"].append(claim.label)
        if spec.stereo:
            if not _check_stereo(routes):
                local_errors.append("missing two saved HostAudio2 input routes (jacks 0 and 1)")
            else:
                result["capabilities"].append("two host audio input routes")
        if spec.two_oscillators:
            if not _check_dual_oscillators(modules_by_id, routes):
                local_errors.append("both VCO instances must receive MIDI and feed one mixer")
            else:
                result["capabilities"].append("both MIDI-driven oscillators feed one mixer")
        if spec.snapshot_names:
            if not _check_macro_snapshots(modules_by_id, spec.snapshot_names,
                                          spec.snapshot_count):
                local_errors.append("missing documented Macro8 names or "
                                    "required populated eight-value snapshots")
            else:
                result["capabilities"].append(
                    f"{spec.snapshot_count} versioned Macro8 snapshots")
        if (spec.morph_seconds is not None or spec.bipolar_cutoff
                or spec.bipolar_width or spec.unipolar_macro_outputs):
            macro = next((module for module in modules_by_id.values()
                          if _key(module) == "ModularSynth/Macro8"), None)
            param_values = {
                entry["id"]: entry["value"]
                for entry in macro.get("params", [])
            } if macro is not None else {}
            if spec.morph_seconds is not None:
                seconds = param_values.get(8)
                if not isinstance(seconds, (int, float)) or not math.isclose(
                    seconds, spec.morph_seconds, abs_tol=1e-5
                ):
                    local_errors.append(
                        f"expected Macro8 morph time {spec.morph_seconds:.2f} s "
                        "(first-party param 8)")
                else:
                    result["capabilities"].append("documented Macro8 morph time")
            if spec.bipolar_cutoff:
                if param_values.get(18) != 1:
                    local_errors.append(
                        "macro cutoff CV output range must be bipolar "
                        "(first-party param 18 == 1)")
                else:
                    result["capabilities"].append("bipolar Macro8 cutoff output range")
            if spec.bipolar_width:
                if param_values.get(18) != 1:
                    local_errors.append(
                        "macro width CV output range must be bipolar "
                        "(first-party param 18 == 1)")
                else:
                    result["capabilities"].append("bipolar Macro8 PWM output range")
            for output in spec.unipolar_macro_outputs:
                # Macro8 range params 15..22: 0 means 0..+10 V.
                range_param = 15 + output
                if output < 0 or output >= 8 or param_values.get(range_param) != 0:
                    local_errors.append(
                        f"macro output {output} CV range must be unipolar "
                        f"(first-party param {range_param} == 0)")
                else:
                    result["capabilities"].append(
                        f"unipolar Macro8 output {output} CV")
        if spec.midi_channels is not None:
            midi = next((module for module in modules_by_id.values()
                         if _key(module) == "Cardinal/HostMIDI"), None)
            data = midi.get("data") if midi is not None else None
            if not isinstance(data, dict) or (
                data.get("channels") != spec.midi_channels
                or data.get("polyMode") != spec.midi_poly_mode
            ):
                local_errors.append(
                    f"expected HostMIDI {spec.midi_channels}-channel Reuse polyphony "
                    "(source data.channels and data.polyMode)")
            else:
                result["capabilities"].append(
                    f"{spec.midi_channels}-channel HostMIDI Reuse polyphony")
        if local_errors:
            errors.extend(f"{path.name}: {err}" for err in local_errors)
        result["ok"] = not local_errors

    for slug, patches in coverage.items():
        if not patches:
            errors.append(f"ModularSynth/{slug}: no first-party example instantiates this model")

    return {
        "ok": not errors,
        "examples": example_reports,
        "model_coverage": coverage,
        "errors": errors,
        "sample_rate_status": "not asserted: no host runtime sample-rate execution",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--examples-dir", type=Path)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable report")
    args = parser.parse_args(argv)
    try:
        report = analyze(args.repo_root, args.examples_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: could not analyze source: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"{'PASS' if report['ok'] else 'FAIL'} factory patch claims "
              f"({len(report['examples'])} examples, "
              f"{len(report['model_coverage'])} original models)")
        for slug, patches in sorted(report["model_coverage"].items()):
            print(f"  ModularSynth/{slug}: {', '.join(patches) or 'NOT COVERED'}")
        for patch in report["examples"]:
            print(f"  {'PASS' if patch['ok'] else 'FAIL'} {patch['patch']}: "
                  f"{len(patch['capabilities'])} graph/data claims, "
                  f"{patch['warning_count']} inspector warnings")
        for err in report["errors"]:
            print(f"  ERROR: {err}")
        print("  Sample rates: host execution not tested")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
