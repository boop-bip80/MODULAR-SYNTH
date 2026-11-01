# Module Forge — first-party oscillator and effect scaffolding

**Status:** developer tooling with two starter variants, not a live module forge. This is not yet an
in-app source editor, just-in-time DSP compiler, module hot loader, or standalone
plugin exporter. The separate `plugins/ModularSynth` collection is the home
for original modules; it is distinct from the upstream `plugins/Cardinal`
collection.

## What is available

`tools/module-forge/module_forge.py` supports two Rack-compatible C++17 starters:

- **`--kind oscillator` (default, unchanged):** a four-file, 16-voice sine
  oscillator with one 1 V/oct pitch input, continuous phase, reset, and
  bounded frequency across host sample-rate changes.
- **`--kind effect`:** a five-file stereo, 16-voice TPT one-pole low-pass
  effect with left/right audio inputs and outputs, right-input normalled
  from left, and 1 V/oct cutoff CV. Its generated `<Slug>.dsp.hpp` is a
  Rack-independent, standard-library-only DSP core; `<Slug>.cpp` supplies
  Rack module metadata and GUI/headless widgets.
- Both generate an SVG panel, **single-module JSON manifest fragment**, and
  `INTEGRATION.md` outlining the exact first-party build/registration edits.

It creates a new directory and refuses to overwrite a preexisting generated
module. No third-party modules are downloaded.

## Generate your first module

From the repository root:

```bash
python3 tools/module-forge/module_forge.py new \
    --slug OrbitSine \
    --name "Orbit Sine" \
    --out module-forge-output
python3 tools/module-forge/module_forge.py check module-forge-output/OrbitSine
```

Generate a stereo low-pass starter with the same workflow:

```bash
python3 tools/module-forge/module_forge.py new \
    --kind effect \
    --slug StereoTPT \
    --name "Stereo TPT" \
    --out module-forge-output
python3 tools/module-forge/module_forge.py check module-forge-output/StereoTPT
```

The outputs will be `module-forge-output/OrbitSine/` and
`module-forge-output/StereoTPT/`. Read each generated
`INTEGRATION.md` **before** moving source/artwork into
`plugins/ModularSynth` or registering the model in the static loader.
Generated sources are not automatically built or installed.

Module identifiers use stable PascalCase letters and digits (2–40 characters,
first character uppercase). Display names use a conservative subset of ASCII;
this prevents unsafe identifiers and unintended XML content. A given slug must
remain stable after patches begin referring to it.

## Automated scaffolder tests

```bash
python3 -m unittest discover -s tools/module-forge \
    -p "test_*.py" -v
```

Tests cover both deterministic variants, backward-compatible default oscillator
output, manifest and port metadata, C++ model/panel/DSP header references,
refusal to overwrite user-edited files, and invalid identifiers. Integration
fixtures exercise ordinary and effect dry-runs and applies, header collisions,
registry updates, case-insensitive collisions, stale plans, parent symlinks,
interruption, and rollback after injected write failures.
When a C++ compiler is available, `test_effect_core.py` also builds and
executes a standalone C++17 probe against the generated Rack-free filter header:
DC convergence, reset, impulse decay, 44.1/48/96 kHz, and IEEE-bitwise
NaN/Inf input, coefficient, cutoff and sample-rate behavior. Each probe is
compiled and executed with ordinary `-O2`, production-style
`-O2 -ffast-math -fno-finite-math-only`, and strict `-O2 -ffast-math`.
The nonfinite checks inspect raw float exponent bits so strict fast-math
cannot silently fold the test assertions away. This does **not** compile or
load the Rack/Cardinal module.

### Generated wrapper compile/process gate (HEADLESS test shim)

The developer gate now generates **both** fresh starters and checks their
*actual generated* `.cpp` wrappers against the repository's small test-only
Rack stand-in, without installing modules or editing registry files:

```bash
python3 -m unittest discover -s tools/module-forge \
    -p "test_generated_wrappers.py" -v
```

