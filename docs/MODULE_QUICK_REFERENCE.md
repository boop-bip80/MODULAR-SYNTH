# MODULAR-SYNTH Originals — musician's quick reference

Five first-party Rack models are **statically registered in source** and expected
under **MODULAR-SYNTH Originals** in the module browser after a successful build.
This page is a patching cheat sheet for the models actually
declared in [the collection manifest](../plugins/ModularSynth/plugin.json)
and [the checked-in example patches](../patches/examples/). All voltage and
control ranges below are from their C++ Rack metadata/DSP wrappers, **not**
measured audio or a verified DAW session.

## Choose a module

| Module (registered slug) | What it does | Jacks | Useful starting controls |
| --- | --- | --- | --- |
| **Morph VCO** (`MorphVCO`) | Polyphonic sine → saw → pulse oscillator | **4 in / 2 out** | Octave 0; fine 0 cents; morph 0%; pulse width 50%; FM depth 0% |
| **State Filter** (`StateFilter`) | Polyphonic multimode filter; simultaneous LP/BP/HP | **4 in / 3 out** | Cutoff 1 kHz; resonance 0%; drive 0% |
| **Macro8 Performance Macros** (`Macro8`) | Eight named performer CVs and four A–D scenes | **0 in / 8 out** | All eight macros 0%; unipolar 0 to +10 V; transition 0.25 s; RECALL |
| **Stereo Echo** (`StereoEcho`) | Polyphonic stereo delay with wet/dry and ping-pong crossfeed | **5 in / 2 out** | Time 250 ms; feedback 35%; wet 40%; crossfeed 50% |
| **Clocked LFO** (`ClockedLFO`) | Sixteen-lane free/externally clocked modulation; 5 wave/trigger outputs | **5 in / 5 out** | Free rate 0.5 Hz; clock ratio 1:1; phase 0%; width 50% |

### Morph VCO (`MorphVCO`)

[Source/configuration](../plugins/ModularSynth/src/MorphVCO.cpp)

- **Inputs:** PITCH is **1 V/oct**; exponential FM is **5 V/oct at 100% depth**.
  MORPH CV and PWM CV each add **0.1 of their normalized knob range per volt**
  (10 V full span), including negative CV. The sums are bounded in DSP.
- **Controls:** snapped octave offset −4…+4, fine tune −100…+100 cents,
  morph 0…100% (sine → saw → pulse), pulse width 5…95%, FM depth 0…100%.
- **Outputs:** morphed waveform and sine audio, nominally **±5 V**.
  Pitch/modulation ports can carry up to **16 polyphonic lanes**.

### State Filter (`StateFilter`)

[Source/configuration](../plugins/ModularSynth/src/StateFilter.cpp)

- **Audio input:** IN. Simultaneous **LP**, **BP** and **HP** audio outputs.
- **Controls:** cutoff about **20 Hz…20 kHz**, displayed in Hz (1 kHz
  default); normalized resonance and input drive 0…100%.
- **CV inputs:** FREQ adds **1 octave per volt** to the cutoff setting;
  RES and DRV each add **0.1 normalized units per volt** (10 V full span).
  The result is bounded by the filter DSP. Up to **16 polyphonic lanes**.

### Macro8 Performance Macros (`Macro8`)

[Source/configuration](../plugins/ModularSynth/src/Macro8.cpp) ·
[Instrument Builder state and export limits](INSTRUMENT_BUILDER.md)

- Eight independent **monophonic** CV outputs. Each has its own right-click
  range: **0…+10 V** unipolar or **−5…+5 V** bipolar; the eight live knobs
  show 0…100% normalized position.
- Choose **STORE** and press A/B/C/D to capture all eight knob values in
  one of four slots. Choose **RECALL** to select stored scenes; a fresh
  empty slot has no effect. **MORPH TIME** 0…5 seconds describes roughly
  99.9% settling. **LIVE** returns CV control to physical knob positions.
- Renaming uses the right-click menu (short printable ASCII names, up to
  12 characters). Recalled scenes **do not move the on-panel knobs**;
  the selected LED identifies the active CV source.
- This is a performer CV controller, **not** a nested patch-to-plugin exporter.

