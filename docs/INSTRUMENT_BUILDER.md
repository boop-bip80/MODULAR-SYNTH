# Instrument Builder — Macro8 performance and offline source bundles

## Scope

**Instrument Builder is currently an offline source-packaging prototype.**
Macro8 is the first-party performance controller: eight independently
controllable CV outputs, custom short labels, four versioned snapshot slots,
and sample-smoothed transitions. The new Python tool packages a validated
Rack/VCV patch and a derived, versioned performance manifest into one
deterministic `.msinstrument` source ZIP. It does **not** group/compile nested
modules, execute patches, provide a custom performance GUI, embed samples,
export VST/AU/CLAP, or create a standalone runtime.

An **opt-in manifest v2** additionally records direct, source-verified Macro8
output-to-module-input cable mappings. The default remains v1, so existing
bundles and the v1 concept preview remain compatible.

The source lives under `plugins/ModularSynth` to preserve the upstream Cardinal
module collection. The Rack-independent DSP/snapshot implementation is
`plugins/ModularSynth/src/Macro8.hpp`.

## Offline `.msinstrument` source bundles (Phase 3)

`tools/instrument-builder/instrument_builder.py` uses only the Python standard
library and reads an **existing saved `.vcv` JSON patch**. The patch must contain
at least one real `ModularSynth/Macro8` module with `macro8Version: 1` data.
For example, from the repository root:

```bash
python3 tools/instrument-builder/instrument_builder.py pack \
  patches/examples/MODULAR_-_Morphing_State_Pad.vcv \
  --name "Morphing State Pad" \
  --out Morphing_State_Pad.msinstrument

python3 tools/instrument-builder/instrument_builder.py inspect \
  Morphing_State_Pad.msinstrument

python3 tools/instrument-builder/instrument_builder.py unpack \
  Morphing_State_Pad.msinstrument --out unpacked-pad
```

`pack` exclusively creates a **new** `.msinstrument` file; `unpack`
exclusively creates a **new** output directory containing exactly:

| ZIP entry / extracted path | Meaning |
| --- | --- |
| `manifest.json` | Versioned, verified performance metadata |
| `patch/main.vcv` | Original `.vcv` patch bytes, unchanged |

No machine paths, creation timestamps, random identifiers, or plugin binaries
are embedded. ZIP entries are stored uncompressed with a fixed 1980-01-01
timestamp, regular-file permissions and fixed ordering. Packing the same patch
bytes with the same instrument name produces **byte-identical bundles**.

### Compare two saved instrument revisions (source-only)

The `diff` command compares **two independently validated** `.msinstrument`
archives before printing a report. It is useful for reviewing saved performance
changes before replacing a preset or sharing a patch with collaborators:

```bash
python3 tools/instrument-builder/instrument_builder.py diff \
  Old_Pad.msinstrument New_Pad.msinstrument

# Deterministic JSON, suitable for review automation:
python3 tools/instrument-builder/instrument_builder.py diff \
  Old_Pad.msinstrument New_Pad.msinstrument --json

# Optional CI gate: status 1 if saved semantic state changed:
python3 tools/instrument-builder/instrument_builder.py diff \
  Old_Pad.msinstrument New_Pad.msinstrument --fail-on-change
```

It checks both source ZIPs, SHA-256, full patch schemas, Macro8 state and
manifest-to-patch consistency first. No file is written or migrated. The
machine-readable comparison tracks the instrument name, format version,
historical mapping-contract marker, top-level patch metadata, modules and
cables by **stable saved Rack IDs**, plus changed Macro8 controls and A–D
scenes. This catches patch rewiring, renamed macros, changed live values,
snapshot adjustments and state/format changes without relying on JSON array
order. Added, removed and modified IDs are sorted reproducibly.

A patch JSON whitespace or array-order rewrite is identified separately as
`sourcePatchBytesChanged`, but is **not** treated as a semantic change if
the saved objects and metadata are equivalent. Ordinary `diff` returns
**0** for two valid inputs, whether different or identical. The optional
`--fail-on-change` returns **1** when saved semantic state differs; **2**
means either archive could not be read or verified. The default text output
keeps the saved-ID details compact; use `--json` for exact ID lists.

This comparison never upgrades older v1 or historical v2 route contracts.
A changed mapping-contract marker is reported as an **interpretation**
difference, not evidence of a newly working CV route. Both archives may
still fail to load in Cardinal or a DAW, require external samples/plugins,
or behave differently at runtime: no audio, MIDI, automation, CPU, live
state-restoration or plugin execution is tested.

### Manifest schema v1

The manifest has `format: "modular-synth-source-instrument"`,
`formatVersion: 1`, a printable 1–64 character `name`,
`patch: {file, sha256, size}`, sorted `requiredPlugins`, and
`performance.macro8`, ordered by Rack module ID. Each Macro8 record contains:

