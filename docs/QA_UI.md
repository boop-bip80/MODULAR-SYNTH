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

The standard-library-only checker validates four first-party source panels
(Morph VCO, State Filter, Macro8, StereoEcho) as parseable SVGs with an SVG
namespace and expected **12/14/20/16 HP** widths, standard **3U
(128.5 mm)** height, and Rack viewBoxes of **15 px/HP × 380 px**. It cross-checks the exact `setPanel()` asset paths in C++ and
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
`nvgRGB()` / `nvgText()` calls in all four module widgets, and reads SVG
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

**Important uncertainty:** The first-party SVGs use gradient and/or layered
backgrounds. The tool keeps **actual label underlays UNKNOWN** even when
the source foreground is a static NanoVG color. For an explicitly opaque
full-panel base gradient with valid literal RGB stops, it additionally
computes a **conservative source-only base-gradient contrast lower bound**:
every possible interpolated RGB channel is bounded by the extrema of the
stops, and relative luminance is monotone in each channel. The reported
bound compares text foreground with that **bottom SVG layer only**. It does
not account for decorative circles, lines, shadows, Rack knobs, NanoVG
antialiasing or an actual font glyph pixel; it is **not a measured local
label contrast or a WCAG pass**.

Across the four original dark-gradient panels, the source palette bounds
remain comfortably above the 4.5:1 text advisory. The audit deliberately
keeps these sites marked UNKNOWN, including Macro8's dynamic labels. An
invalid/missing stop, transparency, stylesheet or unsupported paint construct
withholds the bound; a weak lower bound is **inconclusive**, not automatic
proof of low contrast, and does not trigger strict-mode failure. The bare
SVGs were preview-rendered with Inkscape for geometry/color inspection, but
that preview omits C++ NanoVG labels and Rack controls. No opaque label
plates were added because the source evidence does not justify obscuring
the existing design.

StereoEcho's four radial-gradient knob-dial fills are also reported as
**UNKNOWN** control outline ratios, while its seven flat port-ring
fill/stroke pairs are measurable. Many thin SVG circles/outlined
decorations sit **behind** actual Rack knobs and ports; their palette
ratios are not proof of interactive control visibility.

This preflight **does not render the UI or establish WCAG conformance**.
It cannot assess antialiasing, font size/weight in final pixels, labels over
knobs, dynamic states, color-vision usability, hit areas or keyboard use.
Review a real host screenshot and complete the manual UI checks above.

## 9. Parameter, port and tooltip discoverability (manual)

The following inventory is based on first-party Rack `configParam()`,
`configInput()`, `configOutput()` metadata and the matching DSP scaling,
not on a recorded plugin-tooltip screenshot.

| Module | Knob tooltip/display conventions | Port and mode semantics |
| --- | --- | --- |
| **Morph VCO** | Snapped octave offset **−4 to +4**; fine tune **−100 to +100 cents**; wave morph **0–100%**; pulse width **5–95%**; FM depth **0–100%** | Pitch **1 V/oct**; FM **5 V/oct at full depth**; morph and PWM CV each add **0.1 normalized units per volt** to their knobs; morphed/sine audio outputs nominally **±5 V** |
| **State Filter** | Cutoff shows actual Hz (about **20 Hz–20 kHz**, **1 kHz** default) despite log2 internal storage; resonance/drive show **0–100% of normalized control range** | Cutoff CV adds **1 octave per volt**; resonance/drive CV each add **0.1 normalized units per volt**; LP/BP/HP outputs are filtered audio |
| **Macro8** | Eight macro positions show **0–100%**; snapshot transition time **0–5 s** represents **99.9% settling** | Each CV output selects **0 to +10 V** unipolar or **−5 to +5 V** bipolar; A–D buttons **store or recall according to mode**; LIVE returns to physical macro knobs |
| **StereoEcho** | Echo time **1–1000 ms** (**250 ms** default); feedback **0–90%** (**35%** default); wet mix **0–100%** (**40%** default); ping-pong crossfeed **0–100%** (**50%** default) | Unpatched **right input uses left audio**; signed TIME CV adds **100 ms/V**, feedback and wet-mix CV add **0.1 normalized units (10 percentage points) per volt**; L/R outputs are mixed wet/dry audio |

The percentages describe *control positions*, not linear acoustic
gain, resonance Q, or the instantaneous CV when a snapshot is selected.
Renamed Macro8 panel labels do not rename the underlying host parameter IDs.

- [ ] Hover/right-click every first-party knob and jack in an actual plugin
  build. Confirm these labels and units appear, default values are sensible,
  and automation/DAW parameter lists remain understandable.
- [ ] Change Macro8 CV polarity and Store/Recall mode, then verify that
  the corresponding tooltip text and observed voltage/scene behavior agree.
- [ ] Verify the percentage-formatted knobs preserve their underlying
  normalized state and DAW automation values when an existing patch reopens.

The automated source consistency checks are:

```sh
python3 -m unittest discover -s tests -p 'test_first_party_tooltips.py' -v
```

**Status:** not manually verified; passing these text/source checks does
not prove actual tooltip rendering, localization or host accessibility.

## 10. StereoEcho source-panel acceptance (pending host UI test)

StereoEcho's first-party source/panel is checked independently of static
plugin loader/manifest registration. Its **16 HP x 3U**
SVG uses a **240 x 380** viewBox; the C++ widget statically declares
**4 centered controls**, **5 input jacks**, **2 output jacks**, and
**13 `nvgText()` call sites**. With the prior 31 label sites, the audit
now checks **44** source label calls. Since the panel background and four
knob-dial fills are gradients, those local contrasts remain **UNKNOWN**;
none are promoted to a contrast pass by inspecting gradient stops.

- [ ] In a build with StereoEcho registered, confirm it appears
  once in the browser and displays a correctly scaled 16 HP panel.
- [ ] Inspect TIME, FEEDBACK, DRY/WET, PING-PONG knobs; IN L/R, TIME/FB/MIX CV
  inputs; L/R outputs and all painted labels at normal and HiDPI zoom.
- [ ] Hover these StereoEcho knobs and jacks; verify their units,
  250 ms/35%/40%/50% defaults, maximum feedback 90%, and additive CV
  descriptions in a real Rack/DAW tooltip, including negative TIME CV.
- [ ] Check unpatched RIGHT follows LEFT and patching RIGHT overrides the
  normalled input; confirm the L/R mixed wet/dry output tooltips are clear.
- [ ] Patch mono-to-stereo, explicit left/right, all three CV controls and
  host outputs; verify port mapping, normalled right input and controls.
- [ ] Save/reopen both a standalone patch and a DAW project with StereoEcho
  and verify UI, cable routing and audible state. Record host, screenshot
  and build SHA; actual UI/DAW verification is **not yet executed**.

Source-level checks (independent of registration) are:

```sh
python3 tools/ui-check/validate_panels.py
python3 tools/ui-check/contrast_audit.py --fail-on-low-contrast
python3 -m unittest discover -s tests -p 'test_ui_panels.py' -v
python3 -m unittest discover -s tests -p 'test_panel_contrast.py' -v
```

The checks do not render StereoEcho, prove jack hitboxes, or determine
pixel contrast over its gradient panel. Runtime audio/host behavior is
outside these static geometry and color tools.
