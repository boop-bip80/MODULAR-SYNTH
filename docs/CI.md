# Continuous integration and release verification

This fork inherits the substantial upstream Cardinal build matrix. It also has a fast quality gate for the original MODULAR-SYNTH additions.

## Workflow policy

| Workflow | Automatic triggers | Manual trigger | Purpose |
| --- | --- | --- | --- |
| `quality-baseline.yml` | Pull requests and pushes to `main` | Yes | Fast repository/patch tests, offline submodule preflight, Module Forge and Instrument Builder suites, and standalone DSP compile/smoke tests (optimization and runtime-probed sanitizers) |
| `real-rack-headers.yml` | PRs and `main` pushes changing original wrapper source, Rack/DPF pins or the check itself | Yes | Seven original HEADLESS C++ translation-unit syntax checks against exact pinned **real** Rack/DPF/Jansson headers; no linking or host execution |
| `build.yml` | Pushes to `main` (except documentation-only changes) and all tag pushes | Yes | Full cross-platform builds, plugin validation, platform packaging, release uploads |
| `irc.yml` | None | Yes, but its upstream-only job is skipped on this fork | Prevent derivative activity from posting announcements to Cardinal's upstream IRC channel |

Previously, the full build workflow ran on every feature-branch push **and** its associated pull request. This produced duplicate heavyweight matrices for one change. Full matrices now run only for integration/release/manual verification, while the quality gate remains available on every PR.

