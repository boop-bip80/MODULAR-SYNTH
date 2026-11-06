"""CI source/build identity gate tests using *synthetic* WAV fixtures only.

No test fixture here was recorded in Carla, LV2, Reaper or any actual DAW.
Passing these tests does not establish real-host audio provenance.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import test_ci_host_audio_capture as fixtures


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("host_capture_ci", ROOT / "tools/ci/verify_host_audio_capture_ci.py")
assert SPEC and SPEC.loader
ci = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci)


class HostAudioCIPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = fixtures.HostCaptureTests("test_valid_synth_stereo_midi_and_negative_control")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.build_root = Path(self.temp.name)
        self.bin_dir = self.build_root / "bin"
        self.lv2_dir = self.build_root / "lv2"
        self.capture_file = self.fixture.base / "capture.json"
        self.build_target = self.lv2_dir / "CardinalSynth.lv2" / "CardinalSynth.so"
        self.build_target.parent.mkdir(parents=True)
        self.fixture.manifest["host"]["plugin_format"] = "LV2"
        shutil.copy2(self.fixture.base / "compiled-plugin.so", self.build_target)
        self.write_manifest()

    def write_manifest(self) -> None:
        self.capture_file.write_text(json.dumps(self.fixture.manifest), encoding="utf-8")

    def run_gate(self) -> dict:
        return ci.verify_ci(self.capture_file, fixtures.SOURCE_SHA, self.bin_dir, self.lv2_dir)

    def test_operator_attested_wavs_pass_only_with_matching_ci_binary(self) -> None:
        result = self.run_gate()
        self.assertTrue(result["accepted"])
        self.assertEqual(result["build_artifact_sha256"], self.fixture.manifest["plugin"]["sha256"])
        self.assertIn("operator-attested", result["provenance_scope_warning"])

    def test_build_plugin_different_from_capture_plugin_fails(self) -> None:
        self.build_target.write_bytes(self.build_target.read_bytes() + b"different build")
        with self.assertRaisesRegex(ci.CaptureError, "differs from freshly built"):
            self.run_gate()

    def test_capture_absent_fails_closed(self) -> None:
        self.capture_file.unlink()
        with self.assertRaisesRegex(ci.CaptureError, "real host recording is REQUIRED"):
            self.run_gate()

    def test_compiled_plugin_absent_fails_closed(self) -> None:
        self.build_target.unlink()
        with self.assertRaisesRegex(ci.CaptureError, "absent"):
            self.run_gate()

    def test_wrong_source_sha_fails(self) -> None:
        self.fixture.manifest["source_sha"] = "b" * 40
        self.write_manifest()
        with self.assertRaisesRegex(ci.CaptureError, "source commit mismatch"):
            self.run_gate()

    def test_linked_vst3_variant_selected_from_claimed_host_format(self) -> None:
        self.fixture.manifest["host"]["plugin_format"] = "VST3"
        self.write_manifest()
        with self.assertRaisesRegex(ci.CaptureError, "absent"):
            self.run_gate()
        target = self.bin_dir / "CardinalSynth.vst3/Contents/x86_64-linux/CardinalSynth.so"
        target.parent.mkdir(parents=True)
        shutil.copy2(self.fixture.base / "compiled-plugin.so", target)
        self.assertTrue(self.run_gate()["accepted"])

    def test_effect_mode_selects_fx_binary(self) -> None:
        fixtures.write_wav(self.fixture.base / "dry.wav", amplitude=.18)
        self.fixture.manifest["mode"] = "effect"
        self.fixture.refresh("dry.wav", "stimulus")
        self.write_manifest()
        with self.assertRaisesRegex(ci.CaptureError, "absent"):
            self.run_gate()
        target = self.lv2_dir / "CardinalFX.lv2/CardinalFX.so"
        target.parent.mkdir(parents=True)
        shutil.copy2(self.fixture.base / "compiled-plugin.so", target)
        self.assertTrue(self.run_gate()["accepted"])

    def test_dispatch_gate_requires_external_capture_and_exact_build_sha(self) -> None:
        workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        job = workflow.split("\n  plugin-validation:\n", 1)[1]
        self.assertIn("require_host_audio_evidence:", workflow)
        self.assertIn("host_audio_capture_run_id:", workflow)
        self.assertIn("actions: read", job)
        self.assertIn("gh run download \"$EVIDENCE_RUN_ID\"", job)
        self.assertIn("--name modular-real-host-audio", job)
        self.assertIn("test -s host-evidence/capture.json", job)
        self.assertIn("--expected-sha \"$(git rev-parse HEAD)\"", job)
        self.assertIn("python3 -B tools/ci/verify_host_audio_capture_ci.py", job)
        self.assertIn("HOST AUDIO NOT PROVEN", job)


if __name__ == "__main__":
    unittest.main()
