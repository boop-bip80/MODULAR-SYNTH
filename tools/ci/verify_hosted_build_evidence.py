#!/usr/bin/env python3
"""Audit an exact GitHub Actions build's run/jobs/artifacts JSON, offline.

This is an *evidence* gate, not a host compatibility, signed-release or
production-readiness certificate. `core` proves only the named automated
Linux/Windows 64-bit build and LV2/VST bridge checks on one source commit;
`full` demands all 20 current matrix jobs and their published archives.

Export the GET responses for `/actions/runs/ID`, `/actions/runs/ID/jobs?per_page=100`
and `/actions/runs/ID/artifacts?per_page=100` to files before running this tool.
No GitHub credential, network access, file mutation or artifact execution occurs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_INPUT_BYTES = 4 * 1024 * 1024

CORE_JOBS = ("plugin-validation", "linux (x86_64)", "windows (win64)")
CORE_PLUGIN_STEPS = (
    "Build Cardinal (carla, deps and plugins)",
    "Build Cardinal (final build stage)",
    "Verify linked first-party collection",
    "Run Cardinal self-tests",
    "Validate LV2 ttl syntax",
    "Validate LV2 metadata and binaries",
    "Test LV2 plugin",
    "Test VST2 plugin",
    "Test VST3 plugin",
)
FULL_JOBS = CORE_JOBS + (
    "source-tarball", "lto", "headless", "sysdeps", "linux-x86_64-debug",
    "linux (i686)", "linux (aarch64)", "linux (armhf)", "linux (riscv64)",
    "windows (win32)", "macos", "wasm (simd)", "wasm (nosimd)",
    "mod-plugin-builder (darkglass-anagram, darkglass-anagram)",
    "mod-plugin-builder (modduo, modduo-static, MODDUO=true)",
    "mod-plugin-builder (modduox, modduox-static)",
    "mod-plugin-builder (moddwarf, moddwarf)",
)
assert len(FULL_JOBS) == 20 and len(set(FULL_JOBS)) == len(FULL_JOBS)

CORE_ARTIFACT_SUFFIXES = ("linux-x86_64", "win64")
FULL_ARTIFACT_SUFFIXES = CORE_ARTIFACT_SUFFIXES + (
    "source", "linux-x86_64-debug", "linux-i686", "linux-aarch64",
    "linux-armhf", "linux-riscv64", "win32", "macOS-universal",
    "wasm-simd", "wasm-nosimd", "darkglass-anagram", "modduo",
    "modduox", "moddwarf",
)


class EvidenceError(ValueError):
    """Input is not a well-formed, bounded snapshot of a GitHub API response."""


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise EvidenceError(f"duplicate JSON key {key!r}")
        obj[key] = value
    return obj


def read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
            raise EvidenceError(f"missing or oversized JSON evidence file: {path}")
        obj = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs,
                         parse_constant=lambda value: (_ for _ in ()).throw(
                             EvidenceError(f"non-JSON numeric constant: {value}")))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise EvidenceError(f"cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(obj, dict):
        raise EvidenceError(f"expected JSON object: {path}")
    return obj


def _integer(value: Any) -> bool:
    return type(value) is int and value > 0


def _by_name(items: Any, label: str, reasons: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        raise EvidenceError(f"{label} response requires a list")
    names: list[str] = []
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise EvidenceError(f"{label} contains an entry without a string name")
        name = item["name"]
        names.append(name)
        result[name] = item
    for name, count in sorted(Counter(names).items()):
        if count > 1:
            reasons.append(f"duplicate {label} name: {name}")
            result.pop(name, None)
    return result


def evaluate(run: dict[str, Any], jobs: dict[str, Any],
             artifacts: dict[str, Any], expected_sha: str,
             profile: str = "full") -> dict[str, Any]:
    """Return machine-readable, fail-closed results without making claims about DAWs."""
    if not SHA.fullmatch(expected_sha):
        raise EvidenceError("expected commit must be an exact lowercase 40-character SHA")
    if profile not in ("core", "full"):
        raise EvidenceError("profile must be core or full")
    if not _integer(run.get("id")):
        raise EvidenceError("workflow run must contain a positive integer id")
    if not _integer(run.get("run_attempt")):
        raise EvidenceError("workflow run must contain a positive integer run_attempt")
    if not isinstance(jobs, dict) or not isinstance(artifacts, dict):
        raise EvidenceError("jobs and artifacts responses must be objects")

    reasons: list[str] = []
    if run.get("head_sha") != expected_sha:
        reasons.append("workflow run head_sha does not match expected commit")
    if run.get("name") != "build":
        reasons.append("workflow run is not the expected build workflow")
    if run.get("path") != ".github/workflows/build.yml":
        reasons.append("workflow run path does not match build.yml")
    if run.get("status") != "completed":
        reasons.append("workflow run has not completed")
    if profile == "full" and run.get("conclusion") != "success":
        reasons.append("full build workflow did not complete successfully")

    job_names = _by_name(jobs.get("jobs"), "job", reasons)
    # A successful job with the expected name is not evidence for this build if
    # it was copied from another commit, run, or rerun attempt.
    for job in jobs["jobs"]:
        name = job["name"]
        if not _integer(job.get("run_id")) or job["run_id"] != run["id"]:
            reasons.append(f"job does not attest requested run: {name}")
        if job.get("head_sha") != expected_sha:
            reasons.append(f"job does not attest requested commit: {name}")
        if (not _integer(job.get("run_attempt"))
                or job["run_attempt"] != run["run_attempt"]):
            reasons.append(f"job does not attest requested run attempt: {name}")
    artifact_names = _by_name(artifacts.get("artifacts"), "artifact", reasons)
    declared = jobs.get("total_count")
    if type(declared) is not int or declared < len(jobs.get("jobs", [])):
        reasons.append("jobs total_count is missing or inconsistent")
    elif declared != len(jobs["jobs"]):
        reasons.append("job evidence is paginated/incomplete")
    artifact_total = artifacts.get("total_count")
    if artifact_total is not None:
        if type(artifact_total) is not int or artifact_total != len(artifacts["artifacts"]):
            reasons.append("artifact evidence is paginated/incomplete")

    needed_jobs = CORE_JOBS if profile == "core" else FULL_JOBS
    for name in needed_jobs:
        job = job_names.get(name)
        if job is None:
            reasons.append(f"required job missing: {name}")
        elif job.get("status") != "completed" or job.get("conclusion") != "success":
            reasons.append(f"required job not successful: {name}")

    plugin_job = job_names.get("plugin-validation")
    if plugin_job is not None:
        steps = plugin_job.get("steps")
        if not isinstance(steps, list):
            reasons.append("plugin-validation has no step evidence")
        else:
            step_names = _by_name(steps, "plugin-validation step", reasons)
            for name in CORE_PLUGIN_STEPS:
                step = step_names.get(name)
                if step is None or step.get("status") != "completed" or step.get("conclusion") != "success":
                    reasons.append(f"required plugin validation step not successful: {name}")

    needed_artifacts = (CORE_ARTIFACT_SUFFIXES if profile == "core"
                        else FULL_ARTIFACT_SUFFIXES)
    for suffix in needed_artifacts:
        name = f"MODULAR-SYNTH-{suffix}-{expected_sha[:8]}"
        item = artifact_names.get(name)
        if item is None:
            reasons.append(f"required build artifact missing: {name}")
            continue
        if not _integer(item.get("size_in_bytes")):
            reasons.append(f"artifact empty or invalid size: {name}")
        if item.get("expired") is not False:
            reasons.append(f"artifact expired or unknown expiry: {name}")
        if not isinstance(item.get("digest"), str) or not DIGEST.fullmatch(item["digest"]):
            reasons.append(f"artifact has no valid sha256 archive digest: {name}")
        linked = item.get("workflow_run")
        if (not isinstance(linked, dict) or linked.get("id") != run["id"]
                or linked.get("head_sha") != expected_sha):
            reasons.append(f"artifact does not attest the requested run/commit: {name}")

    return {
        "profile": profile,
        "expected_sha": expected_sha,
        "run_id": run["id"],
        "run_conclusion": run.get("conclusion"),
        "automated_evidence_complete": not reasons,
        "required_jobs": len(needed_jobs),
        "required_artifacts": len(needed_artifacts),
        "failures": sorted(set(reasons)),
        "scope_warning": (
            "Automated CI metadata only; does not verify per-DAW state reload, "
            "audio output, usability, signed installers or a production release."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-json", type=Path, required=True)
    parser.add_argument("--jobs-json", type=Path, required=True)
    parser.add_argument("--artifacts-json", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--profile", choices=("core", "full"), default="full")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 unless all required automated evidence passes")
    parser.add_argument("--json", action="store_true", help="emit only JSON result")
    args = parser.parse_args(argv)
    try:
        result = evaluate(read_json(args.run_json), read_json(args.jobs_json),
                          read_json(args.artifacts_json), args.expected_sha,
                          profile=args.profile)
    except EvidenceError as exc:
        print(f"Invalid hosted-build evidence: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        state = "PASS" if result["automated_evidence_complete"] else "INCOMPLETE"
        print(f"{state}: {args.profile} automated hosted-build evidence for "
              f"{args.expected_sha} (run {result['run_id']})")
        for failure in result["failures"]:
            print(f"  - {failure}")
        print(result["scope_warning"])
    return 1 if args.strict and not result["automated_evidence_complete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
