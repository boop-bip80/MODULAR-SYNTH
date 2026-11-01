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
        self.assertTrue({"MorphVCO", "StateFilter", "Macro8"}.issubset(
            report["model_coverage"]))
        self.assertTrue(all(report["model_coverage"].values()))
        self.assertIn("Morphing_State_Pad.vcv",
                      report["model_coverage"]["StateFilter"][0])
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
                self.assertGreaterEqual(len(report["model_coverage"]), 3)
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

    def test_missing_original_model_fails_manifest_coverage(self) -> None:
        filename = "MODULAR_-_Morphing_State_Pad.vcv"

        def remove_macro(patch: dict) -> None:
            macro = next(module["id"] for module in patch["modules"]
                         if module.get("plugin") == "ModularSynth"
                         and module.get("model") == "Macro8")
            patch["modules"] = [module for module in patch["modules"]
                                if module["id"] != macro]
            patch["cables"] = [
                cable for cable in patch["cables"]
                if cable["outputModuleId"] != macro and cable["inputModuleId"] != macro
            ]

        self.mutate(filename, remove_macro)
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("ModularSynth/Macro8: no first-party example" in err
                            for err in report["errors"]), report["errors"])

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

    def test_missing_factory_patch_is_reported(self) -> None:
        (self.examples / "MODULAR_-_Granular_Veil.vcv").unlink()
        report = self.inspect()
        self.assertFalse(report["ok"])
        self.assertTrue(any("advertised example patch is missing" in err
                            for err in report["errors"]), report["errors"])


if __name__ == "__main__":
    unittest.main()