| Field | Direct source in the saved Macro8 |
| --- | --- |
| `moduleId`, `stateVersion` | Rack module `id`, `data.macro8Version` (1) |
| `names` | Eight real `data.names` labels (printable ASCII, 1–12 chars) |
| `ranges` | Eight `unipolar` / `bipolar` modes from params 15–22 |
| `liveValues` | Eight normalized knobs from params 0–7 |
| `morphSeconds` | Param 8, 0–5 seconds |
| `snapshotAction` | Param 9, `store` or `recall` |
| `snapshots` | Four `data.snapshots` slots: `null` or 8 normalized values |
| `selectedSlot` | `data.selectedSlot`: −1 (LIVE) or 0–3 (A–D) |

Param ranges mirror Macro8's compiled definitions. Missing knob/switch params
use Macro8 defaults; duplicated IDs or values outside the declared ranges are
rejected. An active snapshot must actually exist. The manifest is **derived
from** the patch, not editable independent state: `inspect` and `unpack`
recompute its contents and SHA-256 and refuse any inconsistency. Editing
`manifest.json` alone cannot alter playback.

### Opt-in manifest schema v2 — explicit Macro8 cable mappings

Use v2 to inspect *where an existing saved patch routes each Macro8 control*
without editing that patch or assuming a plugin runtime:

```bash
python3 tools/instrument-builder/instrument_builder.py pack \
  patches/examples/MODULAR_-_Echo_Motion_Performance.vcv \
  --name "Echo Motion Performance" --format-version 2 \
  --out Echo_Motion.msinstrument

python3 tools/instrument-builder/instrument_builder.py inspect \
  Echo_Motion.msinstrument
```

`formatVersion: 2` retains every v1 field and adds an array at
`performance.controlMappings`. One record is derived **per direct saved cable**
whose source is `ModularSynth/Macro8`. An output may appear more than once when
it fans out. Unconnected Macro8 controls remain present in `performance.macro8`
but have no mapping row. For example, Echo Motion's first macro has a saved
direct connection to StereoEcho's echo-time CV input:

```json
{
  "cableId": 980000000210,
  "source": {
    "moduleId": 980000000107,
    "outputId": 0,
    "controlNumber": 1,
    "name": "Time",
    "range": "unipolar"
  },
  "destination": {
    "moduleId": 980000000105,
    "plugin": "ModularSynth",
    "model": "StereoEcho",
    "inputId": 2,
    "inputKind": "cv",
    "inputLabel": "Echo time CV (additive 100 ms/V; accepts negative CV)",
    "modulatesParameter": {"id": 0, "name": "Echo time"}
  }
}
```

All Rack IDs and input/output IDs are copied from the `.vcv` graph, with
zero-based port IDs and one-based performer-facing `controlNumber`. Routes sort
by source module ID, output ID, destination module ID, destination input ID,
then cable ID, regardless of the original JSON order. The source `name` and
`range` are taken from validated Macro8 data/parameters, not user-supplied
mapping annotations. A matching `modulatesParameter` describes a **known CV
input's effect on a first-party knob**, not a cable to that Rack parameter,
automation assignment, or a promise that the host applies a particular value.

Nine first-party modules are now registered, and all nine have **current
source-backed input contracts** for opt-in v2 Macro8 routing: Macro8 (zero
inputs), MorphVCO, StateFilter, StereoEcho, ClockedLFO, FoldDrive, FMVoice,
ChanceHold and DualVCA. Descriptors derive from exact `InputIds`, `configInput` and
related `configParam` declarations in `plugins/ModularSynth/src/*.cpp`;
regression tests keep source port contracts synchronized. The newer FMVoice
ChanceHold and DualVCA descriptors are only available in source bundles bearing
their respective additive v2 mapping contract markers; earlier archive
contracts must retain their original `unverified` destinations. These saved
descriptors are not evidence of live host CV behavior.

The `ClockedLFO` source-backed input contract uses its exact zero-based Rack
`inputId` values:

| Input ID | Saved cable destination | Related Rack knob (if any) |
| --- | --- | --- |
| 0 | Free-rate CV (1 V/oct) | Param 0, Free-run frequency |
| 1 | External tempo pulse (2 V rising threshold) | None — clock edges synchronize timing |
| 2 | Phase reset trigger (2 V rising threshold) | None — a trigger, not automation |
| 3 | Output phase CV (10 V per cycle) | Param 2, Output phase offset |
| 4 | Pulse width CV (10 V full range) | Param 3, Pulse width |

