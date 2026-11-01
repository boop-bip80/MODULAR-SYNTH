# MODULAR-SYNTH development roadmap

> **Status: Phase 1 in progress.** This is a proposed development plan and a set of exit gates, **not a claim that features have shipped**. A phase is complete only when its acceptance criteria are independently verified and linked below. Updated 2026-11-01.

## Purpose and baseline

MODULAR-SYNTH aims to become an extensible, professionally reliable modular sound-design workstation: an environment for writing original DSP modules, assembling patches, making reusable performance instruments, and using those instruments within DAWs. Creative ambition is not a substitute for tested audio software.

The baseline repository, prior to project-specific development, matched [DISTRHO Cardinal](https://github.com/DISTRHO/Cardinal) exactly at commit [`0a530b73273afc914ec71a78e9165cd28c53b599`](https://github.com/DISTRHO/Cardinal/commit/0a530b73273afc914ec71a78e9165cd28c53b599) (2026-07-28). At that baseline both repositories had the same Git tree and 730 tree entries. The foundation includes the VCV Rack engine via a pinned submodule, DPF plugin formats, built-in modules and Cardinal host integration. Those capabilities are **upstream work**, not new MODULAR-SYNTH features.

As of this roadmap's initial publication there are **no fork-specific releases and no completed GitHub Actions runs on this fork**. The existing `.github/workflows/build.yml` is substantial but its presence must not be confused with successful verification in this repository. Upstream release downloads, demonstrations and screenshots are **not** MODULAR-SYNTH builds.

## Guiding constraints

1. **Preserve provenance.** Retain upstream contributors, GPL-3.0-or-later notices and third-party notices. Respect distinct licenses for panels, fonts and artwork. Review every added dependency and bundled module.
2. **Audio continuity first.** No UI or disk/network work on the audio callback; bounded work, no unintended allocations or blocking locks, no NaN/Inf leakage, predictable reset and sample-rate changes.
3. **Cross-platform reality.** Linux, Windows and macOS plugin/standalone paths are release targets. A platform is supported only after a tested artifact exists, not merely because a build matrix mentions it.
4. **Stable state.** Every released patch and plugin state must survive saving, reloading, host restart and future schema migration. Version all newly serialized data.
5. **Keep the upstream advantage.** Cardinal's self-contained modules and low-jitter host-thread audio remain the production default. Any optional dynamic module loading or parallel scheduling is a separately gated experimental feature.
6. **Design for musicians.** A module is finished when it is playable, documented, accessible, automatable when appropriate, and accompanied by representative preset sounds.
7. **Evidence over percentages.** Do not declare a phase 100% done based on code presence alone. Track code review, CI, host testing, real audio renders, measurable CPU/latency and residual defects.

## Status register

| Milestone | Status | Required evidence before marking complete |
| --- | --- | --- |
| Baseline provenance recorded | Documented | Upstream commit/tree comparison and license inventory |
| Phase 1 — First original module and trustworthy baseline | In progress | Original module build, basic audio smoke test, CI results, patch open/save, README |
| Phase 2 — Module Forge developer workflow | Planned | Generated module compiles and passes documented checks on supported systems |
| Phase 3 — Patch-to-Instrument Builder | Planned | Save, reload, play and automate a generated instrument from a nested patch |
| Phase 4 — Distinct flagship synthesis engines | Planned | Listening tests, reference renders and stress/performance evidence |
| Phase 5 — Production workflow and releases | Planned | DAW roundtrips, installers, release artifacts and cross-platform signoff |
| Phase 6 — Experimental frontier | Planned | Explicit opt-in, performance/security evaluation and fallback path |

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
- [ ] Unit tests or an offline reference-render harness validate representative oscillator outputs, phase continuity and absence of obvious clipping/NaN faults.
- [ ] A patch containing the new module saves, reloads and recalls its controls identically; compatibility with existing Cardinal patches is verified.
- [ ] All introduced panel assets, dependencies and source code have compatible licensing and recorded attribution.
- [ ] Any UI and patch additions have reproducible manual or automated validation instructions.
- [ ] No newly introduced blocker remains in existing Cardinal self-tests/plugin validation. CI results are reported accurately, including skipped platforms.
- [ ] README status and direct links to **this fork's** verified artifacts are updated; if no artifacts pass, README explicitly says so.

**Phase 1 output:** A playable first-party module, credible quality baseline, developer documentation and testable release direction. Do not create a versioned public release merely to claim progress.

## Phase 2 — Module Forge

**Goal:** Developers can create entirely original oscillators and effects without reverse-engineering the build system each time.

Build a versioned module API/convention, source generator, standard voltage/port definitions, manifest validation, DSP and panel templates, parameter migration guidance, and a documented one-command development loop. Consider Faust as an optional code-generation path after the native C++ path is dependable; compiling user-supplied DSP must occur outside real-time audio execution.

**Acceptance gates:**

- [ ] One example oscillator and one example effect created using Module Forge build and load successfully.
- [ ] Generated module slugs, IDs, parameters and port naming remain stable across regeneration.
- [ ] Invalid manifests and unsafe schema collisions are rejected with actionable errors.
- [ ] Sample-rate, block-size, mono/polyphony and host-reload tests pass against the generated examples.
- [ ] The toolkit is documented and exercised on a clean checkout; license obligations are covered.

**Non-goal:** Promising hot-loaded arbitrary third-party binaries. Cardinal intentionally bundles modules; runtime loading requires a separate ABI/security/reproducibility design.

## Phase 3 — Patch-to-Instrument Builder

**Goal:** Turn a modular rack into a reusable instrument with a purposeful performance surface.

Implement grouping, user-defined macros, exposed controls, patch snapshots, visual panel layout, instance identity, stable serialization, performance-mode switching and parameter mapping. Start with an instrument stored inside MODULAR-SYNTH; standalone/VST3/CLAP export becomes a later packaging subproject.

**Acceptance gates:**

- [ ] A representative rack collapses into one reusable instrument with at least eight labeled macro controls.
- [ ] Macro mapping is stable, reversible and produces no zipper noise beyond a documented bound.
- [ ] Save/reopen and DAW project-reopen preserve sound, routing, custom UI and automation.
- [ ] Snapshots morph continuously where possible; intentionally discrete controls switch predictably.
- [ ] Undo/redo, copy/paste, nested/grouped connections and legacy patch loading are regression-tested.
- [ ] At least three factory instruments include playable controls, demos and CPU measurements.

## Phase 4 — Flagship sound engines

**Goal:** Own distinctive original synthesis technology, not only repackaged community modules.

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

**Release integrity rule:** Never display an upstream Cardinal download link or screenshot as a MODULAR-SYNTH release artifact. If the fork has no tested release, say **no verified fork release is available**.