With a C++17 compiler, the test compiles each complete wrapper as its own
translation unit using `-DHEADLESS`, the first-party plugin header, the
`pluginInstance__ModularSynth` compile namespace, and `tests/rack_stub`.
It also compiles and executes a program including both generated wrappers and
the stereo effect's Rack-free DSP header. This checks exported model symbols,
parameter and CV/audio port cardinality, sample processing, two-voice 1 V/oct
pitch tracking, stereo right-input normalled from left, independent stereo
inputs, polyphony, resets, nonfinite audio/CV and invalid sample-rate fallback.
The C++ probe runs under ordinary `-O2`, production-style
`-O2 -ffast-math -fno-finite-math-only`, and strict `-O2 -ffast-math`;
the oscillator uses the same IEEE-754 bitwise finite guard as the effect core.

The test also asks the **dry-run** integrator to plan changes against the
current `plugins/ModularSynth` static collection. It checks both manifest
fragments, **six** oscillator and **seven** effect edits, the source and
resource destinations, `plugins/Makefile` compilation entry,
`plugin.hpp` extern model declaration and exactly-once
`initStatic__ModularSynth()` registration. Nothing is applied.

The generator's HEADLESS widgets intentionally call only `setModule()`;
knobs and jacks are created in the ordinary GUI build path. Both generated
process callbacks use Rack's `getNormalPolyVoltage(0, voice)` API, as existing
first-party modules do. Invalid or nonfinite sample rates fall back to
48 kHz in the starters; they still need real-host sample-rate and audio QA.

**Boundary:** `tests/rack_stub` is a narrow stand-in, *not* the Rack SDK.
Passing this compile/process gate does not prove GUI compilation, upstream
Rack/Cardinal ABI compatibility, plugin load, DAW playback, or audio quality.
Real plugin variants still need the production build and host checks before
shipping.

## Dry-run integration (explicit opt-in)

The scaffolder now has a separate **safe integration command**. It previews
changes to the existing ModularSynth collection without modifying any file:

```bash
python3 tools/module-forge/integrate.py module-forge-output/OrbitSine --repo-root .
```

Review its complete unified diff. Only then apply the same validated plan:

```bash
python3 tools/module-forge/integrate.py module-forge-output/OrbitSine --repo-root . --apply
```

The command prepares **six edits for oscillators** (C++ source and SVG plus
four collection registry files) or **seven for effects** (the same plus
`plugins/ModularSynth/src/<Slug>.dsp.hpp`). The four registries are
`plugins/Makefile`, `plugins/plugins.cpp`,
`plugins/ModularSynth/src/plugin.hpp`, and
`plugins/ModularSynth/plugin.json`. It checks all anchors, model/slug identity,
duplicate registration, case-insensitive destination collisions, UTF-8 and SVG
validity, the exported C++ model symbol, and source/header/compiler namespace
compatibility before writing. It refuses to
overwrite existing source, DSP header, or panel files and refuses changes to unsupported loader
layouts. It never edits the upstream `plugins/Cardinal` collection.

On `--apply`, all replacement content is staged first, then published one
file at a time. Original registry files are backed up during the transaction.
If publication fails, the tool attempts to restore every completed edit and
remove only the new files it created. Multi-file operations cannot be fully
atomic across process crashes. On POSIX the publisher holds no-follow directory
handles to prevent parent symlinks from redirecting writes; on other platforms
it rechecks paths but does not claim security against hostile concurrent edits.
If restoration fails, it prints the retained
`.module-forge-transaction-*` backup directory. Do not remove that directory
until you have recovered the source. Do not run concurrent integration or make
manual edits to the same files while applying.

**Recovery and review:**

1. Before applying, commit/stash unrelated work and inspect `git status`.
2. After applying, inspect `git diff` and run tests/builds before committing.
3. If the command refused, it should have left the project unchanged.
4. If you need to undo a successful integration, review the exact changed paths
   with `git diff -- plugins/Makefile plugins/plugins.cpp plugins/ModularSynth`;
   restore only your intended changes from version control and remove only the
   two generated module files (oscillator) or three (effect, including the
   `.dsp.hpp` header) you just introduced. Avoid broad resets or cleans.
5. If a process crash left `.module-forge-transaction-*`, review the saved
   `.bak` registry snapshots and current files before manually recovering.

This tool is a developer convenience, not an installed-module manager or
untrusted-code sandbox. Review generated C++ and artwork before `--apply`.

## Manual source integration

The current engine compiles approved modules into the plugin binary. The
generated instructions assume the dedicated first-party collection:

