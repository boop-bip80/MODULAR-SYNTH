"""Source-only acceptance for the expressive MIDI film-scoring starter patch."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "patches"))
import factory_patch_coverage as coverage  # noqa: E402
import patch_inspector  # noqa: E402

NAME = "MODULAR_-_Noir_Expressive_Lead.vcv"


class NoirExpressiveLeadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = ROOT / "patches" / "examples" / NAME

    def setUp(self) -> None:
        self.patch = json.loads(self.path.read_text(encoding="utf-8"))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.examples = Path(self.tmp.name) / "examples"
        shutil.copytree(ROOT / "patches" / "examples", self.examples)

    def verify_bad_patch(self, reason: str) -> None:
        (self.examples / NAME).write_text(
            json.dumps(self.patch, indent=2) + "\n", encoding="utf-8"
        )
        result = coverage.analyze(ROOT, self.examples)
        self.assertFalse(result["ok"], reason)
        self.assertTrue(any(NAME in error for error in result["errors"]), result["errors"])

    def module(self, model: str) -> dict:
        return next(m for m in self.patch["modules"] if m["model"] == model)

    def cable(self, source: str, output: int, target: str, input: int) -> dict:
        ids = {m["id"]: m["model"] for m in self.patch["modules"]}
        return next(c for c in self.patch["cables"]
                    if ids[c["outputModuleId"]] == source and c["outputId"] == output
                    and ids[c["inputModuleId"]] == target and c["inputId"] == input)

    def test_saved_patch_is_midi_performance_ready_at_source_level(self) -> None:
        inspected = patch_inspector.inspect_patch(self.path, ROOT)
        self.assertTrue(inspected["ok"], inspected["errors"])
        self.assertEqual(len(self.patch["modules"]), 9)
        self.assertEqual(len(self.patch["cables"]), 15)
        self.assertEqual(len(inspected["components"]), 2)  # TextEditor is a note.
        self.assertEqual(self.module("HostMIDI")["data"]["channels"], 1)
        self.assertEqual(self.module("HostMIDI")["data"]["polyMode"], 0)
        self.assertNotIn("HostTime", {m["model"] for m in self.patch["modules"]})
        for source, output, target, input in (
            ("HostMIDI", 0, "MorphVCO", 0),
            ("HostMIDI", 1, "ADSR", 4),
            ("HostMIDI", 3, "MorphVCO", 2),  # 0..10 V aftertouch -> wave CV
            ("HostMIDI", 5, "StereoEcho", 4),  # 0..10 V modwheel -> wet CV
            ("ADSR", 0, "VCA-1", 0),
            ("StereoEcho", 0, "HostAudio2", 0),
            ("StereoEcho", 1, "HostAudio2", 1),
        ):
            with self.subTest(source=source, target=target):
                self.cable(source, output, target, input)
        claims = coverage.analyze(ROOT)
        self.assertTrue(claims["ok"], claims["errors"])
        accepted = next(p for p in claims["examples"] if p["patch"] == NAME)
        self.assertEqual(len(accepted["capabilities"]), 23)

    def test_gain_delay_and_scenes_are_conservative_source_choices(self) -> None:
        vca = {p["id"]: p["value"] for p in self.module("VCA-1")["params"]}
        audio = {p["id"]: p["value"] for p in self.module("HostAudio2")["params"]}
        echo = {p["id"]: p["value"] for p in self.module("StereoEcho")["params"]}
        self.assertLessEqual(vca[0], 0.35)
        self.assertLessEqual(audio[0], 0.25)
        self.assertLessEqual(echo[1], 0.2)
        self.assertLessEqual(echo[2], 0.1)
        self.assertGreaterEqual(echo[0], 1)
        self.assertLessEqual(echo[0], 300)
        macro = self.module("Macro8")
        params = {p["id"]: p["value"] for p in macro["params"]}
        self.assertEqual(params[8], 0.65)
        self.assertEqual([params[i] for i in range(15, 20)], [0] * 5)
        data = macro["data"]
        self.assertEqual(data["selectedSlot"], -1)
        self.assertEqual(len(data["snapshots"]), 4)
        self.assertEqual([row[:5] for row in data["snapshots"]], [
            [0.08, 0.08, 0.10, 0.02, 0.14],
            [0.16, 0.14, 0.20, 0.06, 0.25],
            [0.28, 0.24, 0.30, 0.13, 0.43],
            [0.42, 0.32, 0.38, 0.20, 0.56],
        ])
        # Source formula: 180 ms base + Macro8 0..10 V * 100 ms/V.
        self.assertEqual([180 + row[0] * 1000 for row in data["snapshots"]],
                         [260, 340, 460, 600])

    def test_rejects_wrong_expressive_controller_jacks(self) -> None:
        aftertouch = self.cable("HostMIDI", 3, "MorphVCO", 2)
        aftertouch["outputId"] = 2  # velocity instead of aftertouch
        self.verify_bad_patch("aftertouch destination must use HostMIDI output 3")

        aftertouch["outputId"] = 3
        modwheel = self.cable("HostMIDI", 5, "StereoEcho", 4)
        modwheel["outputId"] = 4  # pitchbend instead of mod wheel
        self.verify_bad_patch("wet CV must use HostMIDI mod-wheel output 5")

    def test_rejects_broken_macro_and_voice_chains(self) -> None:
        self.patch["cables"].remove(self.cable("Macro8", 4, "MorphVCO", 3))
        self.verify_bad_patch("pulse width scene must remain cable-connected")
        self.patch = json.loads(self.path.read_text(encoding="utf-8"))
        self.patch["cables"].remove(self.cable("ADSR", 0, "VCA-1", 0))
        self.verify_bad_patch("MIDI gate envelope must drive VCA")

    def test_rejects_wrong_macro_mode_or_snapshot_schema(self) -> None:
        macro = self.module("Macro8")
        next(p for p in macro["params"] if p["id"] == 19)["value"] = 1
        self.verify_bad_patch("pulse-width macro should be unipolar")
        next(p for p in macro["params"] if p["id"] == 19)["value"] = 0
        macro["data"]["snapshots"][3] = None
        self.verify_bad_patch("all four performance scenes must exist")


if __name__ == "__main__":
    unittest.main()
