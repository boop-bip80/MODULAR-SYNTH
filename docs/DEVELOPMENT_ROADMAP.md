# MODULAR-SYNTH development roadmap

> **Status: Phase 1 in progress.** This is a proposed development plan and a set of exit gates, **not a claim that features have shipped**. A phase is complete only when its acceptance criteria are independently verified and linked below. Updated 2026-11-05.

## Purpose and baseline

MODULAR-SYNTH aims to become an extensible, professionally reliable modular sound-design workstation: an environment for writing original DSP modules, assembling patches, making reusable performance instruments, and using those instruments within DAWs. Creative ambition is not a substitute for tested audio software.

The baseline repository, prior to project-specific development, matched [DISTRHO Cardinal](https://github.com/DISTRHO/Cardinal) exactly at commit [`0a530b73273afc914ec71a78e9165cd28c53b599`](https://github.com/DISTRHO/Cardinal/commit/0a530b73273afc914ec71a78e9165cd28c53b599) (2026-07-28). At that baseline both repositories had the same Git tree and 730 tree entries. The foundation includes the VCV Rack engine via a pinned submodule, DPF plugin formats, built-in modules and Cardinal host integration. Those capabilities are **upstream work**, not new MODULAR-SYNTH features.

The [hosted `063239ab` main build](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/42111770601) produced Linux/Windows artifacts and passed linked Cardinal self-tests, first-party ELF checks, and LV2/VST2/VST3 Carla plugin bridge testing. In [PR #123](https://github.com/boop-bip80/MODULAR-SYNTH/pull/123), source quality, nine-original genuine Rack-header checks and six generated-starter genuine-header checks also passed on their exact PR source. The [subsequent `3e44c84` merged-main build](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/42126069430) successfully built Linux x86-64 and started on `macos-15-intel`, but MOD hardware still failed because a verified Linaro source archive is unavailable; full macOS and Windows outputs require their own job conclusions. **Neither hosted checkpoint proves the new tenth SlewGlide/seventh ADSR source or a public fork-owned release.** Third-party DAW save/reopen, UI audition, control automation, MIDI/audio response and true host CPU/latency remain unverified.

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
| Phase 1 — Original voice and trustworthy baseline | **Ten registered first-party modules:** MorphVCO, StateFilter, FoldDrive, Macro8, StereoEcho, ClockedLFO, FMVoice, ChanceHold, DualVCA and SlewGlide. **Twenty** fork-authored source patches, including stereo SlewGlide Luminous Portamento Duets; ten-panel source geometry/129 controls and verified source paths, independent standalone DSP and runtime Rack-shim tests. Earlier nine-wrapper genuine-header and linked Cardinal/plugin-validation gates passed on prior source, not this tenth-module revision. | Fresh hosted ten-wrapper source and full plugin build, manual module-browser audio/MIDI and DAW save/reopen, real host CPU/latency, release artifacts |
| Phase 2 — Module Forge developer workflow | Seven opt-in C++/SVG generators: sine, polyBLEP saw/pulse/PWM, polyBLAMP triangle, stereo TPT effect and 16-lane linear ADSR envelope. Strict generated reset handling, deterministic shims/profiles, and **14** configured C++11/C++17 genuine Rack-header translation-unit checks; new ADSR hosted pass is still pending. | Fresh genuine-header compilation, linked generated Cardinal module, GUI/module browser, live audio and state reload |
| Phase 3 — Patch-to-Instrument Builder | Macro8 scenes/CV and versioned deterministic `.msinstrument` v1/v2 source ZIP bundles; direct route provenance to **eight** verified first-party targets, preserved historical markers, controls, semantic diff, strict ZIP safety, single/interrupted sequence morph previews and exact-sample source-estimated CV-by-route JSON/formula-safe CSV exports. No compiled instrument or actual MIDI/DAW automation is exported. | Live patch grouping, musician-designed panels, host automation/MIDI, DAW roundtrip and standalone/plugin instrument export |
| Phase 4 — Flagship synthesis | Ten original modules including 16-lane DualVCA and SlewGlide; independently tested StateFilter coefficient caching, FMVoice upward pitch-index and self-feedback spectral alias guards, stable StereoEcho tails and deterministic offline WAV sketches. Repeated C++11 benchmark now covers **seven** source DSP engines × **42** sample-rate/polyphony cases, with allocation detection and strict historical comparator gates, not host CPU numbers. | DAW audio/listening audition, actual host CPU/latency/automation measurement, performance budgets, further flagships and broader oversampling/antialiasing |
| Phase 5 — Production workflow and releases | Earlier Linux/Windows hosted artifacts and plugin-validator pass; source-only exact-SHA hosted evidence and fail-closed stereo audio-capture validators; stronger Linux compiled binary and ten-module source archive inventory, Windows ZIP/PE and macOS Mach-O/XAR payload safeguards; supported `macos-15-intel` runner; MOD Linaro offline archive staging only with independently checked SHA-256. Source panel QA/contrast and provenance pass. **No all-platform release or actual host-audition certificate.** | Fresh hosted ten/seven checks and plugin binary build, macOS/Windows/MOD outcomes, authenticated MOD dependency, DAW audio/MIDI/save/reopen, installer/signing, host CPU, fork release |
| Phase 6 — Experimental frontier | Planned, opt-in only | Security/performance evaluation and stable fallback path |

**Fourth twelve-agent source integration (2026-11-05, hosted checks pending on this new revision):** **736/736 Python tests passed** on the integrated tree: **505** repository/patch/CI, **79** Module Forge and **152** Instrument Builder, plus **68/68 independently compiled and executed standalone C++ DSP profiles** (17 suites × strict, production, aggressive fast-math and UBSan). Combined ASan+UBSan could not run reliably under runtime tracing, so UBSan is the sanitizer claimed. Exactly **ten** original modules and **20** factory source patches pass source coverage, including the new eight-voice SlewGlide *Luminous Portamento Duets* with both HostAudio2 routes traced. **Ten** panels and **129** candidate widget centers pass source geometry, six source-audited panels/13 signal rails/38 labelled jacks pass measured-source checks, and Macro8's five scene controls pass source checks; the strict first-party license/provenance audit reports **0 errors / 0 warnings**. New work also includes FMVoice signed-feedback spectral guards, a seventh Module Forge polyphonic ADSR starter, fail-closed source-estimated Macro8 CV automation tables, directed feedback-cycle diagnostics, seven-engine/42-case no-allocation benchmark, strict Linux host-capture evidence gate, macOS/Windows payload trust checks, and verified-only MOD source staging. **The current ten-original/seven-generated hosted gates, full host/plugin build, actual audio/MIDI/DAW audition, macOS/MOD/Windows installation and public fork release remain separate open acceptance criteria.**

**Third twelve-agent source integration (2026-11-05, merged via [PR #123](https://github.com/boop-bip80/MODULAR-SYNTH/pull/123); exact PR source/header checks passed):** **663/663 Python tests passed**: **444** repository/patch/CI, **75** Module Forge and **144** Instrument Builder, plus **60/60 compiled-and-executed C++ DSP profiles** (strict, production, aggressive fast-math and UBSan). All **19** factory source graphs passed coverage, nine panels/121 widget centers passed geometry checks, and the DualVCA/StereoEcho port-rail audit checked 14 jacks and labels at source level. Strict first-party provenance returned **0 errors / 0 warnings**. Combined ASan+UBSan was unavailable under runtime tracing; do not infer ASan or real-host success. New work includes missed-clock compensation, upward FM index clamp, denormal-tail snapping, generated audio-thread deferred reset, sequence morph preview, Reed Chamber Organ patch, conservative duplicate-model state matching, repeated bench comparison, exact-SHA hosted evidence inspection, fail-closed plugin bridge inventory, and `macos-15-intel` runner migration. **That round's nine/six PR header checks passed; all-platform build, real DAW loading/audio/UI and fork release remain open.**

**Second twelve-agent source integration (2026-11-05, awaiting its own hosted builds):** **603/603 Python tests** passed across **394** repository/patch/CI, **74** Module Forge and **135** Instrument Builder cases, plus **60/60 compiled and executed standalone DSP profiles** across strict, production, fast-math and UBSan. Combined ASan+UBSan was unavailable under runtime tracing. Eighteen original factory examples passed graph/source coverage, all nine panels and 121 source widget centers passed strict geometry/resource checks, and the first-party license audit reported **0 errors / 0 warnings**. The new additions include StateFilter coefficient equivalence, polyBLEP PWM code generation, chordal FMVoice offline WAVs, an original dual-timbre patch, Macro8 morph preview, cable-by-cable provenance, expanded Rack shim save/reload testing and hardened Linux/Windows/macOS/MOD build safeguards. No live DAW audition or macOS/MOD build success is inferred from these source checks.

**Previous twelve-agent integrated-source checkpoint (2026-11-05, not a published release):** **338/338 repository Python tests**, **69/69 Module Forge tests**, **127/127 Instrument Builder tests** and **60/60 standalone C++ DSP profile runs** passed independently on that earlier combined tree. Nine original models, seventeen factory patches, nine SVG panels/121 candidate widget centers and strict provenance (0 errors, 0 warnings) passed. The [preceding main build](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/42104155795) succeeded on Linux ARMHF/AArch64/i686 but exposed Windows Wine/container and MOD toolchain failures. The later [`063239ab` build](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/42111770601) fixed the Windows issue and passed plugin validation. UBSan ran locally; ASan+UBSan could not run under the sandbox.

**Latest independent merged-main source verification (2026-11-02, [`2f14a2f`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/2f14a2f3ea4a10557385cac62db022658927c5f0), PRs #114–#119):** **477/477 Python tests** (296 repository/patch/CI, 63 Module Forge, 118 Instrument Builder) plus **60/60 compiled-and-executed standalone C++ profiles** (15 suites × strict, production, aggressive fast-math and UBSan). Nine registered originals, sixteen factory source patches, nine panels/121 source widget centers and strict first-party provenance (0 errors, 0 warnings) passed. The new stereo Morph VCO → DualVCA → HostAudio2 route passes the source-verified strict graph gate. ASan+UBSan was unavailable at runtime. The nine-original/four-generated genuine-header gates, hosted full plugin builds, real MIDI/audio/GUI/DAW/save-reopen, host CPU/latency and fork release remain **unverified**; hosted builds were queued at the check.

**Previous independent combined-source verification (2026-11-02, pre-merge integration tree corresponding to [#106–#112](https://github.com/boop-bip80/MODULAR-SYNTH/pull/112) and integrated by [`7793120`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/77931207dc6285ab8afc9b8da5141c8c86d46005)):** **447/447 Python tests passed** (278 repository/patch/CI, 57 Module Forge, 112 Instrument Builder), plus **56/56 compiled-and-executed standalone C++ DSP compiler profiles** (14 suites × strict, production, aggressive fast-math and UBSan). The combined test run covers eight registered models, sixteen source factory patches, panel geometry, saved bundle diff, offline WAV tails and new ChanceHold wrapper against a **test Rack shim**. Current-source real Rack/DPF/Jansson compile/link, hosted full builds, host MIDI/audio/UI, DAW roundtrip and fork release remain **unverified**; earlier 7-original/2-generated true-header source passes do not establish the new 8/3 gate. ASan+UBSan was unavailable under ptrace.

## Source implementation record — 2026-11-02

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
- [#73](https://github.com/boop-bip80/MODULAR-SYNTH/pull/73): sixth statically registered original [FoldDrive](FOLD_DRIVE.md), its original sine-fold DSP/atomic reset and 12 HP source panel, with [Fold Drive Cinematic Motion](../patches/examples/MODULAR_-_Fold_Drive_Cinematic_Motion.vcv) as fourteenth source-checked patch. **At #73**, alias power and host CPU were still unmeasured; #80 subsequently added isolated alias testing.
- [#74](https://github.com/boop-bip80/MODULAR-SYNTH/pull/74): prior source-gate integration snapshot and README refresh; host/release gates explicitly kept open.
- [#75](https://github.com/boop-bip80/MODULAR-SYNTH/pull/75): cold-cache full-matrix compile/package stages and stricter missing-artifact gates; hosted full-build success still unverified.
- [#76](https://github.com/boop-bip80/MODULAR-SYNTH/pull/76): generated oscillator and effect sources each pass **pinned real Rack-header syntax-only** checks locally, distinct from plugin linking.
- [#77](https://github.com/boop-bip80/MODULAR-SYNTH/pull/77): source-verified FoldDrive CV routing and safe version markers for old Instrument Builder v2 archives.
- [#78](https://github.com/boop-bip80/MODULAR-SYNTH/pull/78): deterministic offline 44.1/48/96 kHz, 16-note stereo WAV rendering through first-party MorphVCO/StateFilter DSP with five repeatability/safety tests.
- [#79](https://github.com/boop-bip80/MODULAR-SYNTH/pull/79): semantic patch comparison now detects previously ignored persisted module/MIDI/bypass configuration; #86 subsequently extended detection to unknown cable/parameter metadata.
- [#80](https://github.com/boop-bip80/MODULAR-SYNTH/pull/80): FoldDrive first-order ADAA and high-frequency alias regressions; no complete bandlimit or host CPU claim.
- [#81](https://github.com/boop-bip80/MODULAR-SYNTH/pull/81): correct standalone audio-renderer CLI/evidence wording and broken checklist formatting.
- [#82](https://github.com/boop-bip80/MODULAR-SYNTH/pull/82): FoldDrive regression for dry-mode ADAA history, CV-slewed wet reopening, reset and folded-path phase/timbre limits; no algorithm or port changes.
- [#83](https://github.com/boop-bip80/MODULAR-SYNTH/pull/83): Module Forge blocks generated integration over mismatched existing Makefile/manifest or C++ model declaration/loader sets, with three new tests.
- [#84](https://github.com/boop-bip80/MODULAR-SYNTH/pull/84): offline renderer opt-in real StereoEcho stage (`--with-stereo-echo`), fixed safe settings, deterministic 44.1/48/96 kHz delay-onset/checksum checks and preserved dry reference.
- [#85](https://github.com/boop-bip80/MODULAR-SYNTH/pull/85): musician-readable `routes`/JSON saved Macro8 cable mapping inspection; unknown ports remain unverified and bundle bytes/format remain unchanged.
- [#86](https://github.com/boop-bip80/MODULAR-SYNTH/pull/86): patch comparator now includes unknown parameter-entry and cable metadata, with duplicate cable multiset semantics and five regressions.

- [#88](https://github.com/boop-bip80/MODULAR-SYNTH/pull/88): sample-rate-aware StereoEcho control smoothing and deterministic automation regressions.
- [#89](https://github.com/boop-bip80/MODULAR-SYNTH/pull/89): generated Module Forge oscillator/effect retire inactive polyphonic phase/filter state, with compiled test-shim regression.
- [#90](https://github.com/boop-bip80/MODULAR-SYNTH/pull/90): optional source-backed HostAudio2 patch-output wiring diagnostics and eight verified new tests.
- [#91](https://github.com/boop-bip80/MODULAR-SYNTH/pull/91): fail-closed source-tarball existence/readability checks and five verified regression tests; no actual release.
- [#92](https://github.com/boop-bip80/MODULAR-SYNTH/pull/92): saved Macro8 `controls`/JSON inventory with six verified new tests, preserving v1/v2 source-bundle bytes.
- [#93](https://github.com/boop-bip80/MODULAR-SYNTH/pull/93): original 16-voice two-operator FMVoice, first-party panel, static registration, 15th factory patch, DSP/shim/source QA. No linked host/DAW proof.
- [#94](https://github.com/boop-bip80/MODULAR-SYNTH/pull/94): reject microscopic StereoEcho dry/output subnormals without changing Rack ports or saved patches; C++ stress regressions.
- [#95](https://github.com/boop-bip80/MODULAR-SYNTH/pull/95): source release archive membership/root checks covering all seven original modules' C++/headers/panels; offline corruption and omission fixtures.
- [#96](https://github.com/boop-bip80/MODULAR-SYNTH/pull/96): Module Forge refuses cross-registry C++/manifest slug identity drift before applying a generated module.
- [#97](https://github.com/boop-bip80/MODULAR-SYNTH/pull/97): source-only HostAudio2 direct-control-source advisories and disconnected MorphVCO/FMVoice generator reachability with an opt-in route gate.
- [#98](https://github.com/boop-bip80/MODULAR-SYNTH/pull/98): immutable, versioned Instrument Builder FMVoice CV route contracts with tamper and historical archive tests.
- [#99](https://github.com/boop-bip80/MODULAR-SYNTH/pull/99): narrow FMVoice high-frequency index guard and safe frequency product, with measured selected-bin alias reductions but no claim of complete anti-aliasing.
- [#100](https://github.com/boop-bip80/MODULAR-SYNTH/pull/100): standalone four-second stereo FMVoice WAV renderer, repeatability and FM-versus-sine PCM checks at 44.1/48/96 kHz; no host audition.
- [#101](https://github.com/boop-bip80/MODULAR-SYNTH/pull/101): opt-in v2 Macro8 SVG saved-route visualization, with source-verified labels, unverified port warnings and unchanged default preview/archive bytes.
- [#102](https://github.com/boop-bip80/MODULAR-SYNTH/pull/102): opt-in Module Forge polyBLEP saw generator, measured 14.93 dB reduction in selected high-note alias bins versus a naïve saw; not a completely alias-free oscillator.
- [#103](https://github.com/boop-bip80/MODULAR-SYNTH/pull/103): FMVoice signed feedback adds negative-knob carrier self-feedback while preserving positive modulator feedback, IDs and saved CV mapping.
- [#104](https://github.com/boop-bip80/MODULAR-SYNTH/pull/104): seven original first-party Rack object compiles, temporary ELF link and model registration checks with real pinned headers; not a host-loadable binary.
- [#105](https://github.com/boop-bip80/MODULAR-SYNTH/pull/105): 25 ms stereo-coherent read-head crossfade on abrupt StereoEcho delay changes, with measured bounds at 48/384 kHz and no new allocations.

- [#106](https://github.com/boop-bip80/MODULAR-SYNTH/pull/106): generated polyBLEP saw added to the three-variant genuine-header gate; mocked orchestration tests passed, hosted true-header run pending.
- [#107](https://github.com/boop-bip80/MODULAR-SYNTH/pull/107): RISC-V dpkg foreign-architecture/mirror fix and source regression test; complete cross-build pending.
- [#108](https://github.com/boop-bip80/MODULAR-SYNTH/pull/108): bounded deterministic one/two-second optional StereoEcho WAV tails preserving four-second PCM prefix.
- [#109](https://github.com/boop-bip80/MODULAR-SYNTH/pull/109): FMVoice subnormal-frequency handling, overflow-safe sideband guard and 16-voice event stress.
- [#110](https://github.com/boop-bip80/MODULAR-SYNTH/pull/110), [#111](https://github.com/boop-bip80/MODULAR-SYNTH/pull/111): validated `.msinstrument diff`, deterministic semantic reports, malformed-bundle failure and null-vs-absent saved metadata regression.
- [#112](https://github.com/boop-bip80/MODULAR-SYNTH/pull/112): original 16-channel ChanceHold module, panel, 16th source patch, registry/build/panel/packaging tests and 14th DSP suite.
- [#114](https://github.com/boop-bip80/MODULAR-SYNTH/pull/114): cumulative ChanceHold Macro8 destination mapping with all five CV ports and historical bundle regression.
- [#115](https://github.com/boop-bip80/MODULAR-SYNTH/pull/115): deterministic stereo FMVoice unison WAV render with 1/2/4 independent detuned layers and multirate tests.
- [#116](https://github.com/boop-bip80/MODULAR-SYNTH/pull/116): source-verified signal-port graph checks, DualVCA transfer constraints and strict opt-in routing gate.
- [#117](https://github.com/boop-bip80/MODULAR-SYNTH/pull/117): original opt-in fixed-duty polyBLEP pulse starter, compiled alias/safety tests and fourth generated real-header gate.
- [#118](https://github.com/boop-bip80/MODULAR-SYNTH/pull/118): manifest-derived linked Linux ELF identity and source archive inventory gates, tested with negative cases.
- [#119](https://github.com/boop-bip80/MODULAR-SYNTH/pull/119): original 16-lane DualVCA, panel, shim/DSP tests, stereo Morph VCO patch wiring and nine-module registry/header gate.

**Previous integrated source evidence (2026-11-02, exact merged [`f8b1c42`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/f8b1c42abc709fe78a4a47c2623f2ca82fe59874)):** **431/431 Python tests passed** (274 repository/patch/CI, 55 Module Forge, 102 Instrument Builder) and **52/52 standalone C++ DSP profiles** (13 suites × 4 compiler/sanitizer modes, including UBSan). Strict first-party provenance passed with zero issues, and 15/15 factory patches passed source-only HostAudio2 and directed generator-route checks. All **seven original HEADLESS wrapper objects compiled and linked into a temporary ELF** against genuine pinned Rack/DPF/Jansson headers; **2/2 default generated wrappers** passed separate real-header syntax checks. The ELF intentionally retains unresolved Rack/host imports and is **not a loadable Cardinal plugin**. Combined ASan+UBSan could not run under ptrace. GitHub Actions and the full fork build/DAW/host/release acceptance criteria remain outstanding; neither numerical DSP tests nor static route maps prove audible host behavior.

**Previous independently executed integrated source evidence (2026-11-02, exact merged [`87d27f3`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/87d27f341b56e3229a7a98ac6b73bf5f63510aa3)):** **409/409 Python tests passed** (265 repository/patch/CI, 51 Module Forge, 93 Instrument Builder) and **48/48 standalone C++ DSP compiled/executed profiles** including UBSan; combined ASan+UBSan was unavailable. Both source-only HostAudio2 gates passed all 15 factory patches, and seven SVG panels/97 conservative widget centers plus strict first-party provenance passed. The contrast audit still cannot identify actual pixel underlays for 84 NanoVG label sites. Full-build, real-header and source-quality Actions jobs for the exact code merge were queued, not passing; no latest-main linked plugin, DAW audio or installed fork binary has been verified.

**Additional pinned real-header preflight (2026-11-02, same [`87d27f3`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/87d27f341b56e3229a7a98ac6b73bf5f63510aa3) code):** **7/7 original** and **2/2 freshly generated Module Forge** HEADLESS translation units passed GCC 13.3.0 `-fsyntax-only` with the genuine exact pinned Rack/DPF/six nested dependency Gitlinks and Ubuntu 24.04 Jansson 2.14-2build2 development headers. This closes a local *source-header* gate, **not** the required full Cardinal link, host ABI, DAW/UI/audio or release acceptance. The hosted real-header run was still queued at the integration check.

**Previous integrated source evidence (2026-11-02, exact merged [`060a2a83`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/060a2a83b6803e61e63eabf9bcbf631eb488c5c2)):** **391/391 Python tests passed** (257 repository/patch/CI, 49 Module Forge, 85 Instrument Builder). Twelve standalone C++ DSP suites passed **48/48 compiled/executed profiles including UBSan**; ASan+UBSan runtime was unavailable. Seven first-party SVG panels and 97 conservative widget centers passed source geometry, while 84 label underlays remain visually UNKNOWN; the source-level HostAudio2 output audit passed all 15 factory patches and the strict first-party license/provenance preflight reported zero issues. This does **not** establish a complete linked Cardinal build, loaded real-Rack FMVoice module, actual DAW audio, MIDI automation, host state roundtrip, CPU/latency, visual accessibility or released binary. The added seventh original genuine-header gate is configured, not yet observed passing.

**Earlier observed source-level integration validation (2026-11-02, tested source commit [`46c5587`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/46c558753ec65893350bb21208ca1d876131cd3e)):** **370/370 Python tests passed independently** across **243 repository/patch/CI**, **48 Module Forge** and **79 Instrument Builder** checks. Eleven standalone DSP suites passed **44/44 compiled-and-executed profiles** (strict, production fast-math, aggressive fast-math and UBSan). ASan+UBSan runtime was unavailable, so no ASan pass is claimed. Six original source panels/86 widget centers pass geometry; **71 label-underlay contrasts remain UNKNOWN**. Prior exact-pin real Rack/DPF/Jansson HEADLESS `-fsyntax-only` checks passed **6/6 original** and **2/2 generated** translation units locally, but did not link a plugin. FoldDrive's first-order ADAA reduced selected synthetic alias-bin energy **8.18–13.86 dB** versus naïve folding; a new dry→wet/reset regression covers CV automation history. Deterministic MorphVCO → StateFilter WAV output optionally uses the actual StereoEcho source DSP and checks 44.1/48/96 kHz delay onset and file identity. These are **source/offline** signals; no latest-main linked Cardinal plugin, live GUI/DAW, CPU/latency, host state roundtrip or fork-owned release has been verified.

**Held work:** [PR #20](https://github.com/boop-bip80/MODULAR-SYNTH/pull/20) remains open and superseded; **do not merge it**. Its independently reviewed and safety-hardened additive renderer was reworked as [PR #78](https://github.com/boop-bip80/MODULAR-SYNTH/pull/78), which **is merged**. That renderer is source-level offline audio evidence, not a plugin, host demonstration, or downloadable release.

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
- [x] All seven original Rack wrappers have source-level shim compile/process coverage against a deliberately limited **test-only HEADLESS shim**, with saved-state/finite reset checks split across the [six-original shared wrapper smoke](../tests/test_rack_wrapper_smoke.py) and [separate FoldDrive wrapper contract](../tests/test_folddrive_contract.py), [PR #64](https://github.com/boop-bip80/MODULAR-SYNTH/pull/64) and [PR #73](https://github.com/boop-bip80/MODULAR-SYNTH/pull/73). This narrower source check does **not** satisfy the separate real-Rack/full-plugin build gate above.
- [x] All seven original HEADLESS translation units passed **7/7 local syntax-only** compilation with exact pinned *real* Rack/DPF/Jansson headers (and **2/2 generated Module Forge** units separately) at [`87d27f3`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/87d27f341b56e3229a7a98ac6b73bf5f63510aa3): [preflight](../tools/ci/check_real_rack_headers.py), [workflow](../.github/workflows/real-rack-headers.yml). The separate link/ABI, GUI, host/audio and downloadable artifact gates remain **unchecked**.
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
- [x] Both generated HEADLESS wrappers compile and execute against a test-only Rack shim in multiple compiler modes ([PR #67](https://github.com/boop-bip80/MODULAR-SYNTH/pull/67)). Separately, both generated source translation units passed **2/2 pinned genuine Rack/DPF/Jansson header `-fsyntax-only` checks** ([PR #76](https://github.com/boop-bip80/MODULAR-SYNTH/pull/76)). These do **not** link a plugin, test GUI widgets/ABI or demonstrate live audio/host loading.
- [ ] Sample-rate, block-size, mono/polyphony and host-reload tests pass against the generated examples.
- [ ] The toolkit is documented and exercised on a clean checkout; license obligations are covered.

**Non-goal:** Promising hot-loaded arbitrary third-party binaries. Cardinal intentionally bundles modules; runtime loading requires a separate ABI/security/reproducibility design.

## Phase 3 — Patch-to-Instrument Builder

**Goal:** Turn a modular rack into a reusable instrument with a purposeful performance surface.

Implement grouping, user-defined macros, exposed controls, patch snapshots, visual panel layout, instance identity, stable serialization, performance-mode switching and parameter mapping. Start with an instrument stored inside MODULAR-SYNTH; standalone/VST3/CLAP export becomes a later packaging subproject.

**Source-only increment now available:** The [Instrument Builder prototype](INSTRUMENT_BUILDER.md) packs a saved Macro8 patch into a deterministic `.msinstrument` archive, verifies versioned manifest metadata/SHA-256, extracts unchanged `.vcv`, previews a **static** SVG performance panel, prints musician-readable `routes`/`routes --json` and `controls`/`controls --json` reports, and source-checks first-party slugs. Opt-in v2 derives direct Macro8 cables to **six source-verified destination models** (ClockedLFO, MorphVCO, StateFilter, StereoEcho, FoldDrive and FMVoice); Macro8 itself has a zero-input contract, and unknown third-party ports remain unverified. Immutable ClockedLFO/FoldDrive/FMVoice contract markers preserve older v2 archive interpretation; v1 remains default. Strict `check --require-verified-routes` rejects unknown/direct unverified routes or forged mapping contracts, while existing v1/v2 bytes and default behaviors remain backward compatible. Its [93 verified offline tests](../tools/instrument-builder/) do **not** prove live grouping, host UI, automation, DAW state, or exported audio-plugin functionality.

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
- [Fifteen example patch coverage](PATCH_COVERAGE.md)
- [Instrument Builder source prototype](INSTRUMENT_BUILDER.md)
- [Source-only license/provenance QA](COMPLIANCE_QA.md)

**Release integrity rule:** Never display an upstream Cardinal download link or screenshot as a MODULAR-SYNTH release artifact. If the fork has no tested release, say **no verified fork release is available**.
