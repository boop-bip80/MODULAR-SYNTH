# Module Forge — first-party module development (initial scaffolder)

**Status:** first implementation, developer tooling only. This is not yet an
in-app source editor, just-in-time DSP compiler, module hot loader, or standalone
plugin exporter. The separate `plugins/ModularSynth` collection is the home
for original modules; it is distinct from the upstream `plugins/Cardinal`
collection.

## What is available

`tools/module-forge/module_forge.py` generates four files for an original
Rack-compatible module:

- A C++ DSP/GUI starter with one 1 V/oct pitch input and a polyphonic sine
  output, including sample-rate-safe phase integration, reset, and finite CV
  handling.
- A self-contained SVG panel.
- A **single-module JSON fragment** for the `ModularSynth` manifest.
- Integration steps listing the specific Cardinal build/registration changes.

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

The output will be `module-forge-output/OrbitSine/`. Read the generated
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

Tests cover generated structure, manifest identity, C++ model/panel references,
refusal to overwrite user-edited files, and rejection of invalid identifiers.
The integration tests also simulate registry updates, case-insensitive collisions,
stale plans, mixed existing collections, parent symlinks, interruption, and
rollback after an injected write failure. These are not a substitute for compiling/loading the C++
module in Cardinal or testing its audio behavior.

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

The command prepares six edits: the new C++ source and SVG panel, plus
`plugins/Makefile`, `plugins/plugins.cpp`,
`plugins/ModularSynth/src/plugin.hpp`, and
`plugins/ModularSynth/plugin.json`. It checks all anchors, model/slug identity,
duplicate registration, case-insensitive destination collisions, UTF-8 and SVG
validity, the exported C++ model symbol, and source/header/compiler namespace
compatibility before writing. It refuses to
overwrite existing source/panel files and refuses changes to unsupported loader
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
   two generated module files you just introduced. Avoid broad resets or cleans.
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

A newly generated sine oscillator is a *starter*, not a flagship DSP module.
Its code demonstrates:

- 1 V/oct pitch conversion, referenced to middle C (261.625565 Hz at 0 V).
- ±5 V peak sine output and up to the standard Rack 16 polyphonic channels.
- Continuous per-channel phase and consistent reset behavior.
- Frequency clamping below Nyquist across host sample-rate changes.
- A process callback without explicit heap allocation, locking, filesystem
  access, network use, logging, or synchronous UI work.

Keep these constraints when replacing the starter with custom oscillators,
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

1. Run generated-module compilation and host smoke tests automatically in CI.
2. Provide an atomic command that integrates new modules with reviewed edits
   to `plugins/Makefile`, model declaration, model registry and manifest.
3. Add a reusable DSP utility library and deterministic offline unit tests.
4. Build editable panel templates and a configurable module manifest schema.
5. Offer an optional scripting/DSL workflow compiled outside the real-time
   audio callback, with caching and trusted-module policies.
6. Evaluate a separate development edition for external modules only after a
   clear security and ABI design.

This project continues to inherit GPL-3.0-or-later obligations from Cardinal
and relevant Rack components. All contributed code, sample assets and panel art
require license/provenance review. Preserve the upstream copyright notices and
provide proper attribution to authors rather than claiming upstream code as
newly authored here.
