# MODULAR-SYNTH — Manual UI and DAW State QA

**Status: NOT EXECUTED.** This is a checklist for human verification of
the nine first-party modules, including the introductory Morph VCO, State Filter
and Macro8 voice as well as FMVoice, Chance Hold and Dual VCA. No desktop/DAW
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
  **State Filter**, **Fold Drive**, **Macro8 Performance Macros**,
  **Stereo Echo**, **Clocked LFO**, **FM Voice**, **Chance Hold** and
  **Dual VCA** in the **MODULAR-SYNTH Originals** collection.
  Search resolves all nine.
- [ ] Inspect each SVG panel, ports, labels, controls and lights at normal
  and HiDPI scaling; zoom, close/reopen the editor and check alignment.
- [ ] Confirm the release package actually contains
  `ModularSynth/res/MorphVCO.svg`,
  `ModularSynth/res/StateFilter.svg`,
  `ModularSynth/res/FoldDrive.svg`,
  `ModularSynth/res/Macro8.svg`,
  `ModularSynth/res/StereoEcho.svg`,
  `ModularSynth/res/ClockedLFO.svg`,
  `ModularSynth/res/FMVoice.svg`,
  `ModularSynth/res/ChanceHold.svg` and
  `ModularSynth/res/DualVCA.svg`.

- [ ] With Fold Drive between Morph VCO and State Filter, verify dry
  transparency at zero DRIVE, audible fold changes with increasing DRIVE,
  positive/negative BIAS asymmetry and MIX CV direction. Start with low
  VCA/host gain, test 1/8/16 lanes, and record aliasing, summed headroom,
  CPU and reset-on-playback behavior at 44.1/48/96 kHz. **No results are
  recorded yet:** the source fold is not bandlimited or oversampled, and
  its ±10 V bound applies per voice, not to summed host audio.

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

- [ ] Save a standalone `.vcv` patch with the three modules used by the
  introductory MorphVCO + StateFilter + Macro8 voice, cables,
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
- [ ] Run all discovered standalone C++ DSP suites using
  `python3 -B tests/run_dsp_tests.py --sanitize=auto`, then run the
  repository/Module Forge/Instrument Builder Python suites. Attach their
  exact commit, compiler/sanitizer profile and outputs. The seven-original
  and generated-module HEADLESS wrapper smokes use a **test-only Rack stub**;
  they do **not** prove a real Rack/DPF plugin build.
- [ ] Check CI/build status and release archive contents. Attach
  screenshots of actual working UI (including HiDPI), a sample patch,
  saved DAW project, and any bug reports.
- [ ] For macOS release tags, confirm an **actual matching `.pkg`** was
  generated and uploaded by the completed tag workflow (not merely that
  its missing-file YAML guard passed source tests). Install it on a real
  macOS machine and validate plugin discovery, loading, audio, state and
  DAW reopens. Apply equivalent artifact/install checks to other targets.
- [ ] For Windows release tags, confirm a **nonempty tag-matching fork ZIP**
  (`MODULAR-SYNTH-win32|win64-<tag>.zip`) **and exactly one matching-target
  nonempty Inno Setup installer** were uploaded. Install that exact artifact
  on Windows and exercise plugin discovery, audio and state reopen; the
  source YAML gate alone is not sufficient evidence.

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