| Change | File |
| --- | --- |
| Add the module source | `plugins/ModularSynth/src/<Slug>.cpp` |
| Add the Rack-free DSP header (effect only) | `plugins/ModularSynth/src/<Slug>.dsp.hpp` |
| Install SVG artwork | `plugins/ModularSynth/res/<Slug>.svg` |
| Add the source to the built-in object list | `plugins/Makefile` |
| Declare the exported C++ model pointer | `plugins/ModularSynth/src/plugin.hpp` |
| Register the model with `initStatic__ModularSynth()` | `plugins/plugins.cpp` |
| Append one module object | `plugins/ModularSynth/plugin.json` |

A module's panel must be available before its widget is instantiated. Ensure
the resource pipeline includes the new SVG (the current Cardinal build uses
plugin resource globbing). Changes to Cardinal Mini require an independent
review of the Mini source list, module browser and headless variants.

We deliberately do not expose an arbitrary external binary module loader: it
would be a different architecture, with host-crash isolation, license, security,
ABI, resource ownership and update-compatibility work.

## Audio and module conventions

Both variants are *starters*, not finished flagship DSP modules.

The sine oscillator demonstrates:

- 1 V/oct pitch conversion, referenced to middle C (261.625565 Hz at 0 V).
- ±5 V peak sine output and up to the standard Rack 16 polyphonic channels.
- Continuous per-channel phase and consistent reset behavior.
- Frequency clamping below Nyquist across host sample-rate changes.
- A process callback without explicit heap allocation, locking, filesystem
  access, network use, logging, or synchronous UI work.

The stereo effect demonstrates:

- Two audio inputs and outputs, with right input normalled to left, and up to
  16 polyphonic voices (including CV-polyphony expansion).
- Cutoff offset in octaves and 1 V/oct CV, with nonfinite CV reset to 0 and
  bounded tuning before frequency conversion.
- A bilinear/TPT one-pole low-pass core in a reusable Rack-independent header,
  with NaN/Inf-safe audio and coefficient handling, reset, cutoff clamping to
  5 Hz–0.45 × sample rate, and no dynamic allocation. Both the Rack wrapper
  and core use IEEE-754 binary32 exponent-bit checks via `std::memcpy`:
  `std::isfinite` can be incorrectly optimized away under strict `-ffast-math`.
- Separate per-voice left/right state so stereo paths and polyphonic voices
  cannot contaminate one another. Recompute coefficients when the host's
  sample rate changes; an audible patch test remains necessary.

Keep these constraints when replacing the starters with custom oscillators,
filters or effects. Also add tests for pitch tracking, bounded levels, host
sample rates and block sizes, reset, state serialization, CV extremes, NaN/Inf,
16-channel behavior, and patch restore. The repository's `Makefile.base.mk` requests GNU C++17; the generated source
uses C++17 `std::clamp`. The HEADLESS fallback mirrors upstream Cardinal's
minimal `ModuleWidget` port registration pattern (for example, `HostTime.cpp`).
Still compile-check both regular and headless variants in CI before release.

Anti-aliasing for discontinuous waves,
oversampling and DSP CPU budgets require separate implementation and
measurement; a sine starter does not solve those.

For CV semantics, use Rack/VCV conventions when possible; label atypical
voltage ranges explicitly. Stable model names, port indexes and parameter
indexes are part of patch compatibility, so never silently reorder them.

## Next Module Forge milestones

1. Add generated-module regular and HEADLESS Cardinal compilation plus host
   smoke tests in CI, once the full toolchain is available.
2. Extend offline DSP tests with precise frequency-response, CPU/aliasing and
   CV/polyphony regression cases; the Rack-independent TPT core is the first
   example, not a shared DSP framework yet.
3. Build editable panel templates and a configurable, validated module schema.
4. Offer an optional scripting/DSL workflow compiled outside the real-time
   audio callback, with caching and trusted-module policies.
5. Evaluate external modules only after a clear security, licensing and ABI
   design.

This project continues to inherit GPL-3.0-or-later obligations from Cardinal
and relevant Rack components. All contributed code, sample assets and panel art
require license/provenance review. Preserve the upstream copyright notices and
provide proper attribution to authors rather than claiming upstream code as
newly authored here.
