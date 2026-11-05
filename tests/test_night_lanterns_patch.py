"""Source-level regressions for the Night Lanterns dual-timbre preset.

These checks inspect saved patch structure and first-party wrapper ports. They
do not load Cardinal, render audio, or establish actual stereo width/headroom.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/examples/MODULAR_-_Night_Lanterns_Dual_Timbre.vcv"
sys.path.insert(0, str(ROOT / "tools/patches"))
import factory_patch_coverage as coverage  # noqa: E402
import patch_inspector  # noqa: E402


class NightLanternsPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.patch = json.loads(PATCH.read_text(encoding="utf-8"))
        cls.by_id = {module["id"]: module for module in cls.patch["modules"]}
        cls.by_model = {
            f"{module['plugin']}/{module['model']}": module
            for module in cls.patch["modules"]
        }
        cls.edges = {
            (cls.by_id[cable["outputModuleId"]]["model"], cable["outputId"],
             cls.by_id[cable["inputModuleId"]]["model"], cable["inputId"])
            for cable in cls.patch["cables"]
        }

    def test_graph_is_structurally_valid_and_both_voices_reach_host(self) -> None:
        report = patch_inspector.inspect_patch(PATCH, ROOT)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(len(self.patch["modules"]), 13)
        self.assertEqual(len(self.patch["cables"]), 26)
        self.assertEqual(len(self.by_model), len(self.patch["modules"]))
        check = subprocess.run(
            [sys.executable, str(ROOT / "tools/patches/patch_audio_routes.py"),
             str(PATCH), "--require-host-input", "--require-generator-route"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn("HostAudio2 source contract: verified", check.stdout)
        self.assertIn("First-party voices with source-verified signal-port chains: 2", check.stdout)
        self.assertIn("signal chain: 2/2", check.stdout)

    def test_eight_voices_are_tuned_and_envelope_gated_on_both_sides(self) -> None:
        midi = self.by_model["Cardinal/HostMIDI"]["data"]
        self.assertEqual((midi["channels"], midi["polyMode"]), (8, 1))
        required = (
            ("HostMIDI", 0, "MorphVCO", 0),
            ("HostMIDI", 0, "FMVoice", 0),
            ("HostMIDI", 1, "ADSR", 4),
            ("HostMIDI", 6, "ADSR", 5),
            ("MorphVCO", 0, "FoldDrive", 0),
            ("FoldDrive", 0, "StateFilter", 0),
            ("StateFilter", 0, "DualVCA", 0),
            ("FMVoice", 0, "DualVCA", 2),
            ("ADSR", 0, "DualVCA", 1),
            ("ADSR", 0, "DualVCA", 3),
            ("DualVCA", 0, "StereoEcho", 0),
            ("DualVCA", 1, "StereoEcho", 1),
            ("StereoEcho", 0, "HostAudio2", 0),
            ("StereoEcho", 1, "HostAudio2", 1),
        )
        for edge in required:
            with self.subTest(edge=edge):
                self.assertIn(edge, self.edges)
        morph = self.by_model["ModularSynth/MorphVCO"]
        fm = self.by_model["ModularSynth/FMVoice"]
        self.assertEqual({p["id"]: p["value"] for p in morph["params"]}[0], -1)
        self.assertAlmostEqual({p["id"]: p["value"] for p in fm["params"]}[2], 2.003)
        self.assertLessEqual(
            max(p["value"] for p in self.by_model["ModularSynth/DualVCA"]["params"]
                if p["id"] in (0, 2)), 0.16)
        self.assertLessEqual(
            self.by_model["Cardinal/HostAudio2"]["params"][0]["value"], 0.15)

    def test_clocked_lfo_routes_are_tied_to_host_beats_not_midi_gate(self) -> None:
        for edge in (
            ("HostTime", 3, "ClockedLFO", 1),
            ("HostTime", 1, "ClockedLFO", 2),
            ("ClockedLFO", 0, "MorphVCO", 3),
            ("ClockedLFO", 1, "FoldDrive", 2),
        ):
            self.assertIn(edge, self.edges)
        params = {p["id"]: p["value"]
                  for p in self.by_model["ModularSynth/ClockedLFO"]["params"]}
        self.assertEqual(params[0], -2)  # 0.25 Hz when transport clock absent
        self.assertEqual(params[1], 0)  # one LFO cycle every four beat pulses
        self.assertFalse(any(
            edge[0] == "HostMIDI" and edge[2] == "ClockedLFO"
            for edge in self.edges
        ))

    def test_all_eight_macro_outputs_are_routed_and_scenes_are_versioned(self) -> None:
        macro = self.by_model["ModularSynth/Macro8"]
        expected = (
            ("MorphVCO", 2), ("FMVoice", 2), ("StateFilter", 2),
            ("FoldDrive", 1), ("StereoEcho", 4), ("StereoEcho", 2),
            ("StereoEcho", 3), ("FoldDrive", 3),
        )
        for channel, (model, input_id) in enumerate(expected):
            self.assertIn(("Macro8", channel, model, input_id), self.edges)
        self.assertEqual(macro["data"]["macro8Version"], 1)
        self.assertEqual(macro["data"]["selectedSlot"], -1)
        self.assertEqual(len(macro["data"]["names"]), 8)
        self.assertEqual(len(macro["data"]["snapshots"]), 4)
        self.assertTrue(all(len(slot) == 8 for slot in macro["data"]["snapshots"]))
        self.assertTrue(all(0 <= value <= 1 for slot in macro["data"]["snapshots"]
                            for value in slot))
        params = {p["id"]: p["value"] for p in macro["params"]}
        self.assertEqual(params[8], 2.0)
        self.assertEqual(tuple(params[i] for i in range(15, 23)), (0,) * 8)

    def test_nominal_scene_extremes_stay_within_conservative_controls(self) -> None:
        scenes = self.by_model["ModularSynth/Macro8"]["data"]["snapshots"]
        peaks = [max(scene[i] for scene in scenes) for i in range(8)]
        # Formulas come from the eight saved unipolar Macro8 outputs and the
        # first-party target CV wrappers; they do not prove audio headroom.
        self.assertLessEqual(0.22 + peaks[0], 0.78)           # VCO morph
        self.assertLessEqual(0.48 + 8 * peaks[1], 1.93)      # FM index, radians
        self.assertLessEqual(0.12 + peaks[2], 0.23)          # filter Q
        self.assertLessEqual(0.18 + peaks[3], 0.43)          # fold drive
        self.assertLessEqual(0.18 + peaks[4], 0.39)          # echo wet
        self.assertLessEqual(320 + 1000 * peaks[5], 630)    # echo time, ms
        self.assertLessEqual(0.16 + peaks[6], 0.28)          # echo feedback
        self.assertLessEqual(0.25 + peaks[7], 0.41)          # fold wet

    def test_coverage_registry_reviews_every_saved_cable(self) -> None:
        spec = coverage.EXAMPLES[PATCH.name]
        routes = coverage._routes_for(self.patch, self.by_id)
        self.assertEqual(len(spec.routes), len(self.patch["cables"]))
        self.assertTrue(all(coverage._claim_present(claim, routes)
                            for claim in spec.routes))
        self.assertTrue(coverage._check_stereo(routes))
        self.assertTrue(coverage._check_macro_snapshots(
            self.by_id, spec.snapshot_names, spec.snapshot_count))
        no_fm = [route for route in routes if not (
            route[0]["model"] == "FMVoice" and route[1]["model"] == "DualVCA")]
        self.assertFalse(coverage._claim_present(
            next(item for item in spec.routes if item.label == "FM layer to B VCA"),
            no_fm,
        ))


if __name__ == "__main__":
    unittest.main()
