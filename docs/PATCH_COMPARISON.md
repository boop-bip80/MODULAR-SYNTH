# Compare two Cardinal/VCV patches offline

The `tools/patches/patch_compare.py` command reports **sound-design changes** between two plain-text `.vcv` files without building Cardinal or launching a DAW. It complements the [patch inspector](PATCH_WORKFLOW.md), which validates the structure of an individual patch. A successful comparison **does not** prove that either patch loads, produces audio, avoids clipping, or survives a DAW save/reopen.

## Quick start

From the repository root, with Python 3.10+ and no extra packages:

```sh
python3 tools/patches/patch_compare.py \
  patches/examples/MODULAR_-_Cinematic_Drift_Pad.vcv \
  patches/examples/MODULAR_-_Rhythmic_Grit_Bass.vcv
```

For JSON output suitable for code review, a diff viewer, or automation:

```sh
python3 tools/patches/patch_compare.py \
  patches/examples/MODULAR_-_Cinematic_Drift_Pad.vcv \
  patches/examples/MODULAR_-_Rhythmic_Grit_Bass.vcv \
  --json
```

An example run against the source patches committed as of 2026-11-01 reports:

| Observation | Result |
| --- | ---: |
| Models matched | 8 |
| Regenerated module IDs ignored | 6 |
| Parameter values changed | 18 |
| Macro8 names/snapshot fields changed | 10 |
| Cable endpoints added or removed | 0 |

This tells us both patches use the **same cable graph** while their synth controls and stored scenes differ. It says nothing about how either sounds.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | No semantic changes under this tool's documented comparison rules |
| `1` | One or more differences found (normal and expected when comparing distinct patches) |
| `2` | Input parse/structural error, such as invalid JSON, duplicate module IDs or dangling cable endpoints; also used by command-line argument parsing |

The JSON report has `before`, `after`, `summary`, `modules` and `cables` objects. The summary provides `changed` plus counts. Changed parameter records include the module reference, old/new module IDs, parameter ID and old/new values. Macro8 state records identify fields such as `name[1]` and `snapshot[A].macro3`. Cable records contain source/destination module references, output/input port IDs and multiplicity. Arrays and human-readable lines have deterministic ordering.

## What counts as a change?

| Tracked | Intentionally ignored |
| --- | --- |
| Added or removed modules, identified by `plugin/model` | Patch-level `zoom`, module `pos` and other visual layout |
| Added, removed or changed numeric parameters, keyed by per-module parameter ID | Order of modules, parameters, cables and JSON object keys |
| Macro8 `macro8Version`, macro names, A–D snapshot values and `selectedSlot` where present | Cable IDs and colors |
| Added or removed signal cables, compared by the two endpoint module identities and port numbers | Patch/module `version` metadata and unrelated raw module `data` payloads |

For snapshots, a changed stored slot is reported as a slot change when it switches between `null` (empty) and an array; when both versions have arrays, changed macro values are reported individually. The comparison distinguishes a **missing** parameter from one with an explicit value; an absent parameter's host default is not guessed. Only the known first-party `ModularSynth/Macro8` snapshot data schema receives detailed module-state comparison.

Other module `data` fields—including HostMIDI settings, TextEditor annotations and non-Macro8 custom state—are outside this tool's comparison scope. **Some of those fields can matter musically.** Review them manually when changing MIDI setup, plugin-specific state, assets, sample references or patch notes. This intentionally narrow report should not be interpreted as a complete serialized-state diff.

### Matching modules across files

Rack module ID numbers are often stable when you edit a patch, but may be regenerated if you build another patch from the same layout. The comparator uses this documented two-stage matching:

1. Match a module by **the same numeric ID and the same `plugin/model`** across both files.
2. For unmatched modules, pair a `plugin/model` only when **exactly one unmatched instance of that type exists in each file**. Thus one MorphVCO in each patch can be compared even when their numeric IDs differ.

The resulting ID changes appear in `modules.id_remaps` for traceability, but are not themselves counted as semantic differences. Cable endpoints are normalized through these matches, so regenerated cable IDs and module IDs alone cannot fabricate a rewire.

If a patch has **several indistinguishable copies of the same model with no stable IDs**, pairing by proximity or knob similarity could silently compare the wrong voices. The tool deliberately reports ambiguous instances as removals/additions instead. Keep IDs stable across revisions of such patches, or review their mapping by hand. If a numeric ID is reused for a *different* `plugin/model`, the old module is removed and the new one is added.

## Validation and limitations

The comparator rejects malformed UTF-8/JSON, duplicate JSON keys, non-finite numeric values, duplicate module/parameter/cable IDs, negative or malformed endpoint IDs, and cables pointing to missing modules. It retains **cable multiplicity** when comparing endpoints, so duplicate wiring is not silently deduplicated.

It **does not** validate registered plugin/model names, audio-vs-CV port semantics, module parameter bounds or whether a third-party module is installed. Run the existing inspector **on both files first**:

```sh
python3 tools/patches/patch_inspector.py validate \
  patches/examples/MODULAR_-_Cinematic_Drift_Pad.vcv \
  patches/examples/MODULAR_-_Rhythmic_Grit_Bass.vcv
python3 -m unittest discover -s tests -p 'test_patch_compare.py' -v
```

The inspector has first-party source-backed checks where metadata is available, but inherited Cardinal/Fundamental or unknown third-party port bounds may remain **unverified**. Neither tool executes DSP, measures audio, checks CPU usage, audits licenses, tests a compiled binary, or establishes DAW patch persistence. For playing and snapshot controls, see the musician's [Getting Started](GETTING_STARTED.md) guide.

## Suggested review workflow

1. Keep your original `.vcv` file, then save a revised copy.
2. Run `patch_inspector.py validate` on both; resolve structural errors and inspect warning provenance.
3. Run `patch_compare.py original.vcv revised.vcv`; inspect modules, parameters, Macro8 scenes and cables. An exit status of 1 simply means changes were detected.
4. Review untracked module `data` manually, especially external sample paths, MIDI settings or third-party state.
5. Load **your fork-built plugin** in an actual DAW, audition notes and snapshots at safe monitoring level, then save/reopen the patch and project. These are required manual checks, not achievements of the offline tools.

Tests use only Python's standard library and cover permutation invariance, module ID remapping, ambiguity with duplicate models, cable rewires and multiplicity, parameter additions/removals, Macro8 snapshots and malformed input. One regression compares the two committed cinematic/bass examples directly.
