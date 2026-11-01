# MODULAR-SYNTH — Manual UI and DAW State QA

**Status: NOT EXECUTED.** This is a checklist for human verification of
the first-party Morph VCO, State Filter, and Macro8 modules. No desktop/DAW
UI run is claimed. All checkboxes intentionally remain unchecked.

| Record before running | Value |
| --- | --- |
| Tester, date, build commit | Not run |
| OS/architecture; standalone or DAW/version | Not run |
| Plugin format; sample rate/buffer size | Not run |
| Patch/project files; screenshots; logs | Not captured |
| Result | **UNVERIFIED** |

Use a real packaged build of the exact commit under test. Mark each item
pass/fail with repro steps and an evidence link; repeat the essentials on
each supported host/plugin format.

## 1. Discovery, resources, layout

- [ ] The app/DAW discovers and opens the plugin with no crash, blank panel,
  missing SVG warning, or host rescan error.
- [ ] Module browser offers exactly one each of **Morph VCO**,
  **State Filter**, and **Macro8 Performance Macros** in the
  **MODULAR-SYNTH Originals** collection. Search resolves all three.
- [ ] Inspect each SVG panel, ports, labels, controls and lights at normal
  and HiDPI scaling; zoom, close/reopen the editor and check alignment.
- [ ] Confirm the release package actually contains
  `ModularSynth/res/MorphVCO.svg`,
  `ModularSynth/res/StateFilter.svg` and
  `ModularSynth/res/Macro8.svg`.

## 2. State Filter signal and CV

- [ ] Route a known oscillator to State Filter **IN**, then **LP** to host
  audio. Sweep **CUTOFF** and hear/observe a smooth frequency response.
- [ ] Compare **LP**, **BP**, and **HP** outputs on an analyzer; all remain
  finite and distinguishable. Increase **RESONANCE** and **DRIVE** across
  their full ranges and check for runaway levels, stuck output or clicks.
- [ ] Patch positive/negative modulation separately to **FREQ** (1 V/oct),
  **RES**, and **DRV** (10 V full span). Check modulation direction, scaling
  and return to knob-only control when disconnected.
- [ ] Repeat with 1 and 16 polyphonic channels; verify correct channel
  count and no audible cross-talk.
- [ ] Check 44.1/48/96 kHz and at least two buffer sizes. If the host
  permits, change sample rate while running and record artifacts.

## 3. Macro8 performance controls

- [ ] Patch **OUT 1** into Morph VCO's morph CV and **OUT 2/3** into State
  Filter resonance/drive CV. Turn the respective Macro8 knobs; check
  independent modulation and all remaining outputs with a voltage monitor.
- [ ] In default unipolar range each output tracks approximately
  **0, +5, +10 V** at knob minimum, midpoint, maximum (allow morph time
  to settle). Change one range in **right-click → CV output ranges**
  to bipolar and verify approximately **−5, 0, +5 V**; other outputs
  must retain their ranges.
- [ ] Rename all eight controls through **right-click → Rename
  performance controls**. Check short and long labels, keyboard
  editing/paste, panel legibility and persistence after editor reopen.
- [ ] Confirm independent knob/range state survives module duplication
  and that the copy does not modify the original.

## 4. Snapshot A–D and morphing

- [ ] Select **STORE**, set distinct values on all eight knobs, and
  capture slots **A**, **B**, **C**, **D** with the corresponding buttons.
  Select **RECALL**, recall each and verify the output CV and active light.
- [ ] In a fresh Macro8, recall an empty slot; live CV should continue
  unchanged and no slot should be falsely selected.
- [ ] Recall distinct slots with **MORPH TIME** at 0, ~1 and 5 seconds.
  Verify immediate 0-second response and smooth longer transitions
  with no permanent short-of-target freeze (repeat 5 seconds at 96 kHz).
- [ ] While recalled, move a physical macro knob: CV remains governed by
  the snapshot until **LIVE** is pressed; then CV returns smoothly to
  the knob positions and LIVE light activates. The current design does
  **not** animate knobs to recalled values.
- [ ] Recapture a slot in STORE and recall the replacement. Rapidly
  alternate slot buttons, STORE/RECALL and LIVE during playback; check
  clicks, stuck LEDs, invalid CV and crashes.

## 5. Patch/DAW state and recovery

- [ ] Save a standalone `.vcv` patch with all three modules, cables,
  8 custom macro names, mixed unipolar/bipolar ranges, four populated
  snapshots and one selected slot. Reopen and compare every value,
  label, selection, connection and the sound.