The standard-library-only checker validates nine first-party source panels
(Morph VCO, State Filter, FoldDrive, Macro8, StereoEcho, ClockedLFO,
FMVoice, ChanceHold, DualVCA) as parseable SVGs with an SVG namespace
and expected **12/14/12/20/16/16/12/16/12 HP** widths, standard
**3U height** and Rack viewBoxes of **15 px/HP × 380 px**. Seven panels
specify 128.5 mm physical height; ClockedLFO and ChanceHold declare
equivalent 380 px dimensions. It cross-checks exact `setPanel()` asset paths in C++ and
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
python3 -m unittest discover -s tests -p 'test_panel_focus_contrast.py' -v
```

The audit derives **actual text foreground colors** from NanoVG
`nvgRGB()` / `nvgText()` calls in all nine module widgets, and reads SVG
panel fill and decorative control-outline colors. It computes standard
sRGB relative luminance and contrast ratios and flags measured swatches
below **4.5:1** for small text and **3:1** for SVG control outlines as
**advisory warnings**. Use `--fail-on-low-contrast` to turn those measured
warnings into exit status 2; the default is report-only.

The original panel SVGs now retain **6.45–6.64:1** decorative dial-ring
contrast on Morph VCO, **6.17:1** for Macro8's nine knob surrounds,
**6.07:1** for its eight output-jack surrounds, **6.35:1** for its five
snapshot-button surrounds, and **6.24:1** for its store-mode rim.
FM Voice's five dial rings measure **6.35–6.64:1**. These changes preserve
all corresponding circle/rect geometry. Dedicated tests pin the Macro8/FM
Voice control centers and verify the source-color ratios stay at least **6:1**.
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

Across the dark-gradient panels, the source palette bounds
remain comfortably above the 4.5:1 text advisory. ClockedLFO has a
separately inspected flat/layered SVG background; all **112 local source-label
contrasts across the nine panels remain UNKNOWN**, including Macro8's
dynamic labels. The base-only bounds can be evaluated for 80 sites but
never establish the actual local pixel background. An
invalid/missing stop, transparency, stylesheet or unsupported paint construct
withholds the bound; a weak lower bound is **inconclusive**, not automatic
proof of low contrast, and does not trigger strict-mode failure. The bare
SVGs were preview-rendered with Inkscape for geometry/color inspection, but
that preview omits C++ NanoVG labels and Rack controls. No separate opaque
plates were added to each text label; two panels now have solid signal-lane
backplates, with source-color caveats documented below.

StereoEcho's four radial-gradient knob-dial fills are also reported as
**UNKNOWN** control outline ratios, while its seven flat port-ring
fill/stroke pairs are measurable. Many thin SVG circles/outlined
decorations sit **behind** actual Rack knobs and ports; their palette
ratios are not proof of interactive control visibility.

This preflight **does not render the UI or establish WCAG conformance**.
It cannot assess antialiasing, font size/weight in final pixels, labels over
knobs, dynamic states, color-vision usability, hit areas or keyboard use.
Review a real host screenshot and complete the manual UI checks above.

### Stereo Echo / Dual VCA signal-path zone review

The two dense lower-port areas now distinguish the **input** and **output**
lanes with broad solid-color backplates and visibly outlined boundaries:

| Panel / zone | Literal SVG fill | Outline | Source fill/outline ratio | NanoVG label/fill ratio (lowest in zone) |
| --- | --- | --- | ---: | ---: |
| Dual VCA: four signal/CV inputs | `#122E3E` | `#78D5DB` | 8.30:1 | 10.42:1 |
| Dual VCA: A, B and summed outputs | `#28243F` | `#D1AAF1` | 7.59:1 | 9.87:1 |
| Stereo Echo: L/R audio and time/feedback CV inputs | `#132F41` | `#6FD8DE` | 8.31:1 | 9.28:1 |
| Stereo Echo: lower-left **MIX CV input** | `#15334A` | `#6FD8DE` | 7.82:1 | 8.74:1 |
| Stereo Echo: lower-right L/R outputs | `#2D2646` | `#C9A4F3` | 6.83:1 | 8.06:1 |

**Before:** the two panels had zero enclosed role-separated signal rails:
thin dividers, decorative port rings and gradient backgrounds did not
establish five solid roles/label-underlay regions. **After:** five enclosed
zones are statically associated with all **14 real Rack PJ301MPort centers**
and all **14 matching NanoVG label coordinates and source colors**. The
decorative jack rings are checked for containment inside their zones. The
signal-zone changes are SVG-only; the underlying module DSP and Rack widget
positions, port identifiers and parameter identifiers are unchanged.

The source-driven regression is separate from the general SVG geometry
preflight:

```sh
python3 tools/ui-check/port_rail_audit.py
python3 -m unittest discover -s tests -p 'test_ui_panels.py' -v
```

It checks actual `addInput` / `addOutput` callsites, expected port roles,
label coordinates, literal opaque rail paint, port-ring containment, and
source-color ratio advisories (at least 3:1 for frame strokes and 4.5:1
for labels against their solid rail fill). Fixture regressions deliberately
reject a moved jack **still inside the physical panel**, a false MIX CV
output classification, deleted rail, escaped label, insufficient palette
contrast, or clipped port decoration. This establishes the reported
**source-palette** figures, not actual composited screen pixels.

For repeatable SVG artwork inspection, render at fixed width, for example:

```sh
inkscape plugins/ModularSynth/res/DualVCA.svg --export-type=png --export-width=600 --export-filename=/tmp/DualVCA-preview.png
inkscape plugins/ModularSynth/res/StereoEcho.svg --export-type=png --export-width=600 --export-filename=/tmp/StereoEcho-preview.png
```

The two SVGs were preview-rendered before and after the change, and the
jack-zone boundaries, halo fit and left MIX CV grouping were visually
inspected at 600 pixels wide. **The SVG-only render cannot show labels
drawn by C++, Rack jack controls, plug/cable occlusion, HiDPI scaling or
actual keyboard/host interaction.** It is not an accessibility conformance
measurement. A host tester must therefore still verify:

- [ ] All fourteen labels and their jacks align at normal and HiDPI zoom,
  without clipped letters or border/plug collisions.
- [ ] The Stereo Echo **MIX CV** remains obviously an input despite being
  beside the **L OUT/R OUT** pair; both output lanes are distinct.
- [ ] Dual VCA A/B audio/CV inputs are easily distinguished from A/B/SUM
  outputs in an active patch with ordinary colored cables.
- [ ] The panel remains readable at practical display sizes and under common
  color-vision differences, without depending solely on the hue of a jack.

