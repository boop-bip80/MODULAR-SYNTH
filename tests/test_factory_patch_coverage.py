"""Factory patch coverage and advertised capability regression tests."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "patches"))
import factory_patch_coverage as coverage  # noqa: E402


class FactoryPatchCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.examples = Path(self.temp.name) / "examples"
        self.examples.mkdir()
        for name in coverage.EXAMPLES:
            shutil.copyfile(ROOT / "patches" / "examples" / name,
                            self.examples / name)

    def inspect(self) -> dict:
        return coverage.analyze(ROOT, self.examples)

    def mutate(self, name: str, change) -> None:
        path = self.examples / name
        patch = json.loads(path.read_text(encoding="utf-8"))
        change(patch)
        path.write_text(json.dumps(patch, indent=2), encoding="utf-8")

    def test_all_advertised_examples_and_original_models_are_covered(self) -> None:
        report = coverage.analyze(ROOT)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(len(report["examples"]), len(coverage.EXAMPLES))
        self.assertTrue(all(patch["ok"] for patch in report["examples"]))
        self.assertTrue({"MorphVCO", "StateFilter", "FoldDrive", "Macro8",
                         "StereoEcho", "ClockedLFO", "FMVoice", "ChanceHold"}.issubset(
            report["model_coverage"]))
        self.assertTrue(all(report["model_coverage"].values()))
        self.assertTrue(any("Morphing_State_Pad.vcv" in name
                            for name in report["model_coverage"]["StateFilter"]))
        self.assertIn("MODULAR_-_Stereo_Echo_Showcase.vcv",
                      report["model_coverage"]["StereoEcho"])
        self.assertIn("MODULAR_-_Clocked_Modulation_Studio.vcv",
                      report["model_coverage"]["ClockedLFO"])
        self.assertIn("MODULAR_-_Fold_Drive_Cinematic_Motion.vcv",
                      report["model_coverage"]["FoldDrive"])
        self.assertIn("MODULAR_-_FM_Voice_Performance.vcv",
                      report["model_coverage"]["FMVoice"])
        self.assertIn("MODULAR_-_Chance_Hold_FM_Drift.vcv",
                      report["model_coverage"]["ChanceHold"])
        self.assertIn("MODULAR_-_Major_Glow_Quantized_Performance.vcv",
                      report["model_coverage"]["ScaleQuantizer"])
        self.assertEqual(report["sample_rate_status"],
                         "not asserted: no host runtime sample-rate execution")
        self.assertGreater(sum(patch["warning_count"]
                               for patch in report["examples"]), 0,
                           "Unknown third-party bounds must remain visible")

    def test_cli_json_and_text(self) -> None:
        script = ROOT / "tools" / "patches" / "factory_patch_coverage.py"
        for json_mode in (True, False):
            args = [sys.executable, str(script)]
            if json_mode:
                args.append("--json")
            proc = subprocess.run(args, cwd=ROOT, text=True,
                                  capture_output=True, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            if json_mode:
                report = json.loads(proc.stdout)
                self.assertTrue(report["ok"])
                self.assertGreaterEqual(len(report["model_coverage"]), 8)
            else:
                self.assertIn("PASS factory patch claims", proc.stdout)
                self.assertIn("host execution not tested", proc.stdout)

    def test_missing_advertised_route_is_not_structural_error(self) -> None:
        filename = "MODULAR_-_Clockwork_Pulses.vcv"

        def remove_lfo_link(patch: dict) -> None:
            lfo = next(module["id"] for module in patch["modules"]
                       if module["plugin"] == "Bogaudio"
                       and module["model"] == "Bogaudio-LFO")
            patch["cables"] = [cable for cable in patch["cables"]
                               if cable["outputModuleId"] != lfo]

        self.mutate(filename, remove_lfo_link)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("missing advertised route: LFO modulation to Plaits" in err
                            for err in report["errors"]), report["errors"])

    def test_fm_voice_example_requires_enveloped_midi_pitch_route(self) -> None:
        filename = "MODULAR_-_FM_Voice_Performance.vcv"

        def remove_pitch(patch: dict) -> None:
            fm = next(m["id"] for m in patch["modules"]
                      if m.get("plugin") == "ModularSynth"
                      and m.get("model") == "FMVoice")
            patch["cables"] = [
                c for c in patch["cables"]
                if not (c["inputModuleId"] == fm and c["inputId"] == 0)
            ]

        self.mutate(filename, remove_pitch)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any(
            "missing advertised route: MIDI pitch to FM Voice 1V/oct" in err
            for err in report["errors"]
        ), report["errors"])

    def test_missing_original_model_fails_manifest_coverage(self) -> None:
        def remove_macro(patch: dict) -> None:
            ids = {module["id"] for module in patch["modules"]
                   if module.get("plugin") == "ModularSynth"
                   and module.get("model") == "Macro8"}
            patch["modules"] = [module for module in patch["modules"]
                                if module["id"] not in ids]
            patch["cables"] = [
                cable for cable in patch["cables"]
                if cable["outputModuleId"] not in ids
                and cable["inputModuleId"] not in ids
            ]

        # Macro8 appears in State Pad AND the two newer factory patches.
        # Remove all uses to exercise manifest-wide coverage, not just a
        # per-patch required-model assertion.
        for filename in coverage.EXAMPLES:
            self.mutate(filename, remove_macro)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("ModularSynth/Macro8: no first-party example" in err
                            for err in report["errors"]), report["errors"])

    def test_fold_drive_patch_requires_midi_modwheel_wet_cv(self) -> None:
        filename = "MODULAR_-_Fold_Drive_Cinematic_Motion.vcv"

        def remove_wet_cv(patch: dict) -> None:
            fold = next(m["id"] for m in patch["modules"]
                        if m.get("plugin") == "ModularSynth"
                        and m.get("model") == "FoldDrive")
            patch["cables"] = [c for c in patch["cables"]
                               if not (c["inputModuleId"] == fold and c["inputId"] == 3)]

        self.mutate(filename, remove_wet_cv)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("missing advertised route: MIDI mod wheel changes FoldDrive wet mix"
                            in error for error in report["errors"]), report["errors"])

    def test_fold_drive_patch_must_remain_unsynchronized_free_running(self) -> None:
        filename = "MODULAR_-_Fold_Drive_Cinematic_Motion.vcv"

        def change_free_rate(patch: dict) -> None:
            lfo = next(m for m in patch["modules"]
                       if m.get("plugin") == "ModularSynth"
                       and m.get("model") == "ClockedLFO")
            lfo["params"][0]["value"] = 1.0

        self.mutate(filename, change_free_rate)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("expected free-running LFO with saved rate 0.25 Hz"
                            in error for error in report["errors"]), report["errors"])

    def test_invalid_first_party_cable_is_delegated_to_inspector(self) -> None:
        filename = "MODULAR_-_Morphing_State_Pad.vcv"

        def corrupt_macro_port(patch: dict) -> None:
            macro = next(module["id"] for module in patch["modules"]
                         if module["plugin"] == "ModularSynth"
                         and module["model"] == "Macro8")
            link = next(cable for cable in patch["cables"]
                        if cable["outputModuleId"] == macro)
            link["outputId"] = 100

        self.mutate(filename, corrupt_macro_port)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("outputs index 100 exceeds known count 8" in err
                            for err in report["errors"]), report["errors"])

    def test_snapshot_claim_rejects_missing_saved_slot(self) -> None:
        filename = "MODULAR_-_Morphing_State_Pad.vcv"

        def remove_snapshot(patch: dict) -> None:
            macro = next(module for module in patch["modules"]
                         if module["plugin"] == "ModularSynth"
                         and module["model"] == "Macro8")
            macro["data"]["snapshots"][1] = None

        self.mutate(filename, remove_snapshot)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("missing documented Macro8" in err
                            for err in report["errors"]), report["errors"])

    def test_new_factory_patch_needs_coverage_review(self) -> None:
        shutil.copyfile(self.examples / "MODULAR_-_Pulse_Bass.vcv",
                        self.examples / "MODULAR_-_Unreviewed.vcv")
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("no source-grounded capability claims reviewed" in err
                            for err in report["errors"]), report["errors"])

    def test_new_patches_require_bipolar_cutoff_range(self) -> None:
        filename = "MODULAR_-_Cinematic_Drift_Pad.vcv"

        def remove_bipolar_mode(patch: dict) -> None:
            macro = next(module for module in patch["modules"]
                         if module["plugin"] == "ModularSynth"
                         and module["model"] == "Macro8")
            mode = next(param for param in macro["params"] if param["id"] == 18)
            mode["value"] = 0

        self.mutate(filename, remove_bipolar_mode)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("macro cutoff CV output range must be bipolar" in err
                            for err in report["errors"]), report["errors"])

    def test_new_patches_require_documented_morph_time(self) -> None:
        filename = "MODULAR_-_Rhythmic_Grit_Bass.vcv"

        def slow_morph(patch: dict) -> None:
            macro = next(module for module in patch["modules"]
                         if module["plugin"] == "ModularSynth"
                         and module["model"] == "Macro8")
            morph = next(param for param in macro["params"] if param["id"] == 8)
            morph["value"] = 3.0

        self.mutate(filename, slow_morph)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("expected Macro8 morph time 0.20 s" in err
                            for err in report["errors"]), report["errors"])

    def test_both_granular_oscillators_need_midi_pitch(self) -> None:
        filename = "MODULAR_-_Granular_Veil.vcv"

        def remove_one_midi_feed(patch: dict) -> None:
            oscillator_ids = [
                module["id"] for module in patch["modules"]
                if module["plugin"] == "Bogaudio"
                and module["model"] == "Bogaudio-VCO"
            ]
            target = oscillator_ids[0]
            patch["cables"] = [
                cable for cable in patch["cables"]
                if cable["inputModuleId"] != target
                or cable["outputModuleId"] not in {
                    module["id"] for module in patch["modules"]
                    if module["plugin"] == "Cardinal"
                    and module["model"] == "HostMIDI"
                }
            ]

        self.mutate(filename, remove_one_midi_feed)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("both VCO instances must receive MIDI" in err
                            for err in report["errors"]), report["errors"])

    def test_poly_motion_pad_has_source_grounded_voices_and_snapshots(self) -> None:
        filename = "MODULAR_-_Polyphonic_Motion_Pad.vcv"
        report = self.inspect()
        patch = next(item for item in report["examples"]
                     if item["patch"] == filename)
        self.assertTrue(patch["ok"], patch["errors"])
        self.assertEqual({key for key in patch["modules"] if key.startswith("ModularSynth/")},
                         {"ModularSynth/MorphVCO",
                          "ModularSynth/StateFilter", "ModularSynth/Macro8"})
        self.assertIn("8-channel HostMIDI Reuse polyphony",
                      patch["capabilities"])
        self.assertIn("4 versioned Macro8 snapshots", patch["capabilities"])
        self.assertIn("bipolar Macro8 PWM output range", patch["capabilities"])
        self.assertIn("per-voice MIDI pitch to filter cutoff",
                      patch["capabilities"])
        self.assertIn("two host audio input routes", patch["capabilities"])

    def test_poly_motion_rejects_mono_host_midi(self) -> None:
        filename = "MODULAR_-_Polyphonic_Motion_Pad.vcv"

        def make_mono(patch: dict) -> None:
            midi = next(module for module in patch["modules"]
                        if module["plugin"] == "Cardinal"
                        and module["model"] == "HostMIDI")
            midi["data"]["channels"] = 1

        self.mutate(filename, make_mono)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("expected HostMIDI 8-channel Reuse polyphony" in err
                            for err in report["errors"]), report["errors"])

    def test_poly_motion_rejects_split_midi_pitch_and_gate_sources(self) -> None:
        filename = "MODULAR_-_Polyphonic_Motion_Pad.vcv"

        def split_midi(patch: dict) -> None:
            midi = next(module for module in patch["modules"]
                        if module["plugin"] == "Cardinal"
                        and module["model"] == "HostMIDI")
            clone = json.loads(json.dumps(midi))
            clone["id"] = max(module["id"] for module in patch["modules"]) + 1
            patch["modules"].append(clone)
            for cable in patch["cables"]:
                if (cable["outputModuleId"] == midi["id"]
                        and cable["outputId"] == 0):
                    cable["outputModuleId"] = clone["id"]

        self.mutate(filename, split_midi)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("polyphonic MIDI voice flow" in err
                            for err in report["errors"]), report["errors"])

    def test_poly_motion_rejects_missing_keytracking_cable(self) -> None:
        filename = "MODULAR_-_Polyphonic_Motion_Pad.vcv"

        def remove_keytrack(patch: dict) -> None:
            midi = next(module["id"] for module in patch["modules"]
                        if module["plugin"] == "Cardinal"
                        and module["model"] == "HostMIDI")
            filt = next(module["id"] for module in patch["modules"]
                        if module["plugin"] == "ModularSynth"
                        and module["model"] == "StateFilter")
            patch["cables"] = [
                c for c in patch["cables"] if not (
                    c["outputModuleId"] == midi and c["outputId"] == 0
                    and c["inputModuleId"] == filt and c["inputId"] == 1
                )
            ]

        self.mutate(filename, remove_keytrack)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("per-voice MIDI pitch to filter cutoff" in err
                            for err in report["errors"]), report["errors"])

    def test_poly_motion_requires_all_four_macro_snapshots(self) -> None:
        filename = "MODULAR_-_Polyphonic_Motion_Pad.vcv"

        def empty_fourth(patch: dict) -> None:
            macro = next(module for module in patch["modules"]
                         if module["plugin"] == "ModularSynth"
                         and module["model"] == "Macro8")
            macro["data"]["snapshots"][3] = None

        self.mutate(filename, empty_fourth)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("missing documented Macro8 names" in err
                            for err in report["errors"]), report["errors"])

    def test_poly_motion_requires_bipolar_width_range(self) -> None:
        filename = "MODULAR_-_Polyphonic_Motion_Pad.vcv"

        def make_unipolar(patch: dict) -> None:
            macro = next(module for module in patch["modules"]
                         if module["plugin"] == "ModularSynth"
                         and module["model"] == "Macro8")
            next(param for param in macro["params"] if param["id"] == 18)["value"] = 0

        self.mutate(filename, make_unipolar)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("macro width CV output range must be bipolar" in err
                            for err in report["errors"]), report["errors"])


    def test_echo_showcase_has_distinct_filter_stereo_paths(self) -> None:
        filename = "MODULAR_-_Stereo_Echo_Showcase.vcv"
        report = self.inspect()
        patch = next(item for item in report["examples"]
                     if item["patch"] == filename)
        self.assertTrue(patch["ok"], patch["errors"])
        self.assertIn("filter LP to StereoEcho left", patch["capabilities"])
        self.assertIn("filter HP to StereoEcho right", patch["capabilities"])
        self.assertIn("StereoEcho left to host left", patch["capabilities"])
        self.assertIn("StereoEcho right to host right", patch["capabilities"])
        self.assertIn("two host audio input routes", patch["capabilities"])

    def test_echo_showcase_rejects_missing_right_filter_input(self) -> None:
        filename = "MODULAR_-_Stereo_Echo_Showcase.vcv"

        def remove_highpass_to_echo(patch: dict) -> None:
            filt = next(module["id"] for module in patch["modules"]
                        if module["plugin"] == "ModularSynth"
                        and module["model"] == "StateFilter")
            echo = next(module["id"] for module in patch["modules"]
                        if module["plugin"] == "ModularSynth"
                        and module["model"] == "StereoEcho")
            patch["cables"] = [
                cable for cable in patch["cables"] if not (
                    cable["outputModuleId"] == filt and cable["outputId"] == 2
                    and cable["inputModuleId"] == echo and cable["inputId"] == 1
                )
            ]

        self.mutate(filename, remove_highpass_to_echo)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("filter HP to StereoEcho right" in error
                            for error in report["errors"]), report["errors"])

    def test_echo_showcase_rejects_missing_right_host_output(self) -> None:
        filename = "MODULAR_-_Stereo_Echo_Showcase.vcv"

        def remove_right_host_output(patch: dict) -> None:
            patch["cables"] = [
                cable for cable in patch["cables"] if not (
                    cable["inputModuleId"] == 1 and cable["inputId"] == 1
                )
            ]

        self.mutate(filename, remove_right_host_output)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("StereoEcho right to host right" in error
                            for error in report["errors"]), report["errors"])
        self.assertTrue(any("missing two saved HostAudio2 input routes" in error
                            for error in report["errors"]), report["errors"])

    def test_missing_factory_patch_is_reported(self) -> None:
        (self.examples / "MODULAR_-_Granular_Veil.vcv").unlink()
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("advertised example patch is missing" in err
                            for err in report["errors"]), report["errors"])

    def test_clocked_modulation_studio_has_source_grounded_tempo_routes(self) -> None:
        filename = "MODULAR_-_Clocked_Modulation_Studio.vcv"
        report = self.inspect()
        patch = next(item for item in report["examples"]
                     if item["patch"] == filename)
        self.assertTrue(patch["ok"], patch["errors"])
        for capability in (
            "host beat clocks LFO",
            "host reset phase-aligns LFO",
            "MIDI pitch provides poly free-rate CV",
            "LFO cycle trigger to ADSR retrigger",
            "LFO sine modulates VCO morph",
            "LFO triangle modulates filter cutoff",
            "LFO pulse switches Echo wet mix",
            "Echo left to host left",
            "Echo right to host right",
            "two host audio input routes",
            "8-channel HostMIDI Reuse polyphony",
        ):
            self.assertIn(capability, patch["capabilities"])

    def test_clocked_modulation_rejects_missing_tempo_clock(self) -> None:
        filename = "MODULAR_-_Clocked_Modulation_Studio.vcv"

        def remove_beat_clock(patch: dict) -> None:
            host = next(module["id"] for module in patch["modules"]
                        if module["plugin"] == "Cardinal"
                        and module["model"] == "HostTime")
            lfo = next(module["id"] for module in patch["modules"]
                       if module["plugin"] == "ModularSynth"
                       and module["model"] == "ClockedLFO")
            patch["cables"] = [cable for cable in patch["cables"] if not (
                cable["outputModuleId"] == host and cable["outputId"] == 3
                and cable["inputModuleId"] == lfo and cable["inputId"] == 1
            )]

        self.mutate(filename, remove_beat_clock)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("host beat clocks LFO" in err
                            for err in report["errors"]), report["errors"])

    def test_clocked_modulation_rejects_bad_eoc_output_port(self) -> None:
        filename = "MODULAR_-_Clocked_Modulation_Studio.vcv"

        def corrupt_end_of_cycle(patch: dict) -> None:
            lfo = next(module["id"] for module in patch["modules"]
                       if module["plugin"] == "ModularSynth"
                       and module["model"] == "ClockedLFO")
            retrigger = next(cable for cable in patch["cables"]
                             if cable["outputModuleId"] == lfo
                             and cable["outputId"] == 4)
            retrigger["outputId"] = 42

        self.mutate(filename, corrupt_end_of_cycle)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("outputs index 42 exceeds known count 5" in err
                            for err in report["errors"]), report["errors"])


if __name__ == "__main__":
    unittest.main()
