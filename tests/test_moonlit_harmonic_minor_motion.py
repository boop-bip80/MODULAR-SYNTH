"""Offline source-contract tests for the original Moonlit Harmonic Minor factory patch.

These test saved CV/trigger/audio routes and musical control intent, not a
Cardinal host session, rendered audio, or actual MIDI timing.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH_NAME = "MODULAR_-_Moonlit_Harmonic_Minor_Motion.vcv"
PATCH_PATH = ROOT / "patches" / "examples" / PATCH_NAME
sys.path.insert(0, str(ROOT / "tools" / "patches"))
import factory_patch_coverage  # noqa: E402


def read_patch() -> dict:
    return json.loads(PATCH_PATH.read_text(encoding="utf-8"))


def modules(patch: dict) -> dict[str, dict]:
    return {f"{m['plugin']}/{m['model']}": m for m in patch["modules"]}


def routes(patch: dict) -> set[tuple[str, int, str, int]]:
    id_to_key = {m["id"]: f"{m['plugin']}/{m['model']}" for m in patch["modules"]}
    return {
        (id_to_key[c["outputModuleId"]], c["outputId"],
         id_to_key[c["inputModuleId"]], c["inputId"])
        for c in patch["cables"]
    }


class MoonlitHarmonicMinorMotionTests(unittest.TestCase):
    def test_harmonic_minor_quantized_gliding_midi_voice(self) -> None:
        p = read_patch()
        m = modules(p)
        self.assertEqual(len(p["modules"]), 13)
        self.assertEqual(len(p["cables"]), 21)
        midi = m["Cardinal/HostMIDI"]
        self.assertEqual(midi["data"]["channels"], 1)
        self.assertEqual(midi["data"]["polyMode"], 0)
        q = {v["id"]: v["value"] for v in m["ModularSynth/ScaleQuantizer"]["params"]}
        self.assertEqual((q[0], q[1], q[2], q[3]), (2, 4, 0, 13))
        s = {v["id"]: v["value"] for v in m["ModularSynth/SlewGlide"]["params"]}
        self.assertAlmostEqual(s[0], 0.12)
        self.assertAlmostEqual(s[1], 0.18)

        links = routes(p)
        for link in (
            ("Cardinal/HostMIDI", 0, "ModularSynth/ScaleQuantizer", 0),
            ("ModularSynth/ScaleQuantizer", 0, "ModularSynth/SlewGlide", 0),
            ("ModularSynth/SlewGlide", 1, "ModularSynth/MorphVCO", 0),
            ("ModularSynth/ScaleQuantizer", 1, "Fundamental/ADSR", 5),
            ("Cardinal/HostMIDI", 1, "Fundamental/ADSR", 4),
            ("ModularSynth/MorphVCO", 0, "ModularSynth/DualVCA", 0),
            ("Fundamental/ADSR", 0, "ModularSynth/DualVCA", 1),
            ("ModularSynth/DualVCA", 0, "ModularSynth/StateFilter", 0),
        ):
            self.assertIn(link, links)
        self.assertNotIn(
            ("ModularSynth/ScaleQuantizer", 0, "ModularSynth/MorphVCO", 0),
            links,
            "Melodic voice must actually pass through SlewGlide",
        )

    def test_timed_chance_movement_and_real_stereo_paths(self) -> None:
        p = read_patch()
        m = modules(p)
        rate = m["ModularSynth/ClockedLFO"]["params"][0]["value"]
        self.assertAlmostEqual(2.0 ** rate, 2.0 ** -1.5)
        chance = {v["id"]: v["value"] for v in m["ModularSynth/ChanceHold"]["params"]}
        self.assertAlmostEqual(chance[1], 0.67)
        self.assertAlmostEqual(chance[2], 0.85)
        links = routes(p)
        for link in (
            ("ModularSynth/ClockedLFO", 3, "ModularSynth/ChanceHold", 1),
            ("ModularSynth/ChanceHold", 1, "ModularSynth/StateFilter", 1),
            ("ModularSynth/ChanceHold", 0, "ModularSynth/StateFilter", 3),
            ("ModularSynth/StateFilter", 0, "ModularSynth/StereoEcho", 0),
            ("ModularSynth/StateFilter", 2, "ModularSynth/StereoEcho", 1),
            ("ModularSynth/StereoEcho", 0, "Cardinal/HostAudio2", 0),
            ("ModularSynth/StereoEcho", 1, "Cardinal/HostAudio2", 1),
        ):
            self.assertIn(link, links)
        self.assertNotIn("Cardinal/HostTime", m,
                         "The modulation clock is free-running, not host-synced")

    def test_scenes_are_source_backed_and_macro_glide_routes_both_directions(self) -> None:
        p = read_patch()
        macro = modules(p)["ModularSynth/Macro8"]
        self.assertEqual(macro["data"]["macro8Version"], 1)
        self.assertEqual(macro["data"]["names"][:5],
                         ["Time", "Feedback", "Wet", "Wave", "Glide"])
        self.assertEqual(len(macro["data"]["snapshots"]), 4)
        self.assertEqual([row[4] for row in macro["data"]["snapshots"]],
                         [0.025, 0.08, 0.14, 0.21])
        links = routes(p)
        self.assertIn(("ModularSynth/Macro8", 4, "ModularSynth/SlewGlide", 1), links)
        self.assertIn(("ModularSynth/Macro8", 4, "ModularSynth/SlewGlide", 2), links)
        self.assertEqual(len(p["cables"]), len({c["id"] for c in p["cables"]}))
        self.assertEqual(len(p["modules"]), len({m["id"] for m in p["modules"]}))

    def test_factory_contract_refuses_missing_chance_filter_route(self) -> None:
        p = read_patch()
        chance_id = modules(p)["ModularSynth/ChanceHold"]["id"]
        filter_id = modules(p)["ModularSynth/StateFilter"]["id"]
        p["cables"] = [
            cable for cable in p["cables"] if not (
                cable["outputModuleId"] == chance_id
                and cable["outputId"] == 1
                and cable["inputModuleId"] == filter_id
                and cable["inputId"] == 1
            )
        ]
        with tempfile.TemporaryDirectory(prefix="moonlit-minor-") as temp:
            dest = Path(temp) / PATCH_NAME
            dest.write_text(json.dumps(p), encoding="utf-8")
            # The factory analyser checks the complete advertised catalog.
            # Seed all other examples from the real repo for a precise negative.
            for name in factory_patch_coverage.EXAMPLES:
                if name == PATCH_NAME:
                    continue
                shutil.copyfile(ROOT / "patches" / "examples" / name,
                                Path(temp) / name)
            report = factory_patch_coverage.analyze(ROOT, Path(temp))
        self.assertFalse(report["ok"])
        self.assertTrue(any("missing advertised route: chance glide moves filter cutoff"
                            in error for error in report["errors"]), report["errors"])


if __name__ == "__main__":
    unittest.main()
