# Hosted build evidence: exact-run audit

`tools/ci/verify_hosted_build_evidence.py` evaluates saved GitHub Actions API
responses offline. It deliberately distinguishes **automated CI metadata** from
host, audio, hardware, or release readiness evidence.

Collect all three GitHub REST responses from the **same** workflow run:

- `GET /repos/OWNER/REPO/actions/runs/RUN_ID`
- `GET /repos/OWNER/REPO/actions/runs/RUN_ID/jobs?per_page=100`
- `GET /repos/OWNER/REPO/actions/runs/RUN_ID/artifacts?per_page=100`

Save their JSON objects as `run.json`, `jobs.json`, and `artifacts.json`, ensuring
all pages are represented. Then run:

```sh
python3 tools/ci/verify_hosted_build_evidence.py \
  --run-json run.json --jobs-json jobs.json --artifacts-json artifacts.json \
  --expected-sha "$EXPECTED_COMMIT_SHA" --profile full --strict --json
```

An automated PASS requires the expected workflow and exact commit, the required
successful jobs and validation steps, and nonempty, unexpired, SHA-256-tagged
artifact metadata linked to that run. Each job must also identify that run's
`id`, `head_sha`, and **`run_attempt`**. A success copied from another run,
commit, or rerun attempt cannot satisfy the evidence gate, even if its job name
and outcome match. Missing provenance fails closed. The `core` profile checks a
smaller named subset; it does not establish success of the full build matrix.

This is **not** an independent verification of downloaded archive bytes or
the contents of installed binaries. The GitHub API `digest` is an attestation
recorded in artifact metadata; verify hashes against downloaded archives
separately if distributing them. Neither profile proves that a DAW loaded the
plugins, emitted audible output, recalled state, or passed hardware testing.
