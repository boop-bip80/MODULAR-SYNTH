# Instrument Builder — Macro8 foundation (work in progress)

## Scope

**Macro8 is a first-party performance controller, not a finished Instrument Builder.**
It provides eight independently controllable CV outputs, custom short labels,
four versioned snapshot slots, and sample-smoothed transitions between sounds.
It does **not** yet group modules, compile nested patches, export a standalone
instrument/plugin, or provide a custom reskinnable performance panel.

The source lives under `plugins/ModularSynth` to preserve the upstream Cardinal
module collection. The Rack-independent DSP/snapshot implementation is
`plugins/ModularSynth/src/Macro8.hpp`.

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

## Build registration required

Macro8 is isolated in this workstream. Integrate these exact shared-file
changes in one consistent commit with the original-module registry:

- `plugins/Makefile`: add `PLUGIN_FILES += ModularSynth/src/Macro8.cpp`
  immediately after the existing `MorphVCO.cpp` entry.
- `plugins/ModularSynth/src/plugin.hpp`: add
  `extern Model* modelMacro8;`.
- `plugins/plugins.cpp`: inside `initStatic__ModularSynth()`, register
  `p->addModel(modelMacro8);` along with `modelMorphVCO`; wrap the
  `if (spl.ok())` body in braces.
- `plugins/ModularSynth/plugin.json`: append a module entry:
  `{"slug":"Macro8","name":"Macro8 Performance Macros","description":"Eight named CV performance outputs with four recallable smoothly morphing snapshots and per-output voltage modes.","tags":["Controller","Utility"]}`.

The SVG panel is `plugins/ModularSynth/res/Macro8.svg`. No additional
third-party library is needed.

## Tests and acceptance

Run the Rack-independent test:

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