- [ ] Save a project in a supported DAW, quit the host completely, reopen
  and verify that the embedded patch and Macro8 state restore without
  manually reloading a patch.
- [ ] If available, map/automate macro/filter parameters and save/reopen.
  Check automation and snapshot recalls coexist without unintended jumps.
- [ ] Duplicate Macro8 or copy/paste a rack selection; verify the two
  instances have independent snapshot banks and labels.
- [ ] Test missing Macro8 custom JSON and an unknown `macro8Version`
  **only on a disposable copy** of a patch. Check for safe defaults
  and no crash, then restore the intact file.
- [ ] Save/reopen while host transport plays (where supported). Record
  any state loss, nonfinite output, crash or GUI-label corruption.
- [ ] Check undo/redo for knob/range edits; note the known current
  limitation: snapshot capture has no dedicated history action.

## 6. Release evidence and decision

- [ ] Sustain at least 10 minutes of audio with filter CV and repeated
  snapshot morphs. Record CPU, xruns/dropouts, sample rate and host.
- [ ] Run the standalone C++ DSP tests
  `tests/macro8_dsp_test.cpp`,
  `tests/statefilter_dsp_test.cpp`, and
  `tests/morphvco_dsp_smoke.cpp`; attach command/output and commit SHA.
- [ ] Check CI/build status and release archive contents. Attach
  screenshots of actual working UI (including HiDPI), a sample patch,
  saved DAW project, and any bug reports.

**Release gate:** Keep **UNVERIFIED** until a real tester records successful
GUI/host results, not just compilation or DSP unit tests. Block a
production-ready claim for crashes, state loss, corrupt panels, nonfinite
CV/audio, or repeatable real-time dropout regressions.

## 7. Automated panel geometry preflight (source-level only)

Run these separately from the manual UI/DAW acceptance checklist:

```sh
python3 tools/ui-check/validate_panels.py
python3 -m unittest discover -s tests -p 'test_ui_panels.py' -v
```

The standard-library-only checker validates that all three original panels
are parseable SVG documents with an SVG namespace, the expected **12/14/20 HP**
width and **3U (128.5 mm)** height, and Rack panel viewBoxes of **15 px/HP ×
380 px**. It cross-checks the exact `setPanel()` asset paths in C++ and
checks statically resolvable centered knobs, ports, switches and lights
against panel coordinate bounds. It conservatively expands simple constant
arrays and conditional positions; non-constant expressions are reported as
**NOTE** and skipped rather than guessed.

This is **not** a rendered or interactive visual test: it cannot validate
font availability, text clipping, visual overlaps, knob/port footprints,
screw positioning, hit areas, HiDPI layout, DAW state, or host audio. Keep
the manual checkboxes above unverified until an actual plugin/host UI run
is documented.

## 8. Source-color and contrast preflight (advisory only)

```sh
python3 tools/ui-check/contrast_audit.py
python3 -m unittest discover -s tests -p 'test_panel_contrast.py' -v
```

The audit derives **actual text foreground colors** from NanoVG
`nvgRGB()` / `nvgText()` calls in the three module widgets, and reads SVG
panel fill and decorative control-outline colors. It computes standard
sRGB relative luminance and contrast ratios and flags measured swatches
below **4.5:1** for small text and **3:1** for SVG control outlines as
**advisory warnings**. Use `--fail-on-low-contrast` to turn those measured
warnings into exit status 2; the default is report-only.

For the original panel SVGs, the source-swatches of the three Morph VCO
knob surrounds, five Macro8 snapshot-button rings, and Macro8 store-mode
switch rim were adjusted to approximately **3.27:1**, **3.30:1** and
**3.25:1**, respectively, against their adjacent flat circle/rect fills.
The source-level check should now complete successfully in strict mode:

```sh
python3 tools/ui-check/contrast_audit.py --fail-on-low-contrast
```

These numbers measure SVG decorative fill/stroke colors, **not** the
actual Rack widget controls after drawing/compositing.

**Important uncertainty:** The current SVG panels use gradient/layered
backgrounds. The tool marks the actual label underlay **UNKNOWN** and
may report contrast against known gradient *stop swatches* only as
context; it never treats those stop values as measured local text contrast.
Macro8's dynamic labels also require manual inspection. Many thin SVG
circles/outlined decorations sit **behind** actual Rack knobs and ports;
their ratios are not proof of interactive control visibility.

This preflight **does not render the UI or establish WCAG conformance**.
It cannot assess antialiasing, font size/weight in final pixels, labels over
knobs, dynamic states, color-vision usability, hit areas or keyboard use.
Review a real host screenshot and complete the manual UI checks above.