All five are voltage/control inputs (`inputKind: "cv"`). Clock and reset are
**edge-triggered**, so their mappings contain `modulatesParameter: null`.
Rate CV changes the free-run oscillator rate; a detected external clock can
override that free-run rate while clock-locked. These descriptors report the
saved cable's destination and source-code semantics, **not** a direct
parameter connection, clock synchronization guarantee, or plugin host test.

### FoldDrive's four saved input ports

The FoldDrive source contract follows the exact Rack input indices from
`plugins/ModularSynth/src/FoldDrive.cpp` and the real CV semantics used by
the FoldDrive wrapper:

| Input ID | Saved Macro8 cable destination | Related Rack knob (if any) |
| --- | --- | --- |
| 0 | Audio signal input (nominal ±5 V) | None — an **audio** port, not knob modulation |
| 1 | Drive CV (+10 V adds 100%; 3 ms slew) | Param 0, Sine fold drive |
| 2 | Bias CV (+10 V adds +100%; 3 ms slew) | Param 1, Fold asymmetry bias |
| 3 | Wet mix CV (+10 V adds 100%; 3 ms slew) | Param 2, Wet mix |

Input 0 reports `inputKind: "audio"`, while inputs 1–3 report
`inputKind: "cv"` with source-verified parameter references. The CV values
are additive signals applied by FoldDrive's wrapper; they are **not** direct
Rack parameter writes or DAW automation. A Macro8 CV-to-audio cable can be
described structurally but is not automatically a useful audio connection.

### FMVoice's four saved CV input ports

The original two-operator FMVoice uses the exact zero-based source input
indices and `configInput` labels in `plugins/ModularSynth/src/FMVoice.cpp`.
Each is a control-voltage input, not an audio input:

| Input ID | Saved Macro8 cable destination | Related Rack knob (if any) |
| --- | --- | --- |
| 0 | Pitch CV (1 V/oct; C4 at 0 V) | None — pitch adds to octave and fine tune, not a single knob |
| 1 | Ratio CV (1 V doubles ratio) | Param 2, Modulator/carrier frequency ratio |
| 2 | Index CV (1 V adds 0.8 rad) | Param 3, Phase modulation index |
| 3 | Feedback CV (10 V adds 95%) | Param 4, Modulator self-feedback |

All report `inputKind: "cv"`. The ratio scales multiplicatively by powers
of two; index and feedback add control values before DSP clamping. The related
parameter is a source-label **reference**, not a direct parameter cable or a
DAW automation assignment. These saved source descriptors do not verify that
a patch loads, produces sound or remains stable at a particular host buffer
size.

### ChanceHold's five saved clock and probability CV inputs

The original polyphonic ChanceHold module declares five zero-based Rack
`InputIds` in `plugins/ModularSynth/src/ChanceHold.cpp`. All five saved
destinations are `inputKind: "cv"`; clock/reset are trigger-oriented inputs,
not automatable knobs:

| Input ID | Saved Macro8 cable destination | Related Rack knob (if any) |
| --- | --- | --- |
| 0 | Free clock rate CV (1 V/oct) | Param 0, Free-run sample rate |
| 1 | External sample clock (2 V rising threshold) | None — clock pulse |
| 2 | Reproducible random sequence reset (2 V rising threshold) | None — reset trigger |
| 3 | Sample probability CV (+10 V adds 100%) | Param 1, Probability of taking a sample |
| 4 | Glide duration CV (+10 V adds 2 seconds) | Param 2, Glide time (99% settling) |

Clock, reset, probability and glide controls are source-described CV inputs;
they do not constitute DAW automation. Source-backed cable labels cannot
prove timing, audio quality, or host compatibility.

### DualVCA's four saved audio and envelope inputs

`plugins/ModularSynth/src/DualVCA.cpp` declares the exact input indices:

| Input ID | Source-declared input label | Input kind | Related Rack knob |
| --- | --- | --- | --- |
| 0 | A audio (nominal +/-5 V) | `audio` | None |
| 1 | A gain envelope (0 to +10 V; unpatched is unity) | `cv` | None |
| 2 | B audio (nominal +/-5 V) | `audio` | None |
| 3 | B gain envelope (0 to +10 V; unpatched is unity) | `cv` | None |

The two envelope inputs influence channel gains but are **not** modulation of
a single named Rack parameter: `modulatesParameter` remains `null`. Macro8
connections to audio inputs are saved graph facts, not claims of useful audio
or validated playback. Use v2 `routes`, `check --require-verified-routes`, or
`preview --show-routes` for source-only cable reports.

### Immutable v2 source port contracts and old bundle compatibility

Version 2 has six deliberately distinct, cumulative port interpretations:

| Saved v2 contract marker | Verified first-party destinations | DualVCA routes in that archive |
| --- | --- | --- |
| Absent (original v2) | Macro8 (zero inputs), MorphVCO, StateFilter, StereoEcho | `unverified` |
| `modular-synth-v2-clockedlfo-inputs-v1` | Above plus ClockedLFO | `unverified` |
| `modular-synth-v2-folddrive-inputs-v1` | Above plus ClockedLFO and FoldDrive | `unverified` |
| `modular-synth-v2-fmvoice-inputs-v1` | Above plus ClockedLFO, FoldDrive and FMVoice | `unverified` |
| `modular-synth-v2-chancehold-inputs-v1` | Above plus ClockedLFO, FoldDrive, FMVoice and ChanceHold | `unverified` |
| `modular-synth-v2-dualvca-inputs-v1` | All previous models plus DualVCA | Source-verified input labels/kinds |

New v2 bundles with a direct Macro8 → DualVCA route use
`performance.controlMappingContract = "modular-synth-v2-dualvca-inputs-v1"`,
even if the patch also routes to ChanceHold, FMVoice, FoldDrive or ClockedLFO.
Without a DualVCA route, the previous ChanceHold → FMVoice → FoldDrive →
ClockedLFO marker precedence remains unchanged. Patches without any direct
Macro8 route to those newer models retain the original unmarked v2 bytes.

Readers preserve the meaning of **every older marker**. In all five earlier
contract variants, a saved Macro8 → DualVCA cable remains `unverified`. In
older unmarked, ClockedLFO-, FoldDrive- and FMVoice-marked archives,
ChanceHold remains `unverified`, and the older models retain their prior
source-verified semantics according to the saved contract marker.
The reader independently re-derives all mappings using the exact saved marker
and rejects spoofed, unsupported, replaced or missing markers and route rows.
It never silently upgrades a bundle. Repack a **trusted original .vcv** with
`--format-version 2` to opt into DualVCA source descriptions.

The v1 default is unchanged. These additive source-contract revisions inside
v2 do **not** prove a linked Cardinal plugin, installed modules, DAW routing,
automation or audible playback.

Across first-party and external destinations, the mapping reports:

| `destination.inputKind` | Meaning |
| --- | --- |
| `cv` | Verified first-party destination CV input, labeled by source; `modulatesParameter` is populated only for a corresponding first-party knob |
| `audio` | Verified first-party audio input; no claimed control-parameter modulation |
| `unverified` | Third-party input or unrecognized first-party model; input bounds, name and semantics are unknown, with `inputLabel` and `modulatesParameter` explicitly `null` |

For known first-party models, v2 refuses an out-of-range or missing input ID; it
also rejects Macro8 source output IDs outside 0–7 and duplicate saved routes
with identical source-output/destination-input endpoints (while allowing real
fan-out to distinct inputs). Unknown external model ports are
retained as `unverified`, **not validated or inferred to work**. v2 never
traverses multi-hop cables, checks third-party port schemas, alters a Rack
parameter, generates a performance GUI, or confirms actual sound. This is a
static *patch wiring index*, not a remapping system. No user-authored mapping
can override source wiring.

`inspect`, `unpack` and `check` accept both v1 and v2; manifest validation
re-derives all v2 routes from the unchanged patch bytes and rejects deleted,
modified, duplicated or fabricated mapping rows. `preview` still draws the
same verified eight Macro8 controls and four snapshots; it projects a verified
v2 manifest onto the unchanged v1 concept renderer, without displaying routes.
Repacking an unpacked v2 bundle requires the **same name and**
`--format-version 2` to reproduce identical archive bytes:

```bash
python3 tools/instrument-builder/instrument_builder.py unpack \
  Echo_Motion.msinstrument --out Echo_Motion_source
python3 tools/instrument-builder/instrument_builder.py pack \
  Echo_Motion_source/patch/main.vcv \
  --name "Echo Motion Performance" --format-version 2 \
  --out Echo_Motion_repacked.msinstrument
```

The v1 format remains the default and its byte layout is unchanged. Existing
v1 archives are not silently upgraded. Future changes to existing source-backed
destination semantics require a new format or explicit immutable contract
identifier; old source-bundle claims must not be silently reinterpreted.

### Readable saved Macro8 route map

Use `routes` to see the **actual saved direct Macro8 cable graph** in
performer-friendly text, including each Macro8 control number/name/range,
destination model and input port, source-declared audio/CV label, and the
related knob (when the module source associates one with that CV port).
Rows sort deterministically by Macro8 controller, control number, and
destination, so performers can scan one control's fan-out together:

```bash
python3 tools/instrument-builder/instrument_builder.py routes \
  Echo_Motion.msinstrument

# Stable machine-readable representation of the same saved source mapping:
python3 tools/instrument-builder/instrument_builder.py routes \
  Echo_Motion.msinstrument --json
```

