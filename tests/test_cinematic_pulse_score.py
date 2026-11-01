"""Cinematic Pulse Score saved-source graph, CV and negative regression fixtures.

No real Cardinal host, DAW transport, audio, clipping or subjective playback test.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "patches"))
import factory_patch_coverage as coverage  # noqa: E402
import patch_catalog  # noqa: E402

FILENAME = "MODULAR_-_Cinematic_Pulse_Score.vcv"


class CinematicPulseScoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.examples = Path(self.temp.name) / "examples"
        self.examples.mkdir()
        for name in coverage.EXAMPLES:
            shutil.copyfile(ROOT / "patches" / "examples" / name,
                            self.examples / name)

    def source(self) -> dict:
        return json.loads((self.examples / FILENAME).read_text(encoding="utf-8"))

    def write(self, patch: dict) -> None:
        (self.examples / FILENAME).write_text(
            json.dumps(patch, indent=2), encoding="utf-8")

    def restore(self) -> None:
        shutil.copyfile(ROOT / "patches" / "examples" / FILENAME,
                        self.examples / FILENAME)

    def analyze(self) -> dict:
        return coverage.analyze(ROOT, self.examples)

    @staticmethod
    def unit(patch: dict, plugin: str, model: str) -> dict:
        matches = [m for m in patch["modules"]
                   if m["plugin"] == plugin and m["model"] == model]
        if len(matches) != 1:
            raise AssertionError(
                f"expected single {plugin}/{model}, found {len(matches)}")
        return matches[0]

    @staticmethod
    def values(module: dict) -> dict[int, float]:
        return {p["id"]: p["value"] for p in module["params"]}

    @classmethod
    def roles(cls, patch: dict) -> dict[str, int]:
        midi = cls.unit(patch, "Cardinal", "HostMIDI")["id"]
        lfo = cls.unit(patch, "ModularSynth", "ClockedLFO")["id"]
        filt = cls.unit(patch, "ModularSynth", "StateFilter")["id"]
        echo = cls.unit(patch, "ModularSynth", "StereoEcho")["id"]
        morph = cls.unit(patch, "ModularSynth", "MorphVCO")["id"]
        cables = patch["cables"]

        def endpoint(source: int, out: int, inp: int) -> int:
            links = [c["inputModuleId"] for c in cables
                     if c["outputModuleId"] == source
                     and c["outputId"] == out and c["inputId"] == inp]
            if len(links) != 1:
                raise AssertionError(f"expected one route {source}/{out} -> in{inp}")
            return links[0]

        def source_of(target: int, inp: int, out: int) -> int:
            links = [c["outputModuleId"] for c in cables
                     if c["inputModuleId"] == target
                     and c["inputId"] == inp and c["outputId"] == out]
            if len(links) != 1:
                raise AssertionError(f"expected one route out{out} -> {target}/in{inp}")
            return links[0]

        return {
            "midi": midi, "lfo": lfo, "filter": filt, "echo": echo, "morph": morph,
            "voice_adsr": endpoint(midi, 1, 4),
            "rhythm_adsr": endpoint(lfo, 3, 4),
            "voice_vca": source_of(filt, 0, 0),
            "rhythm_vca": endpoint(filt, 0, 1),
            "host": cls.unit(patch, "Cardinal", "HostAudio2")["id"],
            "macro": cls.unit(patch, "ModularSynth", "Macro8")["id"],
        }

    @staticmethod
    def cut(patch: dict, source: int, out: int, target: int, inp: int) -> None:
        old = len(patch["cables"])
        patch["cables"] = [
            c for c in patch["cables"] if not (
                c["outputModuleId"] == source and c["outputId"] == out
                and c["inputModuleId"] == target and c["inputId"] == inp)
        ]
        if len(patch["cables"]) != old - 1:
            raise AssertionError("fixture must remove exactly one saved cable")

    def test_two_distinct_envelope_roles_and_four_safe_scene_settings(self) -> None:
        report = self.analyze()
        self.assertTrue(report["ok"], report["errors"])
        row = next(r for r in report["examples"] if r["patch"] == FILENAME)
        self.assertTrue(row["ok"], row["errors"])
        self.assertIn("separate MIDI voice and LFO pulse ADSR/VCA chains",
                      row["capabilities"])
        self.assertIn("free-running LFO at 0.8 Hz; no host clock",
                      row["capabilities"])
        self.assertIn("4 versioned Macro8 snapshots", row["capabilities"])
        self.assertIn("two host audio input routes", row["capabilities"])
        self.assertTrue(all(f"unipolar Macro8 output {i} CV" in row["capabilities"]
                            for i in range(4)))

        patch = self.source()
        self.assertEqual(len(patch["modules"]), 12)
        self.assertEqual(len(patch["cables"]), 17)
        roles = self.roles(patch)
        self.assertNotEqual(roles["voice_adsr"], roles["rhythm_adsr"])
        self.assertNotEqual(roles["voice_vca"], roles["rhythm_vca"])
        self.assertEqual({m["model"] for m in patch["modules"]
                          if m["plugin"] == "ModularSynth"},
                         {"ClockedLFO", "Macro8", "MorphVCO",
                          "StateFilter", "StereoEcho"})
        self.assertFalse(any(m["model"] == "HostTime" and m["plugin"] == "Cardinal"
                             for m in patch["modules"]))

        lfo = self.unit(patch, "ModularSynth", "ClockedLFO")
        lp = self.values(lfo)
        self.assertAlmostEqual(2.0 ** lp[0], 0.8, places=6)
        self.assertAlmostEqual(lp[3], 0.28)
        self.assertFalse(any(c["inputModuleId"] == lfo["id"]
                             and c["inputId"] in (1, 2) for c in patch["cables"]))

        macro = self.unit(patch, "ModularSynth", "Macro8")
        state = macro["data"]
        self.assertEqual(state["macro8Version"], 1)
        self.assertEqual(state["selectedSlot"], -1)  # LIVE on open
        self.assertEqual(state["names"][:4],
                         ["Tension", "Warmth", "Repeats", "Space"])
        self.assertAlmostEqual(self.values(macro)[8], 2.6)
        self.assertTrue(all(self.values(macro)[15 + i] == 0 for i in range(4)))
        self.assertEqual(len(state["snapshots"]), 4)
        filt = self.unit(patch, "ModularSynth", "StateFilter")
        echo = self.unit(patch, "ModularSynth", "StereoEcho")
        filt_base = self.values(filt)
        echo_base = self.values(echo)
        self.assertAlmostEqual(echo_base[0], 460)  # fixed, NOT MIDI BPM
        self.assertTrue(all(c["inputModuleId"] != echo["id"] or c["inputId"] != 2
                            for c in patch["cables"]))
        expected = ((0.08, 0.02, 0.16, 0.20),
                    (0.12, 0.05, 0.24, 0.28),
                    (0.20, 0.09, 0.35, 0.40),
                    (0.11, 0.04, 0.25, 0.30))
        for scene_no, (snapshot, row_expected) in enumerate(zip(
                state["snapshots"], expected)):
            with self.subTest(scene=scene_no):
                self.assertEqual(len(snapshot), 8)
                self.assertTrue(all(type(value) in (int, float)
                                    and math.isfinite(value)
                                    and 0.0 <= value <= 1.0 for value in snapshot))
                # Macro8 normalized unipolar -> +10 V; all destinations
                # add 0.1 normalized units per volt, so +snapshot amount.
                effective = (filt_base[1] + snapshot[0],
                             filt_base[2] + snapshot[1],
                             echo_base[1] + snapshot[2],
                             echo_base[2] + snapshot[3])
                for got, wanted in zip(effective, row_expected):
                    self.assertAlmostEqual(got, wanted)
                self.assertLessEqual(effective[2], 0.40)
                self.assertLessEqual(effective[3], 0.45)
        host = self.unit(patch, "Cardinal", "HostAudio2")
        self.assertLessEqual(self.values(host)[0], 0.15)

    def test_each_distinct_voice_or_pulse_route_is_mandatory(self) -> None:
        patch = self.source()
        r = self.roles(patch)
        edges = (
            (r["midi"], 1, r["voice_adsr"], 4),
            (r["voice_adsr"], 0, r["voice_vca"], 0),
            (r["voice_vca"], 0, r["filter"], 0),
            (r["lfo"], 3, r["rhythm_adsr"], 4),
            (r["rhythm_adsr"], 0, r["rhythm_vca"], 0),
            (r["filter"], 0, r["rhythm_vca"], 1),
            (r["rhythm_vca"], 0, r["echo"], 0),
        )
        for edge in edges:
            with self.subTest(edge=edge):
                self.restore()
                p = self.source()
                self.cut(p, *edge)
                self.write(p)
                result = self.analyze()
                self.assertFalse(result["ok"])
                self.assertTrue(any(
                    "rhythmic LP requires two distinct MIDI/LFO ADSR-to-VCA chains"
                    in err for err in result["errors"]), result["errors"])

    def test_each_macro_and_lfo_wave_cv_route_is_mandatory(self) -> None:
        r = self.roles(self.source())
        edges = (
            ((r["lfo"], 0, r["morph"], 2),
             "LFO sine into oscillator morph CV"),
            ((r["macro"], 0, r["filter"], 2),
             "macro tension to filter resonance CV"),
            ((r["macro"], 1, r["filter"], 3),
             "macro warmth to filter drive CV"),
            ((r["macro"], 2, r["echo"], 3),
             "macro repeats to Echo feedback CV"),
            ((r["macro"], 3, r["echo"], 4),
             "macro space to Echo wet CV"),
        )
        for edge, label in edges:
            with self.subTest(edge=edge):
                self.restore()
                p = self.source()
                self.cut(p, *edge)
                self.write(p)
                report = self.analyze()
                self.assertFalse(report["ok"])
                self.assertTrue(any(label in err for err in report["errors"]),
                                report["errors"])

    def test_filter_highpass_and_stereo_host_routes_are_mandatory(self) -> None:
        r = self.roles(self.source())
        edges = (
            ((r["filter"], 2, r["echo"], 1), "filter HP into Echo right"),
            ((r["echo"], 0, r["host"], 0), "Echo left into host left"),
            ((r["echo"], 1, r["host"], 1), "Echo right into host right"),
        )
        for edge, label in edges:
            with self.subTest(edge=edge):
                self.restore()
                p = self.source()
                self.cut(p, *edge)
                self.write(p)
                report = self.analyze()
                self.assertFalse(report["ok"])
                self.assertTrue(any(label in err for err in report["errors"]),
                                report["errors"])

    def test_missing_fourth_scene_fails_coverage(self) -> None:
        p = self.source()
        macro = self.unit(p, "ModularSynth", "Macro8")
        macro["data"]["snapshots"][3] = None
        self.write(p)
        result = self.analyze()
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing documented Macro8 names" in err
                            for err in result["errors"]), result["errors"])

    def test_bipolar_macro_range_fails_coverage(self) -> None:
        p = self.source()
        macro = self.unit(p, "ModularSynth", "Macro8")
        next(q for q in macro["params"] if q["id"] == 15)["value"] = 1
        self.write(p)
        result = self.analyze()
        self.assertFalse(result["ok"])
        self.assertTrue(any("macro output 0 CV range must be unipolar" in err
                            for err in result["errors"]), result["errors"])

    def test_clock_or_reset_connection_breaks_free_run_claim(self) -> None:
        r = self.roles(self.source())
        for input_id in (1, 2):
            with self.subTest(input_id=input_id):
                self.restore()
                p = self.source()
                p["cables"].append({
                    "id": 996000000900 + input_id,
                    "outputModuleId": r["midi"], "outputId": 1,
                    "inputModuleId": r["lfo"], "inputId": input_id,
                    "color": "#ffffff",
                })
                self.write(p)
                result = self.analyze()
                self.assertFalse(result["ok"])
                self.assertTrue(any(
                    "expected free-running LFO" in err for err in result["errors"]
                ), result["errors"])

    def test_extreme_or_nonfinite_saved_lfo_rate_rejects_gracefully(self) -> None:
        # Exercise the guard directly: structural inspection would normally
        # reject malformed/range-breaking JSON *before* this coverage branch.
        for value in (1e308, -1e308, float("inf"), float("-inf"),
                      float("nan"), 10 ** 1000, True, "huge", None):
            with self.subTest(value=repr(value)):
                self.assertFalse(coverage._matches_free_lfo_rate(value, 0.8))
        self.assertTrue(coverage._matches_free_lfo_rate(
            -0.3219280948873623, 0.8))

        # Also prove real saved JSON fails with a report, not OverflowError.
        patch = self.source()
        lfo = self.unit(patch, "ModularSynth", "ClockedLFO")
        next(p for p in lfo["params"] if p["id"] == 0)["value"] = 1e308
        self.write(patch)
        report = self.analyze()
        self.assertFalse(report["ok"])
        self.assertTrue(report["errors"])
        self.assertTrue(any("ClockedLFO" in error or "free-running LFO" in error
                            for error in report["errors"]), report["errors"])

    def test_changed_lfo_free_rate_breaks_documented_08_hz(self) -> None:
        p = self.source()
        lfo = self.unit(p, "ModularSynth", "ClockedLFO")
        next(q for q in lfo["params"] if q["id"] == 0)["value"] = -1.0
        self.write(p)
        result = self.analyze()
        self.assertFalse(result["ok"])
        self.assertTrue(any("expected free-running LFO" in err
                            for err in result["errors"]), result["errors"])

    def test_dynamic_catalog_auto_discovers_new_patch_without_spec_changes(self) -> None:
        catalog = patch_catalog.collect(ROOT, self.examples)
        self.assertTrue(catalog["ok"], catalog["errors"])
        row = next(p for p in catalog["patches"] if p["file"].endswith("/" + FILENAME))
        self.assertEqual(row["module_count"], 12)
        self.assertEqual(row["cable_count"], 17)
        self.assertEqual(row["macro8_stored_scenes"], 4)
        self.assertEqual(row["midi_channels_saved"], 1)
        self.assertTrue(row["midi_routed"])
        self.assertFalse(row["host_transport_routed"])
        self.assertEqual(row["original_modules"],
                         ["ClockedLFO", "Macro8", "MorphVCO",
                          "StateFilter", "StereoEcho"])


if __name__ == "__main__":
    unittest.main()
