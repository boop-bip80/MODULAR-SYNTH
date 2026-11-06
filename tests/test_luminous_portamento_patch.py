"""Source-only checks for Luminous Portamento Duets, not a DAW audition."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/examples/MODULAR_-_Luminous_Portamento_Duets.vcv"
sys.path.insert(0, str(ROOT / "tools/patches"))
import factory_patch_coverage as coverage  # noqa: E402
import patch_inspector  # noqa: E402


class LuminousPortamentoSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.patch = json.loads(PATCH.read_text(encoding="utf-8"))
        cls.by_id = {module["id"]: module for module in cls.patch["modules"]}
        cls.by_model = {
            f"{module['plugin']}/{module['model']}": module
            for module in cls.patch["modules"]
            if module["model"] not in ("MorphVCO", "StateFilter")
        }
        cls.oscillators = sorted(
            (module for module in cls.patch["modules"]
             if module["model"] == "MorphVCO"),
            key=lambda module: module["id"],
        )
        cls.filters = sorted(
            (module for module in cls.patch["modules"]
             if module["model"] == "StateFilter"),
            key=lambda module: module["id"],
        )
        cls.cables = cls.patch["cables"]
        cls.edges = {
            (c["outputModuleId"], c["outputId"],
             c["inputModuleId"], c["inputId"])
            for c in cls.cables
        }

    def test_structural_integrity_and_source_verified_stereo(self) -> None:
        result = patch_inspector.inspect_patch(PATCH, ROOT)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(len(self.by_id), 12)
        self.assertEqual(len(self.cables), 23)
        proc = subprocess.run(
            [sys.executable, "-B",
             str(ROOT / "tools/patches/patch_audio_routes.py"),
             str(PATCH), "--require-source-verified-signal-route",
             "--require-source-verified-stereo"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("2/2", proc.stdout)

    def test_two_different_pitch_slew_outputs_feed_two_octave_manuals(self) -> None:
        midi = self.by_model["Cardinal/HostMIDI"]
        slew = self.by_model["ModularSynth/SlewGlide"]
        self.assertEqual((midi["data"]["channels"], midi["data"]["polyMode"]),
                         (8, 1))
        self.assertEqual(len(self.oscillators), 2)
        left, right = self.oscillators
        self.assertIn((midi["id"], 0, slew["id"], 0), self.edges)
        self.assertIn((slew["id"], 0, left["id"], 0), self.edges)
        self.assertIn((slew["id"], 1, right["id"], 0), self.edges)
        self.assertNotIn((midi["id"], 0, left["id"], 0), self.edges)
        self.assertNotIn((midi["id"], 0, right["id"], 0), self.edges)
        left_params = {p["id"]: p["value"] for p in left["params"]}
        right_params = {p["id"]: p["value"] for p in right["params"]}
        # MorphVCO param 0 is *octaves*, param 1 is *cents* (not semitones).
        self.assertEqual((left_params[0], right_params[0]), (0, 1))
        self.assertEqual((left_params[1], right_params[1]), (0, -3))
        slew_params = {p["id"]: p["value"] for p in slew["params"]}
        self.assertEqual((slew_params[0], slew_params[1]), (0.12, 0.18))

    def test_distinct_lowpass_and_bandpass_path_share_gate(self) -> None:
        midi = self.by_model["Cardinal/HostMIDI"]["id"]
        adsr = self.by_model["Fundamental/ADSR"]["id"]
        vca = self.by_model["ModularSynth/DualVCA"]["id"]
        echo = self.by_model["ModularSynth/StereoEcho"]["id"]
        host = self.by_model["Cardinal/HostAudio2"]["id"]
        left, right = self.oscillators
        lp, bp = self.filters
        for edge in (
            (midi, 1, adsr, 4), (midi, 6, adsr, 5),
            (left["id"], 0, lp["id"], 0),
            (right["id"], 0, bp["id"], 0),
            (lp["id"], 0, vca, 0),
            (bp["id"], 1, vca, 2),
            (adsr, 0, vca, 1), (adsr, 0, vca, 3),
            (vca, 0, echo, 0), (vca, 1, echo, 1),
            (echo, 0, host, 0), (echo, 1, host, 1),
        ):
            with self.subTest(edge=edge):
                self.assertIn(edge, self.edges)
        vp = {p["id"]: p["value"]
              for p in self.by_model["ModularSynth/DualVCA"]["params"]}
        self.assertEqual((vp[0], vp[2]), (0.18, 0.14))
        self.assertLessEqual(
            self.by_model["Cardinal/HostAudio2"]["params"][0]["value"], 0.14)

    def test_four_macro_scenes_drive_both_glide_controls(self) -> None:
        macro = self.by_model["ModularSynth/Macro8"]
        slew = self.by_model["ModularSynth/SlewGlide"]
        self.assertEqual(macro["data"]["macro8Version"], 1)
        self.assertEqual(macro["data"]["selectedSlot"], -1)
        self.assertEqual(len(macro["data"]["snapshots"]), 4)
        self.assertEqual(len(macro["data"]["names"]), 8)
        self.assertEqual({c["outputId"] for c in self.cables
                          if c["outputModuleId"] == macro["id"]}, set(range(8)))
        self.assertIn((macro["id"], 0, slew["id"], 1), self.edges)
        self.assertIn((macro["id"], 1, slew["id"], 2), self.edges)
        params = {p["id"]: p["value"] for p in macro["params"]}
        self.assertEqual(params[8], 1.25)
        self.assertEqual(tuple(params[i] for i in range(15, 23)), (0,) * 8)
        nominal_times = [
            (0.12 + 5.0 * scene[0], 0.18 + 5.0 * scene[1])
            for scene in macro["data"]["snapshots"]
        ]
        expected = ((0.16, 0.23), (0.395, 0.63), (1.02, 1.58), (1.72, 1.23))
        for actual, goal in zip(nominal_times, expected):
            self.assertAlmostEqual(actual[0], goal[0])
            self.assertAlmostEqual(actual[1], goal[1])
        # CV ranges, not actual performed glide or audio output levels.
        self.assertLessEqual(max(max(pair) for pair in nominal_times), 2.0)

    def test_factory_registry_accounts_for_every_route_without_ambiguity(self) -> None:
        spec = coverage.EXAMPLES[PATCH.name]
        self.assertEqual(len(spec.routes), len(self.cables))
        self.assertTrue(spec.stereo)
        self.assertEqual(spec.snapshot_count, 4)
        self.assertEqual(spec.midi_channels, 8)
        actual = Counter((
            f"{self.by_id[c['outputModuleId']]['plugin']}/"
            f"{self.by_id[c['outputModuleId']]['model']}", c["outputId"],
            f"{self.by_id[c['inputModuleId']]['plugin']}/"
            f"{self.by_id[c['inputModuleId']]['model']}", c["inputId"],
        ) for c in self.cables)
        declared = Counter((r.source, r.output, r.target, r.input)
                           for r in spec.routes)
        self.assertEqual(actual, declared)
        report = coverage.analyze(ROOT)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(len(report["examples"]), 21)
        self.assertEqual(
            report["model_coverage"]["SlewGlide"], [PATCH.name])


if __name__ == "__main__":
    unittest.main()