For example, a MorphVCO destination is described as a **source-verified
wave-morph CV input** with a related Wave morph position knob. That does not
turn the cable into a Rack parameter write, DAW automation assignment, or
proof that the patch loads and sounds in a host. Audio ports are separately
marked `audio`; unidentified external and historical ports remain
`UNVERIFIED` without invented names or knob links.

The report validates the full two-entry bundle and patch-derived manifest
before displaying anything. It never changes or upgrades the source archive.
Legacy v1 shows a clear instruction to repack the original `.vcv` with
`--format-version 2`; v2 with no direct Macro8 cables reports zero routes.
Older unmarked or ClockedLFO-marked v2 interpretations stay conservative.

The informational `routes` command exits **0** for any valid archive,
including archives with unverified routes; **2** means a corrupt/invalid
bundle or file read failure. For CI enforcement use the existing
`check --require-verified-routes` command, which exits **1** if the
source-only route gate fails. The opt-in strict check's output and the
default `inspect`, `check`, and `pack` behavior are unchanged.

### Saved Macro8 controls and snapshot inventory

The offline **controls** command inventories **all eight knobs on every Macro8**
even if they are unpatched. Use it when preparing a performance, comparing the
saved LIVE setting with a selected A–D scene, or identifying unused controls:

~~~bash
python3 tools/instrument-builder/instrument_builder.py controls \
  Echo_Motion.msinstrument

# Machine-readable report with the same saved values and deterministic ordering:
python3 tools/instrument-builder/instrument_builder.py controls \
  Echo_Motion.msinstrument --json
~~~

Each controller is sorted by saved Rack module ID and includes its STORE/RECALL
mode, saved LIVE/A/B/C/D target selection, morph time, and populated scene
names. Its eight controls show the saved name and unipolar/bipolar mode,
normalized LIVE knob position, **saved target** position, and each A–D snapshot's
saved value (or null for an empty scene). For convenience the report calculates
*nominal voltages* from the declared Macro8 source mapping: unipolar
(10 × normalized) V and bipolar (10 × normalized − 5) V. These values are
not audio-CV measurements; Macro8 may still be morphing between targets in
the actual Rack engine.

For a validated **v2** source bundle, each control also shows how many direct
saved Macro8 cables leave it, broken out by first-party source-verified and
conservatively unverified destination port contracts. These are **saved
connections**, not proven functional host routes; third-party inputs and older
v2 contracts stay unverified. For **v1**, cable counts are explicitly null
(routes unknown (v1) in text), never zero: the historical v1 manifest has
no source-verified routing records. Repack trusted .vcv source with
--format-version 2 if those counts matter.

Both text and --json views validate the full source ZIP, patch SHA-256,
Macro8 state and derived manifest before displaying anything. Neither command
changes bundle bytes or upgrades its schema. Exit code **0** means the bundle
is valid even if saved routes are unknown/unverified; **2** means the source
bundle or read failed. Use check --require-verified-routes for a strict
source-only route gate. This inventory cannot tell whether a plugin was linked,
a patch loaded, a CV actually emitted, a knob was host-automated or any sound
was produced.

### Safety and limits

- The source `.vcv` is parsed as strict JSON: duplicate keys, NaN/Inf,
  nonfinite exponent overflow, enormous integer numeric values that cannot be
  represented as finite floats, inconsistent cable module endpoints, bad module
  IDs, unsupported Macro8 state versions, malformed names/snapshots/ranges,
  and missing Macro8 modules are rejected before output is created. This is
  **structural/schema/graph validation**, not a Rack loader: the tool does
  **not** know third-party modules' input/output port bounds or confirm that
  Cardinal or a DAW can actually load every model or restore its runtime state.
- The ZIP must have **exactly two** allowlisted file entries. It rejects
  traversal (`../`), absolute/drive paths, backslash paths, duplicate names,
  Unix symlink entries, encryption, unsupported compression, and unknown files.
  Extraction writes fixed paths only—it does not trust ZIP member names as
  filesystem targets.
- Limits: patch 8 MiB; manifest 128 KiB; 256 modules; 4096 cables; eight
  Macro8 modules. These are prototype caps, not Rack host capacities.
- Input files are checked through their opened file descriptors, including a
  regular-file check and a bounded read. On POSIX platforms with `O_NOFOLLOW`,
  the final path component cannot be switched to a symlink between the open
  check and read; `O_NONBLOCK` also avoids hanging on a raced-in FIFO. On
  platforms without no-follow opens, the existing symlink check is only a
  best-effort fallback against hostile concurrent path replacement. Ancestor
  path components of input filenames are not constrained to non-symlink paths.
- Both commands refuse to overwrite a file or directory. POSIX extraction
  uses component-wise no-follow directory handles and exclusive file creation;
  other platforms reject known symlink parents but are not hardened against
  hostile concurrent filesystem races.