The [fast workflow](../.github/workflows/quality-baseline.yml) directly discovers `tools/instrument-builder/test_*.py` alongside repository and Module Forge tests ([PR #59](https://github.com/boop-bip80/MODULAR-SYNTH/pull/59)). In an independently executed **local source run on exact merged [`3fbda096`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/3fbda096db2165dcc681abd8c210892624ad7b92)** on 2026-11-02, **219 repository + 40 Forge + 65 Instrument Builder = 324/324 Python tests passed**; ten standalone DSP suites passed **40/40 compiled-and-executed profiles including UBSan**. Combined ASan+UBSan was unavailable at runtime, so this is **not an ASan pass**. A separate pinned-real-header gate passed **6/6 local HEADLESS `-fsyntax-only` checks** (not plugin linking). These counts are **local evidence, not a claim that a hosted Actions run or the full build matrix succeeded**.

**Hosted-status snapshot (2026-11-02 00:23 UTC, exact `3fbda096`):** the [source-quality run](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41366740187) had **one queued job and zero executed steps**; the [real Rack header run](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41366740367) had **one queued job and zero executed steps**; and the [full-build run](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41366740224) had **20 queued jobs and zero executed steps**. These exact-run observations are **pending, not passing**. No fork-owned release was listed at the same check. Prior superseded runs may be cancelled by concurrency policy; cancellation is not evidence of failed compilation. Recheck hosted jobs and release contents before any release decision.

**Latest integrated offline source snapshot ([`87d27f3`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/87d27f341b56e3229a7a98ac6b73bf5f63510aa3)):** **265 repository + 51 Module Forge + 93 Instrument Builder = 409/409 Python tests passed**, plus **48/48 compiled and executed standalone DSP profiles**, including UBSan. The opt-in HostAudio2 and directed first-party generator route audits passed all 15 factory examples; seven source-panel SVGs/97 conservative widget centers and the strict first-party provenance check passed. The local ASan+UBSan runtime probe failed under ptrace, so do not infer an ASan pass. At this exact code merge, the [source-quality run](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41386608738), [seven-original real-header run](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41386608694) and [full build](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41386608744) were all **queued, not completed**; these source passes do not establish linked binaries, host audio, DAW automation, plugin UI or a release. A subsequent independent local genuine-header check passed **7/7 originals plus 2/2 generated Module Forge starters** on this exact code, while the hosted real-header workflow remained unexecuted at the source snapshot.

**Previous independent source snapshot ([`060a2a83`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/060a2a83b6803e61e63eabf9bcbf631eb488c5c2)):** 257 repository + 49 Forge + 85 Instrument Builder = **391/391 Python tests**, plus **48/48 standalone C++ DSP compile-and-execute profiles** (12 suites, including UBSan). The source audit also checked 15 example output routes, seven SVG panels and strict license metadata. Combined ASan+UBSan could not run under the local environment; this is **not** an AddressSanitizer result. The seven-wrapper real Rack-header workflow is configured, but the previous **6/6** pinned-header syntax pass remains historical and **FMVoice's seventh real-header check has not been independently executed**. These source results do not substitute for the queued full linked builds, plugin binaries or DAW host tests.

## Cold-cache build and release-asset safeguards

The inherited full matrix used to run key compile/package steps **only after a cache hit**. On a clean runner, macOS, Windows, WebAssembly and MOD hardware jobs could bootstrap dependencies yet skip the actual build or packing; a tagged Windows build would then fail the artifact gate, and other jobs could lack release assets. Caches are now performance optimizations rather than prerequisites: build and packaging steps run after dependency bootstrap on both cache hits and misses. The MOD hardware toolchain bootstrap remains cache-miss-only because it is intended to populate the cache.

The inherited macOS packaging script produces `Cardinal-macOS.pkg`; the workflow now verifies that exact nonempty output before renaming it to a fork-prefixed artifact. Linux and WebAssembly tagged releases also reject missing uploaded files and unmatched release globs, joining the existing Windows and macOS checks. Offline regression checks in `tests/test_ci_cold_cache.py` pin these workflow contracts. These changes remove source-level release blockers, **not** the need for a real hosted build, artifact inspection, plugin validation, DAW audition, signing/notarization decisions or an actual fork-owned release.

## Build matrix scope

**Observed external checkout blocker (November 1, 2026):** Several full-build jobs failed before compilation because the nested `src/Rack/dep/speexdsp` GitLab repository returned HTTP 502/504. The official `xiph/speexdsp` GitHub mirror contains the exact pinned commit `27ddf98b627ab425d5337b1a0d8b80d7528f9b30`. The build workflow now applies a temporary Git URL rewrite for that single source using `GIT_CONFIG_*`; it does not alter the pinned source revision. Every full-build job now verifies Git's URL resolution *before* recursive checkout, while `tests/test_ci_git_mirror.py` checks the declared environment configuration and confirms the Gitlink index is unchanged. These checks require no network access; the mirror's availability and a full hosted build remain unverified until Actions completes.

**Observed PawPaw dependency download failure (November 1, 2026):** An older Linux x86_64 job reached `Build extra dependencies` but could not fetch FLAC 1.5.0: `downloads.xiph.org` ended the TLS connection unexpectedly, and the PawPaw `kx.studio` fallback presented a certificate that did not match its hostname. The Linux, macOS, WebAssembly, and Windows cross-build jobs now run `.github/workflows/scripts/seed-pawpaw-flac.sh` before `bootstrap-cardinal.sh`. This seeds the *exact* PawPaw cache entry (`$HOME/PawPawBuilds/downloads/flac-1.5.0.tar.xz`) from the [official Xiph GitHub release](https://github.com/xiph/flac/releases/tag/1.5.0), verifies its published SHA-256 (`f2c1c76592a82ffff8413ba3c4a1299b6c7ab06c734dee03fd88630485c2b920`), and rejects partial or altered downloads. PawPaw's gitlink and source remain pinned; `tests/test_ci_pawpaw_flac.py` checks the workflow ordering, published URL/digest, and corruption rejection without network access. This is a mitigation based on the historical job log, **not** evidence of a successful new hosted build.

**Observed Windows installer failure (November 1, 2026):** An older `win32` packaging job downloaded an 11,639-byte response from the mutable `jrsoftware.org/download.php/is.exe` URL into a file named `innosetup-6.0.5.exe`; Wine then rejected it as an unsupported executable (exit 47). `utils/create-windows-installer.sh` now calls `utils/fetch-inno-setup.sh` to fetch the **actual version 6.0.5** from the [official immutable jrsoftware release](https://github.com/jrsoftware/issrc/releases/tag/is-6_0_5), using the publisher's SHA-256 (`ae6823b523df87e9441789e51845434e4e0e70aac0b88afe80f94f20f4b98acb`). An intact cached installer is reused; an invalid cache entry is replaced only after a complete, hash-verified download. `tests/test_ci_innosetup.py` checks cache recovery, failed downloads, and checksum rejection offline. This corrects a verified download defect, **not** proof that Wine packaging or a full Windows build passes on hosted runners.

**Windows release ZIP/installer gate:** Windows packaging creates fork-named ZIPs such as `MODULAR-SYNTH-win64-v26.02.zip`, while Inno Setup outputs a target-specific `Cardinal-win64-<version>-installer.exe`. The old upload and Release globs expected `Cardinal-*.zip`, so a packaged fork ZIP would be excluded. Tagged Windows builds now require a nonempty ZIP for the exact tag and exactly one nonempty matching-target installer before upload, and the upload/release globs include both correct filename families with missing-asset failures. Ordinary main cache-warming builds may warn if packaging was skipped. The offline [regression test](../tests/test_ci_windows_release_assets.py) checks the gate and source wiring; **this does not establish a successful hosted build, shipped release, or installed Windows plugin**.

**macOS release-tag package gate (PR [#65](https://github.com/boop-bip80/MODULAR-SYNTH/pull/65)):** The macOS job is **not** a matrix job; its old Release step incorrectly checked `matrix.debug == '0'` and could silently skip an upload. The tag-only GitHub Release step now checks `startsWith(github.ref, 'refs/tags/')` without that matrix condition. On a tag, `actions/upload-artifact` fails if no matching `*.pkg` exists and `softprops/action-gh-release` uses `fail_on_unmatched_files: true`. On an ordinary main push, a cache-warming job may legitimately skip package creation and gets a warning instead. [Source test](../tests/test_ci_macos_release.py) verifies the YAML conditions; **no macOS `.pkg`, signed/notarized installer, hosted package step or tag release has yet passed**.

The upstream-derived `build.yml` keeps its existing jobs intact: Linux cross-builds, Linux debug, macOS, Windows, MOD hardware builds, WebAssembly, headless, LTO, system dependency builds, source tarball, and plugin validation. Workflow changes should not silently delete platforms or plugin formats.

Superseded `main` push runs are automatically cancelled within the same Git ref. Release tag builds are **never** automatically cancelled. A manual run uses a unique concurrency key so it is not interrupted by an ordinary push.

The release-producing jobs alone receive GitHub token `contents: write` permission; all other jobs remain read-only. No repository secrets or paid external services are required by these changes.

The full matrix ignores pushes that change only Markdown/documentation files, to avoid rebuilding every platform for wording-only edits. Every tag push can still trigger a full release build, regardless of changed paths.

## Source archive release safeguards

The inherited source-tarball job builds two archives in the checkout's parent
directory: `cardinal-<version>.tar.xz` and `cardinal+deps-<version>.tar.xz`,
where `<version>` comes from `make -s version`. A new pre-upload check
requires **both** files to be nonempty and verifies that GNU tar can list their
contents using the Makefile's existing `--lzma` encoder. It also checks that
every listed member is inside the expected `cardinal-<version>/` archive
root, rejects `..` traversal components, and requires the license, README,
Makefile, original-module manifest, shared plugin header, and the **seven
registered original modules' C++ wrappers, DSP headers, and SVG panels**
(including FMVoice) in **both** archives. The offline test compares the
required slug list with `plugins/ModularSynth/plugin.json` so a future
registration change cannot silently bypass the gate. This catches
valid-but-incomplete or mis-versioned archives; it is a narrow first-party
source inventory, **not** a complete third-party-license audit.

Tag artifact uploads now fail if no files match, and the GitHub Release step uses a **single**
parent-relative file pattern and fails when it matches nothing. The one-pattern
contract matters because `softprops/action-gh-release` rejects each unmatched
pattern individually; the old three alternative `/home/runner` path depths
would cause false failures if used with strict matching. [Offline release-gate tests](../tests/test_ci_source_tarball.py)
exercise successful archive validation and rejection of missing, empty, corrupt,
mis-rooted, incomplete and unsafe-version inputs.

**Caveat:** The upstream Makefile uses GNU tar `--lzma` despite the
`.tar.xz` filename extension; the guard deliberately tests the *current
encoding*, not a claim of standard xz encoding. A later archive-format
migration needs its own compatibility review. These safeguards are source
and offline-test evidence only: no latest-main full build, published tarball,
download validation or fork-owned Release is established by them.

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
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover -s tools/module-forge -p 'test_*.py' -v
python3 -B -m unittest discover -s tools/instrument-builder -p 'test_*.py' -v
python3 -B tests/run_dsp_tests.py --sanitize=auto
```

## Real Rack header compatibility preflight

[`tools/ci/check_real_rack_headers.py`](../tools/ci/check_real_rack_headers.py)
adds a **separate, narrower Linux source compatibility signal** beyond the
`tests/rack_stub` test double. It parses the actual seven
`plugins/ModularSynth/src/*.cpp` translation units individually with the
production `pluginInstance` alias, `HEADLESS` and `USING_CARDINAL_NOT_RACK`
definitions, actual pinned Rack/DPF API headers, and authentic dependency
headers. It checks **exact Gitlink revisions** of Rack, DPF and all six
required nested Rack submodules before compiling. It never fetches sources,
installs packages, or checks in generated dependency headers itself.

From a Linux source checkout, without cloning all other plugin submodules:

```sh
git submodule update --init --depth 1 src/Rack dpf
git -C src/Rack submodule update --init --depth 1 \
  dep/glfw dep/nanosvg dep/oui-blendish dep/pffft dep/simde dep/speexdsp

# Supply Jansson development headers (for example, apt install libjansson-dev).
python3 -B tools/ci/check_real_rack_headers.py
```

Dependencies remain pinned through this repository's `src/Rack` Gitlink
(`8c6f41b778b4bf8860b89b36d5503fd37924077f`), DPF Gitlink
(`461ea6d45d842d273ae4d53ad5490e43459419cc`), and each nested Rack
Gitlink—not a floating branch. The isolated CI job fetches only these two
top-level SDK submodules and six nested dependencies. It uses the same
official Xiph SpeexDSP mirror URL rewrite already configured for the full
build workflow while preserving Rack's pinned SpeexDSP commit
`27ddf98b627ab425d5337b1a0d8b80d7528f9b30`.

For non-installed Jansson headers, pass `--jansson-include /path/to/usr/include`
where both `jansson.h` and `jansson_config.h` reside. For SDKs already checked
out elsewhere, pass `--rack-root /path/to/pinned/Rack` and
`--dpf-root /path/to/pinned/dpf`; their revisions must **still match** this
repository's Gitlinks. `--preflight-only` validates exact source revisions and
headers without compiling. On missing/wrong dependencies the check exits 2
with a targeted setup message; source compilation failure exits 1. The
SpeexDSP Linux type header is generated from the pinned upstream `.in`
template in an automatically removed temporary directory—never vendored.

### First-party linked-object smoke (additional gate)

Run `python3 -B tools/ci/check_real_rack_headers.py --link-smoke` after
initializing the same exact pinned SDK headers. This mode checks that the
manifest, `plugins/Makefile`, shared model declarations and
`initStatic__ModularSynth()` loader describe the **same seven originals**,
then compiles every original HEADLESS Rack translation unit to a real
position-independent object and links them into one **temporary Linux ELF
shared object**. It uses `nm -D` to require exactly one defined
`model<Module>` symbol for each original and to reject unresolved first-party
model symbols. Missing translation units, duplicate model definitions or
broken loader/source registration fail the gate. Offline negative fixtures
exercise these failures.

The smoke object is automatically deleted and deliberately permits unresolved
**Rack/host imports**, which the full Cardinal integration must supply. It has
no complete plugin entry point or linked host implementation. **It is not a
loadable Cardinal, VST3, CLAP or LV2 binary**, nor proof of actual audio,
DAW compatibility, symbol resolution at runtime, or a releasable artifact.
The real-header Actions workflow now runs both syntax-only and this separate
object/link gate when runners execute; neither should be marked green before
an actual completed run.

At the 2026-11-02 inspection, [full-build run 41386608744](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41386608744)
had **20/20 queued jobs, zero executed steps**, and [real-header run
41386608694](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41386608694)
had **one queued job, zero steps**. This is a pre-execution scheduling
condition, **not a measured compile failure**; repository code alone cannot
establish the exact GitHub runner-side cause. A focused link gate cannot
resolve runner availability, but can supply stronger evidence once scheduled.

**Historical local evidence (2026-11-02, exact merged `3fbda096`, before FMVoice):** GCC 13.3.0 `-fsyntax-only` completed for
**MorphVCO, StateFilter, FoldDrive, Macro8, StereoEcho and ClockedLFO (6/6)** against
the exact Rack and DPF Gitlinks, exact six nested dependency Gitlinks,
and official Ubuntu 24.04 `libjansson-dev` 2.14-2build2 headers. The runner
does **not link** Rack/Cardinal libraries, build GUI widgets in a running host,
exercise the Rack plugin ABI, produce `.so`/CLAP/VST3 binaries, load any DAW,
or establish audio quality/performance. A hosted green job must be observed
before reporting the gate as passing on GitHub Actions. A real full host
build and manual patch/audio/DAW QA remain required for Phase 1 acceptance.

**Additional current local evidence (2026-11-02, exact [`87d27f3`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/87d27f341b56e3229a7a98ac6b73bf5f63510aa3)):** GCC 13.3.0 completed HEADLESS `-fsyntax-only` for **all seven original modules (7/7)** using pinned Rack Gitlink `8c6f41b`, DPF Gitlink `461ea6d` and the exact pinned GLFW/nanosvg/oui-blendish/pffft/simde/SpeexDSP nested revisions. `libjansson-dev` **2.14-2build2** headers were extracted from the official Ubuntu 24.04 package into a temporary workspace, without installing a system package. The official Xiph SpeexDSP GitHub mirror supplied the pinned commit. [Module Forge's real-header checker](../tools/module-forge/check_real_generated_headers.py) also compiled **two freshly generated wrapper units (2/2)** against the same authentic headers. These **9/9 source translation-unit syntax checks** neither link Cardinal nor exercise Rack's plugin ABI, GUI, DAW runtime, MIDI/audio, save/reopen, or host CPU; they do not establish a hosted Actions success or a fork release.

The [six-original shared wrapper smoke](../tests/test_rack_wrapper_smoke.py) exercises MorphVCO/StateFilter/Macro8/StereoEcho/ClockedLFO/FMVoice, while the separate [FoldDrive wrapper/concurrency contract](../tests/test_folddrive_contract.py) exercises the seventh original. Together they compile/process HEADLESS wrappers against **`tests/rack_stub`**, a deliberately small fake Rack API. [Module Forge's generated wrapper tests](../tools/module-forge/test_generated_wrappers.py) compile both fresh oscillator/effect starters using the **same stub** under ordinary and aggressive optimization modes. These are valuable additional C++ source checks, **not real Rack SDK headers, binary ABI compatibility, GUI builds, plugin packaging, DAW loading or audio auditions**.

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

For a **Windows tagged release**, confirm the exact tag's nonempty `MODULAR-SYNTH-win32|win64-<tag>.zip` **and** exactly one matching-target nonempty `Cardinal-winXX-<version>-installer.exe` were packaged and uploaded; then install and test that build on Windows. The [source ZIP/installer gate](../tests/test_ci_windows_release_assets.py) is not evidence that a real host or installer passed. For an offline instrument bundle, opt-in `python3 tools/instrument-builder/instrument_builder.py check <bundle>.msinstrument --require-verified-routes` can reject unknown *direct Macro8 routes*, but this does not replace any installed-DAW routing test.

## What passing means

- **Fast quality success:** manifest and Gitlink checks, offline SpeexDSP mirror preflight, repository/patch tests (including a test-shim wrapper smoke), Module Forge generated-wrapper/shim and Instrument Builder suites, and discovered standalone DSP smokes meet their assertions.
- **Full build success:** the cross-platform jobs that executed passed compilation and packaging checks.
- **Audio-host production readiness:** still requires real DAW loading, live MIDI/audio, project save/restore, audio regression, performance, and UI validation; it is not established by source-only tests.

A queued, cancelled, skipped, or not-yet-run job is **not** evidence of a successful build.

## Maintenance considerations

The `build.yml` matrix is expensive because it checks out many git submodules and builds multiple architectures. New PRs should rely on fast tests for early feedback; maintainers should request full builds when integration risk warrants them. When adding a new standalone DSP test, name it `tests/<module>_dsp_smoke.cpp` or `tests/<module>_dsp_test.cpp`; it will be automatically compiled and run in all three profiles. Keep Rack/DPF wrapper tests outside this naming convention. Python tests are automatically discovered under `tests/test_*.py`, `tools/module-forge/test_*.py`, or `tools/instrument-builder/test_*.py`.

These trigger and concurrency changes do not retroactively cancel runs queued before they were merged. Review old queued runs separately if they continue consuming runner capacity.