## 9. Parameter, port and tooltip discoverability (manual)

The following inventory is based on first-party Rack `configParam()`,
`configInput()`, `configOutput()` metadata and the matching DSP scaling,
not on a recorded plugin-tooltip screenshot.

| Module | Knob tooltip/display conventions | Port and mode semantics |
| --- | --- | --- |
| **Morph VCO** | Snapped octave offset **−4 to +4**; fine tune **−100 to +100 cents**; wave morph **0–100%**; pulse width **5–95%**; FM depth **0–100%** | Pitch **1 V/oct**; FM **5 V/oct at full depth**; morph and PWM CV each add **0.1 normalized units per volt** to their knobs; morphed/sine audio outputs nominally **±5 V** |
| **State Filter** | Cutoff shows actual Hz (about **20 Hz–20 kHz**, **1 kHz** default) despite log2 internal storage; resonance/drive show **0–100% of normalized control range** | Cutoff CV adds **1 octave per volt**; resonance/drive CV each add **0.1 normalized units per volt**; LP/BP/HP outputs are filtered audio |
| **Fold Drive** | DRIVE **0–100%** (30% default), BIAS **−100…+100%** (0% default), WET MIX **0–100%** (65% default); smooth ~3 ms control changes | IN nominal ±5 V; DRV/BIA/MIX CV each add **0.1 normalized units per volt**; OUT is clamped to ±10 V **per lane**, not summed host audio; sine fold is not bandlimited or oversampled |
| **Macro8** | Eight macro positions show **0–100%**; snapshot transition time **0–5 s** represents **99.9% settling** | Each CV output selects **0 to +10 V** unipolar or **−5 to +5 V** bipolar; A–D buttons **store or recall according to mode**; LIVE returns to physical macro knobs |
| **StereoEcho** | Echo time **1–1000 ms** (**250 ms** default); feedback **0–90%** (**35%** default); wet mix **0–100%** (**40%** default); ping-pong crossfeed **0–100%** (**50%** default) | Unpatched **right input uses left audio**; signed TIME CV adds **100 ms/V**, feedback and wet-mix CV add **0.1 normalized units (10 percentage points) per volt**; L/R outputs are mixed wet/dry audio |
| **FMVoice** | Octave **−4 to +4**; fine tune **−100 to +100 cents**; carrier/modulator ratio **0.125–16×**; phase-modulation index **0–8 radians**; modulator feedback **0–95%** | Pitch CV **1 V/oct** (C4 at 0 V); ratio CV **+1 V doubles the ratio**; index CV adds **0.8 radians/V**; feedback CV adds **9.5 percentage points/V**; separate carrier FM and modulator sine audio outputs are nominally **±5 V**. The phase-modulation core is not bandlimited. |
| **ClockedLFO** | Free-run rate **1/64–16 Hz** (**0.5 Hz** default); snapped clock ratios **1/4, 1/2, 1, 2 or 4** cycles per clock period (default **1**); output phase **0–100%**; pulse width **5–95%** | External **CLK** and **RESET** are rising-edge inputs (≥2 V, rearmed at ≤1 V); free RATE CV is **1 V/oct**; SIN/TRI/RAMP/PULSE are **±5 V**, EOC nominal **+10 V / 1 ms**. External pulses, not host BPM, govern tempo lock. |

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
**13 `nvgText()` call sites**. At the four-model PR #41 snapshot, these
augmented 31 earlier calls to **44**; the current **seven-model** source
audit checks **84** label calls after FMVoice integration. Since the panel background and four
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

## 11. FMVoice manual host acceptance (NOT EXECUTED)

FMVoice has a registered original **12 HP** source panel, five controls,
four CV inputs and two audio outputs. Its two-operator phase-modulation
engine has standalone C++ tests; this does not establish host audio quality,
GUI alignment, real Rack-header compatibility or a published plugin binary.

- [ ] Discover **FM Voice** exactly once in the **MODULAR-SYNTH Originals**
  module browser. Verify the 12 HP artwork, five knobs, four CV inputs,
  two output jacks and tooltip labels at normal and HiDPI zoom.
- [ ] Open [FM Voice Performance](../patches/examples/MODULAR_-_FM_Voice_Performance.vcv)
  in an actual fork build. Route HostMIDI pitch through FMVoice and the
  bundled ADSR/VCA to HostAudio2. Verify key-on, note-off release and no
  unintended stuck sound.
- [ ] Exercise octave/fine, ratio, index and feedback knobs and each CV
  input; compare to the source-defined scaling in the table above.
  Record output level, high-register aliasing and audible clicks.
- [ ] Test 1, 8 and 16 simultaneous MIDI voices, resets and sample rates
  44.1/48/96 kHz; record CPU, summed headroom and a low-level audio sample.
- [ ] Save and reopen a standalone patch and DAW session; verify parameter,
  port, panel and cable state. Record build SHA, host version and screenshots.

All items remain unverified pending a real host build and audition.