### Stereo Echo (`StereoEcho`)

[Source/configuration](../plugins/ModularSynth/src/StereoEcho.cpp)

- **Audio:** IN L/IN R and separate L/R mixed wet/dry outputs. With **IN R
  unplugged**, the left input is normalled to the right channel.
- **Controls:** TIME **1…1000 ms** (default 250 ms); FEEDBACK **0…90%**
  (35%); WET **0…100%** (40%); PING-PONG crossfeed **0…100%** (50%).
- **CV:** TIME adds **100 ms per volt** (negative CV shortens time);
  FEEDBACK and MIX add **0.1 normalized units / 10 percentage points
  per volt**. The DSP bounds the effective settings. Up to **16 polyphonic
  lanes**; no external sample file is required.

### Clocked LFO (`ClockedLFO`)

[Source/configuration](../plugins/ModularSynth/src/ClockedLFO.cpp) ·
[Standalone timing and sync tests](../tests/clocked_lfo_dsp_test.cpp)

- **Free mode:** RATE runs from 1/64 to 16 Hz (default 0.5 Hz), plus
  RATE CV at **1 V/oct**. DSP bounds extreme summed frequency to a safe
  **1/256…200 Hz**. All five jacks can carry **16 polyphonic lanes**.
- **External tempo clock:** CLOCK accepts rising triggers at ≥2 V after
  rearming at ≤1 V. After two pulses separated by 20 ms…10 s, the LFO
  derives the incoming period. CLOCK x selects **1/4, 1/2, 1, 2 or 4**
  LFO cycles per pulse interval. RESET hard-aligns phase to zero;
  after missing four expected pulses the LFO resumes its free rate
  while maintaining phase. A green LED indicates acquired clock.
- **Wave outputs:** SIN, TRI, rising RAMP and PULSE are **±5 V**;
  **EOC** supplies a nominal **1 ms, +10 V** end-of-cycle trigger.
  PHASE knob/CV rotates the waveform output without resetting the
  underlying time accumulator. WIDTH knob/CV adjusts PULSE duty
  from 5…95%, and phase/width CV each adds 10% per volt.
- **No direct host tempo coupling:** use an external beat/clock pulse;
  the demo explicitly patches **Cardinal HostTime BEAT → Clocked LFO CLK**.
  Clock acquisition, beat-time drift and audible modulation quality still
  require real-host validation.

## Four suggested wiring recipes (host-unverified)

1. **Keyboard subtractive voice:** `Host MIDI pitch → Morph VCO PITCH`;
   `Morph VCO MORPH → State Filter IN → LP → VCA audio IN → Host Audio L/R`.
   Send `Host MIDI gate → ADSR gate → VCA CV`. Start with low listening
   level and adjust cutoff, morph and pulse width.
2. **Perform with four scenes:** patch Macro8 **OUT 1 → Morph VCO MORPH CV**,
   **OUT 2 → State Filter RES CV**, **OUT 3 → State Filter DRV CV**. Store
   A–D, switch to RECALL and morph while holding a MIDI note. For a signed
   modulation, set an output to **bipolar** and use it on Morph VCO PWM CV.
   A unipolar macro is additive, so the destination knob may need to start
   near zero to leave room for its full CV range.
3. **Stereo echo tail:** feed an audio source (for example State Filter LP)
   to **Stereo Echo IN L**; leave IN R unplugged for a normalled mono feed
   or connect a different source to IN R. Send **Echo OUT L/R → Host Audio
   L/R**. Time, feedback and wet defaults are a reasonable place to start;
   no listening-level or clipping result is implied.
4. **Tempo-aware modulation:** send **HostTime BEAT (output 3) → Clocked LFO
   CLK**, **HostTime RESET (output 1) → Clocked LFO RESET**, then patch
   **LFO SIN → Morph VCO MORPH CV**, **TRI → State Filter FREQ CV** and
   **PULSE → Stereo Echo MIX CV**. EOC can retrigger an ADSR while its
   MIDI gate is held. With transport stopped, free-rate modulation continues.

