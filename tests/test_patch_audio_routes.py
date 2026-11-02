"""Regression tests for conservative, source-backed HostAudio2 wiring reports."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "patches"))
from patch_audio_routes import audit_output_routes, format_output_routes  # noqa: E402


def module(mid: int, plugin: str, model: str) -> dict:
    return {"id": mid, "plugin": plugin, "model": model, "params": []}


def wire(cid: int, source: int, target: int, out: int = 0, inp: int = 0) -> dict:
    return {"id": cid, "outputModuleId": source, "outputId": out,
            "inputModuleId": target, "inputId": inp}


class AudioRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "example.vcv"
        self.patch = {
            "version": "2.4.1",
            "modules": [
                module(1, "ModularSynth", "MorphVCO"),
                module(2, "Cardinal", "HostAudio2"),
            ],
            "cables": [wire(3, 1, 2)],
        }

    def audit(self) -> dict:
        self.path.write_text(json.dumps(self.patch), encoding="utf-8")
        return audit_output_routes(self.path, ROOT)

    def test_mono_host_wiring_is_reported_without_claiming_audio(self) -> None:
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertTrue(result["host_contract_verified"])
        self.assertTrue(result["has_wired_host_input"])
        sink = result["sinks"][0]
        self.assertEqual(sink["connected_ports"], [0])
        self.assertEqual(sink["inputs"][0]["source"],
                         {"module_id": 1, "model": "ModularSynth/MorphVCO",
                          "output_port": 0})
        self.assertFalse(sink["inputs"][1]["connected"])
        self.assertEqual(sink["upstream_modules"],
                         [{"module_id": 1, "model": "ModularSynth/MorphVCO"}])
        self.assertIn("not proof of audio", format_output_routes(result))

    def test_multiple_host_sinks_are_sorted_and_reported_independently(self) -> None:
        self.patch["modules"].append(module(9, "Cardinal", "HostAudio2"))
        self.patch["cables"].append(wire(10, 1, 9, 1, 1))
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual([s["module_id"] for s in result["sinks"]], [2, 9])
        self.assertEqual(result["sinks"][0]["connected_ports"], [0])
        self.assertEqual(result["sinks"][1]["connected_ports"], [1])
        self.assertTrue(any("only Right wired" in a for a in result["advisories"]))

    def test_unknown_third_party_and_cv_ancestry_are_graph_only(self) -> None:
        self.patch["modules"].extend([
            module(3, "ThirdParty", "MysteryProcessor"),
            module(4, "Cardinal", "HostMIDI"),
        ])
        self.patch["cables"] = [
            wire(11, 1, 3, 0, 0),
            wire(12, 4, 3, 0, 1),
            wire(13, 3, 2, 0, 0),
        ]
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertTrue(any("ThirdParty/MysteryProcessor" in warning
                            for warning in result["warnings"]))
        self.assertEqual([m["module_id"] for m in result["sinks"][0]["upstream_modules"]],
                         [1, 3, 4])
        self.assertIn("CV/gate paths", format_output_routes(result))

    def test_cycle_does_not_loop_forever(self) -> None:
        self.patch["modules"].extend([
            module(3, "ThirdParty", "ModuleA"),
            module(4, "ThirdParty", "ModuleB"),
        ])
        self.patch["cables"] = [
            wire(11, 3, 4),
            wire(12, 4, 3, 0, 1),
            wire(13, 3, 2),
        ]
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual([m["module_id"] for m in result["sinks"][0]["upstream_modules"]],
                         [3, 4])

    def test_unpatched_host_and_no_host_are_advisory_not_validation_failures(self) -> None:
        self.patch["cables"] = []
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertFalse(result["has_wired_host_input"])
        self.assertTrue(any("neither terminal input" in note for note in result["advisories"]))
        self.patch["modules"].pop()
        result = self.audit()
        self.assertTrue(result["ok"])
        self.assertEqual(result["sinks"], [])
        self.assertTrue(any("No Cardinal/HostAudio2" in note
                            for note in result["advisories"]))

    def test_structural_invalidity_skips_route_traversal(self) -> None:
        self.patch["cables"][0]["inputModuleId"] = 999
        result = self.audit()
        self.assertFalse(result["ok"])
        self.assertFalse(result["has_wired_host_input"])
        self.assertEqual(result["sinks"], [])
        self.assertIn("inspection skipped", result["advisories"][0])

    def test_host_contract_drift_becomes_explicitly_unverified(self) -> None:
        self.patch = {
            "version": "2.4.1",
            "modules": [module(2, "Cardinal", "HostAudio2")],
            "cables": [],
        }
        with tempfile.TemporaryDirectory() as temp:
            fake_root = Path(temp)
            source = fake_root / "plugins" / "Cardinal" / "src" / "HostAudio.cpp"
            source.parent.mkdir(parents=True)
            # The manifest remains authoritative even while deliberately
            # corrupting just the C++ port-contract declaration. Without it,
            # the inspector rightly rejects Cardinal/HostAudio2 as unknown
            # first-party model before reaching the intended drift assertion.
            manifest = fake_root / "plugins" / "Cardinal" / "plugin.json"
            manifest.write_text(
                (ROOT / "plugins" / "Cardinal" / "plugin.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            current = (ROOT / "plugins" / "Cardinal" / "src" / "HostAudio.cpp").read_text()
            source.write_text(current.replace(
                "struct HostAudio2 : HostAudio<2>", "struct HostAudio2 : HostAudio<4>"),
                encoding="utf-8",
            )
            self.path.write_text(json.dumps(self.patch), encoding="utf-8")
            result = audit_output_routes(self.path, fake_root)
            self.assertTrue(result["ok"])
            self.assertFalse(result["host_contract_verified"])
            self.assertTrue(any("not verified" in a for a in result["advisories"]))

    def test_batch_cli_opt_in_exit_status_and_stable_json(self) -> None:
        script = ROOT / "tools" / "patches" / "patch_audio_routes.py"
        self.path.write_text(json.dumps(self.patch), encoding="utf-8")

        def call(*options: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, str(script), str(self.path), *options],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )

        passing = call("--require-host-input", "--json")
        self.assertEqual(passing.returncode, 0, passing.stderr)
        self.assertTrue(json.loads(passing.stdout)[0]["has_wired_host_input"])
        self.assertEqual(passing.stdout, call("--require-host-input", "--json").stdout)
        self.patch["cables"] = []
        self.path.write_text(json.dumps(self.patch), encoding="utf-8")
        advisory = call("--json")
        self.assertEqual(advisory.returncode, 0, advisory.stderr)
        self.assertEqual(call("--require-host-input").returncode, 1)
        self.path.write_text('{"version":"x","modules":[],"modules":[],"cables":[]}',
                             encoding="utf-8")
        self.assertEqual(call().returncode, 2)


if __name__ == "__main__":
    unittest.main()
