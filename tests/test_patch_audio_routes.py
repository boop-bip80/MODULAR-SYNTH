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


    def test_direct_control_source_to_host_is_advisory_only(self) -> None:
        self.patch["modules"][0]["model"] = "Macro8"
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertTrue(result["has_wired_host_input"])
        self.assertEqual(result["control_source_hints"], [{
            "host_module_id": 2, "input_port": 0,
            "module_id": 1, "model": "ModularSynth/Macro8", "output_port": 0,
        }])
        self.assertFalse(result["unrouted_first_party_generators"])
        self.assertTrue(any("control-oriented" in a for a in result["advisories"]))

    def test_disconnected_morph_voice_is_reported_without_failing_patch(self) -> None:
        # The host has a valid direct cable but from an unrelated Macro8 CV
        # bank. A MorphVCO without any cable path must not be counted as routed.
        self.patch["modules"][0]["model"] = "Macro8"
        self.patch["modules"].append(module(6, "ModularSynth", "MorphVCO"))
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertTrue(result["has_wired_host_input"])
        self.assertEqual(result["unrouted_first_party_generators"], [
            {"module_id": 6, "model": "ModularSynth/MorphVCO"},
        ])
        self.assertIn("First-party voices without a host cable-graph route: 1",
                      format_output_routes(result))

    def test_cable_directionality_avoids_false_output_routes(self) -> None:
        # Two upstream modules share a downstream CV target; only the second
        # has a direct route to the host. Undirected connected-components
        # analysis would incorrectly report the VCO as routed.
        self.patch["modules"].append(module(3, "ThirdParty", "CVTarget"))
        self.patch["modules"].append(module(4, "ThirdParty", "Source"))
        self.patch["cables"] = [
            wire(10, 1, 3, 0, 0),
            wire(11, 4, 3, 0, 1),
            wire(12, 4, 2, 0, 0),
        ]
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["unrouted_first_party_generators"], [
            {"module_id": 1, "model": "ModularSynth/MorphVCO"},
        ])

    def test_unknown_processing_hop_does_not_claim_audio_verified(self) -> None:
        self.patch["modules"].append(module(3, "ThirdParty", "UnknownProcessor"))
        self.patch["cables"] = [wire(10, 1, 3), wire(11, 3, 2)]
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["unrouted_first_party_generators"], [])
        self.assertEqual(result["control_source_hints"], [])
        self.assertTrue(any("unverified" in warning
                            for warning in result["warnings"]))

    def test_fmvoice_source_output_routing_matches_new_module(self) -> None:
        self.patch["modules"][0]["model"] = "FMVoice"
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["unrouted_first_party_generators"], [])
        self.patch["cables"] = []
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["unrouted_first_party_generators"], [
            {"module_id": 1, "model": "ModularSynth/FMVoice"},
        ])

    def test_cli_generator_route_gate_is_opt_in(self) -> None:
        script = ROOT / "tools" / "patches" / "patch_audio_routes.py"
        self.patch["modules"][0]["model"] = "Macro8"
        self.patch["modules"].append(module(7, "ModularSynth", "MorphVCO"))
        self.path.write_text(json.dumps(self.patch), encoding="utf-8")

        def call(*flags: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, str(script), str(self.path), *flags],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )

        self.assertEqual(call().returncode, 0)
        self.assertEqual(call("--require-host-input").returncode, 0)
        gated = call("--require-generator-route", "--json")
        self.assertEqual(gated.returncode, 1, gated.stderr)
        self.assertEqual(
            json.loads(gated.stdout)[0]["unrouted_first_party_generators"],
            [{"module_id": 7, "model": "ModularSynth/MorphVCO"}],
        )


    def test_direct_source_verified_signal_route(self) -> None:
        result = self.audit()
        self.assertEqual(result["source_verified_signal_routes"], [{
            "module_id": 1,
            "model": "ModularSynth/MorphVCO",
            "host_module_id": 2,
            "host_input_port": 0,
            "via_module_ids": [1],
        }])
        self.assertEqual(result["unverified_first_party_signal_routes"], [])
        self.assertEqual(result["source_verified_host_inputs"], [
            result["source_verified_signal_routes"][0],
        ])
        self.assertEqual(result["unverified_wired_host_inputs"], [])
        self.assertIn("1/1", format_output_routes(result))
        self.assertIn("not proof of audible output", format_output_routes(result))

    def test_second_wired_host_input_is_not_verified_by_first_voice_route(self) -> None:
        # A valid cable to Left cannot certify separately wired Right. The
        # old all-generator gate remains true even when Right is Macro8 CV.
        self.patch["modules"].append(module(3, "ModularSynth", "Macro8"))
        self.patch["cables"].append(wire(4, 3, 2, 0, 1))
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(len(result["source_verified_signal_routes"]), 1)
        self.assertEqual([route["host_input_port"]
                          for route in result["source_verified_host_inputs"]], [0])
        self.assertEqual(result["unverified_wired_host_inputs"], [{
            "host_module_id": 2,
            "host_input_port": 1,
            "source_module_id": 3,
            "source_model": "ModularSynth/Macro8",
            "source_output_port": 0,
        }])
        self.assertIn("1/2", format_output_routes(result))
        self.assertTrue(any("HostAudio2[2] input 1 is wired" in note
                            for note in result["advisories"]))

    def test_new_terminal_gate_is_strict_and_separate_from_voice_gate(self) -> None:
        script = ROOT / "tools" / "patches" / "patch_audio_routes.py"

        def call(*flags: str) -> subprocess.CompletedProcess[str]:
            self.path.write_text(json.dumps(self.patch), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(script), str(self.path), *flags],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )

        flag = "--require-source-verified-host-inputs"
        self.assertEqual(call(flag).returncode, 0)
        self.patch["modules"].append(module(3, "ModularSynth", "Macro8"))
        self.patch["cables"].append(wire(4, 3, 2, 0, 1))
        self.assertEqual(call("--require-source-verified-signal-route").returncode, 0)
        self.assertEqual(call(flag).returncode, 1)
        serialized = json.loads(call("--json").stdout)[0]
        self.assertEqual(len(serialized["unverified_wired_host_inputs"]), 1)

        # With a second actual MorphVCO output rather than control CV, both
        # terminals have a typed first-party signal path. This is still not a
        # listening test or proof of stereo width.
        self.patch["cables"][-1]["outputModuleId"] = 1
        self.patch["cables"][-1]["outputId"] = 1
        self.assertEqual(call(flag).returncode, 0)
        result = self.audit()
        self.assertEqual([r["host_input_port"] for r in
                          result["source_verified_host_inputs"]], [0, 1])

        # No wired terminal is not vacuously accepted under the new gate.
        self.patch["cables"] = []
        self.assertEqual(call(flag).returncode, 1)

    def test_distinct_host_sinks_are_scored_per_exact_terminal(self) -> None:
        self.patch["modules"].extend([
            module(3, "Cardinal", "HostAudio2"),
            module(4, "ThirdParty", "UnknownEffect"),
        ])
        self.patch["cables"] = [
            wire(10, 1, 2, 0, 1),  # First host Right, first-party signal.
            wire(11, 1, 4, 0, 0),
            wire(12, 4, 3, 0, 0),  # Second host Left, opaque processor.
        ]
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual([(r["host_module_id"], r["host_input_port"])
                          for r in result["source_verified_host_inputs"]], [(2, 1)])
        self.assertEqual([(r["host_module_id"], r["host_input_port"])
                          for r in result["unverified_wired_host_inputs"]], [(3, 0)])

    def test_cv_only_chain_to_other_host_input_does_not_certify_stereo(self) -> None:
        self.patch["modules"].append(module(3, "ModularSynth", "StateFilter"))
        self.patch["cables"] = [
            wire(10, 1, 2, 0, 0),  # Source-verified direct Left.
            wire(11, 1, 3, 0, 1),  # VCO drives CUTOFF CV, not filter audio.
            wire(12, 3, 2, 0, 1),
        ]
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(len(result["source_verified_host_inputs"]), 1)
        self.assertEqual(result["source_verified_host_inputs"][0]["host_input_port"], 0)
        self.assertEqual(result["unverified_wired_host_inputs"][0]["host_input_port"], 1)

    def test_real_factory_patches_distinguish_original_vca_from_opaque_vca(self) -> None:
        folder = ROOT / "patches" / "examples"
        source_verified = audit_output_routes(
            folder / "MODULAR_-_Morph_VCO_Performance.vcv", ROOT)
        self.assertTrue(source_verified["ok"], source_verified["errors"])
        self.assertEqual(len(source_verified["source_verified_host_inputs"]), 2)
        self.assertEqual(source_verified["unverified_wired_host_inputs"], [])

        # Aurora's Fundamental VCA-1 is a legitimate saved processor, but its
        # internal transfer relationship is outside this *first-party* proof.
        # Therefore we classify the host cables as wired but not source-
        # verified, without calling the actual preset broken or silent.
        opaque = audit_output_routes(
            folder / "MODULAR_-_Aurora_Glass_Bells.vcv", ROOT)
        self.assertTrue(opaque["ok"], opaque["errors"])
        self.assertEqual(opaque["source_verified_host_inputs"], [])
        self.assertEqual(len(opaque["unverified_wired_host_inputs"]), 2)

    def test_cv_only_first_party_hop_is_not_a_verified_signal_route(self) -> None:
        # Module reachability alone once misrepresented this as a complete
        # generator route even though the VCO enters StateFilter CUTOFF_CV.
        self.patch["modules"].append(module(3, "ModularSynth", "StateFilter"))
        self.patch["cables"] = [wire(11, 1, 3, 0, 1), wire(12, 3, 2)]
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["unrouted_first_party_generators"], [])
        self.assertEqual(result["source_verified_signal_routes"], [])
        self.assertEqual(result["unverified_first_party_signal_routes"], [
            {"module_id": 1, "model": "ModularSynth/MorphVCO"},
        ])
        self.assertTrue(any("CV-only" in a for a in result["advisories"]))

    def test_source_declared_audio_chain_has_stable_module_path(self) -> None:
        self.patch["modules"].extend([
            module(3, "ModularSynth", "StateFilter"),
            module(4, "ModularSynth", "FoldDrive"),
            module(5, "ModularSynth", "StereoEcho"),
        ])
        self.patch["cables"] = [
            wire(11, 1, 3, 0, 0),  # MorphVCO audio -> filter audio, not cutoff CV
            wire(12, 3, 4, 0, 0),  # low-pass -> wavefolder audio
            wire(13, 4, 5, 0, 0),  # wavefolder -> echo Left
            wire(14, 5, 2, 1, 0),  # echo Right -> host Left/M
        ]
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["source_verified_signal_routes"], [{
            "module_id": 1, "model": "ModularSynth/MorphVCO",
            "host_module_id": 2, "host_input_port": 0,
            "via_module_ids": [1, 3, 4, 5],
        }])
        self.assertEqual(result["unrouted_first_party_generators"], [])

    def test_traces_record_every_cable_and_jack_through_a_processor_chain(self) -> None:
        self.patch["modules"].extend([
            module(3, "ModularSynth", "StateFilter"),
            module(4, "ModularSynth", "FoldDrive"),
            module(5, "ModularSynth", "StereoEcho"),
        ])
        self.patch["cables"] = [
            wire(20, 1, 3, 1, 0),
            wire(21, 3, 4, 2, 0),
            wire(22, 4, 5, 0, 1),
            wire(23, 5, 2, 0, 1),
        ]
        report = self.audit()
        self.assertTrue(report["ok"], report["errors"])
        traces = report["source_verified_host_input_traces"]
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]["via_module_ids"], [1, 3, 4, 5])
        self.assertEqual(traces[0]["host_input_port"], 1)
        self.assertEqual(traces[0]["cable_hops"], [
            {"cable_id": cid, "output_module_id": src, "output_port": out,
             "input_module_id": dst, "input_port": inp}
            for cid, src, out, dst, inp in (
                (20, 1, 1, 3, 0), (21, 3, 2, 4, 0),
                (22, 4, 0, 5, 1), (23, 5, 0, 2, 1),
            )
        ])
        # The legacy report is intentionally unchanged for existing tools.
        self.assertNotIn("cable_hops", report["source_verified_host_inputs"][0])
        described = format_output_routes(report, show_signal_traces=True)
        self.assertIn("ModularSynth/MorphVCO[1] -> HostAudio2[2]:in1", described)
        self.assertIn("cable #21: 3:out2 -> 4:in0", described)
        self.assertNotIn("cable #21:", format_output_routes(report))

    def test_multiple_generators_contributing_to_one_vca_sum_are_all_traced(self) -> None:
        self.patch["modules"].extend([
            module(3, "ModularSynth", "FMVoice"),
            module(4, "ModularSynth", "DualVCA"),
        ])
        self.patch["cables"] = [
            wire(10, 1, 4, 1, 0),  # MorphVCO -> VCA lane A
            wire(11, 3, 4, 0, 2),  # FMVoice -> VCA lane B
            wire(12, 4, 2, 2, 0),  # SUM -> HostAudio2 Left/M
        ]
        report = self.audit()
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(len(report["source_verified_host_inputs"]), 1)
        traces = report["source_verified_host_input_traces"]
        self.assertEqual([trace["module_id"] for trace in traces], [1, 3])
        self.assertEqual([[hop["cable_id"] for hop in trace["cable_hops"]]
                          for trace in traces], [[10, 12], [11, 12]])
        self.assertEqual([trace["via_module_ids"] for trace in traces],
                         [[1, 4], [3, 4]])
        self.assertIn("2 (includes distinct generators", format_output_routes(report))
        self.path.write_text(json.dumps(self.patch), encoding="utf-8")
        cli = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "patches" / "patch_audio_routes.py"),
             str(self.path), "--show-signal-traces"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertIn("cable #12: 4:out2 -> 2:in0", cli.stdout)

    def test_cv_cable_does_not_become_a_verified_trace_through_filter(self) -> None:
        self.patch["modules"].append(module(3, "ModularSynth", "StateFilter"))
        self.patch["cables"] = [
            wire(10, 1, 3, 0, 2),  # Resonance CV, not audio.
            wire(11, 3, 2, 0, 0),
        ]
        report = self.audit()
        self.assertTrue(report["ok"])
        self.assertEqual(report["source_verified_host_input_traces"], [])
        self.assertEqual(len(report["unverified_wired_host_inputs"]), 1)

    def test_stereo_gate_requires_both_source_verified_ports_on_each_host(self) -> None:
        script = ROOT / "tools" / "patches" / "patch_audio_routes.py"

        def call() -> subprocess.CompletedProcess[str]:
            self.path.write_text(json.dumps(self.patch), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(script), str(self.path),
                 "--require-source-verified-stereo"],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )

        self.assertEqual(call().returncode, 1)  # Only Left/M cabled.
        self.patch["cables"].append(wire(4, 1, 2, 1, 1))
        self.assertEqual(call().returncode, 0)
        self.patch["modules"].append(module(3, "Cardinal", "HostAudio2"))
        self.patch["cables"].append(wire(5, 1, 3, 0, 0))
        self.assertEqual(call().returncode, 1)  # Second host lacks Right.
        self.patch["cables"].append(wire(6, 1, 3, 1, 1))
        self.assertEqual(call().returncode, 0)
        self.patch["modules"].append(module(4, "ModularSynth", "Macro8"))
        self.patch["cables"][-1] = wire(6, 4, 3, 0, 1)
        self.assertEqual(call().returncode, 1)  # Right is a control signal.
        self.patch["modules"] = [module(4, "ModularSynth", "Macro8")]
        self.patch["cables"] = []
        self.assertEqual(call().returncode, 1)  # No host: never vacuous pass.

    def test_opaque_third_party_hop_remains_unverified(self) -> None:
        self.patch["modules"].append(module(3, "ThirdParty", "UnknownVCA"))
        self.patch["cables"] = [wire(11, 1, 3), wire(12, 3, 2)]
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["unrouted_first_party_generators"], [])
        self.assertEqual(result["source_verified_signal_routes"], [])
        self.assertEqual(result["unverified_first_party_signal_routes"], [
            {"module_id": 1, "model": "ModularSynth/MorphVCO"},
        ])

    def test_source_verified_route_gate_is_strict_and_opt_in(self) -> None:
        script = ROOT / "tools" / "patches" / "patch_audio_routes.py"
        self.path.write_text(json.dumps(self.patch), encoding="utf-8")

        def call(*flags: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, str(script), str(self.path), *flags],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )

        strong = "--require-source-verified-signal-route"
        self.assertEqual(call(strong).returncode, 0)
        self.patch["modules"].append(module(3, "ModularSynth", "StateFilter"))
        self.patch["cables"] = [wire(11, 1, 3, 0, 1), wire(12, 3, 2)]
        self.path.write_text(json.dumps(self.patch), encoding="utf-8")
        # Graph-only compatibility gate continues to accept this cable path.
        self.assertEqual(call("--require-generator-route").returncode, 0)
        self.assertEqual(call(strong).returncode, 1)
        report = json.loads(call(strong, "--json").stdout)[0]
        self.assertEqual(report["source_verified_signal_routes"], [])
        self.assertEqual(len(report["unverified_first_party_signal_routes"]), 1)



    def test_dual_vca_only_propagates_its_source_declared_audio_lanes(self) -> None:
        manifest = json.loads(
            (ROOT / "plugins" / "ModularSynth" / "plugin.json")
            .read_text(encoding="utf-8"))
        if not any(model["slug"] == "DualVCA"
                   for model in manifest.get("modules", [])):
            self.skipTest("DualVCA module source lands in another PR")
        self.patch["modules"].append(module(3, "ModularSynth", "DualVCA"))

        # Audio fed to lane A must NOT be treated as reaching lane B output.
        self.patch["cables"] = [wire(10, 1, 3, 0, 0), wire(11, 3, 2, 1, 0)]
        result = self.audit()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["source_verified_signal_routes"], [])
        self.assertEqual(len(result["unverified_first_party_signal_routes"]), 1)

        # A signal reaches both lane A output and summed output, but not B.
        for output_port in (0, 2):
            self.patch["cables"][1]["outputId"] = output_port
            result = self.audit()
            self.assertTrue(result["ok"], result["errors"])
            self.assertEqual(result["source_verified_signal_routes"][0]["via_module_ids"],
                             [1, 3])

        # Lane B input reaches B output.
        self.patch["cables"][0]["inputId"] = 2
        self.patch["cables"][1]["outputId"] = 1
        result = self.audit()
        self.assertEqual(len(result["source_verified_signal_routes"]), 1)

        # Gain CV without an audio input does not certify the signal chain.
        self.patch["cables"][0]["inputId"] = 1
        result = self.audit()
        self.assertEqual(result["source_verified_signal_routes"], [])


if __name__ == "__main__":
    unittest.main()
