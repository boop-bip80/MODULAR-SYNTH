"""Source-only guarantees for the Reed Chamber Organ factory arrangement.

These checks do not instantiate Cardinal, listen to a DAW, or establish a
physical tonewheel/rotary-speaker model. They establish only saved routing,
declared first-party port contracts and conservative nominal CV ranges.
"""
from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PRESET = ROOT / "patches/examples/MODULAR_-_Reed_Chamber_Organ.vcv"
sys.path.insert(0, str(ROOT / "tools/patches"))
import factory_patch_coverage as coverage  # noqa: E402
import patch_inspector  # noqa: E402


class ReedChamberOrganTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.patch = json.loads(PRESET.read_text(encoding="utf-8"))
        cls.by_id = {m["id"]: m for m in cls.patch["modules"]}
        cls.by_model = {
            f"{m['plugin']}/{m['model']}": m
            for m in cls.patch["modules"]
            if m["model"] != "MorphVCO"
        }
        cls.manuals = sorted(
            (m for m in cls.patch["modules"] if m["model"] == "MorphVCO"),
            key=lambda m: m["id"],
        )
        cls.cables = cls.patch["cables"]
        cls.edges = {
            (c["outputModuleId"], c["outputId"],
             c["inputModuleId"], c["inputId"])
            for c in cls.cables
        }

    def test_saved_patch_is_source_valid_and_has_two_verified_host_paths(self) -> None:
        result = patch_inspector.inspect_patch(PRESET, ROOT)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual((len(self.patch["modules"]), len(self.cables)), (11, 23))
        self.assertEqual(len(self.by_id), 11)
        check = subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools/patches/patch_audio_routes.py"),
             str(PRESET), "--require-source-verified-stereo", "--show-signal-traces"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn("source-verified", check.stdout.lower())
        self.assertIn("HostAudio2", check.stdout)

    def test_pitch_and_gates_feed_two_distinct_octave_manually_tuned_voices(self) -> None:
        midi = self.by_model["Cardinal/HostMIDI"]
        self.assertEqual((midi["data"]["channels"], midi["data"]["polyMode"]),
                         (8, 1))
        self.assertEqual(len(self.manuals), 2)
        lower, upper = self.manuals
        lp = {p["id"]: p["value"] for p in lower["params"]}
        up = {p["id"]: p["value"] for p in upper["params"]}
        self.assertEqual((lp[0], up[0]), (0, 1))
        self.assertEqual((lp[1], up[1]), (-2, 4))
        self.assertEqual(len([c for c in self.cables
                              if c["outputModuleId"] == midi["id"]
                              and c["outputId"] == 0
                              and c["inputModuleId"] in {lower["id"], upper["id"]}]), 2)
        adsr = self.by_model["Fundamental/ADSR"]["id"]
        for edge in ((midi["id"], 1, adsr, 4),
                     (midi["id"], 6, adsr, 5)):
            self.assertIn(edge, self.edges)

    def test_separate_manual_audio_and_shared_adsr_reach_both_host_jacks(self) -> None:
        lower, upper = self.manuals
        filt = self.by_model["ModularSynth/StateFilter"]["id"]
        vca = self.by_model["ModularSynth/DualVCA"]["id"]
        adsr = self.by_model["Fundamental/ADSR"]["id"]
        echo = self.by_model["ModularSynth/StereoEcho"]["id"]
        host = self.by_model["Cardinal/HostAudio2"]["id"]
        paths = (
            (lower["id"], 0, filt, 0), (filt, 0, vca, 0),
            (upper["id"], 0, vca, 2), (adsr, 0, vca, 1),
            (adsr, 0, vca, 3), (vca, 0, echo, 0),
            (vca, 1, echo, 1), (echo, 0, host, 0),
            (echo, 1, host, 1),
        )
        for edge in paths:
            with self.subTest(edge=edge):
                self.assertIn(edge, self.edges)
        vp = {p["id"]: p["value"] for p in self.by_model["ModularSynth/DualVCA"]["params"]}
        self.assertEqual((vp[0], vp[2]), (0.16, 0.10))
        self.assertLessEqual(
            self.by_model["Cardinal/HostAudio2"]["params"][0]["value"], 0.17)

    def test_free_running_phase_coherent_vibrato_is_deliberately_small(self) -> None:
        self.assertFalse(any(m["model"] == "HostTime" for m in self.patch["modules"]))
        lfo = self.by_model["ModularSynth/ClockedLFO"]
        params = {p["id"]: p["value"] for p in lfo["params"]}
        self.assertAlmostEqual(math.pow(2.0, params[0]), 3.0, places=7)
        self.assertFalse(any(c["inputModuleId"] == lfo["id"]
                             and c["inputId"] in (1, 2) for c in self.cables))
        for manual in self.manuals:
            self.assertIn((lfo["id"], 0, manual["id"], 1), self.edges)
            depth = next(p["value"] for p in manual["params"] if p["id"] == 4)
            # 5-V LFO sine into FM input; wrapper multiplies FM depth by CV/5.
            self.assertLessEqual(1200.0 * depth, 15.0)

    def test_four_macros_are_bounded_and_all_eight_outputs_have_routes(self) -> None:
        macro = self.by_model["ModularSynth/Macro8"]
        self.assertEqual(macro["data"]["macro8Version"], 1)
        self.assertEqual(macro["data"]["selectedSlot"], -1)
        self.assertEqual(len(macro["data"]["snapshots"]), 4)
        self.assertEqual(len(macro["data"]["names"]), 8)
        self.assertTrue(all(len(slot) == 8 for slot in macro["data"]["snapshots"]))
        self.assertTrue(all(0 <= value <= 1 for slot in macro["data"]["snapshots"]
                            for value in slot))
        self.assertEqual({c["outputId"] for c in self.cables
                          if c["outputModuleId"] == macro["id"]}, set(range(8)))
        self.assertEqual(len([c for c in self.cables
                              if c["outputModuleId"] == macro["id"]]), 8)
        params = {p["id"]: p["value"] for p in macro["params"]}
        self.assertEqual(params[8], 1.2)
        self.assertEqual(tuple(params[i] for i in range(15, 23)), (0,) * 8)
        peaks = [max(s[i] for s in macro["data"]["snapshots"]) for i in range(8)]
        self.assertLessEqual(0.10 + peaks[0], 0.40)          # lower morph
        self.assertLessEqual(0.20 + peaks[1], 0.51)          # upper morph
        self.assertLessEqual(1000 * 2 ** (0.35 + 10 * peaks[2]), 3000)
        self.assertLessEqual(0.15 + peaks[3], 0.25)          # resonance
        self.assertLessEqual(0.08 + peaks[4], 0.21)          # echo wet
        self.assertLessEqual(160 + 1000 * peaks[5], 361)    # echo time
        self.assertLessEqual(0.10 + peaks[6], 0.20)          # echo feedback
        self.assertLessEqual(0.46 + peaks[7], 0.70)          # upper pulse width

    def test_factory_registry_claims_exactly_cover_saved_cables(self) -> None:
        spec = coverage.EXAMPLES[PRESET.name]
        self.assertEqual(len(spec.routes), len(self.cables))
        self.assertEqual(spec.snapshot_count, 4)
        self.assertEqual(spec.free_lfo_rate_hz, 3.0)
        self.assertEqual(spec.midi_channels, 8)
        self.assertEqual(spec.midi_poly_mode, 1)
        actual = Counter(
            (f"{self.by_id[c['outputModuleId']]['plugin']}/{self.by_id[c['outputModuleId']]['model']}",
             c["outputId"],
             f"{self.by_id[c['inputModuleId']]['plugin']}/{self.by_id[c['inputModuleId']]['model']}",
             c["inputId"])
            for c in self.cables
        )
        declared = Counter((r.source, r.output, r.target, r.input)
                           for r in spec.routes)
        self.assertEqual(actual, declared)
        self.assertTrue(coverage._check_macro_snapshots(
            self.by_id, spec.snapshot_names, spec.snapshot_count))


if __name__ == "__main__":
    unittest.main()
