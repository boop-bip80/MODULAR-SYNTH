#!/usr/bin/env python3
"""Source-grounded Rack tooltip/units invariants for first-party modules.

These tests verify metadata against known DSP scaling and documented display
conventions. They do not render a Rack tooltip or validate a DAW host UI.
"""
from __future__ import annotations

import math
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = ROOT / "plugins" / "ModularSynth" / "src"
MODULES = ("MorphVCO", "StateFilter", "Macro8")


def _source(model: str) -> str:
    return (MODULE_DIR / (model + ".cpp")).read_text(encoding="utf-8")


def _compact(source: str) -> str:
    return re.sub(r"\s+", " ", source)


def _split_arguments(source: str) -> list[str]:
    result: list[str] = []
    start = 0
    depth = 0
    quote = ""
    escaped = False
    for index, char in enumerate(source):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in ('"', "'"):
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            result.append(source[start:index].strip())
            start = index + 1
    result.append(source[start:].strip())
    return result


def _config_calls(source: str, method: str) -> list[list[str]]:
    calls: list[list[str]] = []
    for match in re.finditer(r"\b" + re.escape(method) + r"\s*\(", source):
        start = match.end()
        cursor = start
        depth = 1
        quote = ""
        escaped = False
        while depth and cursor < len(source):
            char = source[cursor]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
            elif char in ('"', "'"):
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            cursor += 1
        if depth != 0:
            raise ValueError(f"unterminated {method} call")
        calls.append(_split_arguments(source[start:cursor - 1]))
    return calls


def _number(text: str) -> float:
    return float(text.strip().rstrip("fF"))


class FirstPartyTooltipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = {name: _source(name) for name in MODULES}

    def config(self, model: str, method: str, identifier: str) -> list[str]:
        matches = [args for args in _config_calls(self.sources[model], method)
                   if args and args[0] == identifier]
        self.assertEqual(len(matches), 1,
                         f"expected one {model} {method}({identifier}, ...) call")
        return matches[0]

    def check_percent_param(self, model: str, identifier: str, minimum: float,
                            maximum: float, default: float) -> list[str]:
        args = self.config(model, "configParam", identifier)
        self.assertEqual(tuple(_number(value) for value in args[1:4]),
                         (minimum, maximum, default))
        self.assertEqual(args[5:], ['" %"', '0.0f', '100.0f'])
        self.assertEqual(_number(args[7]) * default, default * 100.0)
        return args

    def test_expected_config_cardinality(self) -> None:
        self.assertEqual(len(_config_calls(self.sources["MorphVCO"], "configParam")), 5)
        self.assertEqual(len(_config_calls(self.sources["StateFilter"], "configParam")), 3)
        # Macro8 registers one indexed eight-knob bank and one morph-time knob.
        self.assertEqual(len(_config_calls(self.sources["Macro8"], "configParam")), 2)
        self.assertEqual(len(_config_calls(self.sources["Macro8"], "configOutput")), 1)

    def test_morph_octave_fine_and_percentage_knobs(self) -> None:
        octave = self.config("MorphVCO", "configParam", "OCTAVE_PARAM")
        self.assertEqual(tuple(_number(v) for v in octave[1:4]), (-4.0, 4.0, 0.0))
        self.assertEqual(octave[4], '"Octave offset"')
        self.assertIn("getParamQuantity(OCTAVE_PARAM)->snapEnabled = true;",
                      self.sources["MorphVCO"])
        fine = self.config("MorphVCO", "configParam", "FINE_PARAM")
        self.assertEqual(tuple(_number(v) for v in fine[1:4]), (-100, 100, 0))
        self.assertEqual(fine[5], '" cents"')
        self.check_percent_param("MorphVCO", "MORPH_PARAM", 0, 1, 0)
        width = self.check_percent_param("MorphVCO", "PULSE_WIDTH_PARAM",
                                         0.05, 0.95, 0.5)
        self.assertEqual(width[4], '"Pulse width"')
        self.check_percent_param("MorphVCO", "FM_DEPTH_PARAM", 0, 1, 0)
        self.assertEqual(0.05 * 100, 5)
        self.assertEqual(0.95 * 100, 95)

    def test_morph_cv_sensitivity_labels_match_code(self) -> None:
        src = _compact(self.sources["MorphVCO"])
        expected = {
            "PITCH_INPUT": "Pitch CV (1 V/oct)",
            "FM_INPUT": "Exponential FM CV (5 V/oct at 100% depth)",
            "MORPH_CV_INPUT": "Wave morph CV (10 V full span; adds to knob)",
            "PWM_CV_INPUT": "Pulse width CV (10 V full span; adds to knob)",
        }
        for identifier, name in expected.items():
            self.assertEqual(self.config("MorphVCO", "configInput", identifier),
                             [identifier, f'"{name}"'])
        self.assertIn("pitchOctave = baseOctave + fineOctave + pitchCV + (fmCV / 5.0) * fmDepth;",
                      src)
        self.assertRegex(src, r"morph = baseMorph \+ inputs\[MORPH_CV_INPUT\].+ \* 0\.1f;")
        self.assertRegex(src, r"width = baseWidth \+ inputs\[PWM_CV_INPUT\].+ \* 0\.1f;")

    def test_morph_outputs_explain_audio_range(self) -> None:
        for identifier, name in (
            ("MORPH_OUTPUT", "Morphed waveform audio (nominal +/-5 V)"),
            ("SINE_OUTPUT", "Sine waveform audio (nominal +/-5 V)"),
        ):
            self.assertEqual(self.config("MorphVCO", "configOutput", identifier),
                             [identifier, f'"{name}"'])
        src = self.sources["MorphVCO"]
        self.assertIn("setVoltage(5.0f * sample.morph, c)", src)
        self.assertIn("setVoltage(5.0f * sample.sine, c)", src)

    def test_filter_cutoff_tooltip_is_frequency_not_log_control(self) -> None:
        args = self.config("StateFilter", "configParam", "CUTOFF_PARAM")
        self.assertEqual(args[4:], ['"Cutoff"', '" Hz"', '2.0f', '1000.0f'])
        lower, upper, default = (_number(v) for v in args[1:4])
        self.assertAlmostEqual(1000 * math.pow(2, default), 1000, places=6)
        self.assertAlmostEqual(1000 * math.pow(2, lower), 20, delta=0.02)
        self.assertAlmostEqual(1000 * math.pow(2, upper), 20000, delta=0.05)
        self.assertIn("1000.0 * std::exp2(octave)", self.sources["StateFilter"])

    def test_filter_normalized_amounts_and_cv_tooltips(self) -> None:
        for identifier in ("RESONANCE_PARAM", "DRIVE_PARAM"):
            args = self.check_percent_param("StateFilter", identifier, 0, 1, 0)
            self.assertIn("amount", args[4])
        expected = {
            "AUDIO_INPUT": "Audio signal input",
            "CUTOFF_CV_INPUT": "Cutoff CV (1 V/oct; adds to knob)",
            "RESONANCE_CV_INPUT": "Resonance CV (10 V full span; adds to knob)",
            "DRIVE_CV_INPUT": "Drive CV (10 V full span; adds to knob)",
        }
        for identifier, label in expected.items():
            self.assertEqual(self.config("StateFilter", "configInput", identifier),
                             [identifier, f'"{label}"'])
        src = _compact(self.sources["StateFilter"])
        self.assertIn("baseOctaves + (modular_synth::dsp::StateFilter::ieeeFinite(cutoffCV) ? cutoffCV : 0.0)",
                      src)
        self.assertIn("resonanceCV * 0.1", src)
        self.assertIn("driveCV * 0.1", src)

    def test_filter_outputs_are_explicitly_audio(self) -> None:
        for identifier, label in (
            ("LOWPASS_OUTPUT", "Low-pass filtered audio"),
            ("BANDPASS_OUTPUT", "Band-pass filtered audio"),
            ("HIGHPASS_OUTPUT", "High-pass filtered audio"),
        ):
            self.assertEqual(self.config("StateFilter", "configOutput", identifier),
                             [identifier, f'"{label}"'])

    def test_macro_normalized_knob_and_bipolar_ranges(self) -> None:
        args = self.check_percent_param("Macro8", "MACRO_1_PARAM + i", 0, 1, 0)
        self.assertEqual(args[4], 'label + " position"')
        out = self.config("Macro8", "configOutput", "MACRO_1_OUTPUT + i")
        self.assertIn('" CV (0 to +10 V unipolar; -5 to +5 V bipolar)"',
                      out[1])
        switch = self.config("Macro8", "configSwitch", "RANGE_1_PARAM + i")
        self.assertEqual(tuple(_number(v) for v in switch[1:4]), (0, 1, 0))
        self.assertIn('"Unipolar: 0 to +10 V"', switch[5])
        self.assertIn('"Bipolar: -5 to +5 V"', switch[5])
        core = (MODULE_DIR / "Macro8.hpp").read_text(encoding="utf-8")
        self.assertIn("bipolar ? value * 10.0 - 5.0 : value * 10.0", core)

    def test_snapshot_buttons_and_morph_time_describe_behavior(self) -> None:
        for letter in "ABCD":
            ident = f"SLOT_{letter}_PARAM"
            self.assertEqual(self.config("Macro8", "configButton", ident),
                             [ident, f'"Snapshot {letter} (store or recall per mode)"'])
        mode = self.config("Macro8", "configSwitch", "STORE_MODE_PARAM")
        self.assertEqual(tuple(_number(v) for v in mode[1:4]), (0, 1, 0))
        self.assertIn('"Recall"', mode[5])
        self.assertIn('"Store"', mode[5])
        self.assertIn("if (storing)", self.sources["Macro8"])
        self.assertIn("snapshots.store(slot, knobValues)", self.sources["Macro8"])
        self.assertIn("else if (snapshots.has(slot))", self.sources["Macro8"])
        morph = self.config("Macro8", "configParam", "MORPH_TIME_PARAM")
        self.assertEqual(tuple(_number(v) for v in morph[1:4]), (0, 5, 0.25))
        self.assertIn("99.9% settling", morph[4])
        self.assertEqual(morph[5], '" s"')
        live = self.config("Macro8", "configButton", "LIVE_PARAM")
        self.assertEqual(live[1], '"Return to live macro knobs"')


if __name__ == "__main__":
    unittest.main()