For an actual prewired version of (1), start with **Morph VCO Performance**.
For scenes, start with **Morphing State Pad**. For the stereo signal path,
open **Stereo Echo Showcase**—that saved patch uses the filter's **LP
and HP** as separate echo left/right inputs. **Echo Motion Performance**
adds saved Macro8 A–D modulation of echo time, feedback, wet mix and
oscillator morph. Those are saved signal/CV routes, not an audio audition.
**Clocked Modulation Studio** adds eight-voice MIDI, source-grounded
HostTime beat/reset routing and Clocked LFO modulation to VCO, filter,
ADSR retrigger and Echo wet mix; it needs host transport for beat lock.

## Eleven factory patches

All eleven links below are actual `.vcv` files under
`patches/examples/`. **Bundled-only** means the patch uses Cardinal's
existing plugin collection and does not require one of these five first-party
modules; **Originals** means it includes at least one `ModularSynth` model.

| Patch | Models | Play/try this |
| --- | --- | --- |
| [Pulse Bass](../patches/examples/MODULAR_-_Pulse_Bass.vcv) | Bundled-only | MIDI bass: Fundamental oscillator → Bogaudio filter → envelope/VCA |
| [Granular Veil](../patches/examples/MODULAR_-_Granular_Veil.vcv) | Bundled-only | Hold MIDI notes; dual oscillators into Clouds texture |
| [Clockwork Pulses](../patches/examples/MODULAR_-_Clockwork_Pulses.vcv) | Bundled-only | Start host transport; sequence → Plaits → Plateau reverb |
| [Morph VCO Performance](../patches/examples/MODULAR_-_Morph_VCO_Performance.vcv) | Originals | Play MIDI notes; move wave morph and pulse width |
| [Morphing State Pad](../patches/examples/MODULAR_-_Morphing_State_Pad.vcv) | Originals | Hold notes; recall Macro8 A/B to modulate oscillator/filter |
| [Cinematic Drift Pad](../patches/examples/MODULAR_-_Cinematic_Drift_Pad.vcv) | Originals | Long ADSR pad; alternate Macro8 A/B with slow transitions |
| [Rhythmic Grit Bass](../patches/examples/MODULAR_-_Rhythmic_Grit_Bass.vcv) | Originals | Short MIDI rhythms; rapid Macro8 scene transitions |
| [Polyphonic Motion Pad](../patches/examples/MODULAR_-_Polyphonic_Motion_Pad.vcv) | Originals | Eight-channel MIDI chord; four Macro8 scenes and filter keytracking |
| [Stereo Echo Showcase](../patches/examples/MODULAR_-_Stereo_Echo_Showcase.vcv) | Originals | MIDI → VCA → filter LP/HP → stereo echo → host L/R |
| [Echo Motion Performance](../patches/examples/MODULAR_-_Echo_Motion_Performance.vcv) | Originals | Play MIDI; recall Macro8 A–D to change echo time/feedback/wet and VCO wave morph |
| [Clocked Modulation Studio](../patches/examples/MODULAR_-_Clocked_Modulation_Studio.vcv) | Originals | Start host transport and play eight-voice MIDI; clocked sine/tri/pulse/EOC modulate VCO, filter, Echo and envelope |

If the examples folder is included in the build, open a patch through
**File → Open demo / example project**; otherwise load its `.vcv` directly.
**Clockwork Pulses** is transport-driven; **Clocked Modulation Studio** uses
host transport beats *and* MIDI notes; the remaining nine accept MIDI notes.
Begin at a conservative
monitor level. [Factory-patch details and structural validation](FACTORY_PATCHES.md)
and [offline patch checks](PATCH_WORKFLOW.md) provide more context.

## What is—and is not—verified

The manifest, module C++ metadata and all eleven saved patch graphs can be
checked offline with:

```sh
python3 -m unittest discover -s tests -p 'test_module_reference.py' -v
python3 tools/patches/factory_patch_coverage.py
python3 tools/ui-check/validate_panels.py
```

**Not verified by this reference:** actual plugin UI appearance, audio
rendering, sonic quality, clipping, MIDI voice-stealing behavior, sample-rate
or CPU performance, DAW save/reopen, or whether every patch's optional
third-party dependencies exist in an installed release. Perform a real
Cardinal/DAW audition before using the patches live.
