"""Source-graph regression for the Aurora Glass Bells factory preset.

These assertions do not synthesize audio or verify a loaded Cardinal/DAW host.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/examples/MODULAR_-_Aurora_Glass_Bells.vcv"
sys.path.insert(0, str(ROOT / "tools/patches"))
import factory_patch_coverage as coverage  # noqa: E402
import patch_inspector  # noqa: E402


class AuroraGlassBellsTests(unittest.TestCase):
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

    def test_graph_is_source_valid_and_has_genuine_host_routes(self) -> None:
        report = patch_inspector.inspect_patch(PATCH, ROOT)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(len(self.patch["modules"]), 11)
        self.assertEqual(len(self.patch["cables"]), 17)
        self.assertNotIn("Cardinal/HostTime", self.by_model)
        self.assertEqual(len(self.by_model), len(self.patch["modules"]))
        self.assertEqual(
            {"FMVoice", "ChanceHold", "DualVCA", "Macro8", "StateFilter", "StereoEcho"},
            {m["model"] for m in self.patch["modules"]
             if m["plugin"] == "ModularSynth"},
        )
        route_check = subprocess.run(
            [sys.executable, str(ROOT / "tools/patches/patch_audio_routes.py"),
             str(PATCH), "--require-host-input", "--require-generator-route"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(route_check.returncode, 0, route_check.stdout + route_check.stderr)
        self.assertIn("HostAudio2 source contract: verified", route_check.stdout)
        self.assertIn("Left/M: ModularSynth/StereoEcho", route_check.stdout)
        self.assertIn("Right: ModularSynth/StereoEcho", route_check.stdout)

    def test_eight_voice_per_note_envelope_and_spectral_stereo_paths(self) -> None:
        midi = self.by_model["Cardinal/HostMIDI"]
        self.assertEqual(midi["data"]["channels"], 8)
        self.assertEqual(midi["data"]["polyMode"], 1)
        for edge in (
            ("HostMIDI", 0, "FMVoice", 0),
            ("HostMIDI", 1, "ADSR", 4),
            ("HostMIDI", 6, "ADSR", 5),
            ("FMVoice", 0, "VCA-1", 1),
            ("ADSR", 0, "VCA-1", 0),
            ("VCA-1", 0, "StateFilter", 0),
            ("StateFilter", 0, "StereoEcho", 0),
            ("StateFilter", 1, "StereoEcho", 1),
            ("StereoEcho", 0, "HostAudio2", 0),
            ("StereoEcho", 1, "HostAudio2", 1),
        ):
            self.assertIn(edge, self.edges)
        # LP and BP are deliberately distinct spectral inputs, rather than
        # copying a mono signal directly to both host jacks.
        self.assertNotIn(("VCA-1", 0, "HostAudio2", 0), self.edges)
        self.assertNotIn(("VCA-1", 0, "HostAudio2", 1), self.edges)

    def test_random_cutoff_drift_is_gain_limited_and_not_transport_clocked(self) -> None:
        chance = self.by_model["ModularSynth/ChanceHold"]
        dual = self.by_model["ModularSynth/DualVCA"]
        chance_params = {p["id"]: p["value"] for p in chance["params"]}
        dual_params = {p["id"]: p["value"] for p in dual["params"]}
        self.assertEqual(chance_params, {0: -2, 1: 0.65, 2: 1.4, 3: 0})
        self.assertEqual(dual_params, {0: 0.24, 1: 0, 2: 0, 3: 0})
        self.assertIn(("ChanceHold", 1, "DualVCA", 0), self.edges)
        self.assertIn(("DualVCA", 0, "StateFilter", 1), self.edges)
        self.assertFalse(any(
            cable["inputModuleId"] == chance["id"]
            and cable["inputId"] in (1, 2)
            for cable in self.patch["cables"]
        ), "ChanceHold free-runs without host CLOCK/RESET")
        self.assertFalse(any(
            cable["inputModuleId"] == dual["id"]
            and cable["inputId"] == 1
            for cable in self.patch["cables"]
        ), "DualVCA A must use the normalled unity CV for fixed attenuation")
        self.assertEqual(5.0 * dual_params[0], 1.2)

    def test_five_source_routed_scene_controls_are_safe_at_saved_values(self) -> None:
        macro = self.by_model["ModularSynth/Macro8"]
        data = macro["data"]
        self.assertEqual(data["macro8Version"], 1)
        self.assertEqual(data["names"][:5],
                         ["Index", "Resonance", "Wet", "Time", "Feedback"])
        self.assertEqual(data["selectedSlot"], -1)
        params = {p["id"]: p["value"] for p in macro["params"]}
        self.assertEqual(params[8], 1.6)
        self.assertEqual(tuple(params[i] for i in range(15, 20)), (0, 0, 0, 0, 0))
        for edge in (
            ("Macro8", 0, "FMVoice", 2),
            ("Macro8", 1, "StateFilter", 2),
            ("Macro8", 2, "StereoEcho", 4),
            ("Macro8", 3, "StereoEcho", 2),
            ("Macro8", 4, "StereoEcho", 3),
        ):
            self.assertIn(edge, self.edges)
        self.assertEqual(len(data["snapshots"]), 4)
        for scene in data["snapshots"]:
            self.assertEqual(len(scene), 8)
            self.assertTrue(all(0 <= value <= 1 for value in scene))
            # From the checked-in FMVoice/StereoEcho/StateFilter CV scales.
            self.assertLessEqual(1.15 + 8 * scene[0], 2.6)  # FM index, rad
            self.assertLessEqual(0.13 + scene[1], 0.3)     # resonance
            self.assertLessEqual(0.18 + scene[2], 0.4)     # wet mix
            self.assertLessEqual(210 + 1000 * scene[3], 600)  # delay, ms
            self.assertLessEqual(0.20 + scene[4], 0.4)     # feedback

    def test_every_published_route_is_present_and_reviewed(self) -> None:
        spec = coverage.EXAMPLES[PATCH.name]
        routes = coverage._routes_for(self.patch, self.by_id)
        self.assertEqual(len(spec.routes), 17)
        self.assertTrue(all(coverage._claim_present(claim, routes)
                            for claim in spec.routes))
        self.assertTrue(coverage._check_stereo(routes))
        self.assertTrue(coverage._check_macro_snapshots(self.by_id,
                        spec.snapshot_names, spec.snapshot_count))
        # Removing the sole pitch cable must invalidate the musical claim.
        without_pitch = [item for item in routes
                         if not (item[0]["model"] == "HostMIDI"
                                 and item[2]["outputId"] == 0
                                 and item[1]["model"] == "FMVoice")]
        self.assertFalse(coverage._claim_present(spec.routes[0], without_pitch))


if __name__ == "__main__":
    unittest.main()
