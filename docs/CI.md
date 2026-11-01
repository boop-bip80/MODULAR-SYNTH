# Continuous integration and release verification

This fork inherits the substantial upstream Cardinal build matrix. It also has a fast quality gate for the original MODULAR-SYNTH additions.

## Workflow policy

| Workflow | Automatic triggers | Manual trigger | Purpose |
| --- | --- | --- | --- |
| `quality-baseline.yml` | Pull requests and pushes to `main` | Yes | Fast repository integrity, Module Forge generator tests, and standalone Morph VCO DSP compile/smoke |
| `build.yml` | Pushes to `main` (except documentation-only changes) and all tag pushes | Yes | Full cross-platform builds, plugin validation, platform packaging, release uploads |
| `irc.yml` | None | Yes, but its upstream-only job is skipped on this fork | Prevent derivative activity from posting announcements to Cardinal's upstream IRC channel |

Previously, the full build workflow ran on every feature-branch push **and** its associated pull request. This produced duplicate heavyweight matrices for one change. Full matrices now run only for integration/release/manual verification, while the quality gate remains available on every PR.

## Build matrix scope

The upstream-derived `build.yml` keeps its existing jobs intact: Linux cross-builds, Linux debug, macOS, Windows, MOD hardware builds, WebAssembly, headless, LTO, system dependency builds, source tarball, and plugin validation. Workflow changes should not silently delete platforms or plugin formats.

Superseded `main` push runs are automatically cancelled within the same Git ref. Release tag builds are **never** automatically cancelled. A manual run uses a unique concurrency key so it is not interrupted by an ordinary push.

The release-producing jobs alone receive GitHub token `contents: write` permission; all other jobs remain read-only. No repository secrets or paid external services are required by these changes.

The full matrix ignores pushes that change only Markdown/documentation files, to avoid rebuilding every platform for wording-only edits. Every tag push can still trigger a full release build, regardless of changed paths.

## Run the fast gate locally

From a checkout with Python 3 and a C++17 compiler:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover -s tools/module-forge -p 'test_*.py' -v
c++ -std=c++17 -O2 -Wall -Wextra -Werror tests/morphvco_dsp_smoke.cpp -o /tmp/morphvco_dsp_smoke
/tmp/morphvco_dsp_smoke
```

The DSP smoke binary is independent of JUCE/VCV Rack libraries, so it can catch defects in the original oscillator's pure DSP core quickly.

## Manually request a full build

1. Open the repository's **Actions** tab.
2. Choose the **build** workflow.
3. Select **Run workflow** and the branch or tag you want to verify.
4. Review every required job result and download the artifacts from the successful run.

For releases, push the intended version tag and inspect all release jobs and artifacts. An artifact or a GitHub release must not be described as verified until its corresponding workflow has actually completed successfully.

## What passing means

- **Fast quality success:** manifests, patch graphs, Module Forge tests, and the standalone oscillator DSP smoke meet their test assertions.
- **Full build success:** the cross-platform jobs that executed passed compilation and packaging checks.
- **Audio-host production readiness:** still requires real DAW loading, live MIDI/audio, project save/restore, audio regression, performance, and UI validation; it is not established by source-only tests.

A queued, cancelled, skipped, or not-yet-run job is **not** evidence of a successful build.

## Maintenance considerations

The `build.yml` matrix is expensive because it checks out many git submodules and builds multiple architectures. New PRs should rely on fast tests for early feedback; maintainers should request full builds when integration risk warrants them. When adding a new standalone DSP test or module scaffolder validation, put its discoverable test under `tests/test_*.py` or `tools/module-forge/test_*.py`, or add an explicit compile/smoke command to the fast workflow.

These trigger and concurrency changes do not retroactively cancel runs queued before they were merged. Review old queued runs separately if they continue consuming runner capacity.
