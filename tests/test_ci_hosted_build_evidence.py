"""Adversarial tests for source-commit-specific GitHub Actions evidence.

These are offline API-response fixtures, not a claim that a DAW was tested.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/ci/verify_hosted_build_evidence.py"
spec = importlib.util.spec_from_file_location("verify_hosted_build_evidence", SCRIPT)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

SHA = "a" * 40
RUN_ID = 42111770601
DIGEST = "sha256:" + "f" * 64


def snapshot() -> tuple[dict, dict, dict]:
    run = {
        "id": RUN_ID,
        "run_attempt": 1,
        "name": "build",
        "path": ".github/workflows/build.yml",
        "head_sha": SHA,
        "status": "completed",
        "conclusion": "success",
    }
    jobs = {
        "total_count": len(gate.FULL_JOBS),
        "jobs": [
            {"name": name, "run_id": RUN_ID, "head_sha": SHA, "run_attempt": 1,
             "status": "completed", "conclusion": "success",
             "steps": ([{"name": step, "status": "completed", "conclusion": "success"}
                        for step in gate.CORE_PLUGIN_STEPS]
                       if name == "plugin-validation" else [])}
            for name in gate.FULL_JOBS
        ],
    }
    artifacts = {
        "total_count": len(gate.FULL_ARTIFACT_SUFFIXES),
        "artifacts": [
            {
                "name": f"MODULAR-SYNTH-{suffix}-{SHA[:8]}",
                "size_in_bytes": 1024,
                "expired": False,
                "digest": DIGEST,
                "workflow_run": {"id": RUN_ID, "head_sha": SHA},
            }
            for suffix in gate.FULL_ARTIFACT_SUFFIXES
        ],
    }
    return run, jobs, artifacts


class HostedBuildEvidenceTests(unittest.TestCase):
    def valid(self, profile: str = "full") -> tuple[dict, dict, dict, dict]:
        run, jobs, artifacts = snapshot()
        report = gate.evaluate(run, jobs, artifacts, SHA, profile)
        self.assertTrue(report["automated_evidence_complete"], report["failures"])
        self.assertIn("does not verify per-DAW", report["scope_warning"])
        return run, jobs, artifacts, report

    def expect_incomplete(self, run: dict, jobs: dict, artifacts: dict,
                          phrase: str, profile: str = "full") -> None:
        report = gate.evaluate(run, jobs, artifacts, SHA, profile)
        self.assertFalse(report["automated_evidence_complete"])
        self.assertTrue(any(phrase in reason for reason in report["failures"]),
                        report["failures"])

    def test_full_and_core_valid_fixtures_are_explicitly_only_automated(self) -> None:
        self.valid("full")
        self.valid("core")

    def test_canceled_matrix_can_pass_scoped_core_but_not_full(self) -> None:
        run, jobs, artifacts = snapshot()
        run["conclusion"] = "cancelled"
        for name in ("macos", "mod-plugin-builder (modduox, modduox-static)"):
            next(j for j in jobs["jobs"] if j["name"] == name)["conclusion"] = "cancelled"
        self.expect_incomplete(run, jobs, artifacts, "full build workflow", "full")
        self.assertTrue(gate.evaluate(run, jobs, artifacts, SHA, "core")
                        ["automated_evidence_complete"])

    def test_head_sha_is_not_interchangeable_with_artifact_sha_prefix(self) -> None:
        run, jobs, artifacts = snapshot()
        run["head_sha"] = "b" * 40
        self.expect_incomplete(run, jobs, artifacts, "head_sha")
        run, jobs, artifacts = snapshot()
        artifacts["artifacts"][0]["workflow_run"]["head_sha"] = "b" * 40
        self.expect_incomplete(run, jobs, artifacts, "does not attest")

    def test_jobs_from_another_run_commit_or_attempt_fail_closed(self) -> None:
        for key, wrong, phrase in (
            ("run_id", RUN_ID + 1, "requested run"),
            ("run_id", None, "requested run"),
            ("head_sha", "b" * 40, "requested commit"),
            ("head_sha", None, "requested commit"),
            ("run_attempt", 2, "requested run attempt"),
            ("run_attempt", None, "requested run attempt"),
        ):
            with self.subTest(key=key, wrong=wrong):
                run, jobs, artifacts = snapshot()
                jobs["jobs"][0][key] = wrong
                self.expect_incomplete(run, jobs, artifacts, phrase)

    def test_rerun_attempt_must_match_across_all_jobs(self) -> None:
        run, jobs, artifacts = snapshot()
        run["run_attempt"] = 3
        for job in jobs["jobs"]:
            job["run_attempt"] = 3
        self.assertTrue(gate.evaluate(run, jobs, artifacts, SHA)["automated_evidence_complete"])
        jobs["jobs"][-1]["run_attempt"] = 2
        self.expect_incomplete(run, jobs, artifacts, "requested run attempt")

    def test_invalid_run_attempt_is_rejected(self) -> None:
        for invalid in (None, 0, True, "1"):
            with self.subTest(invalid=invalid):
                run, jobs, artifacts = snapshot()
                run["run_attempt"] = invalid
                with self.assertRaisesRegex(gate.EvidenceError, "run_attempt"):
                    gate.evaluate(run, jobs, artifacts, SHA)

    def test_run_identity_and_workflow_path_fail_closed(self) -> None:
        for key, wrong, phrase in (
            ("name", "quality", "expected build"),
            ("path", "another.yml", "build.yml"),
            ("status", "in_progress", "has not completed"),
            ("conclusion", "failure", "did not complete"),
        ):
            with self.subTest(key=key):
                run, jobs, artifacts = snapshot()
                run[key] = wrong
                self.expect_incomplete(run, jobs, artifacts, phrase)

    def test_all_required_job_outcomes_are_verified(self) -> None:
        for name in ("plugin-validation", "macos",
                     "mod-plugin-builder (modduox, modduox-static)"):
            with self.subTest(name=name):
                run, jobs, artifacts = snapshot()
                next(j for j in jobs["jobs"] if j["name"] == name)["conclusion"] = "failure"
                self.expect_incomplete(run, jobs, artifacts, f"not successful: {name}")

    def test_skipped_plugin_bridge_or_registry_check_is_not_success(self) -> None:
        for target in ("Verify linked first-party collection", "Run Cardinal self-tests",
                       "Test LV2 plugin", "Test VST2 plugin", "Test VST3 plugin"):
            with self.subTest(step=target):
                run, jobs, artifacts = snapshot()
                plugin = next(j for j in jobs["jobs"] if j["name"] == "plugin-validation")
                next(s for s in plugin["steps"] if s["name"] == target)["conclusion"] = "skipped"
                self.expect_incomplete(run, jobs, artifacts, target, "core")

    def test_missing_required_step_fails_even_if_job_says_success(self) -> None:
        run, jobs, artifacts = snapshot()
        plugin = next(j for j in jobs["jobs"] if j["name"] == "plugin-validation")
        plugin["steps"] = plugin["steps"][:-1]
        self.expect_incomplete(run, jobs, artifacts, "Test VST3 plugin")

    def test_missing_platform_job_or_archive_fails(self) -> None:
        run, jobs, artifacts = snapshot()
        jobs["jobs"] = [j for j in jobs["jobs"] if j["name"] != "windows (win64)"]
        jobs["total_count"] = len(jobs["jobs"])
        self.expect_incomplete(run, jobs, artifacts, "required job missing: windows (win64)", "core")
        run, jobs, artifacts = snapshot()
        artifacts["artifacts"] = artifacts["artifacts"][1:]
        artifacts["total_count"] = len(artifacts["artifacts"])
        self.expect_incomplete(run, jobs, artifacts, "artifact missing")

    def test_archive_checksum_size_expiry_and_run_linkage_fail(self) -> None:
        for key, value, phrase in (
            ("digest", "sha256:not-a-checksum", "valid sha256"),
            ("size_in_bytes", 0, "invalid size"),
            ("size_in_bytes", True, "invalid size"),
            ("expired", True, "expired"),
            ("expired", None, "expired"),
            ("workflow_run", {"id": 999, "head_sha": SHA}, "does not attest"),
        ):
            with self.subTest(key=key, value=value):
                run, jobs, artifacts = snapshot()
                artifacts["artifacts"][0][key] = value
                self.expect_incomplete(run, jobs, artifacts, phrase)

    def test_duplicate_jobs_artifacts_or_plugin_steps_fail(self) -> None:
        for category in ("job", "artifact", "plugin-validation step"):
            with self.subTest(category=category):
                run, jobs, artifacts = snapshot()
                if category == "job":
                    jobs["jobs"].append(copy.deepcopy(jobs["jobs"][0]))
                    jobs["total_count"] += 1
                elif category == "artifact":
                    artifacts["artifacts"].append(copy.deepcopy(artifacts["artifacts"][0]))
                    artifacts["total_count"] += 1
                else:
                    plugin = next(j for j in jobs["jobs"] if j["name"] == "plugin-validation")
                    plugin["steps"].append(copy.deepcopy(plugin["steps"][0]))
                self.expect_incomplete(run, jobs, artifacts, f"duplicate {category}")

    def test_incomplete_pagination_never_looks_like_full_evidence(self) -> None:
        run, jobs, artifacts = snapshot()
        jobs["total_count"] += 20
        self.expect_incomplete(run, jobs, artifacts, "paginated/incomplete")
        run, jobs, artifacts = snapshot()
        artifacts["total_count"] += 1
        self.expect_incomplete(run, jobs, artifacts, "paginated/incomplete")

    def test_invalid_contracts_fail_explicitly(self) -> None:
        run, jobs, artifacts = snapshot()
        for sha in ("abc", "A" * 40, "z" * 40):
            with self.assertRaises(gate.EvidenceError):
                gate.evaluate(run, jobs, artifacts, sha)
        with self.assertRaises(gate.EvidenceError):
            gate.evaluate(run, jobs, artifacts, SHA, "maybe")
        run["id"] = True
        with self.assertRaises(gate.EvidenceError):
            gate.evaluate(run, jobs, artifacts, SHA)

    def test_bad_response_types_fail_explicitly(self) -> None:
        run, jobs, artifacts = snapshot()
        for payload in (None, {}, 1):
            with self.subTest(payload=payload):
                with self.assertRaises(gate.EvidenceError):
                    gate.evaluate(run, {"jobs": payload}, artifacts, SHA)
                with self.assertRaises(gate.EvidenceError):
                    gate.evaluate(run, jobs, {"artifacts": payload}, SHA)

    def test_cli_strict_fail_and_json_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run, jobs, artifacts = snapshot()
            paths = [root / "run.json", root / "jobs.json", root / "artifacts.json"]
            for path, data in zip(paths, (run, jobs, artifacts), strict=True):
                path.write_text(json.dumps(data), encoding="utf-8")
            args = [sys.executable, "-B", str(SCRIPT), "--run-json", str(paths[0]),
                    "--jobs-json", str(paths[1]), "--artifacts-json", str(paths[2]),
                    "--expected-sha", SHA, "--profile", "full", "--strict", "--json"]
            ok = subprocess.run(args, capture_output=True, text=True, check=False)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertTrue(json.loads(ok.stdout)["automated_evidence_complete"])
            run["conclusion"] = "cancelled"
            paths[0].write_text(json.dumps(run), encoding="utf-8")
            failed = subprocess.run(args, capture_output=True, text=True, check=False)
            self.assertEqual(failed.returncode, 1)
            self.assertFalse(json.loads(failed.stdout)["automated_evidence_complete"])
            unstrict = subprocess.run(args[:-2] + ["--json"], capture_output=True,
                                      text=True, check=False)
            self.assertEqual(unstrict.returncode, 0)

    def test_json_reader_rejects_duplicate_keys_nonfinite_and_oversize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            for payload in ('{"id":1,"id":2}', '{"x":NaN}', '[]', 'not JSON',
                            '[' * 1100 + '0' + ']' * 1100):
                with self.subTest(payload=payload):
                    path.write_text(payload, encoding="utf-8")
                    with self.assertRaises(gate.EvidenceError):
                        gate.read_json(path)
            path.write_bytes(b" " * (gate.MAX_INPUT_BYTES + 1))
            with self.assertRaises(gate.EvidenceError):
                gate.read_json(path)


if __name__ == "__main__":
    unittest.main()
