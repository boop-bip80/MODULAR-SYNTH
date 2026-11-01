# First-party license notices and provenance preflight

The `tools/compliance/license_audit.py` command makes a narrow, **source-only** inventory of first-party MODULAR-SYNTH code/panel notices, Module Forge starter templates, the `ModularSynth` manifest and inherited attribution pointers. Its goal is to catch missing or inconsistent metadata **before** another original module is integrated.

**It is not legal advice, a determination of license compatibility, a copyright clearance, a third-party dependency audit, or evidence that a distributed plugin satisfies every obligation.** Its findings should be reviewed by the project's maintainers and, where appropriate, qualified counsel. The script reads files only and does not modify licenses or upstream notices.

## Run the preflight

From the repository root with Python 3.10+:

```sh
python3 tools/compliance/license_audit.py
python3 tools/compliance/license_audit.py --json
python3 -m unittest discover -s tests -p 'test_license_audit.py' -v
```

For a separate checkout:

```sh
python3 tools/compliance/license_audit.py --repo-root /path/to/MODULAR-SYNTH
```

For release-review sessions where every suggested notice improvement must be addressed, add `--strict`. That switches the **exit status** to failure when warnings remain; it does not relabel warnings as proven legal violations.

| Exit status | Meaning |
| --- | --- |
| `0` | No hard preflight errors (advisory warnings may remain) |
| `1` | Hard metadata/provenance errors, or warnings under `--strict` |
| `2` | Command-line usage error or missing/unusable repository root |

The deterministic `--json` report exposes `summary` (`passed`, error/warning counts, first-party file/model counts, scanned pointer counts and strict mode), `findings` (level, code, repository-relative path, message) and `scope`. No external network requests, submodule downloads, SPDX API calls or binary inspection occur.

## What it checks

| Area | Preflight requirement | What remains human review |
| --- | --- | --- |
| Original C++ and headers | Every `plugins/ModularSynth/src/**/*.cpp` and `*.hpp` has a matching `SPDX-License-Identifier: GPL-3.0-or-later` and an attributable copyright notice near the start | Who actually owns each contribution and whether every incorporated idea/asset is properly licensed |
| First-party SVG panels | A well-formed SVG with a visible source comment identifying it as original MODULAR-SYNTH art; inconsistent SPDX identifier is an error, missing explicit SPDX is currently a warning | Artwork originality, fonts, embedded images, and external asset rights |
| Collection manifest | `plugins/ModularSynth/plugin.json` identifies the first-party collection, declares the same GPL expression, names its author/source URL, has unique safe model slugs, and each declared model has a corresponding C++/SVG | Whether the manifest covers all runtime packaging and all redistributed notices |
| Module Forge templates | The oscillator and effect source templates advertise `GPL-3.0-or-later` and a Module Forge generation marker; SVG templates and integration notes are inspected for provenance reminders | Generated code/panel authorship, any later user edits, and third-party fragments inserted into a new module |
| Inherited attribution pointers | Root GPL license text, `docs/LICENSES.md`, `docs/LICENSE-PERMISSIONS.md`, `docs/MODULE_FORGE.md`, README upstream credit and `.gitmodules` submodule path/URL records exist with expected markers | Whether each third-party submodule's current pin, source, graphics and redistribution terms have actually been reviewed |

The scanner is **deliberately confined to the first-party `plugins/ModularSynth` subtree and named top-level pointer files**. It does not scan `src/Rack`, `dpf`, `carla`, `plugins/OtherVendor` or any other inherited vendor source for our first-party header style. A missing notice in upstream content is **not** automatically treated as this fork's newly introduced error; review its original license and attribution in context.

The `.gitmodules` check confirms that the known `src/Rack` and `dpf` pointers and at least one bundled `plugins/` source pointer exist, with nonempty paths and URLs and no duplicate paths. It does **not** dereference URLs, verify gitlink SHAs, read remote licenses, or assert that those repositories permit any specific redistribution. See [the existing Cardinal-derived license inventory](LICENSES.md) and [permission notes](LICENSE-PERMISSIONS.md), preserving their provenance.

## Current observed baseline

A source-only run against the current fork on 2026-11-01 reported:

| Finding | Count |
| --- | ---: |
| Hard errors | 0 |
| Advisory notice warnings | 9 |
| Registered original models | 3 |
| First-party C++/header files | 7 |
| First-party SVG panels | 3 |
| Upstream submodule provenance pointers | 89 |

The nine warnings are **specific improvement work**, not ignored failures:

- Three original SVG panels identify themselves as MODULAR-SYNTH artwork but lack a per-file SPDX identifier.
- Three Module Forge-generated C++ template variants mention the GPL expression informally rather than using the standardized SPDX notice.
- Two generated SVG panel templates lack a provenance/SPDX XML comment.
- The effect integration guide template needs an explicit license/artwork attribution reminder.

The default preflight passes with those warnings because current first-party C++ headers, collection metadata and referenced attribution pointers are present and internally consistent. `--strict` deliberately fails this baseline. Before a release, confirm the correct rights holder and precise license for any panel/template and update the **original first-party** notices through reviewed commits. Do **not** blanket-relabel inherited upstream assets, remove upstream notices, or use this result as a claim of redistribution clearance.

## Adding a new first-party module

1. Use [Module Forge](MODULE_FORGE.md) to generate source and an SVG starter; inspect all generated files and replace/credit any non-original elements.
2. Ensure the new C++ source (and optional DSP header) has an accurate copyright line and the project's expected SPDX expression. The generator's existing GPL comment alone is flagged for improvement by this audit.
3. Add a truthful original-artwork provenance comment to the SVG and, after checking rights, a matching SPDX identifier.
4. Add the unique model slug to the existing `ModularSynth` collection manifest; preserve its project-level author/source metadata and upstream `LICENSE`/inventory files.
5. Run the generator's own checker, the license preflight, standalone DSP/source tests and, eventually, a real plugin/host test. These are separate acceptance gates.

To review a proposed notice fix without risking an inherited file, examine the scanner's exact repository-relative paths and compare the original contributor history. If you are uncertain about a third-party grant, record that uncertainty and seek appropriate review; the preflight cannot resolve it.

The tests include deliberate missing/wrong SPDX notices, manifest drift, uncredited SVG panels, generator template gaps, inherited-code exclusion and stable JSON/exit behavior. There is also a real-checkout regression that confirms the current first-party baseline has no hard notice errors.
