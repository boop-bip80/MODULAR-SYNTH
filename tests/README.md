# Fast repository quality baseline

This suite complements the existing Cardinal CI in `.github/workflows/build.yml`.
Its orchestration uses the Python standard library; C++17 is needed for the
compiled standalone DSP and HEADLESS wrapper smoke checks. No git submodule
needs to be populated for those offline smokes.

## Run

From the repository root:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

For these tests, Git submodules do **not** need to be initialized. In a normal Git checkout, the suite compares the 160000 Git index entries against `.gitmodules`; for a source archive with no Git index, the URL/path validation still runs and the index comparison is skipped.

## Checks

- **Bundled patch integrity:** every committed `patches/**/*.vcv` file is valid UTF-8 JSON and has a basic Rack patch graph: unique module/cable IDs and no dangling cable endpoints.
- **First-party module manifests:** `plugins/Cardinal/plugin.json` is validated, plus `plugins/ModularSynth/plugin.json` when that original module collection exists. Each manifest has a matching plugin slug; module slugs/names must be nonempty, module slugs unique within their collection, and `tags` must be a list.
- **Submodule consistency:** `.gitmodules` paths are unique, relative, and use HTTPS; when Git metadata is available, every declaration must correspond exactly to a committed submodule gitlink.
- **First-party HEADLESS wrapper smoke:** `test_rack_wrapper_smoke.py` syntax-
  compiles the five actual `plugins/ModularSynth/src/*.cpp` translation units
  separately with Cardinal's `pluginInstance` preprocessor alias, then builds
  one C++17 process harness exercising parameter/port configuration, bounded polyphony counts,
  finite outputs, reset paths and Macro8's JSON method calls. It uses an
  **explicit test double**, `tests/rack_stub/rack.hpp`, in place of Rack.
  This test double is never part of the plugin build or distribution.

Run that check by itself with:

```sh
python3 -B -m unittest discover -s tests -p 'test_rack_wrapper_smoke.py' -v
```

The lightweight workflow runs on pull requests and pushes to `main`.

## What it does *not* prove

The HEADLESS wrapper smoke compiles **against stub Rack types, not upstream
Rack headers/libraries**. It does **not** prove that any module actually compiles
or links inside Cardinal, that GUI code compiles, that patches load in a real
host, that audio is glitch-free, or that plugins work on any platform. Continue
using the upstream-derived `plugin-validation` job and cross-platform builds
in `.github/workflows/build.yml` to establish those separate claims.

Before claiming production audio reliability, add headless deterministic audio-render tests, reference-waveform comparisons with tolerances, real-time allocation/lock checks, CPU load and host project save/restore tests. Baseline results must be recorded before setting performance targets.

The suite checks the *shape* of patch graphs, not whether installed plugin models exist; plugin model resolution requires a built/initialized module set.
