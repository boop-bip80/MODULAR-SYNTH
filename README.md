# MODULAR-SYNTH

> **A Cardinal-derived modular sound-design workstation — early development.** Our direction is to let musicians design original DSP modules, build complete instruments from patches, and use those instruments reliably in professional audio workflows.

**Development status (November 5, 2026): Phase 1 remains open, but a fork-specific hosted plugin-validation build has passed.** The [earlier `063239ab` main-branch build](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/42111770601) produced Linux and Windows artifacts and passed Cardinal self-tests, compiled first-party identifier inspection, and automated LV2/VST2/VST3 bridge tests. That result does **not** validate this newer source round, every DAW or every platform: the macOS job was canceled, MOD hardware remains blocked by a retired toolchain download, and there is no verified fork-owned GitHub Release or interactive DAW save/reopen audition. The fork initially matched [DISTRHO Cardinal](https://github.com/DISTRHO/Cardinal) exactly at upstream commit [`0a530b7`](https://github.com/DISTRHO/Cardinal/commit/0a530b73273afc914ec71a78e9165cd28c53b599) (July 28, 2026). Inherited Cardinal, Rack, DPF and third-party functionality remains credited to its original authors.

**Start here:** [Musician getting-started and MIDI wiring](docs/GETTING_STARTED.md) · [Nine-module quick reference](docs/MODULE_QUICK_REFERENCE.md) · [Eighteen example patches](docs/FACTORY_PATCHES.md) · [Source build instructions](docs/BUILDING.md). The examples are verified structurally, not yet individually auditioned and graded in the fork's module browser.

## Second twelve-agent engineering continuation — 2026-11-05

Twelve independently scoped contributions improve the instrument, its authoring workflow and its release gates on top of [`063239ab`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/063239ab5f12c35cc51f5f05597d547592035816). **The successful hosted build cited above belongs to that earlier commit, not these new changes.**

- **Sound design and DSP:** StateFilter caches unchanged filter/drive coefficients against an independent 24,000-frame audio reference; Module Forge gains an opt-in polyBLEP PWM starter with polyphonic width CV; the standalone FMVoice renderer adds reproducible minor-seventh and quartal harmonies without altering the legacy PCM. The original [Night Lanterns dual-timbre patch](patches/examples/MODULAR_-_Night_Lanterns_Dual_Timbre.vcv) combines MorphVCO/FoldDrive/StateFilter and FMVoice voices, eight Macro8 performance routes and stereo echo.
- **Editing and patch state:** Instrument Builder previews saved Macro8 A/B/C/D/LIVE scene morphs as *estimated control voltage*, not played audio. Patch diagnostics trace every verified cable hop from first-party generators to the host outputs and offer an optional stereo source-verification gate. The C++ Rack test-double exercises all nine first-party wrappers and Macro8 scene serialization across C++11/C++17 profiles.
- **Panel clarity:** ClockedLFO and ChanceHold distinguish input and output sections more clearly. Source SVG checks enforce correct widget counts and safe local assets; uncertain overlaid contrast is labeled unknown instead of being incorrectly reported as measured.
- **Build and distribution reliability:** A checksum-verified alternative source can unblock MOD's retired Linaro archive URL once a trusted mirror is provided. The linked ELF inventory rejects fake model names hidden in writable sections or metadata; Windows distribution validation checks PE architecture and ZIP integrity; macOS release validation checks universal Mach-O binaries and installer XAR structure. These are safeguards, **not** proof of completed MOD or macOS builds.

**Combined source test results:** **603/603 Python tests passed** on the integrated tree (**394** repository/patch/CI, **74** Module Forge, **135** Instrument Builder), alongside **60/60 compiled DSP runs** (15 suites × strict, production, aggressive fast-math and UBSan). Combined ASan+UBSan was unavailable under runtime tracing, so no ASan success is claimed. The 18 factory examples and nine first-party panels/121 control positions pass source checks; strict provenance reports zero errors or warnings. These are local checks and do not replace the new revision's hosted binary/DAW tests. See [the development roadmap](docs/DEVELOPMENT_ROADMAP.md) for acceptance gates.

## Previous twelve-agent engineering continuation — 2026-11-05

The latest source checkpoint adds release and host-integration hardening alongside new musical tooling. These are **implemented and locally tested changes**, not a declaration of a finished plugin or product:

- **Host safety and compiler compatibility:** Six original Rack wrappers defer host reset requests to the audio thread; StereoEcho's C++11 debug linker regression is fixed. The nine original real-Rack header checks and all five generated Module Forge variants now require C++11 **and** C++17 compatibility. The actual pinned-header gates must pass for each published revision.
- **Musical workflows:** Conservative per-HostAudio2-input signal verification distinguishes confirmed first-party paths from opaque third-party or CV routes. An optional standalone FMVoice → DualVCA → StereoEcho renderer produces reproducible stereo WAV demonstrations at 48/96 kHz, without changing historical renders. It is not a live patch/DAW audition.
- **Instrument and DSP engineering:** `.msinstrument` source inputs reject POSIX final-symlink swaps, non-regular files and unbounded numeric conversions, preserving historical v1/v2 bundle bytes. A standalone C++11 benchmark reports four DSP engines at 48/96 kHz with 1/8/16 voices and detects audio-loop allocations, but **not host CPU/latency**.
- **Usability and release correctness:** Macro8/FMVoice control outlines have measurable source contrast improvements without geometry changes. The ELF collection gate checks loaded binary segments and requires all nine original identifiers. Source archives explicitly use XZ and require XZ file signatures; Windows Wine cross-builds use a compatible pinned runner without weakening container security. External MOD toolchain archive failures remain unresolved.

**Integrated local verification:** **338/338** repository Python tests, **69/69** Module Forge tests, **127/127** Instrument Builder tests and **60/60** standalone DSP runs (15 suites × four compiler profiles, UBSan fallback) passed. The strict first-party license preflight reported **0 errors / 0 warnings**, all nine SVG panels and 121 widget centers passed source geometry checks, and the strict contrast audit found no measured low-contrast swatches. Local source tests do **not** establish a host-loadable release; consult the [live Actions matrix](https://github.com/boop-bip80/MODULAR-SYNTH/actions) for hosted status and download artifacts.

## Latest six-agent source integration — 2026-11-05

Six independently developed changes have been integrated and source-tested:

- **Build recovery:** Macro8 now resets its Rack `SchmittTrigger` objects without value-initializing the pinned SDK's inaccessible union constructor. The source-tarball verification step reads and validates the Makefile version without invoking OpenGL-dependent `make version`. These address two errors observed in the [previous failed hosted full-build run](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41400281570), but the corrected host build has **not yet completed**.
- **StereoEcho DSP:** four-point cubic Lagrange fractional-delay interpolation retains approximately **0.884** amplitude at 12 kHz/48 kHz for a half-sample delay, versus **0.707** with the previous linear tap. Bounded two-tap fallback remains at ring boundaries. The better high-frequency response costs additional reads and permits mild one-sample pre/post ringing; it is not a host CPU benchmark or listening test.
- **Module Forge:** opt-in `--waveform triangle` generates a 16-voice polyBLAMP-corrected triangle oscillator, original panel, metadata and integration instructions. The pinned Rack-header gate now covers five generated variants, though the new variant's real-header hosted result remains unverified.
- **Instrument Builder:** versioned v2 source-verified Macro8 routing includes DualVCA's four actual audio/CV inputs. Existing bundle markers keep their historical interpretation; old bundles do not silently acquire new verified destinations. v1 remains the default and no compiled instrument plugin is exported.
- **Musical factory patch:** [Aurora Glass Bells](patches/examples/MODULAR_-_Aurora_Glass_Bells.vcv) provides eight-voice FM, controlled random filter motion, four performance scenes, five Macro8 mappings and LP/BP stereo echo routing. Its saved graph and host-route structure pass validation; actual sound is not yet auditioned in the fork.
- **Panel usability:** MorphVCO's five dial outlines now measure **6.45–6.64:1** against the source panel colors (previously approximately 3.27–3.56:1), with unchanged geometry and a regression guard. Rendered host contrast and accessibility require separate verification.

**Integrated local regression results:** **496/496 Python tests** (303 repository/CI/patch, 68 Module Forge, 125 Instrument Builder) and **60/60 compiled standalone C++ DSP profiles** (15 suites each under strict, production, aggressive fast-math and UBSan) passed. ASan+UBSan was unavailable under ptrace; **no ASan pass is claimed**. Source checks cover **nine original models**, **seventeen factory patches**, **nine SVG panels** and strict first-party provenance with **zero errors and warnings**. Hosted Actions results must be assessed separately; a source test is not a host build.

**Release gate still open:** No fork-owned release exists as of November 5, 2026. A full Cardinal plugin binary, real module-browser rendering, MIDI/audio audition, DAW save/reopen, host automation, multi-platform installation and CPU/latency benchmarking remain unverified. The build fixes above must pass a fresh hosted run before a build can be called successful.

## Previous six-agent integration — 2026-11-02

**Merged source checkpoint:** [`2f14a2f`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/2f14a2f3ea4a10557385cac62db022658927c5f0), integrating six independently developed pull requests:

- [#119](https://github.com/boop-bip80/MODULAR-SYNTH/pull/119) adds the original **Dual VCA** (two 16-lane amplifiers, linear-to-cubic envelope response, 2 ms smoothing, bounded stereo/mix outputs), its original panel, source contracts, and a stereo Morph VCO factory-patch route.
- [#117](https://github.com/boop-bip80/MODULAR-SYNTH/pull/117) adds a 16-voice fixed-duty polyBLEP pulse generator to **Module Forge**, with source-backed spectral and compiler regressions.
- [#114](https://github.com/boop-bip80/MODULAR-SYNTH/pull/114) extends versioned **Instrument Builder** Macro8 destination mappings to ChanceHold's five real CV inputs, retaining old bundle interpretations.
- [#115](https://github.com/boop-bip80/MODULAR-SYNTH/pull/115) adds deterministic 1/2/4-layer stereo **FMVoice WAV unison** rendering; this is an offline DSP example, not a plugin voice option.
- [#116](https://github.com/boop-bip80/MODULAR-SYNTH/pull/116) adds a strict **source-verified audio-route** option, distinguishing audio-port paths through first-party processors from CV-only or opaque connections.
- [#118](https://github.com/boop-bip80/MODULAR-SYNTH/pull/118) adds **manifest-derived release safeguards**: a linked Linux ELF identifier check and source archives requiring every declared module's wrapper, DSP header, SVG panel and current manifest.

**Independently executed on that exact merged source:** **477/477 Python tests** (296 repository/CI/patch, 63 Module Forge, 118 Instrument Builder) and **60/60 compiled C++ DSP profiles** (15 suites under strict, production, aggressive fast-math and UBSan). Source checks cover **nine registered original modules**, **sixteen factory patches**, **nine panels / 121 conservative widget centers**, and a strict provenance audit with **zero errors and warnings**. ASan+UBSan was unavailable at runtime, so UBSan alone is claimed.

**Still open:** the [hosted full-build matrix](https://github.com/boop-bip80/MODULAR-SYNTH/actions/workflows/build.yml), genuine nine-module Rack SDK compile/link and actual Cardinal/DAW load, MIDI/audio, GUI, automation, save/reopen, CPU/latency and distributable fork release. At the checkpoint, hosted build and quality jobs were **queued, not passing**; **no fork-owned release** was published. Offline checks do not establish host correctness.

## First-party source milestones — through 2026-11-05

The following additions are **merged into this fork's `main` branch**:

- [**Morph VCO**](plugins/ModularSynth/src/MorphVCO.cpp): original 16-channel sine/saw/pulse oscillator with 1 V/oct tracking, exponential FM, pulse-width modulation and polyBLEP edge correction. [DSP contract and measured limitations](docs/MORPH_VCO.md).
- [**State Filter**](plugins/ModularSynth/src/StateFilter.cpp): original 16-channel TPT state-variable filter with simultaneous low-pass, band-pass and high-pass outputs, resonance, drive and CV controls. [DSP details](docs/STATE_FILTER.md).
- [**Macro8**](plugins/ModularSynth/src/Macro8.cpp): eight named performance CV outputs, individual bipolar/unipolar ranges, four versioned snapshot slots and smooth transitions. It provides source-level metadata for the offline [Instrument Builder](docs/INSTRUMENT_BUILDER.md), not an embedded instrument GUI.
- [**StereoEcho**](plugins/ModularSynth/src/StereoEcho.cpp): original 16-lane stereo delay with bounded ping-pong feedback, CV-adjustable time/feedback/wet controls, 10 ms wet/feedback/crossfeed automation smoothing, and a −400 dB dry/output denormal floor in addition to finite feedback-ring safeguards. [DSP specification and limits](docs/STEREO_ECHO.md).
- [**Clocked LFO**](plugins/ModularSynth/src/ClockedLFO.cpp): original 16-lane CV modulator with four ±5 V wave outputs, an end-of-cycle trigger and external-pulse clock ratios; it free-runs when valid pulses are absent. [Source timing and synchronization contract](docs/CLOCKED_LFO.md). Its example connects Cardinal HostTime pulses; the module itself does not read DAW tempo.
- [**Fold Drive**](plugins/ModularSynth/src/FoldDrive.cpp): original 16-lane sine-transfer wavefolder with drive, bias and wet CV, deferred reset and first-order analytic antiderivative antialiasing (ADAA). [DSP contract, original 12 HP panel and spectral tests](docs/FOLD_DRIVE.md). Selected high-frequency tests measure **8.18–13.86 dB lower alias energy** versus the earlier naïve fold. A dry→wet CV-reopening and reset regression preserves ADAA input history across automation. It is **not completely alias-free or oversampled**; real host CPU, listening quality and summed polyphonic headroom remain unmeasured.
- [**FM Voice**](plugins/ModularSynth/src/FMVoice.cpp): original 16-lane two-operator phase-modulation oscillator with modulator ratio, index and feedback CV, per-voice reset/retirement, a first-party 12 HP panel and a [source-checked FM performance patch](patches/examples/MODULAR_-_FM_Voice_Performance.vcv). [DSP contract and aliasing limits](docs/FM_VOICE.md). A high-frequency modulation-index guard reduces two selected folded alias components by 22.60 dB and 17.35 dB in coherent source tests, with ~2 ms ceiling slew; FM sidebands are **not fully bandlimited or oversampled**, and live Rack/DAW behavior remains unverified.
- [**Chance Hold**](plugins/ModularSynth/src/ChanceHold.cpp): original 16-lane deterministic probabilistic sample-and-hold control-voltage generator with per-lane seeded state, free/external clock, Schmitt reset, glide, 1/12 V quantization, stepped/smoothed CV and 1 ms accepted-event trigger. Includes an original [16 HP panel](plugins/ModularSynth/res/ChanceHold.svg), [DSP contract](docs/CHANCE_HOLD.md), and [FM Drift source example](patches/examples/MODULAR_-_Chance_Hold_FM_Drift.vcv). Its standalone DSP passes strict/fast-math/UBSan source tests; real Rack and DAW loading are not yet verified.
- [**Dual VCA**](plugins/ModularSynth/src/DualVCA.cpp): original dual 16-channel voltage-controlled amplifier with linear-to-cubic envelope response, independent gain/CV, 2 ms smoothing, A/B and bounded SUM outputs, and an original 12 HP panel. The stereo [Morph VCO Performance](patches/examples/MODULAR_-_Morph_VCO_Performance.vcv) source patch now routes through it. [DSP contract and limits](docs/DUAL_VCA.md); host audio and DAW loading remain unverified.
- [**Module Forge**](docs/MODULE_FORGE.md): generate an original 16-voice sine, opt-in polyBLEP saw (`--waveform saw`), fixed-duty polyBLEP pulse (`--waveform pulse`) or polyBLAMP triangle (`--waveform triangle`) oscillator **or** stereo CV-controlled low-pass effect with C++/SVG/manifests, provenance notices and reviewed static registration through dry-run/opt-in `--apply`. Generated HEADLESS wrappers compile and execute against a **test-only Rack shim**; the separate [pinned real-Rack header gate](.github/workflows/module-forge-real-headers.yml) is configured to syntax-check **five generated variants (sine, saw, pulse, triangle and stereo TPT effect)** against genuine pinned Rack/DPF/Jansson headers; **2/2 earlier variants had a historical local pass**, while the current five-variant hosted result remains unverified. Generated oscillator/effect starters retire inactive polyphonic phase/filter states before voice reuse. The integrator rejects inconsistent existing source/manifest or C++ loader/extern registries **and cross-registry model identity drift**. Neither gate links a Cardinal plugin, loads a module in a host or provides runtime loading.
- [**Instrument Builder**](docs/INSTRUMENT_BUILDER.md): deterministic `.msinstrument` source ZIPs with versioned Macro8 performance metadata and byte-preserved `.vcv`; offline `pack`, `inspect`, `unpack`, SVG `preview` (opt-in v2 `preview --show-routes` visualization), source `check`, musician-readable `routes`/`routes --json`, and `controls`/`controls --json` reports of all saved Macro8 knob, snapshot and route-fanout data; `diff`/`diff --json` compares independently validated source bundles, with optional `--fail-on-change` to gate saved semantic drift. Opt-in v2 maps direct Macro8 cables to **eight source-verified first-party destination modules** (MorphVCO, StateFilter, StereoEcho, ClockedLFO, FoldDrive, FMVoice, ChanceHold and DualVCA), including four FMVoice CV inputs, DualVCA audio/CV ports and a zero-input Macro8 contract. Cumulative versioned markers preserve exact historical v2 archive interpretations; v1 remains the default. Strict `check --require-verified-routes` fails unverified direct routes and tampered mapping contracts. These contracts do **not** prove host wiring, automation or audio, and the bundle does **not** export runnable VST3/CLAP/AU/standalone instruments.
- [**Patch workflow**](docs/PATCH_WORKFLOW.md): offline `.vcv` inspector, [semantic patch comparison](docs/PATCH_COMPARISON.md), a [dynamic eighteen-example catalog](docs/FACTORY_PATCHES.md) and [source-backed coverage matrix](docs/PATCH_COVERAGE.md) for **all nine registered first-party models**. The inspector validates narrow, checked-in Cardinal HostMIDI/HostTime/HostAudio2 port contracts and warns on unknown external ports. The eighteen `MODULAR_-_*.vcv` examples include pads, bass, eight-voice motion, stereo echo, four-scene [Echo Motion performance](patches/examples/MODULAR_-_Echo_Motion_Performance.vcv), [Aurora Glass Bells](patches/examples/MODULAR_-_Aurora_Glass_Bells.vcv), [Night Lanterns](patches/examples/MODULAR_-_Night_Lanterns_Dual_Timbre.vcv), HostTime-driven [Clocked Modulation Studio](patches/examples/MODULAR_-_Clocked_Modulation_Studio.vcv), free-running [Cinematic Pulse Score](patches/examples/MODULAR_-_Cinematic_Pulse_Score.vcv), [Noir Expressive Lead](patches/examples/MODULAR_-_Noir_Expressive_Lead.vcv), [Fold Drive Cinematic Motion](patches/examples/MODULAR_-_Fold_Drive_Cinematic_Motion.vcv), three arrangements using bundled community modules and FM Voice/Chance Hold FM examples. A source-only HostAudio2 audit diagnoses missing terminal wiring, CV-only paths and generators without directed host routes; optional host, generator and source-verified stereo gates are graph checks, **not** evidence of audible signal. Semantic comparison detects saved MIDI/module state, bypass/version, parameter-entry and cable metadata, and non-visual configuration changes while ignoring view-only layout. Saved graphs are checked, but **the eighteen factory sounds have not been independently auditioned inside a DAW**.
- **Cable decluttering:** View → Show patch cables or Ctrl/Cmd+Shift+H, preserving the previous visible-opacity setting.
- [**CI and DSP quality work**](docs/CI.md): offline repository, Module Forge and Instrument Builder tests plus DSP optimization/UBSan profiles; [pinned real Rack-header gate configured for nine originals](.github/workflows/real-rack-headers.yml) (**7/7 historical local real-header HEADLESS syntax pass; current nine-module hosted check pending**) and [five configured generated starters](.github/workflows/module-forge-real-headers.yml) (**2/2 historical local syntax pass; current five-variant hosted check pending**). A historical source gate compiled seven original wrappers to objects and linked a temporary ELF; this does **not** build a loadable Cardinal plugin. Cold-cache macOS/Windows/WebAssembly/MOD build-and-package steps no longer depend on cache hits; package and missing-artifact guards were tightened. Pinned SpeexDSP, FLAC and Inno Setup mitigations address known third-party failures; the source-release gate rejects mis-rooted or first-party-incomplete archives. The 2026-11-05 fix removes the OpenGL requirement from its version lookup and Rack-incompatible Macro8 trigger initialization, but **a fresh hosted full build is still needed**. These are source/CI safeguards, not proof of a released plugin.
- [**Panel, controls and provenance QA**](docs/QA_UI.md): source-geometry tests for **nine** original panels (121 conservative Rack widget centers), improved MorphVCO dial-outline contrast, advisory source-color/contrast analysis including base-gradient lower bounds with label-underlay appearance still requiring rendered UI review, and source-grounded control/CV tooltips. A [license/provenance audit](docs/COMPLIANCE_QA.md) passes its **strict first-party notice checks**; this is neither legal clearance nor a live UI/DAW test.
- [**Measured DSP evidence**](docs/STATE_FILTER.md): 162 LP/BP/HP reference-response cases (maximum 0.0077 dB deviation), [786,432 filter CV calls](docs/FILTER_STABILITY.md), and [24 oscillator alias-power comparisons](docs/OSCILLATOR_ALIASING.md) showing more than 13.8 dB reduction versus naïve saw/pulse edges. FoldDrive ADAA now measures 8.18 dB lower alias energy at 8.1 kHz/44.1 kHz and 13.86 dB at 10.4 kHz/48 kHz in controlled source tests; StereoEcho now rejects microscopic dry/output denormals under standalone stress; FMVoice's high-frequency index guard reduces selected coherent folded sidebands by **22.60 dB** and **17.35 dB** in two 48 kHz test tones while preserving a 440 Hz low-note case. These are **standalone, selected-bin** measurements, not complete anti-aliasing or host listening tests.
- [**Offline WAV demo**](docs/AUDIO_RENDER.md): a standalone C++17 MorphVCO → StateFilter renderer creates deterministic four-second, 16-note stereo WAV examples at 44.1/48/96 kHz, optionally processing the real StereoEcho DSP (`--with-stereo-echo`, fixed 187.5 ms delay/32% feedback/35% wet/70% crossfeed), with bounded optional one- or two-second natural echo tails via `--tail-seconds 1|2`. A separate [FMVoice renderer](tools/audio-render/fm_voice_render.cpp) now offers FM-versus-sine WAV reference output, with four compiled/PCM regression tests. The MorphVCO/StateFilter [source tests](tests/test_audio_render.py) check signal activity, dry/echo delay-onset behavior, transitions, sample-rate repeatability and existing-file protection; the 48 kHz PCM FNV-1a digest is `c3bca79532bd36ad`. This does **not** exercise Cardinal’s plugin, GUI, host MIDI or a DAW.

**Earlier independently executed merged-main source verification (2026-11-02; PRs [#106–#112](https://github.com/boop-bip80/MODULAR-SYNTH/pull/112) integrated at [`7793120`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/77931207dc6285ab8afc9b8da5141c8c86d46005)):** A local pre-merge integration tree combining all six workstreams passed **447/447 Python tests** (278 repository/patch/CI, 57 Module Forge, 112 Instrument Builder) and **56/56 compiled-and-executed standalone C++ DSP profiles** (14 suites × strict, production, aggressive fast-math and UBSan). Source contracts cover eight registered modules, sixteen factory patches, eight SVG panels and 110 conservative widget centers. The new ChanceHold wrapper was exercised with a test Rack shim; its *real* Rack/DPF/Jansson compile/link and actual host loading remain unverified. The real-header workflows are now configured for eight original modules and three generated variants, but previous executed seven-original/two-generated checks belong to older source snapshots. ASan+UBSan was unavailable under ptrace. The completed cross-platform Cardinal binary, host GUI/MIDI/audio, DAW save/reopen, host CPU/latency measurements and fork-owned release **remain unverified**.

**Previous independent merged-main source verification (2026-11-02; tested [`f8b1c42`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/f8b1c42abc709fe78a4a47c2623f2ca82fe59874)):** **431/431 Python tests passed** (274 repository/patch/CI, 55 Module Forge, 102 Instrument Builder), plus **52/52 compiled and executed standalone C++ DSP profiles** (13 suites × strict, production, aggressive fast-math and UBSan). All **seven original Rack HEADLESS wrappers compiled to objects and linked into a temporary ELF** against the genuine pinned Rack/DPF/Jansson headers, with unresolved host imports deliberately allowed; **2/2 generated starters also passed real-header syntax checks**. Fifteen factory patch HostAudio2/directed-generator route checks passed and strict first-party provenance reported **0 errors and 0 warnings**. Selected standalone StereoEcho 48 kHz abrupt delay-time jumps fell from about 8 V to below 0.28 V; this is not a host listening result. Combined ASan+UBSan was unavailable under ptrace. **No loadable Cardinal plugin, full hosted build, DAW audition, host UI/CPU verification or fork-owned release is established.**

**Previous independent integrated source verification (2026-11-02; tested [`87d27f3`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/87d27f341b56e3229a7a98ac6b73bf5f63510aa3)):** **409/409 Python tests passed** (265 repository/patch/CI, 51 Module Forge, 93 Instrument Builder) and **48/48 standalone C++ DSP compiler/runtime profiles passed** (12 suites, including UBSan; combined ASan+UBSan unavailable). The opt-in HostAudio2 and generator-route audits passed all 15 factory patches; seven-panel source geometry checked 97 candidate centers, strict first-party provenance returned zero warnings/errors, and 84 local label underlays remain visually UNKNOWN. The newly hardened source-release gate checks all eight first-party wrappers/headers/panels, but the [latest full-build](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41386608744), [real-header](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41386608694) and [source-quality](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41386608738) jobs were **queued, not passing**, at the exact source check; no complete linked plugin, host/DAW audition, saved-project roundtrip, measured host CPU, fork binary or release is claimed.

**Additional genuine-header compatibility result (2026-11-02; same [`87d27f3`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/87d27f341b56e3229a7a98ac6b73bf5f63510aa3) source):** GCC 13.3.0 compiled **7/7 original** and **2/2 freshly generated Module Forge** HEADLESS translation units with `-fsyntax-only` against exact pinned Rack/DPF/six nested dependency Gitlinks and official Ubuntu 24.04 Jansson 2.14-2build2 headers. The generated SpeexDSP type header was temporary. This **is not a linked plugin build, host ABI check, GUI test or DAW audition**; the hosted real-header job remained queued and must be assessed separately.

**Previous independently executed source verification (2026-11-02; tested [`060a2a83`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/060a2a83b6803e61e63eabf9bcbf631eb488c5c2)):** **391/391 Python tests passed** (257 repository/patch/CI, 49 Module Forge, 85 Instrument Builder) and **48/48 compiled standalone DSP profiles passed** across 12 suites, including UBSan. Source-panel geometry passed for seven panels/97 candidate widget centers; 84 label underlays remain visually UNKNOWN. The separate offline 15-example HostAudio2 output-route audit and strict first-party license/provenance check passed. The pinned real-header gate is configured for FMVoice but **no seventh-original genuine-header pass, complete linked plugin build, live host/DAW audio, save/reopen, verified fork binary or release is claimed**. GitHub Actions jobs may remain queued; see their live status.

**Earlier verified source/DSP snapshot (2026-11-02; tested source commit [`46c5587`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/46c558753ec65893350bb21208ca1d876131cd3e)):** **370/370 Python tests passed** across **243/243 repository/patch/CI**, **48/48 Module Forge** and **79/79 offline Instrument Builder** cases. Eleven standalone DSP suites passed **44/44 compiled-and-executed compiler profiles including UBSan** ([DSP runner](tests/run_dsp_tests.py)); combined ASan+UBSan was unavailable at runtime, so no ASan pass is claimed. Six source panels/86 conservative widget centers pass geometry, while **71 local label-underlay comparisons remain UNKNOWN**. Prior genuine pinned Rack/DPF/Jansson HEADLESS `-fsyntax-only` checks passed **6/6 original** and **2/2 generated** source units; they do not link or load Cardinal. The 44.1/48/96 kHz offline WAV harness tests deterministic dry and optional StereoEcho PCM, not host audio. **No current-main complete linked plugin build, live module browser, DAW save/reopen, host CPU measurement, accessible UI certification or fork-owned release is verified.**

**Current source improvements:** [Chance Hold and eight-model registration (#112)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/112) · [validated instrument diff follow-up (#111)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/111) · [instrument diff (#110)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/110) · [FMVoice denormal/guard hardening (#109)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/109) · [natural echo tails (#108)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/108) · [RISC-V multiarch CI fix (#107)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/107) · [generated saw real-header gate (#106)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/106).

**Previous source improvements:** [FMVoice offline WAV demo (#100)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/100) · [Instrument Builder route-aware SVG (#101)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/101) · [Module Forge polyBLEP saw (#102)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/102) · [signed FM feedback (#103)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/103) · [real-Rack object/link smoke (#104)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/104) · [StereoEcho time-jump crossfade (#105)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/105).

**Previous round source improvements:** [StereoEcho denormal protection (#94)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/94) · [seven-module release-archive validation (#95)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/95) · [Module Forge cross-registry identity checks (#96)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/96) · [directed generator-route diagnostics (#97)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/97) · [versioned FMVoice Instrument Builder routes (#98)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/98) · [FMVoice high-frequency bandwidth guard (#99)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/99).

**Earlier source improvements:** [StereoEcho automation smoothing (#88)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/88) · [Module Forge voice retirement (#89)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/89) · [HostAudio2 patch diagnostics (#90)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/90) · [source release archive gates (#91)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/91) · [Macro8 controls inventory (#92)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/92) · [FM Voice engine and patch (#93)](https://github.com/boop-bip80/MODULAR-SYNTH/pull/93).

**What has not passed yet:** Although an earlier Linux plugin-validation build and several Linux/Windows artifacts succeeded, the complete platform matrix, interactive module-browser visual check, real DAW audio audition, DAW patch save/reopen, system-level host CPU/latency benchmarks, macOS/MOD hardware binaries and a public fork-owned Release remain unverified. These are mandatory gates, not implied by successful automated plugin bridge or standalone DSP tests. See [Actions](https://github.com/boop-bip80/MODULAR-SYNTH/actions) and [the roadmap](docs/DEVELOPMENT_ROADMAP.md).

**Superseded, still unmerged:** [PR #20](https://github.com/boop-bip80/MODULAR-SYNTH/pull/20) remains held; the independently reviewed, additive [offline audio-renderer PR #78](https://github.com/boop-bip80/MODULAR-SYNTH/pull/78) is now merged into `main`. The renderer is a standalone source-level demonstration, **not** a verified plugin/DAW feature or downloadable fork release.

## What exists now, and what is planned

| Area | Implemented in source | Next verification or development goal |
| --- | --- | --- |
| Modular patching | Inherited Rack graph, cable toggle, **eighteen** first-party `.vcv` examples, source inspector, semantic saved-state comparison, dynamic catalog, nine-module patch coverage and cable-by-cable source-verified HostAudio2 route diagnostics | Real host loading/MIDI/audio, reusable presets, navigation and graph diagnostics in a built DAW plugin |
| Sound engines | **Nine registered originals:** MorphVCO, StateFilter, FoldDrive with ADAA, Macro8, StereoEcho with cubic fractional reads, ClockedLFO, FMVoice, ChanceHold and DualVCA; source DSP stability/alias/delay/clock/fold regressions and deterministic offline WAV rendering | Full plugin build, DAW auditions, measured host CPU/latency, and further spectral/granular/physical-modeling engines and more comprehensive/oversampled FM antialiasing |
| Module development | Module Forge sine/saw/pulse/triangle oscillator and effect C++/SVG generation, provenance checks, opt-in static integrator with registry-drift preflight, shim-backed processing smoke and **five configured genuine pinned Rack-header syntax checks** (historical 2/2 local execution on earlier code) | Build, browse, play and reload generated modules with the real Rack SDK inside a linked Cardinal plugin |
| Instrument design | Macro8 saved scenes; `.msinstrument` v1/v2 offline source bundles; **eight source-verified destination models** including DualVCA, strict direct-route checks, versioned legacy compatibility, readable `routes`/`controls` JSON reports and SVG preview | Nested/grouped modules, live custom panels, real DAW state/automation roundtrip and actual instrument/plugin export |
| UI and interaction | Source-backed units/tooltips, nine-panel SVG geometry, advisory contrast tests and measured higher-contrast MorphVCO dials, cable decluttering | Human visual/keyboard/accessibility QA in a real host editor; automation and MIDI behavior |
| Distribution and provenance | Offline Python/DSP regression suites, UBSan profile, **9 historical local real-header syntax checks** (7 original, 2 generated; nine/five configured on current source) plus a **seven-wrapper historical temporary object/link smoke** (not a Cardinal plugin), [first-party license/provenance audit](docs/COMPLIANCE_QA.md), pinned dependency preflights and updated build/release-asset gates | Completed hosted plugin artifacts, third-party license review, live QA, original screenshots/demos, signed/install-tested release packages and fork downloads |

The third column describes planned capabilities; none is a claim of a verified or published release.

## Development roadmap and acceptance gates

Our [six-phase development roadmap](docs/DEVELOPMENT_ROADMAP.md) defines scope, dependencies and verifiable exit criteria:

1. **Phase 1 — Foundation and first original module:** provenance, first-party oscillator, developer baseline, initial usability and patch work, reproducible validation.
2. **Phase 2 — Module Forge:** a documented workflow to create, register, build and test new DSP modules.
3. **Phase 3 — Instrument Builder:** group patches, expose macros and custom panels, save/reopen and automate instruments.
4. **Phase 4 — Flagship sound engines:** original analog-inspired, spectral, granular, FM, physical-modeling and effects modules.
5. **Phase 5 — Production readiness:** professional UI, host compatibility, accessibility, performance, robust release packaging.
6. **Phase 6 — Experimental frontier:** opt-in AI assistance, generative composition and research-grade extensibility.

**A phase only closes when all required evidence exists.** We will not use feature counts or unsupported completion percentages as substitutes for running builds, listening tests, regression suites and DAW project roundtrips.

## Build and downloads

- **Fork release downloads:** [MODULAR-SYNTH releases](https://github.com/boop-bip80/MODULAR-SYNTH/releases). **No fork-owned release was available at the 2026-11-02 post-merge check.** Do not use inherited upstream Cardinal screenshots or download links as evidence of a MODULAR-SYNTH binary.
- **Fork CI:** [MODULAR-SYNTH Actions](https://github.com/boop-bip80/MODULAR-SYNTH/actions). The inherited [cross-platform build workflow](.github/workflows/build.yml) now runs macOS, Windows, WebAssembly and MOD build/packaging stages on cold caches, corrects the macOS `.pkg` input filename, and rejects missing release assets for Linux/WebAssembly as well as existing Windows/macOS checks. The pinned SpeexDSP mirror, SHA-256-verified FLAC download and [checksum-pinned Inno Setup fetch](docs/CI.md) address prior external failures; source tarball release uploads reject missing, empty, unreadable, mis-rooted or first-party-incomplete archives. **A hosted full fork build, installations, audio-host behavior and release remain unverified.** At the exact post-merge `16198d99` checkpoint, [source](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41371248131), [original real-header](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41371248236) and [full-build](https://github.com/boop-bip80/MODULAR-SYNTH/actions/runs/41371248164) jobs were queued or pending; see live Actions for changes.
- **Real Rack header checks:** The [nine-original module gate](.github/workflows/real-rack-headers.yml) and [five generated starter gate](.github/workflows/module-forge-real-headers.yml) use genuine pinned Rack/DPF/Jansson HEADLESS headers rather than the test-only shim. A historical local integration pass verified **7/7 original plus 2/2 generated `-fsyntax-only`** checks on exact source [`87d27f3`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/87d27f341b56e3229a7a98ac6b73bf5f63510aa3). Another historical source snapshot [`f8b1c42`](https://github.com/boop-bip80/MODULAR-SYNTH/commit/f8b1c42abc709fe78a4a47c2623f2ca82fe59874) passed **seven real-Rack object compiles and one temporary ELF link**, plus **2/2 generated syntax checks**; see [evidence limits](docs/CI.md#real-rack-header-compatibility-preflight). **Current nine/five hosted checks and a loadable Cardinal plugin remain unverified.**
- **Source checkout:** `git clone --recurse-submodules https://github.com/boop-bip80/MODULAR-SYNTH.git`
- **Source build:** Follow [Cardinal's inherited build instructions](docs/BUILDING.md). They describe an upstream build process; they are not evidence of a completed fork build.

**Important:** The Cardinal release/download links and screenshots in the upstream reference section below belong to **DISTRHO/Cardinal**, not this fork. Do not treat those artifacts as MODULAR-SYNTH releases. We will add fork-specific download links and screenshots only after successful builds and verification.

## Contributing and engineering rules

Contributions should focus on original capabilities, verified sound quality and a maintainable codebase. Start with the [musician getting-started guide](docs/GETTING_STARTED.md), [nine-module quick reference](docs/MODULE_QUICK_REFERENCE.md), [the roadmap and PR acceptance policy](docs/DEVELOPMENT_ROADMAP.md), [project structure](docs/OVERVIEW.md), [build instructions](docs/BUILDING.md), [first-party provenance preflight](docs/COMPLIANCE_QA.md) and [third-party license inventory](docs/LICENSES.md). Each PR should include an explicit behavior change, evidence of tests or exact reproduction steps, and accurate limitations. Keep `src/override/` modifications small and justified because they track upstream Rack implementation details.

Cardinal is licensed under **GPL-3.0-or-later**, while bundled modules, artwork, fonts and dependencies can have separate licenses. Preserve original copyright notices and obtain any necessary permissions before introducing or redistributing assets. MODULAR-SYNTH does not incorporate VCV Rack Pro proprietary code or proprietary paid modules.

## Upstream attribution

This repository is derived from **[DISTRHO Cardinal](https://github.com/DISTRHO/Cardinal)** by Filipe Coelho/falkTX and contributors, itself using the [VCV Rack](https://github.com/VCVRack/Rack) engine and numerous open-source modules. Its architecture, original modules, compatibility layers, build workflow and extensive existing sound libraries are primarily upstream work. This fork's distinctive features will be identified by original commits and documented evidence, not implied ownership of the inherited source.

---

## Upstream Cardinal README (reference, retained for attribution and inherited behavior)

The following material is the inherited Cardinal README. References to `DISTRHO/Cardinal` releases, build downloads, screenshots, status and project policies describe the **upstream Cardinal project**; fork-specific information is maintained above and in our roadmap.

# Upstream reference: DISTRHO Cardinal

*Cardinal, the Rack!*

Cardinal is a free and open-source virtual modular synthesizer plugin,
available in AudioUnit/CLAP/LV2/VST2/VST3 plugin formats and as a standalone app for FreeBSD, Linux, macOS, Windows and the Web.  
It is based on the popular [VCV Rack](https://vcvrack.com/) but with a focus on being a fully self-contained plugin version.

More specifically, this is a [DPF-based](https://github.com/DISTRHO/DPF/)
plugin wrapper around [VCV Rack](https://github.com/VCVRack/Rack/),
using its code directly instead of forking the project,
with the target of having a **self-contained, fully free and open-source plugin version of Rack**.  
See the [why section](#Why) below for the reasons Cardinal exists,
also for frequently asked questions check this [FAQ document](docs/FAQ.md).

Cardinal contains Rack, some 3rd-party modules and a few internal utilities all in a single binary.  
All "Core" modules from Rack have been replaced by Cardinal equivalents, simplified to better work for an audio plugin.

Cardinal does not load external modules and does not connect to the official Rack library/store.  
All VCV branding has been removed (to the best of our knowledge) in order to avoid any trademark issues.


## Current status

Cardinal should be considered stable, if you spot any bugs please report them.  
Currently the following should be noted:

- CLAP support is a work-in-progress [DPF#383](https://github.com/DISTRHO/DPF/issues/383)
- VST3 plugin hosting (inside [Carla](https://github.com/falkTX/Carla/) or [Ildaeil](https://github.com/DISTRHO/Ildaeil) modules) mostly works but is considered experimental
- Windows 32bit builds still have a few problematic modules [#80](https://github.com/DISTRHO/Cardinal/issues/80)

### Stable release

Cardinal releases have official builds for Linux, macOS and Windows.  
You can find these under https://github.com/DISTRHO/Cardinal/releases.

#### Installing & Updating releases
See our Wiki on installing official builds [Wiki/Install](https://github.com/DISTRHO/Cardinal/wiki/Install).
There are additional notes in [BUILDING.md#installing](docs/BUILDING.md#installing)

There are Linux builds for various architectures (armhf, arm64, i686, riscv64 and x86_64), macOS "universal" (arm64 + intel) and Windows 32 and 64bit builds.
Both macOS and Windows builds have an installer.  

Note: Neither the macOS or Windows builds are signed, so expect warnings saying they are from an "untrusted developer".

### Nightly builds

You can find builds for pretty much any recent Cardinal commit [here](https://github.com/DISTRHO/Cardinal/actions/workflows/build.yml).  
Just click on any successful build, and scroll to the bottom to find the builds.  
(note the canvas-like area in the middle prevents mouse wheel scrolling)

A GitHub account is required in order to download these builds.

### Building

Basic building instructions are available in [BUILDING.md](docs/BUILDING.md).

## Plugin variants

Cardinal provides 3 plugin variants - "main", Synth and FX.  
They are all equivalent in performance and behaviour, with only the IO and metadata that changes.  
This is because some hosts are very strict on which plugins are allowed as instruments vs FX, so separate variants of the same plugin are needed.

FX and Synth variants both have 2 audio outputs, while "main" has 8.  
All variants have MIDI input and output support.

### Main

This variant provides 8 audio inputs and outputs and 10 CV inputs and outputs.

NOTE: Due to AU and VST2 formats not supporting CV ports, this variant is not available for those formats.  
NOTE: This variant is not available in CLAP yet, to be added in a later release

### Synth

This variant provides 2 audio outputs but no audio inputs or CV ports.  
Plugin type is set as "instrument".

### FX

This variant provides 2 audio inputs and outputs, but no CV ports.  
Plugin type is set as regular "effect".

### Mini

This is a special variant with a very small, hand-picked module selection and limited IO (2 audio ports plus 5 CV).  
It only exists as LV2 and Standalone plugin.

For now the list of selected modules is quite small, intentionally. We will add a few more as the need appears.  
All included modules support polyphony, reducing confusion for new users not yet used to mono vs poly approach in Rack/Cardinal.

The main reason for this variant to exist is being able to support DSP/UI separation, which is only possible with more simple modules.  
The DSP/UI separation means we can run the DSP on a different machine than the UI.  
This is particularly interesting for running Cardinal on embed systems, being controlled remotely via a web browser or a native desktop application.  
Such setup is already in use in [Cardinal Mini for MOD Audio](https://forum.mod.audio/t/distrho-cardinal-mini/9262/).


## Screenshots

Because people will ask for it. It is, well... Rack.  
But a couple of modules background's have their colors flipped, because damn we want proper dark mode!

### Module browser

![screenshot](docs/Screenshot_Module-Browser.png "Screenshot")

### Basic patching

![screenshot](docs/Screenshot_Basic-Patching.png "Screenshot")

### [Carla](https://github.com/falkTX/Carla/) and [Ildaeil](https://github.com/DISTRHO/Ildaeil) plugin hosts

![screenshot](docs/Screenshot_Carla+Ildaeil.png "Screenshot")

### Custom Fundamental modules design

![screenshot](docs/Screenshot_Fundamental.png "Screenshot")


## Included modules

At the moment the following 3rd-party modules are provided:

- [21kHz](https://github.com/netboy3/21kHz-rack-plugins)
- [8Mode](https://github.com/8Mode/8Mode-VCV_Modules)
- [Aaron Static](https://github.com/aaronstatic/AaronStatic_modules)
- [Admiral](https://github.com/wapiflapi/admiral)
- [alef's bits](https://github.com/alefnull/alefsbits)
- [AlgoritmArte](https://github.com/algoritmarte/AlgoritmarteVCVPlugin)
- [Amalgamated Harmonics](https://github.com/jhoar/AmalgamatedHarmonics)
- [Animated Circuits](https://github.com/AnimatedCircuits/RackModules)
- [Arable Instruments](https://github.com/adbrant/ArableInstruments)
- [Aria Salvatrice](https://aria.dog/modules/)
- [AS](https://github.com/AScustomWorks/AS)
- [Audible Instruments](https://vcvrack.com/AudibleInstruments)
- [Autinn](https://github.com/NikolaiVChr/Autinn)
- [Axioma](https://github.com/kauewerner/Axioma)
- [Bacon Music](https://github.com/baconpaul/BaconPlugs)
- [Befaco](https://github.com/VCVRack/Befaco)
- [Bidoo](https://github.com/sebastien-bouffier/Bidoo)
- [Biset](https://github.com/gibbonjoyeux/VCV-Biset)
- [Bogaudio](https://github.com/bogaudio/BogaudioModules)
- [Catro/Modulo](https://github.com/catronomix/catro-modulo)
- [cf](https://github.com/cfoulc/cf)
- [ChowDSP](https://github.com/jatinchowdhury18/ChowDSP-VCV)
- [Computerscare](https://github.com/freddyz/computerscare-vcv-modules)
- [CVfunk](https://github.com/codygeary/CVfunk-Modules)
- [dBiz](https://github.com/dBiz/dBiz)
- [DHE Modules](https://github.com/dhemery/DHE-Modules)
- [eightfold](https://github.com/scanner-darkly/eightfold)
- [EnigmaCurry](https://github.com/EnigmaCurry/EnigmaCurry-vcv-pack)
- [E-Series](https://github.com/VCVRack/ESeries)
- [ExpertSleepers Encoders](https://expert-sleepers.co.uk/vcvrack_encoders.html)
- [Extratone](http://extratone.xyz/modules)
- [Fehler Fabrik](https://github.com/RCameron93/FehlerFabrik)
- [forsitan modulare](https://github.com/gosub/forsitan-modulare)
- [Fundamental](https://github.com/VCVRack/Fundamental)
- [Glue the Giant](https://github.com/gluethegiant/gtg-rack)
- [GoodSheperd](https://github.com/jensschulze/GoodSheperd)
- [Grande](https://github.com/dbgrande/GrandeModular)
- [H4N4 Modules](https://github.com/hannakoppelaar/h4n4-modules)
- [Hampton Harmonics](https://gitlab.com/hampton-harmonics/hampton-harmonics-modules)
- [HetrickCV](https://github.com/mhetrick/hetrickcv)
- [ihtsyn](https://github.com/nysthi/ihtsyn)
- [Impromptu](https://github.com/MarcBoule/ImpromptuModular)
- [JW-Modules](https://github.com/jeremywen/JW-Modules)
- [kocmoc](https://github.com/janne808/kocmoc-rack-modules)
- [LifeFormModular](https://github.com/TimeControlledOrganism/LifeFormModular)
- [Lilac Loop](https://grough.github.io/lilac-loop-vcv)
- [Little Utils](https://github.com/mgunyho/Little-Utils)
- [Lomas Modules](https://github.com/LomasModules/LomasModules)
- [Lyrae Modules](https://github.com/VegaDeftwing/LyraeModules)
- [Meander](https://github.com/knchaffin/Meander)
- [MindMeld](https://github.com/MarcBoule/MindMeldModular)
- [ML Modules](https://github.com/martin-lueders/ML_modules)
- [Mockba Modular](https://github.com/MockbaTheBorg/MockbaModular)
- [Mog](https://github.com/JustMog/Mog-VCV)
- [mscHack](https://github.com/mschack/VCV-Rack-Plugins)
- [MSM](https://github.com/netboy3/MSM-vcvrack-plugin)
- [MUS-X](https://github.com/Jojosito/MUS-X)
- [Myth](https://github.com/Ahineya/vcv-myth-plugin)
- [Nonlinear Circuits](https://github.com/mhetrick/nonlinearcircuits)
- [Orbits](https://github.com/RareBreeds/Orbits)
- [Parable Instruments](https://github.com/adbrant/ArableInstruments)
- [Path Set](https://github.com/patheros/PathSetModules)
- [PdArray](https://github.com/mgunyho/PdArray)
- [PinkTrombone](https://github.com/VegaDeftwing/PinkTromboneVCV)
- [Prism](https://github.com/SteveRussell33/Prism)
- [rackwindows](https://github.com/n0jo/rackwindows)
- [RCM](https://github.com/Rcomian/rcm-modules/)
- [RebelTech](https://github.com/hemmer/rebel-tech-vcv)
- [repelzen](https://github.com/wiqid/repelzen)
- [Sapphire](https://github.com/cosinekitty/sapphire)
- [Sonus Modular](https://gitlab.com/sonusdept/sonusmodular)
- [stocaudio](https://github.com/aptrn/stocaudio-modules)
- [Starling Via](https://github.com/starlingcode/Via-for-Rack)
- [Stoermelder Pack-One](https://github.com/stoermelder/vcvrack-packone)
- [Surge XT](https://github.com/surge-synthesizer/surge-rack)
- [unless_modules](https://gitlab.com/unlessgames/unless_modules)
- [Valley](https://github.com/ValleyAudio/ValleyRackFree)
- [Venom](https://github.com/DaveBenham/VenomModules)
- [Voxglitch](https://github.com/clone45/voxglitch)
- [WhatTheRack](https://github.com/korfuri/WhatTheRack)
- [WSTD-Drums](https://github.com/Wasted-Audio/WSTD-Drums)
- [ZetaCarinae](https://github.com/mhampton/ZetaCarinaeModules)
- [ZZC](https://github.com/zezic/ZZC)

Additionally Cardinal provides its own modules for DAW/Host automation, time position, audio to CV pitch conversion and internal plugin hosting.

### Adding modules

Installing new modules on a Cardinal build is not possible, but we can integrate existing open-source modules to be part of Cardinal.
Details on this are available [here](https://github.com/DISTRHO/Cardinal/discussions/28).  
Also check [this wiki page](https://github.com/DISTRHO/Cardinal/wiki/Possible-modules-to-include)
where we discuss possible modules to include.  

### Module restrictions

All included modules are open-source and have a GPLv3+ compatible license. (GPLv3-only modules are not allowed)  
It is a requirement that the final Cardinal binary is GPLv3+ licensed.

Module dependencies should be kept at a minimum, as otherwise it quickly grows the complexity of the build.  
Online access (such as phone-home) is not allowed.

Worth noting that a few modules have artwork licensed separately from their code.  
These licenses range from CC-0 to CC-NC-ND to custom (used with permission).  
An overview of the included artwork licenses can be seen [here](docs/LICENSES.md#artwork--panel-licenses).

Even though CC-NC is problematic for packaging (some linux distributions are commercial in nature),
Cardinal allows their use because of how prevalent they are across many Rack modules.  
Even the Rack "Component Library" (which can be considered the base widget elements) is CC-NC licensed.

Any artwork that uses a custom license has had explicit permission to be used in Cardinal.


## Why

Cardinal was created first and foremost as a way to have Rack as a **proper open-source audio plugin**.  
A proper audio plugin should be self-contained as much as possible, as to not interfere with the DAW/Host.
Loading external modules clearly goes against this idea.  
Not to mention being **open-source**, otherwise we are at the mercy of the wishes of a company for what we can and cannot do,
which is not something Cardinal's authors wish to abide by.

A self-contained plugin can't be overstated, as DLL/shared-object symbol conflicts can trigger hard-to-debug crashes.  
While Rack tries to mitigate this as much as possible, crashes due to conflicting modules have already been seen in v2 builds.  
On the other side, Cardinal redefines class and function names as needed to avoid as many conflicts as possible.

Support for ARM and non-mainstream platforms (for example BSD) has also always been missing from the official Rack since the start.  
While we can patch the Rack free version to support these, same can't be done with Rack Pro with it being a closed-source product.  
The online library/store only supports a very specific set of platforms too,
so non-supported platforms would need any 3rd-party modules to be manually compiled to make them usable.

Unhappiness with the audio threading behaviour of Rack also plays a role.  
Both audio and MIDI should be locked to the host audio thread as to minimize (or even altogether remove) latency and jitter.  
The use of separate threads for MIDI is bad design, one that has been corrected in DAWs and JACK-MIDI for several years...  
But Rack's use of RtMidi requires separate threading, so Cardinal does not use it.

Other relevant reasons include:

 - LV2 plugin version from the start
 - Proper dark mode support
 - Real CV ports to and from the plugin
 - Removing online access from the plugin and included modules (no phone-home here!)
 - Works as a test case for [DPF](https://github.com/DISTRHO/DPF/) and [Carla](https://github.com/falkTX/Carla/)
 - It is fun :)


## Vs. Rack Pro

It needs to be said that Cardinal project and its author(s) do not wish anything bad to the original/official Rack project.  
In fact, Cardinal wouldn't exist if not for Rack v2 release. (which has many needed things to make a plugin version work)

Cardinal and Rack should be able to co-exist friendly and peacefully, as they clearly have different targets.  
It is likely most people will prefer to use Rack Pro for its official support and its big module collection (including commercial ones).

A feature comparison between Cardinal and Rack Pro can be seen [here](docs/DIFFERENCES.md).


## License

Cardinal is licensed under GPLv3+, see [LICENSE](LICENSE) for more details.  
An overview of the included code and linked submodules can be seen [here](docs/LICENSES.md#code-license--binary).


## Community chat

Currently we are all on #cardinal IRC room in irc.libera.chat server.  
Come join us in your favorite IRC client.