- A storage failure can leave an incomplete *new* bundle/directory, never an
  overwritten destination. Inspect the exact path and remove only that failed
  output after confirming it contains no needed data. Run `inspect` before
  sending a bundle elsewhere.

This is a **source-only container**. Other plugins, external samples, paths
inside module custom state and licensing obligations are **not** bundled or
resolved. Opening `patch/main.vcv` still requires a compatible Cardinal build
and the patch's dependencies. Bundles are not cryptographically signed; the
SHA-256 detects internal mismatches, not malicious replacement of both entries.

### Static SVG performance-panel preview

After packing a bundle, create a portable **concept image** from its verified
performance manifest:

```bash
python3 tools/instrument-builder/instrument_builder.py preview \
  Morphing_State_Pad.msinstrument --out Morphing_State_Pad.svg
```

The command generates a self-contained, deterministic SVG (no scripts, external
fonts/assets, URLs or runtime code) showing up to eight Macro8 sections. Each
section has eight named controls with their saved live knob positions, explicit
**0…+10 V / −5…+5 V** polarity, four A–D snapshot buttons with stored/empty
and selected state, and static badges for LIVE/snapshot selection,
STORE/RECALL mode, and morph time. Populated snapshots show eight small value
bars. Multiple Macro8 controllers sort by their stable Rack module IDs;
the visible headings are friendly `MACRO CONTROLLER 1`, `2`, etc., while
the exact IDs remain in SVG `data-module-id` attributes and accessible
controller descriptions for identity-preserving tooling.

Labels are XML-escaped so characters such as `<`, `>` and `&` display as
text, not markup. The 1–12 character Macro8 labels fit within their fixed cards;
instrument titles up to 64 characters wrap to at most two lines. Text/background
palette pairs are tested for at least WCAG AA 4.5:1 contrast. SVG `title` and
`desc` provide an accessible summary.

`preview` checks the entire v1 or v2 source bundle and derived manifest **before**
writing and refuses to overwrite an existing `.svg` file or follow symlink
output parents. The SVG represents *saved metadata* and is **not interactive**:
LIVE bars remain the physical knob values even when snapshot A–D is selected.
It does **not** alter Rack panels, provide a reskinnable runtime UI, execute
audio, or export a plugin.

### Opt-in route-aware static panel

When the source bundle was packed with **--format-version 2**, the existing
performance panel can also display a visual matrix of every controller's saved
direct Macro8 cable destinations:

~~~bash
python3 tools/instrument-builder/instrument_builder.py preview \
  Echo_Motion.msinstrument --show-routes --out Echo_Motion_Routed.svg
~~~

The route-aware SVG retains the familiar eight controls and A–D snapshot
concept above an additional **saved routing map**. For each Macro8 control,
the map shows a source-to-destination connector, the first saved destination
plugin/model and Rack input, the source-declared port name when verified,
and total saved cable/unknown-input counts. Every control has a row, including
unused controls. A fan-out with several destinations shows one destination
and an explicit **+N more** count; the SVG row's accessible title includes
up to three source-derived destinations. Use `routes --json` for the complete
saved routing list. Controllers and rows are deterministic and sorted by
source module and control number; destination selection also has a stable
sort order.

For current, **FMVoice-marked** v2 archives, FMVoice's four CV input
descriptors (pitch, ratio, index and feedback) appear with their exact
source-backed labels. FoldDrive, ClockedLFO and the older original modules
use the same verified v2 route contracts. Unknown third-party inputs and
FMVoice ports in older unmarked/ClockedLFO/FoldDrive-marked v2 archives are
prominently counted as **UNVERIFIED INPUT**. A valid source bundle can still
be previewed when routes are unknown: the panel never upgrades their
historical contract or pretends they work. For v1, `--show-routes` exits with
error code **2** and creates no SVG, because the v1 manifest contains no
route metadata; repack the trusted `.vcv` source as v2 first.

This is an opt-in presentation flag only. **Without --show-routes, output
is byte-for-byte unchanged** (including existing v1/v2 base panels and
established SVG tests). Source ZIPs, manifest versions, patch bytes, saved
parameter state and the default `preview` command remain unchanged.
Every input goes through full ZIP, SHA-256, patch and manifest re-derivation
before any output file is created; malformed routes or tampered source
metadata are rejected. The SVG escapes source text and has no scripts,
external requests, runtime playback or interactive controls. Cable counts
are saved **graph** facts, not measured CV/audio, working DAW automation,
plugin loadability, correct musical routing or a published instrument.

### Source-bundle compatibility preflight

Use `check` to verify a `.msinstrument` **source bundle** and compare only
its first-party model slugs against the repository's
`plugins/ModularSynth/plugin.json`:

```bash
python3 tools/instrument-builder/instrument_builder.py check \
  Morphing_State_Pad.msinstrument

python3 tools/instrument-builder/instrument_builder.py check \
  Morphing_State_Pad.msinstrument --format json

# Optional: inspect against a different MODULAR-SYNTH source checkout.
python3 tools/instrument-builder/instrument_builder.py check \
  Morphing_State_Pad.msinstrument --repo-root /path/to/MODULAR-SYNTH --json

# Optional fail-fast preflight: require v2 *source-verified* Macro8 routing.
python3 tools/instrument-builder/instrument_builder.py check \
  Echo_Motion.msinstrument --require-verified-routes

# Machine-readable result includes `verifiedRoutes` only with this flag.
python3 tools/instrument-builder/instrument_builder.py check \
  Echo_Motion.msinstrument --require-verified-routes --json
```

The command first validates the ZIP member allowlist, saved patch, manifest
schema and SHA-256 and independently re-derives `requiredPlugins` (the same
integrity checks as `inspect`). Next it reads the first-party collection
manifest and groups model references by plugin/model, sorted deterministically
with stable Rack module IDs. It reports:

| Status | Exact meaning |
| --- | --- |
| `DECLARED` | A `ModularSynth/<model>` slug is present **with exact case** in this checkout's first-party manifest |
| `MISSING` | A patch references `ModularSynth/<model>` that is absent from the manifest |
| `UNKNOWN` | All other plugin/model references, including `Cardinal` and `Fundamental`; their availability is deliberately **not** assessed |

The default text report and `--format json` / `--json` output have stable
ordering, counts and no machine-specific absolute paths or timestamps.
Exit code **0** means no missing first-party declarations; **1** means at
least one missing first-party slug (report still printed); **2** means the
bundle, schema or collection manifest is invalid/unreadable. Third-party
`UNKNOWN` references alone do **not** cause failure.

With `--require-verified-routes`, `check` additionally demands an intact
**format-v2** bundle with at least **one direct saved Macro8 output cable** and
source-backed descriptors for **every** such cable's destination input. This
optional stricter check fails with exit code **1** if any destination is
`UNVERIFIED`, there are zero Macro8 routes, or the bundle is format v1. It
does not change how source ZIPs are packed, checked by default, or reopened.
Pack a v2 archive with `pack --format-version 2` when this gate is needed;
v1 deliberately has no saved mapping contract and cannot receive a false
empty-route pass.

The opt-in JSON `verifiedRoutes` report contains a separate `status`, a
machine-readable `reason` (`V1_NO_ROUTE_CONTRACT`,
`NO_DIRECT_MACRO8_ROUTES`, or `UNVERIFIED_DESTINATIONS`), route counts, and
every direct Macro8 cable's stable ID, source, destination module/model and
input index. Route diagnostics are ordered by saved cable ID, not by cable
array order; mixed known and unknown destinations are all shown. A
`SOURCE_VERIFIED` destination means its first-party Rack input name/index and
CV/audio kind match this **source revision**, not that connecting Macro8 is
musically useful, that Rack has loaded the module, or that the parameter is
automatable by a host. Other patch cables, third-party port bounds, binaries,
DAW automation, and runtime audio remain unverified. Older unmarked v2 bundles with ClockedLFO routes, unmarked or
ClockedLFO-marked v2 bundles with FoldDrive routes, and unmarked,
ClockedLFO-marked or FoldDrive-marked v2 bundles with FMVoice routes retain
their original `UNVERIFIED` interpretations. The strict gate will fail such routes until
repacked from trusted `.vcv` source with the appropriate new v2 contract. The existing default `check` output remains
unchanged for backwards compatibility.

**Important:** `DECLARED` does not establish that the model was compiled,
registered in a specific build, installed in the user's host, or loadable in a
DAW. It does not inspect third-party plugins, third-party port indices,
dynamic libraries, audio behavior or external sample paths. This is a
source-level compatibility aid, not a Rack plugin installer or validator.

## Performance workflow

1. Create a Macro8 and connect outputs **1–8** to oscillator, filter, envelope,
   effect, or other module CV inputs.
2. Set the eight performer knobs for an initial sound. Their normalized values
   are mapped to **0…10 V** by default; right-click the module to choose
   **−5…+5 V** separately for any output.
3. Set the **STORE/RECALL** toggle to **STORE** and press **A**. This captures
   the eight current knob positions, not the instantaneous smoothed CV.
4. Change the knobs and capture **B**, **C**, and **D** as needed.
5. Set the toggle to **RECALL**. Pressing a stored slot smoothly moves all
   eight CV outputs toward that slot's target. The **MORPH TIME** knob ranges
   from 0 to 5 seconds, expressed as approximately 99.9% settling time.
6. Press **LIVE** to return to the eight live knob values with the same
   smoothing. Use the context menu to rename macros (printable ASCII,
   maximum 12 characters).

