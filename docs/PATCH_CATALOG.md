# Dynamic factory patch catalog (source-only)

`tools/patches/patch_catalog.py` builds a deterministic index of the repository's original `MODULAR_-_*.vcv` factory examples. It discovers every matching file under `patches/examples/` on **each run**, in case-insensitive filename order, so new examples—including the now-registered Stereo Echo Showcase—appear without adding a hardcoded catalog entry or editing the tool.

This is a **saved-source index**, not a review of music genre, sound quality, audio playback or installed module availability.

## Generate the index

From the repository root, with Python 3.10+ (standard library only):

```sh
python3 tools/patches/patch_catalog.py
python3 tools/patches/patch_catalog.py --format markdown
python3 tools/patches/patch_catalog.py --format json
python3 -m unittest discover -s tests -p 'test_patch_catalog.py' -v
```

The default **Markdown** output is a pasteable table with links relative to `docs/`. Its columns show saved module count and original-module names, actual saved Host MIDI / Host Time output routes, Macro8's saved non-null snapshot slot count, and structural inspector warning flags. A following section lists every saved `plugin/model` instance. **JSON** additionally includes full `plugin/model` inventories, individual inspector warnings and errors, and the unambiguous Host MIDI channel setting when it is serialized.

Output order and formatting do not depend on current time, the shell's working directory or filesystem glob order. Successful source inspection exits 0; a malformed patch or an empty original-patch directory returns 1; an unreadable/malformed inspection setup returns 2.

## What each JSON field means

| Field | Source evidence | What it does **not** prove |
| --- | --- | --- |
| `title`, `file` | Name and path of a checked-in `MODULAR_-_` file | A marketing category or audible genre |
| `module_inventory` | Saved `plugin/model` identifiers and instance counts from the existing inspector | The module exists in a particular installed plugin binary |
| `original_modules` | Saved modules whose plugin slug is `ModularSynth` | Any DSP performance or correct presets |
| `midi_routed` | At least one saved cable originates at a `Cardinal/HostMIDI` module | That a DAW is sending notes or that MIDI is the *only* sound source |
| `host_transport_routed` | At least one saved cable originates at `Cardinal/HostTime` | Sample-accurate playback, transport compatibility or actual clock activity |
| `midi_channels_saved` | Single unambiguous `HostMIDI.data.channels` setting, when it is an integer between 1 and 16 | Audible polyphony, voice-stealing correctness or host MIDI compatibility |
| `macro8_instances` | Number of saved `ModularSynth/Macro8` instances | All macros are connected |
| `macro8_stored_scenes` | Total non-null entries in serialized Macro8 `data.snapshots` arrays | Snapshot validity, smooth morphing or actual recall/audio. The separate coverage suite checks known advertised presets. |
| `inspector_has_warnings`, `inspector_warning_count`, `inspector_warnings` | Warnings returned unchanged by `patch_inspector.py`, including unverified third-party port bounds | A failed audio load; warnings are **not** automatically fatal |
| `structurally_valid`, `errors` | Existing inspector's strict JSON, cable and source-backed original-port checks | Any headless sound render or compiled-host smoke test |
| `catalog_warnings` | Catalog-only metadata uncertainty, e.g. an unrecognized Macro8 snapshot field type | An independent replacement for patch validation |

A **null** field means the catalog could not establish that metadata safely. `false` for MIDI or transport means no corresponding **saved output cable** was found, not that the module type is absent. Macro8 counts are **serialized non-null slots**, even when the actual host might reject or normalize their contents; this tool intentionally does not reimplement the coverage suite's Macro8 data assertions.

### Example interpretation

As of the initial catalog release:

- `MODULAR_-_Clockwork_Pulses.vcv` routes **Host Time** into its saved graph and has no connected Host MIDI route.
- `MODULAR_-_Polyphonic_Motion_Pad.vcv` saves **8** Host MIDI channels and **4** non-null Macro8 scenes, but requires a real fork-built host audition before anyone can claim eight simultaneous audible notes.
- Original patches using Fundamental, Clouds, Plaits, Plateau, etc. still carry unverified third-party source warnings from the existing inspector. The catalog retains them.

Future patches are discovered automatically. An added or malformed patch still receives a row with an explicit inspector failure instead of disappearing or being quietly counted as valid.

## Relationship to existing patch QA

- **`patch_inspector.py`** owns structural JSON/cable and first-party port validation.
- **`factory_patch_coverage.py`** owns advertised signal-flow claims and whether every registered original model is represented by an example.
- **`patch_catalog.py`** only presents dynamically discovered, source-backed inventory/control-route/scene metadata for musicians and reviewers.

Do not infer a DAW block size, sample rate, CPU cost, loudness, stereo imaging or patch sound from this catalog. None is measured. For actual acceptance, load each patch in a built host, perform its documented MIDI/transport interactions, check monitoring levels and save/reopen the DAW project.
