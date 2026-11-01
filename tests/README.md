# Fast repository quality baseline

This suite complements the existing Cardinal CI in `.github/workflows/build.yml`.
It is intentionally small, offline, and Python-standard-library-only.

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

The lightweight workflow runs on pull requests and pushes to `main`.

## What it does *not* prove

This suite does **not** prove that modules compile, patches load in a running host, audio is glitch-free, or plugins work on every platform. Continue using the upstream-derived `plugin-validation` job and cross-platform builds in `.github/workflows/build.yml`.

Before claiming production audio reliability, add headless deterministic audio-render tests, reference-waveform comparisons with tolerances, real-time allocation/lock checks, CPU load and host project save/restore tests. Baseline results must be recorded before setting performance targets.

The suite checks the *shape* of patch graphs, not whether installed plugin models exist; plugin model resolution requires a built/initialized module set.