**Important:** While a snapshot is selected, the physical macro knobs remain
the editable *live* values. They do not visually jump to the stored snapshot
positions. The active slot LED identifies the current target source. Press LIVE
before expecting the knobs to influence the CV outputs again.

A snapshot can be recaptured. A, B, C and D are initially empty, and pressing
an empty slot in RECALL mode does nothing. Outputs are monophonic control
voltages, intended to be patched wherever modulation is desired.

## State and compatibility

Rack saves public knob/switch parameters through its normal parameter state.
Macro8 separately saves custom state under a versioned object:

```json
{
  "macro8Version": 1,
  "names": ["Macro 1", "Macro 2", "Macro 3", "Macro 4",
            "Macro 5", "Macro 6", "Macro 7", "Macro 8"],
  "snapshots": [
    [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
    null,
    null,
    null
  ],
  "selectedSlot": -1
}
```

Each populated snapshot is eight normalized values in `[0,1]`. `null`
means an empty slot. `selectedSlot` is `-1` for live knobs or `0…3`
for A–D. Unknown state versions are ignored rather than guessed; malformed
snapshot entries are skipped, and finite numeric values are clamped.

Snapshot values are atomics and use a generation counter so an audio-thread
load is bounded and never waits for a concurrent state update. If a slot is
temporarily being published, the callback holds its current output while
retaining the selected slot and retries on the next sample. Patch serialization
makes bounded retries to reduce the chance of losing a slot to an in-flight
capture. Editable labels are published as immutable shared strings so GUI
drawing and non-UI host state serialization do not race.

The DSP hot path has no heap allocation, string handling, mutex, file access,
host UI calls, or blocking operations. The eight smoothers use **double**
accumulators (to avoid float rounding stalls at high sample rates), cache
the per-sample coefficient when time/sample rate are unchanged, and maintain
independent output state. IEEE-754 bitwise finite checks work even when
`-ffast-math` is enabled.

**Current limits:** Snapshot capture has no dedicated undo-history item;
macro labels are not automatically synchronized with DAW automation names;
there is no external modulation input or independently programmable range
beyond unipolar/bipolar selection. These are follow-up milestones.

## Existing first-party registration

Macro8 is registered in `plugins/ModularSynth` in the full Cardinal
collection (source in `plugins/ModularSynth/src/Macro8.cpp`, DSP core in
`Macro8.hpp`, panel in `plugins/ModularSynth/res/Macro8.svg`). The offline
Instrument Builder does not modify plugin registration, Mini builds, or runtime
module loading. New patches must still reference module slugs available in
the intended Cardinal build.

## Tests and acceptance

Run the offline Instrument Builder tests first:

```bash
python3 -m unittest discover -s tools/instrument-builder -p "test_*.py" -v
```

They exercise real factory Macro8 data, deterministic ZIP bytes, pack/inspect/
unpack/repack roundtrips, strict schemas, malformed snapshots and ranges,
source-identity mismatches, hostile ZIP paths/symlinks/compression, and
non-overwriting destinations. Compatibility tests scan the **nine genuine**
`MODULAR_-` factory patches, then exercise verified bundles for the four
that contain Macro8 (the other five lack Macro8 and are tested as raw model
references, since `pack` requires Macro8). They cover missing first-party
slugs, explicitly UNKNOWN external modules, manifest collisions, tampering,
deterministic text/JSON and exit codes. The SVG preview tests additionally verify XML
escaping against markup injection, accessible contrast, 64-character title
wrapping, eight fixed control labels, four snapshots, deterministic output,
multiple controllers, invalid bundles, and non-overwriting SVG generation.
The tool uses saved performance state; tests do not load or render a host plugin.

Run the Rack-independent DSP test:

```sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror -pthread \
  tests/macro8_dsp_test.cpp -o /tmp/macro8_dsp_test
/tmp/macro8_dsp_test
```

This checks 8 independent controls, 0–10 V/bipolar voltage conversion,
finite-input handling under strict fast-math, one-second morphing, five-second
morphing at 48/96/192 kHz, every snapshot slot, transient-write detection,
recapture, invalid slot IDs and reset behavior. It does not test host GUI/rendering.

**Release acceptance still required after integration:**

- Native Linux/macOS/Windows plugin compilation and validation;
- Open Macro8 in a DAW and confirm all eight CV outputs work;
- Store A–D, save/reopen patch, recall each and confirm names/modes persist;
- Exercise 0-second and 5-second transitions at 44.1/48/96 kHz and 64/256
  sample buffers with no clicks or NaNs;
- Run existing Cardinal plugin self-tests, host rescans and memory checks;
- Validate panel artwork, keyboard navigation, and user labels on HiDPI.

Until these pass, treat Macro8 as an **implemented, unverified foundation**.
