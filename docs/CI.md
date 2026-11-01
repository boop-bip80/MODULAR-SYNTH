# Continuous integration and release verification

This fork inherits the substantial upstream Cardinal build matrix. It also has a fast quality gate for the original MODULAR-SYNTH additions.

## Workflow policy

| Workflow | Automatic triggers | Manual trigger | Purpose |
| --- | --- | --- | --- |
| `quality-baseline.yml` | Pull requests and pushes to `main` | Yes | Fast repository/patch tests, offline submodule preflight, Module Forge and Instrument Builder suites, and standalone DSP compile/smoke tests (optimization and runtime-probed sanitizers) |
| `build.yml` | Pushes to `main` (except documentation-only changes) and all tag pushes | Yes | Full cross-platform builds, plugin validation, platform packaging, release uploads |
| `irc.yml` | None | Yes, but its upstream-only job is skipped on this fork | Prevent derivative activity from posting announcements to Cardinal's upstream IRC channel |

Previously, the full build workflow ran on every feature-branch push **and** its associated pull request. This produced duplicate heavyweight matrices for one change. Full matrices now run only for integration/release/manual verification, while the quality gate remains available on every PR.

The [fast workflow](../.github/workflows/quality-baseline.yml) directly discovers `tools/instrument-builder/test_*.py` alongside repository and Module Forge tests ([PR #59](https://github.com/boop-bip80/MODULAR-SYNTH/pull/59)). In an independently executed **local source run on exact merged [`4f3ba5af`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/4f3ba5afa9d7e6b2196560b49955fe0617278045)**, **205 repository + 40 Forge + 56 Instrument Builder = 301/301 Python tests passed**; nine standalone DSP suites passed **36/36 compiled-and-executed profiles including UBSan**. Combined ASan+UBSan was unavailable at runtime, so this is **not an ASan pass**. These counts are **local evidence, not a claim that a hosted Actions run or the full build matrix succeeded**.

**Hosted-status snapshot (2026-11-01, exact `4f3ba5af`):** the [source-quality run](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41357736067) was **queued with zero executed steps**, and the [full-build run](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41357736009) had **20 queued jobs and zero executed steps**. Prior superseded runs were cancelled by concurrency policy; cancellation is not evidence of failed compilation. These historical statuses must be rechecked before any release decision.

## Build matrix scope

**Observed external checkout blocker (November 1, 2026):** Several full-build jobs failed before compilation because the nested `src/Rack/dep/speexdsp` GitLab repository returned HTTP 502/504. The official `xiph/speexdsp` GitHub mirror contains the exact pinned commit `27ddf98b627ab425d5337b1a0d8b80d7528f9b30`. The build workflow now applies a temporary Git URL rewrite for that single source using `GIT_CONFIG_*`; it does not alter the pinned source revision. Every full-build job now verifies Git's URL resolution *before* recursive checkout, while `tests/test_ci_git_mirror.py` checks the declared environment configuration and confirms the Gitlink index is unchanged. These checks require no network access; the mirror's availability and a full hosted build remain unverified until Actions completes.

**Observed PawPaw dependency download failure (November 1, 2026):** An older Linux x86_64 job reached `Build extra dependencies` but could not fetch FLAC 1.5.0: `downloads.xiph.org` ended the TLS connection unexpectedly, and the PawPaw `kx.studio` fallback presented a certificate that did not match its hostname. The Linux, macOS, WebAssembly, and Windows cross-build jobs now run `.github/workflows/scripts/seed-pawpaw-flac.sh` before `bootstrap-cardinal.sh`. This seeds the *exact* PawPaw cache entry (`$HOME/PawPawBuilds/downloads/flac-1.5.0.tar.xz`) from the [official Xiph GitHub release](https://github.com/xiph/flac/releases/tag/1.5.0), verifies its published SHA-256 (`f2c1c76592a82ffff8413ba3c4a1299b6c7ab06c734dee03fd88630485c2b920`), and rejects partial or altered downloads. PawPaw's gitlink and source remain pinned; `tests/test_ci_pawpaw_flac.py` checks the workflow ordering, published URL/digest, and corruption rejection without network access. This is a mitigation based on the historical job log, **not** evidence of a successful new hosted build.

**Observed Windows installer failure (November 1, 2026):** An older `win32` packaging job downloaded an 11,639-byte response from the mutable `jrsoftware.org/download.php/is.exe` URL into a file named `innosetup-6.0.5.exe`; Wine then rejected it as an unsupported executable (exit 47). `utils/create-windows-installer.sh` now calls `utils/fetch-inno-setup.sh` to fetch the **actual version 6.0.5** from the [official immutable jrsoftware release](https://github.com/jrsoftware/issrc/releases/tag/is-6_0_5), using the publisher's SHA-256 (`ae6823b523df87e9441789e51845434e4e0e70aac0b88afe80f94f20f4b98acb`). An intact cached installer is reused; an invalid cache entry is replaced only after a complete, hash-verified download. `tests/test_ci_innosetup.py` checks cache recovery, failed downloads, and checksum rejection offline. This corrects a verified download defect, **not** proof that Wine packaging or a full Windows build passes on hosted runners.

**macOS release-tag package gate (PR [#65](https://github.com/boop-bip80/MODULAR-SYNTH/pull/65)):** The macOS job is **not** a matrix job; its old Release step incorrectly checked `matrix.debug == '0'` and could silently skip an upload. The tag-only GitHub Release step now checks `startsWith(github.ref, 'refs/tags/')` without that matrix condition. On a tag, `actions/upload-artifact` fails if no matching `*.pkg` exists and `softprops/action-gh-release` uses `fail_on_unmatched_files: true`. On an ordinary main push, a cache-warming job may legitimately skip package creation and gets a warning instead. [Source test](../tests/test_ci_macos_release.py) verifies the YAML conditions; **no macOS `.pkg`, signed/notarized installer, hosted package step or tag release has yet passed**.

The upstream-derived `build.yml` keeps its existing jobs intact: Linux cross-builds, Linux debug, macOS, Windows, MOD hardware builds, WebAssembly, headless, LTO, system dependency builds, source tarball, and plugin validation. Workflow changes should not silently delete platforms or plugin formats.

Superseded `main` push runs are automatically cancelled within the same Git ref. Release tag builds are **never** automatically cancelled. A manual run uses a unique concurrency key so it is not interrupted by an ordinary push.

The release-producing jobs alone receive GitHub token `contents: write` permission; all other jobs remain read-only. No repository secrets or paid external services are required by these changes.

The full matrix ignores pushes that change only Markdown/documentation files, to avoid rebuilding every platform for wording-only edits. Every tag push can still trigger a full release build, regardless of changed paths.

## Offline submodule and dependency preflight

Before a costly recursive checkout or full build, run:

```sh
python3 -B tools/ci/preflight_submodules.py
```

This **does not contact the network**. It compares every root `.gitmodules` declaration with the committed Gitlink tree, checks initialized submodule HEADs against their exact pinned SHAs, and verifies that Git resolves the GitLab SpeexDSP URL to the official Xiph mirror using `build.yml`'s `GIT_CONFIG_*` environment. When the pinned Rack checkout is initialized, it also checks Rack's nested `dep/speexdsp` Gitlink, URL, and local checkout. Missing local submodule downloads are reported as notes in the default mode so the fast source gate works without fetching a large dependency tree.

For a workspace that should already contain **all declared top-level submodules plus Rack's nested SpeexDSP dependency**, run `python3 -B tools/ci/preflight_submodules.py --require-populated`. Strict mode fails if any of those Gitlinks are uninitialized or checked out at the wrong commit. It **does not recursively inspect every other plugin's nested dependencies**; those still require normal recursive checkout and full build validation. Both modes are strictly local: they cannot prove a remote host is reachable or an application build succeeds. The CLI has network-free tests under `tests/test_ci_submodule_preflight.py`.

## Run the fast gate locally

From a checkout with Python 3 and a C++17 compiler:

```sh
python3 -B tools/ci/preflight_submodules.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover -s tools/module-forge -p 'test_*.py' -v
python3 -B -m unittest discover -s tools/instrument-builder -p 'test_*.py' -v
python3 -B tests/run_dsp_tests.py --sanitize=auto
```

The auto-discovered [five-original wrapper smoke](../tests/test_rack_wrapper_smoke.py) builds actual first-party `.cpp` wrappers as HEADLESS translation units and exercises basic processing/state against **`tests/rack_stub`**, a deliberately small fake Rack API. [Module Forge's generated wrapper tests](../tools/module-forge/test_generated_wrappers.py) compile both fresh oscillator/effect starters using the **same stub** under ordinary and aggressive optimization modes. These are valuable additional C++ source checks, **not real Rack SDK headers, binary ABI compatibility, GUI builds, plugin packaging, DAW loading or audio auditions**.

The DSP runner discovers only top-level `tests/*_dsp_smoke.cpp` and `tests/*_dsp_test.cpp` entrypoints, excluding names containing `rack` or `wrapper`. Each test is compiled and executed in three profiles: strict `-O2 -Wall -Wextra -Werror`, production-style `-O3 -ffast-math -fno-finite-math-only`, and aggressive `-O3 -ffast-math` (the last deliberately exposes finite-math-only assumptions). All profiles use C++17 and warnings-as-errors. Tests must have their own `main()` and be independent of JUCE/VCV Rack. Temporary executables are automatically removed.

Use `python3 -B tests/run_dsp_tests.py --list` to inspect discovered tests without compiling. The runner fails when none are found; source and runtime failures are printed separately.

The **optional sanitizer profile** is enabled by `--sanitize=auto` (used by the fast Actions workflow). Before any DSP test runs under sanitizers, it compiles *and executes* a tiny runtime probe. It prefers AddressSanitizer plus UndefinedBehaviorSanitizer with `-O1 -g -fno-omit-frame-pointer -fno-sanitize-recover=all`; if that probe cannot run on the compiler/host, it explicitly reports the failure and tries UBSan-only. `--sanitize=ubsan` or `--sanitize=asan-ubsan` requires a specific profile, and an unavailable sanitizer produces a nonzero result—not a silent PASS. Once selected, **an actual DSP sanitizer failure is never treated as a reason to fall back**. Omitting `--sanitize` preserves the original three profiles. This sanitizer pass catches many C++ memory/undefined-behavior defects, but cannot substitute for Rack-wrapper, audio-host, or full cross-platform builds.

## Manually request a full build

1. Open the repository's **Actions** tab.
2. Choose the **build** workflow.
3. Select **Run workflow** and the branch or tag you want to verify.
4. Review every required job result and download the artifacts from the successful run.

For releases, push the intended version tag and inspect all release jobs and artifacts. An artifact or a GitHub release must not be described as verified until its corresponding workflow has actually completed successfully.

For a **macOS tagged release**, additionally confirm that the exact-tag run **produced and uploaded a real `.pkg`**, its contents match the intended fork revision, a maintainer actually installed it on macOS, and the resulting plugin/standalone passed appropriate host and patch-reopen tests. The new missing-package failure checks are a safeguard against silently absent files, **not proof that such a package exists**. Repeat analogous installed-artifact QA for Linux/Windows targets; never substitute upstream Cardinal release files.

## What passing means

- **Fast quality success:** manifest and Gitlink checks, offline SpeexDSP mirror preflight, repository/patch tests (including a test-shim wrapper smoke), Module Forge generated-wrapper/shim and Instrument Builder suites, and discovered standalone DSP smokes meet their assertions.
- **Full build success:** the cross-platform jobs that executed passed compilation and packaging checks.
- **Audio-host production readiness:** still requires real DAW loading, live MIDI/audio, project save/restore, audio regression, performance, and UI validation; it is not established by source-only tests.

A queued, cancelled, skipped, or not-yet-run job is **not** evidence of a successful build.

## Maintenance considerations

The `build.yml` matrix is expensive because it checks out many git submodules and builds multiple architectures. New PRs should rely on fast tests for early feedback; maintainers should request full builds when integration risk warrants them. When adding a new standalone DSP test, name it `tests/<module>_dsp_smoke.cpp` or `tests/<module>_dsp_test.cpp`; it will be automatically compiled and run in all three profiles. Keep Rack/DPF wrapper tests outside this naming convention. Python tests are automatically discovered under `tests/test_*.py`, `tools/module-forge/test_*.py`, or `tools/instrument-builder/test_*.py`.

These trigger and concurrency changes do not retroactively cancel runs queued before they were merged. Review old queued runs separately if they continue consuming runner capacity.
