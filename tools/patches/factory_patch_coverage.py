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
    rhythmic_lp_gate: bool = False
    free_lfo_rate_hz: float | None = None
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
    "MODULAR_-_Chance_Hold_FM_Drift.vcv": Example(
        "Seeded Chance Hold smoothed random CV sweeps the FM index",
        ("Cardinal/HostMIDI", "ModularSynth/ChanceHold", "ModularSynth/FMVoice",
         "Fundamental/ADSR", "Fundamental/VCA-1", "Cardinal/HostAudio2"),
        (
            Route("MIDI pitch to FM oscillator", "Cardinal/HostMIDI",
                  "ModularSynth/FMVoice", output=0, input=0),
            Route("MIDI gate to envelope", "Cardinal/HostMIDI",
                  "Fundamental/ADSR", output=1, input=4),
            Route("Chance Hold SMOOTH to FM index CV", "ModularSynth/ChanceHold",
                  "ModularSynth/FMVoice", output=1, input=2),
            Route("FM audio to VCA", "ModularSynth/FMVoice",
                  "Fundamental/VCA-1", output=0, input=1),
            Route("ADSR to VCA CV", "Fundamental/ADSR",
                  "Fundamental/VCA-1", output=0, input=0),
            Route("VCA to host", "Fundamental/VCA-1",
                  "Cardinal/HostAudio2", output=0, input=0),
        ),
    ),
    "MODULAR_-_FM_Voice_Performance.vcv": Example("
        "Two-operator FM Voice with MIDI pitch/gate and enveloped output",
        ("Cardinal/HostMIDI", "ModularSynth/FMVoice",
         "Fundamental/ADSR", "Fundamental/VCA-1", "Cardinal/HostAudio2"),
        (
            Route("MIDI pitch to FM Voice 1V/oct", "Cardinal/HostMIDI",
                  "ModularSynth/FMVoice", output=0, input=0),
            Route("MIDI gate to FM envelope", "Cardinal/HostMIDI",
                  "Fundamental/ADSR", output=1, input=4),
            Route("FM carrier audio to VCA", "ModularSynth/FMVoice",
                  "Fundamental/VCA-1", output=0, input=1),
            Route("FM envelope to VCA CV", "Fundamental/ADSR",
                  "Fundamental/VCA-1", output=0, input=0),
            Route("FM VCA to host", "Fundamental/VCA-1",
                  "Cardinal/HostAudio2", output=0, input=0),
        ),
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

    "MODULAR_-_Clocked_Modulation_Studio.vcv": Example(
        "Eight-lane HostTime beat-synced ClockedLFO with MIDI-gated stereo filtering and Echo",
        ("Cardinal/HostTime", "Cardinal/HostMIDI", "ModularSynth/ClockedLFO",
         "ModularSynth/MorphVCO", "Fundamental/ADSR", "Fundamental/VCA-1",
         "ModularSynth/StateFilter", "ModularSynth/StereoEcho", "Cardinal/HostAudio2"),
        (
            Route("host beat clocks LFO", "Cardinal/HostTime",
                  "ModularSynth/ClockedLFO", output=3, input=1),
            Route("host reset phase-aligns LFO", "Cardinal/HostTime",
                  "ModularSynth/ClockedLFO", output=1, input=2),
            Route("MIDI pitch controls oscillator", "Cardinal/HostMIDI",
                  "ModularSynth/MorphVCO", output=0, input=0),
            Route("MIDI pitch provides poly free-rate CV", "Cardinal/HostMIDI",
                  "ModularSynth/ClockedLFO", output=0, input=0),
            Route("MIDI gate to ADSR", "Cardinal/HostMIDI",
                  "Fundamental/ADSR", output=1, input=4),
            Route("LFO cycle trigger to ADSR retrigger", "ModularSynth/ClockedLFO",
                  "Fundamental/ADSR", output=4, input=5),
            Route("oscillator into VCA", "ModularSynth/MorphVCO",
                  "Fundamental/VCA-1", output=0, input=1),
            Route("ADSR opens VCA", "Fundamental/ADSR",
                  "Fundamental/VCA-1", output=0, input=0),
            Route("LFO sine modulates VCO morph", "ModularSynth/ClockedLFO",
                  "ModularSynth/MorphVCO", output=0, input=2),
            Route("gated VCA to filter", "Fundamental/VCA-1",
                  "ModularSynth/StateFilter", output=0, input=0),
            Route("LFO triangle modulates filter cutoff", "ModularSynth/ClockedLFO",
                  "ModularSynth/StateFilter", output=1, input=1),
            Route("filter LP to Echo left", "ModularSynth/StateFilter",
                  "ModularSynth/StereoEcho", output=0, input=0),
            Route("filter HP to Echo right", "ModularSynth/StateFilter",
                  "ModularSynth/StereoEcho", output=2, input=1),
            Route("LFO pulse switches Echo wet mix", "ModularSynth/ClockedLFO",
                  "ModularSynth/StereoEcho", output=3, input=4),
            Route("Echo left to host left", "ModularSynth/StereoEcho",
                  "Cardinal/HostAudio2", output=0, input=0),
            Route("Echo right to host right", "ModularSynth/StereoEcho",
                  "Cardinal/HostAudio2", output=1, input=1),
        ),
        stereo=True,
        midi_channels=8,
        midi_poly_mode=1,
    ),
    "MODULAR_-_Cinematic_Pulse_Score.vcv": Example(
        "Free-running MIDI score with dual ADSR/VCA roles, LFO-pulsed LP and continuous HP stereo Echo",
        ("Cardinal/HostMIDI", "ModularSynth/ClockedLFO",
         "ModularSynth/Macro8", "ModularSynth/MorphVCO",
         "Fundamental/ADSR", "Fundamental/VCA-1",
         "ModularSynth/StateFilter", "ModularSynth/StereoEcho",
         "Cardinal/HostAudio2"),
        (
            Route("MIDI pitch to oscillator", "Cardinal/HostMIDI",
                  "ModularSynth/MorphVCO", output=0, input=0),
            Route("MIDI gate to main ADSR", "Cardinal/HostMIDI",
                  "Fundamental/ADSR", output=1, input=4),
            Route("oscillator into main VCA", "ModularSynth/MorphVCO",
                  "Fundamental/VCA-1", output=0, input=1),
            Route("main ADSR into main VCA CV", "Fundamental/ADSR",
                  "Fundamental/VCA-1", output=0, input=0),
            Route("main VCA into StateFilter", "Fundamental/VCA-1",
                  "ModularSynth/StateFilter", output=0, input=0),
            Route("filter LP into rhythmic VCA", "ModularSynth/StateFilter",
                  "Fundamental/VCA-1", output=0, input=1),
            Route("LFO pulse into rhythmic ADSR gate", "ModularSynth/ClockedLFO",
                  "Fundamental/ADSR", output=3, input=4),
            Route("rhythmic ADSR into rhythmic VCA CV", "Fundamental/ADSR",
                  "Fundamental/VCA-1", output=0, input=0),
            Route("rhythmic VCA into Echo left", "Fundamental/VCA-1",
                  "ModularSynth/StereoEcho", output=0, input=0),
            Route("filter HP into Echo right", "ModularSynth/StateFilter",
                  "ModularSynth/StereoEcho", output=2, input=1),
            Route("Echo left into host left", "ModularSynth/StereoEcho",
                  "Cardinal/HostAudio2", output=0, input=0),
            Route("Echo right into host right", "ModularSynth/StereoEcho",
                  "Cardinal/HostAudio2", output=1, input=1),
            Route("LFO sine into oscillator morph CV", "ModularSynth/ClockedLFO",
                  "ModularSynth/MorphVCO", output=0, input=2),
            Route("macro tension to filter resonance CV", "ModularSynth/Macro8",
                  "ModularSynth/StateFilter", output=0, input=2),
            Route("macro warmth to filter drive CV", "ModularSynth/Macro8",
                  "ModularSynth/StateFilter", output=1, input=3),
            Route("macro repeats to Echo feedback CV", "ModularSynth/Macro8",
                  "ModularSynth/StereoEcho", output=2, input=3),
            Route("macro space to Echo wet CV", "ModularSynth/Macro8",
                  "ModularSynth/StereoEcho", output=3, input=4),
        ),
        stereo=True,
        rhythmic_lp_gate=True,
        free_lfo_rate_hz=0.8,
        snapshot_names=("Tension", "Warmth", "Repeats", "Space"),
        snapshot_count=4,
        morph_seconds=2.6,
        unipolar_macro_outputs=(0, 1, 2, 3),
    ),
    "MODULAR_-_Noir_Expressive_Lead.vcv": Example(
        "Mono MIDI noir lead with channel aftertouch timbre, mod-wheel Echo wet and Macro8 scenes",
        ("Cardinal/HostMIDI", "ModularSynth/MorphVCO",
         "ModularSynth/StateFilter", "Fundamental/ADSR",
         "Fundamental/VCA-1", "ModularSynth/StereoEcho",
         "ModularSynth/Macro8", "Cardinal/HostAudio2"),
        (
            Route("MIDI pitch drives MorphVCO", "Cardinal/HostMIDI",
                  "ModularSynth/MorphVCO", output=0, input=0),
            Route("MIDI gate opens ADSR", "Cardinal/HostMIDI",
                  "Fundamental/ADSR", output=1, input=4),
            Route("aftertouch shapes the oscillator", "Cardinal/HostMIDI",
                  "ModularSynth/MorphVCO", output=3, input=2),
            Route("mod wheel raises Echo wet mix", "Cardinal/HostMIDI",
                  "ModularSynth/StereoEcho", output=5, input=4),
            Route("oscillator to low-pass filter", "ModularSynth/MorphVCO",
                  "ModularSynth/StateFilter", output=0, input=0),
            Route("low-pass to voice VCA", "ModularSynth/StateFilter",
                  "Fundamental/VCA-1", output=0, input=1),
            Route("ADSR opens voice VCA", "Fundamental/ADSR",
                  "Fundamental/VCA-1", output=0, input=0),
            Route("gated voice to Echo left", "Fundamental/VCA-1",
                  "ModularSynth/StereoEcho", output=0, input=0),
            Route("Echo left to host left", "ModularSynth/StereoEcho",
                  "Cardinal/HostAudio2", output=0, input=0),
            Route("Echo right to host right", "ModularSynth/StereoEcho",
                  "Cardinal/HostAudio2", output=1, input=1),
            Route("macro time to Echo", "ModularSynth/Macro8",
                  "ModularSynth/StereoEcho", output=0, input=2),
            Route("macro repeats to Echo", "ModularSynth/Macro8",
                  "ModularSynth/StereoEcho", output=1, input=3),
            Route("macro resonance to filter", "ModularSynth/Macro8",
                  "ModularSynth/StateFilter", output=2, input=2),
            Route("macro drive to filter", "ModularSynth/Macro8",
                  "ModularSynth/StateFilter", output=3, input=3),
            Route("macro pulse width to MorphVCO", "ModularSynth/Macro8",
                  "ModularSynth/MorphVCO", output=4, input=3),
        ),
        stereo=True,
        snapshot_names=("Delay Time", "Echo FB", "Resonance", "Drive", "Pulse Width"),
        snapshot_count=4,
        morph_seconds=0.65,
        unipolar_macro_outputs=(0, 1, 2, 3, 4),
    ),

    "MODULAR_-_Fold_Drive_Cinematic_Motion.vcv": Example(
        "Eight-voice sine-fold sound design with free-running bipolar LFO and MIDI expression",
        ("Cardinal/HostMIDI", "ModularSynth/MorphVCO", "ModularSynth/FoldDrive",
         "ModularSynth/ClockedLFO", "ModularSynth/StateFilter",
         "Fundamental/ADSR", "Fundamental/VCA-1", "Cardinal/HostAudio2"),
        (
            Route("MIDI poly pitch controls oscillator", "Cardinal/HostMIDI",
                  "ModularSynth/MorphVCO", output=0, input=0),
            Route("MIDI poly gate opens ADSR", "Cardinal/HostMIDI",
                  "Fundamental/ADSR", output=1, input=4),
            Route("MIDI retrigger restarts ADSR", "Cardinal/HostMIDI",
                  "Fundamental/ADSR", output=6, input=5),
            Route("MIDI aftertouch changes VCO wave", "Cardinal/HostMIDI",
                  "ModularSynth/MorphVCO", output=3, input=2),
            Route("MIDI mod wheel changes FoldDrive wet mix", "Cardinal/HostMIDI",
                  "ModularSynth/FoldDrive", output=5, input=3),
            Route("morph oscillator into FoldDrive audio", "ModularSynth/MorphVCO",
                  "ModularSynth/FoldDrive", output=0, input=0),
            Route("LFO triangle modulates fold drive", "ModularSynth/ClockedLFO",
                  "ModularSynth/FoldDrive", output=1, input=1),
            Route("LFO sine modulates fold bias", "ModularSynth/ClockedLFO",
                  "ModularSynth/FoldDrive", output=0, input=2),
            Route("folded audio into StateFilter", "ModularSynth/FoldDrive",
                  "ModularSynth/StateFilter", output=0, input=0),
            Route("filter lowpass into VCA audio", "ModularSynth/StateFilter",
                  "Fundamental/VCA-1", output=0, input=1),
            Route("envelope into VCA level", "Fundamental/ADSR",
                  "Fundamental/VCA-1", output=0, input=0),
            Route("VCA to nominal left host", "Fundamental/VCA-1",
                  "Cardinal/HostAudio2", output=0, input=0),
            Route("VCA to nominal right host", "Fundamental/VCA-1",
                  "Cardinal/HostAudio2", output=0, input=1),
        ),
        stereo=True,
        midi_channels=8,
        midi_poly_mode=1,
        free_lfo_rate_hz=0.25,
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



def _check_dual_envelope_pulse_roles(
        modules_by_id: dict[int, dict],
        routes: list[tuple[dict, dict, dict]]) -> bool:
    """Prove two distinct ADSR/VCA chains, not merely two reused model labels.

    Fundamental's checked-in ADSR has gate input 4/envelope output 0;
    VCA-1 has CV input 0, audio input 1, audio output 0. We deliberately
    bind each claimed route to the SAME patch-local module IDs.
    """
    def ids(key: str) -> set[int]:
        return {mid for mid, m in modules_by_id.items() if _key(m) == key}

    midi, lfo = ids("Cardinal/HostMIDI"), ids("ModularSynth/ClockedLFO")
    osc, filt = ids("ModularSynth/MorphVCO"), ids("ModularSynth/StateFilter")
    echo = ids("ModularSynth/StereoEcho")
    adsrs, vcas = ids("Fundamental/ADSR"), ids("Fundamental/VCA-1")
    if not (len(midi) == len(lfo) == len(osc) == len(filt) == len(echo) == 1
            and len(adsrs) == len(vcas) == 2):
        return False

    edges = {(src["id"], cable["outputId"], dst["id"], cable["inputId"])
             for src, dst, cable in routes}

    def linked(source: int, out: int, target: int, inp: int) -> bool:
        return (source, out, target, inp) in edges

    (midi_id,), (lfo_id,), (osc_id,), (filt_id,), (echo_id,) = (
        tuple(midi), tuple(lfo), tuple(osc), tuple(filt), tuple(echo))
    for voice_adsr in adsrs:
        if not linked(midi_id, 1, voice_adsr, 4):
            continue
        for rhythm_adsr in adsrs - {voice_adsr}:
            if not linked(lfo_id, 3, rhythm_adsr, 4):
                continue
            for voice_vca in vcas:
                if not (linked(osc_id, 0, voice_vca, 1)
                        and linked(voice_adsr, 0, voice_vca, 0)
                        and linked(voice_vca, 0, filt_id, 0)):
                    continue
                for rhythm_vca in vcas - {voice_vca}:
                    if (linked(filt_id, 0, rhythm_vca, 1)
                            and linked(rhythm_adsr, 0, rhythm_vca, 0)
                            and linked(rhythm_vca, 0, echo_id, 0)):
                        return True
    return False


def _matches_free_lfo_rate(log2_hz: object, expected_hz: float) -> bool:
    """Bound saved ClockedLFO RATE_PARAM0 before exponentiating.

    Source configParam(RATE_PARAM, -6.0f, 4.0f, ...) defines the finite
    permitted knob domain. Compare the numeric range before math.isfinite:
    an untrusted arbitrarily large Python integer could itself overflow
    during an eager int-to-float conversion by math.isfinite.
    """
    if type(log2_hz) not in (int, float):
        return False
    if not -6.0 <= log2_hz <= 4.0:
        return False
    if not math.isfinite(log2_hz):
        return False
    return math.isclose(2.0 ** log2_hz, expected_hz,
                        rel_tol=0.0, abs_tol=1e-4)


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
        if spec.rhythmic_lp_gate:
            if not _check_dual_envelope_pulse_roles(modules_by_id, routes):
                local_errors.append(
                    "rhythmic LP requires two distinct MIDI/LFO ADSR-to-VCA "
                    "chains with role-specific filter/Echo routing")
            else:
                result["capabilities"].append(
                    "separate MIDI voice and LFO pulse ADSR/VCA chains")
        if spec.free_lfo_rate_hz is not None:
            lfos = [m for m in modules_by_id.values()
                    if _key(m) == "ModularSynth/ClockedLFO"]
            host_time = any(_key(m) == "Cardinal/HostTime"
                            for m in modules_by_id.values())
            if len(lfos) == 1:
                lfo = lfos[0]
                params = {p["id"]: p["value"] for p in lfo.get("params", [])}
                rate_log2 = params.get(0)
                rate_ok = _matches_free_lfo_rate(
                    rate_log2, spec.free_lfo_rate_hz)
                clock_or_reset = any(
                    cable["inputModuleId"] == lfo["id"]
                    and cable["inputId"] in (1, 2)
                    for cable in patch["cables"]
                )
            else:
                rate_ok = False
                clock_or_reset = True
            if host_time or clock_or_reset or not rate_ok:
                local_errors.append(
                    "expected free-running LFO with saved rate "
                    f"{spec.free_lfo_rate_hz:g} Hz, no HostTime or CLOCK/RESET cables")
            else:
                result["capabilities"].append(
                    f"free-running LFO at {spec.free_lfo_rate_hz:g} Hz; no host clock")
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
