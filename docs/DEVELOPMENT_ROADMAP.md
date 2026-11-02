# MODULAR-SYNTH development roadmap

> **Status: Phase 1 in progress.** This is a proposed development plan and a set of exit gates, **not a claim that features have shipped**. A phase is complete only when its acceptance criteria are independently verified and linked below. Updated 2026-11-02.

## Purpose and baseline

MODULAR-SYNTH aims to become an extensible, professionally reliable modular sound-design workstation: an environment for writing original DSP modules, assembling patches, making reusable performance instruments, and using those instruments within DAWs. Creative ambition is not a substitute for tested audio software.

The baseline repository, prior to project-specific development, matched [DISTRHO Cardinal](https://github.com/DISTRHO/Cardinal) exactly at commit [`0a530b73273afc914ec71a78e9165cd28c53b599`](https://github.com/DISTRHO/Cardinal/commit/0a530b73273afc914ec71a78e9165cd28c53b599) (2026-07-28). At that baseline both repositories had the same Git tree and 730 tree entries. The foundation includes the VCV Rack engine via a pinned submodule, DPF plugin formats, built-in modules and Cardinal host integration. Those capabilities are **upstream work**, not new MODULAR-SYNTH features.

As of the current update there is **no verified fork-specific release and no successful complete fork-owned host/plugin build**. Hosted build jobs have been queued or encountered external dependency/network issues; the existing `.github/workflows/build.yml` must not be confused with a passing production artifact. Upstream release downloads, demonstrations and screenshots are **not** MODULAR-SYNTH builds.

## Guiding constraints

1. **Preserve provenance.** Retain upstream contributors, GPL-3.0-or-later notices and third-party notices. Respect distinct licenses for panels, fonts and artwork. Review every added dependency and bundled module.
2. **Audio continuity first.** No UI or disk/network work on the audio callback; bounded work, no unintended allocations or blocking locks, no NaN/Inf leakage, predictable reset and sample-rate changes.
3. **Cross-platform reality.** Linux, Windows and macOS plugin/standalone paths are release targets. A platform is supported only after a tested artifact exists, not merely because a build matrix mentions it.
4. **Stable state.** Every released patch and plugin state must survive saving, reloading, host restart and future schema migration. Version all newly serialized data.
5. **Keep the upstream advantage.** Cardinal's self-contained modules and low-jitter host-thread audio remain the production default. Any optional dynamic module loading or parallel scheduling is a separately gated experimental feature.
6. **Design for musicians.** A module is finished when it is playable, documented, accessible, automatable when appropriate, and accompanied by representative preset sounds.
7. **Evidence over percentages.** Do not declare a phase 100% done based on code presence alone. Track code review, CI, host testing, real audio renders, measurable CPU/latency and residual defects.

## Status register

| Milestone | Current status | Remaining exit evidence |
| --- | --- | --- |
| Baseline provenance | Documented | Preserve upstream attribution and license checks in new contributions |
| Phase 1 — Original voice and trustworthy baseline | **Six registered first-party models** (MorphVCO, StateFilter, FoldDrive, Macro8, StereoEcho, ClockedLFO), **fourteen fork-authored source example patches** (some using bundled third-party modules), source-checked Cardinal host-port contracts, six-panel UI source checks, standalone DSP, HEADLESS **test-shim** wrapper smokes and separate pinned real-header **syntax-only** verification (6/6 local) | Full fork plugin/standalone build and linking against real Rack/DPF, live module browser, MIDI/audio audition, patch/DAW save-reload, host checks and verified artifact |
| Phase 2 — Module Forge developer workflow | Oscillator and stereo-effect C++/SVG starters and opt-in static integrator implemented; **40 generator/integration/core/HEADLESS shim-wrapper tests** and strict first-party notice preflight pass locally | Generate, compile against the real Rack SDK, browse, play and reload both module types in a real Cardinal host |
| Phase 3 — Patch-to-Instrument Builder | Macro8 CV/snapshots plus deterministic offline `.msinstrument` v1/v2 source bundles, manifest integrity, direct cable mapping for **four routable source-verified first-party destination models** (Macro8 itself has zero inputs; FoldDrive is not yet mapped), opt-in strict verified-route checks, unpack/inspect, static SVG preview and model-declaration preflight; **65 tool tests** | Live patch grouping, FoldDrive mapping contract, custom playable panel, actual host parameter mappings/automation, DAW roundtrip and standalone/plugin instrument export |
| Phase 4 — Flagship synthesis | MorphVCO/StateFilter quantitative tests, original 16-lane StereoEcho delay/denormal guards, 16-lane ClockedLFO external-clock/dropout DSP and original FoldDrive sine-fold/smoothing/reset source checks | Real audio/host renders, FoldDrive alias-power/CPU measurements, performance/latency tests and musician evaluation; further flagship engines |
| Phase 5 — Production workflow and releases | CI dependency/mirror and checksum-pinned Windows Inno Setup preflights, Windows tagged-release fork ZIP/installer and macOS `.pkg` missing-artifact gates, optional UBSan source-DSP profiles, source geometry/contrast QA of six panels, tooltips and reproducible offline verification | Successful hosted multi-platform builds, actual DAW/UI accessibility/automation checks, installed and verified artifacts and fork-owned release |
| Phase 6 — Experimental frontier | Planned, opt-in only | Security/performance evaluation and stable fallback path |

## Source implementation record — 2026-11-01

The source changes below were merged through focused pull requests:

- [#1](https://github.com/boop-bip80/MODULAR-SYNTH/pull/1): distinct project identity and roadmap.
- [#2](https://github.com/boop-bip80/MODULAR-SYNTH/pull/2): reversible patch-cable visibility control.
- [#3](https://github.com/boop-bip80/MODULAR-SYNTH/pull/3), [#8](https://github.com/boop-bip80/MODULAR-SYNTH/pull/8): source integrity, scaffolder and oscillator smoke checks.
- [#4](https://github.com/boop-bip80/MODULAR-SYNTH/pull/4): three bundled-module example arrangements.
- [#5](https://github.com/boop-bip80/MODULAR-SYNTH/pull/5), [#10](https://github.com/boop-bip80/MODULAR-SYNTH/pull/10): Module Forge generator and safe dry-run/opt-in registration tool.
- [#6](https://github.com/boop-bip80/MODULAR-SYNTH/pull/6), [#11](https://github.com/boop-bip80/MODULAR-SYNTH/pull/11): original Morph VCO and compiled DSP hardening.
- [#7](https://github.com/boop-bip80/MODULAR-SYNTH/pull/7), [#9](https://github.com/boop-bip80/MODULAR-SYNTH/pull/9), [#14](https://github.com/boop-bip80/MODULAR-SYNTH/pull/14): fork-safe CI triggers, standalone DSP profile runner and pinned dependency mirror.
- [#12](https://github.com/boop-bip80/MODULAR-SYNTH/pull/12): patch inspector and MIDI-controlled Morph VCO example.
- [#13](https://github.com/boop-bip80/MODULAR-SYNTH/pull/13): original polyphonic State Filter with drive/finite fixes.
- [#15](https://github.com/boop-bip80/MODULAR-SYNTH/pull/15): Macro8 performance CV and snapshot controller.
- [#16](https://github.com/boop-bip80/MODULAR-SYNTH/pull/16): static registration, build-source and manifest integration for StateFilter/Macro8.
- [#17](https://github.com/boop-bip80/MODULAR-SYNTH/pull/17): Macro8 + StateFilter sound-design pad and stronger source-aware patch inspection.
- [#18](https://github.com/boop-bip80/MODULAR-SYNTH/pull/18): host/manual accessibility and DAW QA checklist—documented, not performed.
- [#19](https://github.com/boop-bip80/MODULAR-SYNTH/pull/19): first-party registration consistency tests.
- [#21](https://github.com/boop-bip80/MODULAR-SYNTH/pull/21): 162-case LP/BP/HP digital filter frequency-response regression.
- [#22](https://github.com/boop-bip80/MODULAR-SYNTH/pull/22): cinematic pad and gritty bass factory sound-design patches.
- [#23](https://github.com/boop-bip80/MODULAR-SYNTH/pull/23): automated original SVG panel geometry checks.
- [#24](https://github.com/boop-bip80/MODULAR-SYNTH/pull/24): [musician getting-started guide](GETTING_STARTED.md) grounded in committed code and unverified-host caveats.
- [#25](https://github.com/boop-bip80/MODULAR-SYNTH/pull/25): 786,432 real TPT-filter calls under polyphonic CV and sample-rate stress; [methods](FILTER_STABILITY.md).
- [#26](https://github.com/boop-bip80/MODULAR-SYNTH/pull/26): coherent-FFT [polyBLEP alias regression](OSCILLATOR_ALIASING.md), 24 musical comparisons versus naive waveform edges.
- [#27](https://github.com/boop-bip80/MODULAR-SYNTH/pull/27): [Module Forge](MODULE_FORGE.md) stereo-effect generation, standalone DSP and hardened finite guards.
- [#28](https://github.com/boop-bip80/MODULAR-SYNTH/pull/28): SHA-256-verified FLAC 1.5.0 dependency pre-seeding in PawPaw CI, including older curl fallback.
- [#29](https://github.com/boop-bip80/MODULAR-SYNTH/pull/29): [source-backed panel contrast audit](QA_UI.md) of 31 text sites (all rendered underlays unknown) and 31 decorative outlines (nine initially below advisory 3:1); no claim of WCAG or host-GUI conformance.
- [#30](https://github.com/boop-bip80/MODULAR-SYNTH/pull/30): brighten nine source-measured decorative panel strokes to 3.25–3.30:1 and preserve geometry (actual Rack appearance still untested).
- [#31](https://github.com/boop-bip80/MODULAR-SYNTH/pull/31): [deterministic patch comparison](PATCH_COMPARISON.md) of control, Macro8 scene and cable state, independent of generated Rack IDs.
- [#32](https://github.com/boop-bip80/MODULAR-SYNTH/pull/32): the **then-current** [seven-patch coverage matrix](PATCH_COVERAGE.md) with 63 source-backed graph/snapshot claims; subsequent patches and model coverage are updated below.
- [#33](https://github.com/boop-bip80/MODULAR-SYNTH/pull/33): first post-Phase-1 README and roadmap evidence refresh.
- [#34](https://github.com/boop-bip80/MODULAR-SYNTH/pull/34), [#38](https://github.com/boop-bip80/MODULAR-SYNTH/pull/38): offline pinned-submodule/SpeexDSP mirror preflight and documented scope.
- [#35](https://github.com/boop-bip80/MODULAR-SYNTH/pull/35): first-party 16-lane StereoEcho DSP/panel source with bounded ping-pong feedback.
- [#36](https://github.com/boop-bip80/MODULAR-SYNTH/pull/36): [deterministic `.msinstrument` source bundles](INSTRUMENT_BUILDER.md), integrity-checked pack/inspect/unpack; **not** compiled instruments.
- [#37](https://github.com/boop-bip80/MODULAR-SYNTH/pull/37), [#45](https://github.com/boop-bip80/MODULAR-SYNTH/pull/45): source-grounded first-party knob units, CV scale, normalled-port and snapshot tooltips.
- [#39](https://github.com/boop-bip80/MODULAR-SYNTH/pull/39): [read-only first-party license/provenance audit](COMPLIANCE_QA.md), with explicit warning limitations and exclusion of inherited vendor source.
- [#40](https://github.com/boop-bip80/MODULAR-SYNTH/pull/40): eight-voice Polyphonic Motion Pad with four Macro8 scenes; source graph validation only.
- [#41](https://github.com/boop-bip80/MODULAR-SYNTH/pull/41): four-panel SVG geometry and advisory source-contrast checks, including StereoEcho.
- [#42](https://github.com/boop-bip80/MODULAR-SYNTH/pull/42): StereoEcho static registration and stereo saved-patch showcase.
- [#43](https://github.com/boop-bip80/MODULAR-SYNTH/pull/43): deterministic, accessible **static** SVG [Instrument Builder preview](INSTRUMENT_BUILDER.md); no runtime GUI.
- [#44](https://github.com/boop-bip80/MODULAR-SYNTH/pull/44): optional runtime-probed sanitizer profile for standalone DSP; not full plugin validation.
- [#46](https://github.com/boop-bip80/MODULAR-SYNTH/pull/46): explicit SPDX/provenance notices for original SVG panels and Module Forge starters, taking the strict first-party source audit to zero warnings at that source revision; not legal clearance.
- [#47](https://github.com/boop-bip80/MODULAR-SYNTH/pull/47): dynamic source-only factory patch catalog.
- [#48](https://github.com/boop-bip80/MODULAR-SYNTH/pull/48): [source-bundle compatibility `check`](INSTRUMENT_BUILDER.md) against first-party manifest declarations, with inherited third-party dependencies left unknown.
- [#49](https://github.com/boop-bip80/MODULAR-SYNTH/pull/49), [#52](https://github.com/boop-bip80/MODULAR-SYNTH/pull/52): musician [four-module quick reference](MODULE_QUICK_REFERENCE.md), ten source patch links, exact File menu label and source-level tests.
- [#50](https://github.com/boop-bip80/MODULAR-SYNTH/pull/50): StereoEcho denormal-tail hardening, 16-voice stress and sanitizer-profile DSP checks.
- [#51](https://github.com/boop-bip80/MODULAR-SYNTH/pull/51): four-scene Echo Motion Performance preset; [coverage at that revision](PATCH_COVERAGE.md) required ten examples and all four then-registered models.
- [#53](https://github.com/boop-bip80/MODULAR-SYNTH/pull/53): source-grounded README/roadmap and first-party module status refresh at ten patches/four originals.
- [#55](https://github.com/boop-bip80/MODULAR-SYNTH/pull/55): immutable official Inno Setup **6.0.5** download with SHA-256 verification to mitigate an observed invalid Windows installer response; Wine/package success still unverified.
- [#56](https://github.com/boop-bip80/MODULAR-SYNTH/pull/56): opt-in `.msinstrument` v2 direct Macro8-cable control mappings, with validated first-party input contracts, explicit unknown third-party ports and v1 archive compatibility.
- [#57](https://github.com/boop-bip80/MODULAR-SYNTH/pull/57): original polyphonic [Clocked LFO](CLOCKED_LFO.md), fifth statically registered first-party model, standalone clock/dropout tests and HostTime-connected [Clocked Modulation Studio](../patches/examples/MODULAR_-_Clocked_Modulation_Studio.vcv).
- [#58](https://github.com/boop-bip80/MODULAR-SYNTH/pull/58): conservative base-gradient source-only contrast lower bounds; actual layered label contrasts remain **UNKNOWN**, not a WCAG claim.
- [#59](https://github.com/boop-bip80/MODULAR-SYNTH/pull/59): add the Instrument Builder test suite to the fast source [quality workflow](../.github/workflows/quality-baseline.yml); hosted pass remains unverified.
- [#60](https://github.com/boop-bip80/MODULAR-SYNTH/pull/60): free-running ClockedLFO and dual-ADSR [Cinematic Pulse Score](../patches/examples/MODULAR_-_Cinematic_Pulse_Score.vcv), the twelfth source example, with topology/scene negative tests and all-five-model coverage.
- [#61](https://github.com/boop-bip80/MODULAR-SYNTH/pull/61): source-derived ClockedLFO destination labels for opt-in v2 bundles; an explicit contract marker keeps older unmarked v2 archives compatible.
- [#62](https://github.com/boop-bip80/MODULAR-SYNTH/pull/62): prior five-module/twelve-patch source documentation and checked acceptance inventory at its exact revision.
- [#63](https://github.com/boop-bip80/MODULAR-SYNTH/pull/63): retire inactive MorphVCO/StateFilter polyphonic lanes before channel re-expansion, with source regression; **not** yet exercised in a real Rack host.
- [#64](https://github.com/boop-bip80/MODULAR-SYNTH/pull/64): compile and execute all five first-party HEADLESS Rack wrappers using a **test-only Rack API stand-in**, covering constructor/port counts, finite/reset behavior, Macro8 state and Echo normalization, but not the actual Rack SDK/ABI.
- [#65](https://github.com/boop-bip80/MODULAR-SYNTH/pull/65): macOS tag-release `.pkg` upload is no longer mistakenly gated by non-existent matrix context; tagged artifact and GitHub Release steps fail on missing matching `.pkg`. **Source workflow correction only; no built package verified.**
- [#66](https://github.com/boop-bip80/MODULAR-SYNTH/pull/66): [Noir Expressive Lead](../patches/examples/MODULAR_-_Noir_Expressive_Lead.vcv) becomes the thirteenth source arrangement, with saved aftertouch/mod-wheel routes and source-derived narrow Cardinal HostMIDI/HostTime/HostAudio2 port checks; no audible MIDI/DAW test.
- [#67](https://github.com/boop-bip80/MODULAR-SYNTH/pull/67): generated oscillator/effect HEADLESS wrappers compile and execute against that same test shim under three compiler modes; static registration plans are checked but **not applied or compiled against actual Rack**.
- [#68](https://github.com/boop-bip80/MODULAR-SYNTH/pull/68): the prior evidence-based README/roadmap/CI/QA refresh at five modules and thirteen patch arrangements; those historical counts are superseded here.
- [#69](https://github.com/boop-bip80/MODULAR-SYNTH/pull/69): Windows tagged-release asset gate requires the nonempty, tag-matching **fork-named ZIP** and exactly one target installer; source checks only, no actual packaged install proved.
- [#70](https://github.com/boop-bip80/MODULAR-SYNTH/pull/70): Macro8 reset/reload clears stale smoothing targets on the next audio tick through an atomic deferred request; held STORE buttons no longer accidentally recapture snapshots; test-shim/concurrency evidence, not host audio.
- [#71](https://github.com/boop-bip80/MODULAR-SYNTH/pull/71): opt-in pinned real Rack/DPF/Jansson C++ `HEADLESS` translation-unit **syntax-only** preflight, distinct from shim wrapper processing and a full linked Cardinal build.
- [#72](https://github.com/boop-bip80/MODULAR-SYNTH/pull/72): opt-in Instrument Builder `check --require-verified-routes` fails unknown/unverified direct Macro8 destinations, retaining default v1/v2 bytes and older-archive compatibility; **not** host automation certification.
- [#73](https://github.com/boop-bip80/MODULAR-SYNTH/pull/73): sixth statically registered original [FoldDrive](FOLD_DRIVE.md), its sine-fold DSP/atomic reset and 12 HP source panel, with [Fold Drive Cinematic Motion](../patches/examples/MODULAR_-_Fold_Drive_Cinematic_Motion.vcv) as fourteenth source-checked patch. Audible results, alias power and host CPU remain unmeasured.

**Observed local validation (2026-11-02, exact merged `main` [`3fbda096`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/3fbda096db2165dcc681abd8c210892624ad7b92)):** **324/324 Python tests** passed across **219/219 repository/patch/CI**, **40/40 Module Forge** and **65/65 Instrument Builder** suites, alongside **40/40 compiled-and-executed standalone DSP profile checks across ten suites including UBSan**. ASan+UBSan was runtime-probed and unavailable in this environment; this is **not an ASan pass**. The coverage checker recognizes **fourteen source patches and all six declared original models**; six panels pass conservative source geometry (86 widget centers). The contrast preflight finds no low measured swatches, but **71 local label contrasts remain UNKNOWN** (54 base-gradient-only bounds do not resolve actual pixels). Separately, **6/6 HEADLESS first-party translation units passed local `-fsyntax-only` checking against exact pinned *real* Rack/DPF/Jansson headers**, beyond the independent first-party/generated wrappers that compile and process **against a test-only Rack stand-in**. These are source/SDK compatibility signals: `-fsyntax-only` never links a plugin, and neither route verifies plugin ABI, GUI accessibility/WCAG conformance, audible quality, real host performance, DAW save/reopen or a fork-owned artifact. FoldDrive's sine-transfer fold is not oversampled/bandlimited: alias-power, real host CPU/latency, audition and polyphonic headroom measurements remain **OPEN**. Earlier quantified evidence still includes 162 filter frequency-response cases, 786,432-call polyphonic CV stress and 24 oscillator alias-power comparisons for MorphVCO (not FoldDrive).

**Held work:** [PR #20](https://github.com/boop-bip80/MODULAR-SYNTH/pull/20) contains an independently tested standalone core-level WAV renderer, but its merge is **blocked pending explicit review/approval** after the safety reviewer flagged potentially destructive stale-base differences. It has **not** merged into `main`, is **not** a hosted audio-plugin demonstration and must not be described as a released feature.

**Known build/verification risks:** The inherited full build uses dozens of pinned submodules; historical runs encountered third-party network failures (SpeexDSP GitLab 502/504 and FLAC downloads) and an invalid Windows Inno Setup download. The GitHub mirror rewrite retains the exact submodule commit; official-Xiph FLAC 1.5.0 and official immutable Inno Setup 6.0.5 downloads verify published SHA-256 checksums. Windows release-tag YAML now requires a matching nonempty fork ZIP and a single matching installer, while macOS release-tag YAML requires a matching `.pkg` rather than silently omitting its upload. **None is evidence of a completed hosted build, a working Windows/macOS installer or a released artifact.** The real pinned Rack-header **syntax-only** check has passed locally; a fully **linked** Rack/DPF plugin/standalone build and production host evidence are still missing.

Phase 1 remains **open** until the acceptance gates below are satisfied.

## Phase 1 — Ownership, baseline and the first original voice

**Goal:** Prove that this fork can safely ship a genuinely original module without losing Cardinal's stability.

Implementation workstreams:

- Establish a distinct MODULAR-SYNTH identity, architecture notes, ownership and contributor instructions without pretending upstream features are original.
- Implement a first-party oscillator as a regular integrated Cardinal module with original C++ DSP, manifest registration, panel and usable voltage/knob controls.
- Establish a lightweight source/manifest validation harness and extend existing plugin-validation CI with reproducible audio tests rather than duplicating it.
- Add one narrow user-experience improvement with a keyboard or editing workflow that has a documented test.
- Add a small patch collection using committed, permitted modules and valid `.vcv` state.
- Record a baseline matrix of release targets, host combinations, known failures, CPU cost and latency measurements.

**Acceptance gates (all required):**

- [ ] A fresh recursive checkout builds at least one standalone binary and one DAW plugin variant from this fork through CI; the exact commit and artifact are linked.
- [ ] The first original oscillator loads from the module browser, produces finite audio at 44.1/48/96 kHz, responds to 1 V/oct and CV inputs, and survives sample-rate changes and reset.
- [x] Unit tests validate representative oscillator waveform behavior, phase/sample-rate continuity and non-finite guards: [Morph VCO regression](../tests/morphvco_dsp_smoke.cpp), [PR #11](https://github.com/boop-bip80/MODULAR-SYNTH/pull/11), executed locally at three compiler profiles on integrated [PR #16](https://github.com/boop-bip80/MODULAR-SYNTH/pull/16).
- [x] All six original Rack wrappers compile and execute against a deliberately limited **test-only HEADLESS shim**, with saved-state/finite reset checks split across the [five-original shared wrapper smoke](../tests/test_rack_wrapper_smoke.py) and [sixth FoldDrive wrapper contract](../tests/test_folddrive_contract.py), [PR #64](https://github.com/boop-bip80/MODULAR-SYNTH/pull/64) and [PR #73](https://github.com/boop-bip80/MODULAR-SYNTH/pull/73). This narrower source check does **not** satisfy the separate real-Rack/full-plugin build gate above.
- [x] Six original HEADLESS translation units passed **6/6 local syntax-only** compilation with exact pinned *real* Rack/DPF/Jansson headers: [preflight](../tools/ci/check_real_rack_headers.py), [workflow](../.github/workflows/real-rack-headers.yml). The separate link/ABI, GUI, host/audio and downloadable artifact gates remain **unchecked**.
- [ ] A patch containing the new module saves, reloads and recalls its controls identically; compatibility with existing Cardinal patches is verified.
- [ ] All introduced panel assets, dependencies and source code have compatible licensing and recorded attribution.
- [x] First-party **source notice consistency** (a narrower check than the licensing gate above) passes `license_audit.py --strict` with no errors/warnings after [PR #46](https://github.com/boop-bip80/MODULAR-SYNTH/pull/46); this is not a third-party license or rights determination.
- [x] UI and patch additions have reproducible **source-level** manual or automated validation instructions: [panel geometry tests](../tools/ui-check/validate_panels.py), [QA checklist](QA_UI.md), [patch inspector](PATCH_WORKFLOW.md), [getting-started guide](GETTING_STARTED.md). Actual GUI and audible host checks remain unverified.
- [ ] No newly introduced blocker remains in existing Cardinal self-tests/plugin validation. CI results are reported accurately, including skipped platforms.
- [ ] README status and direct links to **this fork's** verified artifacts are updated; if no artifacts pass, README explicitly says so.

**Phase 1 output:** A playable first-party module, credible quality baseline, developer documentation and testable release direction. Do not create a versioned public release merely to claim progress.

## Phase 2 — Module Forge

**Goal:** Developers can create entirely original oscillators and effects without reverse-engineering the build system each time.

Build a versioned module API/convention, source generator, standard voltage/port definitions, manifest validation, DSP and panel templates, parameter migration guidance, and a documented one-command development loop. Consider Faust as an optional code-generation path after the native C++ path is dependable; compiling user-supplied DSP must occur outside real-time audio execution.

**Acceptance gates:**

- [ ] One example oscillator and one example effect created using Module Forge build and load successfully.
- [ ] Generated module slugs, IDs, parameters and port naming remain stable across regeneration.
- [x] Invalid first-party manifests and unsafe schema/registration collisions are rejected with actionable errors in the [Module Forge test suite](../tools/module-forge/test_integrate.py) and [#10](https://github.com/boop-bip80/MODULAR-SYNTH/pull/10)/[#27](https://github.com/boop-bip80/MODULAR-SYNTH/pull/27). This remains a source-generator test, not runtime host validation.
- [x] Both generated HEADLESS wrappers compile and execute using the test-only Rack stand-in across three compiler profiles: [generator wrapper suite](../tools/module-forge/test_generated_wrappers.py), [PR #67](https://github.com/boop-bip80/MODULAR-SYNTH/pull/67). Real Rack header/ABI, GUI and host loading are still unverified.
- [ ] Sample-rate, block-size, mono/polyphony and host-reload tests pass against the generated examples.
- [ ] The toolkit is documented and exercised on a clean checkout; license obligations are covered.

**Non-goal:** Promising hot-loaded arbitrary third-party binaries. Cardinal intentionally bundles modules; runtime loading requires a separate ABI/security/reproducibility design.

## Phase 3 — Patch-to-Instrument Builder

**Goal:** Turn a modular rack into a reusable instrument with a purposeful performance surface.

Implement grouping, user-defined macros, exposed controls, patch snapshots, visual panel layout, instance identity, stable serialization, performance-mode switching and parameter mapping. Start with an instrument stored inside MODULAR-SYNTH; standalone/VST3/CLAP export becomes a later packaging subproject.

**Source-only increment now available:** The [Instrument Builder prototype](INSTRUMENT_BUILDER.md) packs a saved Macro8 patch into a deterministic `.msinstrument` archive, rechecks its versioned metadata/SHA-256, extracts the unchanged `.vcv`, previews a **static** SVG performance surface and compares first-party slugs to the manifest. Opt-in manifest v2 derives direct saved Macro8 cable mappings with **four routable source-verified first-party input contracts** (ClockedLFO, MorphVCO, StateFilter and StereoEcho); Macro8 has a verified **zero-input** contract, while **FoldDrive direct destination ports are not yet mapped**, as are unknown third-party ports. A ClockedLFO contract marker protects older v2 bundles. The opt-in `check --require-verified-routes` rejects unknown/direct unverified routes, including older unmarked v2 and v1 bundles without a provable mapping contract, without changing default pack/check/inspect behavior. Its [65 offline tests](../tools/instrument-builder/) across `test_*.py` files do not prove any live grouping, host UI, parameter automation or export gates below.

**Acceptance gates:**

- [ ] A representative rack collapses into one reusable instrument with at least eight labeled macro controls.
- [ ] Macro mapping is stable, reversible and produces no zipper noise beyond a documented bound.
- [ ] Save/reopen and DAW project-reopen preserve sound, routing, custom UI and automation.
- [ ] Snapshots morph continuously where possible; intentionally discrete controls switch predictably.
- [ ] Undo/redo, copy/paste, nested/grouped connections and legacy patch loading are regression-tested.
- [ ] At least three factory instruments include playable controls, demos and CPU measurements.

## Phase 4 — Flagship sound engines

**Goal:** Own distinctive original synthesis technology, not only repackaged community modules.

**Current source increment:** [StereoEcho](STEREO_ECHO.md) adds a 16-lane CV-controlled stereo delay with bounded feedback and denormal-tail guards; [ClockedLFO](CLOCKED_LFO.md) adds 16-lane free/external-clock modulation with bounded dropout behavior. With MorphVCO and StateFilter, these expand original DSP but still require audible host renders, CPU measurements in the real plugin and musician evaluation.

Develop in evidence-backed increments:

1. High-quality analog-inspired oscillators and nonlinear filters, with appropriate anti-aliasing and oversampling controls.
2. Spectral transforms: freezing, partial shaping and cross-synthesis, with explicit latency handling.
3. Granular synthesis: bounded polyphony, streaming, transport sync and deterministic seeds.
4. FM/PM and wavetable oscillators with visual modulation and predictable patch state.
5. Physical-modeling resonators and exciters.
6. Cinematic textures, convolution/hybrid reverb and spatial processing.

**Acceptance gates:**

- [ ] Each flagship module has a documented DSP design, tests, a representative preset and a host-rendered reference audio file.
- [ ] Performance is profiled at representative voice/grain counts with p95 and worst-case render times, not only average CPU.
- [ ] Behavior is verified at multiple sample rates and buffer sizes; aliasing, DC, denormal and stability risks are measured.
- [ ] For time/frequency-domain processors, latency and dry/wet alignment are tested and exposed correctly to hosts.
- [ ] At least one demonstrably novel workflow is validated by musician feedback and recorded as a reproducible scenario.

## Phase 5 — Production workflow, performance and releases

**Goal:** Reliable daily use across DAWs and systems.

Implement a cohesive module browser, patch navigation and cable diagnostics, advanced modulation mapping, expression/MPE where supported, microtuning, scalable UI, crash recovery, patch migration, accessible controls, and host-specific automation capabilities. Improve CPU by profiling first; do not enable parallel audio processing without hard real-time evidence.

**Acceptance gates:**

- [ ] Clean Linux/Windows/macOS builds and native standalone/VST3/CLAP or other explicitly supported formats are linked to their exact commits.
- [ ] CI includes host validation, self-tests, audio regression patches, state roundtrips and failure reports.
- [ ] Plugin loads in a representative DAW matrix, saves and reopens projects, and survives repeated instance creation/removal.
- [ ] Performance targets are specified from reproducible baseline measurements and achieved under a published test workload.
- [ ] Signed/notarized installers are provided only where credentials and validation are available; otherwise warnings are explicit.
- [ ] Release notes, accurate screenshots, demo audio, licensing inventory, known issues and README download links refer to verified MODULAR-SYNTH artifacts.

## Phase 6 — Experimental frontier

**Goal:** Explore high-risk features without destabilizing the production audio engine.

Possible experiments: a local AI patch assistant, procedural/generative composition, declarative DSP authoring, optional external module packages, network-free collaborative patch interchange, adaptive workflows, and extended spatial/ambisonic outputs.

**Acceptance gates:**

- [ ] Experimental capabilities are opt-in and have a documented disable/rollback path.
- [ ] Generated patches are validated against a deterministic schema and explicit module allowlist.
- [ ] User-provided code is never executed inside the real-time callback without a separately approved execution/security design.
- [ ] Any new plugin loading mechanism enforces license/version compatibility and tests host-crash/failure behavior.
- [ ] Offline use, privacy boundaries and memory/CPU budgets are documented and tested.
- [ ] Stable versions of MODULAR-SYNTH remain fully functional without experimental features.

## Working agreement for every contribution

1. Read `README.md`, this roadmap, `docs/OVERVIEW.md`, `docs/BUILDING.md`, and applicable source/module documentation.
2. Work on an isolated feature branch with a focused PR, a concrete before/after behavior statement and license review.
3. Include automated tests or exact manual reproduction steps. State explicitly what could not be run.
4. Do not change any acceptance checkbox to `[x]` without a link to evidence (commit, CI run, renderer output or test report). Merge is not proof of successful verification.
5. Update the status register and README only after implementation status actually changes.
6. Preserve upstream provenance and minimize modifications to `src/override/`; these files intentionally track upstream Rack and are update-sensitive.
7. Keep source vs bundled assets, module licensing and closed-source compatibility under active review.
8. A phase may not be promoted merely because a feature branch merged; all mandatory gates must be verified.

## How to follow progress

- [Repository main](https://github.com/boop-bip80/MODULAR-SYNTH)
- [Open pull requests](https://github.com/boop-bip80/MODULAR-SYNTH/pulls)
- [Fork's Actions results](https://github.com/boop-bip80/MODULAR-SYNTH/actions)
- [Fork's releases](https://github.com/boop-bip80/MODULAR-SYNTH/releases)
- [Existing build and validation workflow](../.github/workflows/build.yml)
- [Upstream Cardinal](https://github.com/DISTRHO/Cardinal)
- [Cardinal architecture](OVERVIEW.md)
- [Cardinal build instructions](BUILDING.md)
- [Cardinal license inventory](LICENSES.md)
- [First-party module quick reference](MODULE_QUICK_REFERENCE.md)
- [Fourteen example patch coverage](PATCH_COVERAGE.md)
- [Instrument Builder source prototype](INSTRUMENT_BUILDER.md)
- [Source-only license/provenance QA](COMPLIANCE_QA.md)

**Release integrity rule:** Never display an upstream Cardinal download link or screenshot as a MODULAR-SYNTH release artifact. If the fork has no tested release, say **no verified fork release is available**.
