# MODULAR-SYNTH Factory Patches — original examples

These original patch arrangements are stored in `patches/examples/` for direct `.vcv` loading and, when packaged, Cardinal's **File → Open demo / example project** submenu. The original three use already bundled modules; newer performance patches demonstrate the fork's registered `MorphVCO`, `StateFilter`, `Macro8` and `StereoEcho` modules. A patch file is not evidence that a particular installed binary can load or sound-test it.

| Patch | Purpose | Interaction |
| --- | --- | --- |
| `MODULAR_-_Pulse_Bass.vcv` | Keyboard-controlled oscillator → resonant filter → envelope/VCA bass voice | Play low notes via host MIDI; adjust VCF cutoff/resonance and ADSR |
| `MODULAR_-_Granular_Veil.vcv` | Detuned dual oscillators → slow envelope → Clouds stereo texture | Hold notes via host MIDI; experiment with Clouds' grain and texture controls |
| `MODULAR_-_Clockwork_Pulses.vcv` | Host-clocked 16-step sequence → Plaits → Plateau reverb, with LFO timbral variation | Start the host/DAW transport; alter sequence steps and Plaits controls |
| `MODULAR_-_Morph_VCO_Performance.vcv` | MIDI-controlled first-party Morph VCO with ADSR/VCA | Play notes; adjust wave morph and pulse width |
| `MODULAR_-_Morphing_State_Pad.vcv` | First-party Morph VCO → StateFilter, with three Macro8 CV routes | Recall A/B macro snapshots while holding a note |
| `MODULAR_-_Cinematic_Drift_Pad.vcv` | Long ADSR performance pad and four macros including bipolar cutoff CV | Alternate 4-second Macro8 A/B transitions |
| `MODULAR_-_Rhythmic_Grit_Bass.vcv` | Tightly gated bass with Macro8 cutoff modulation | Play short external MIDI rhythms; recall 0.20-second transitions |
| `MODULAR_-_Polyphonic_Motion_Pad.vcv` | **Eight-voice MIDI polyphonic** Morph VCO → per-note keytracked StateFilter → ADSR/VCA | Hold chords and recall four 1.8-second Macro8 snapshots; see polyphonic notes below |
| `MODULAR_-_Stereo_Echo_Showcase.vcv` | MIDI-gated Morph VCO and StateFilter LP/HP stereo split into StereoEcho | Play notes to explore saved 360 ms delay and crossfeed; adjust Echo knobs |
| `MODULAR_-_Echo_Motion_Performance.vcv` | Three Macro8 outputs change StereoEcho time, feedback and wet mix; fourth moves oscillator shape | Play MIDI and recall four A/B/C/D scenes with 1.2-second transitions; details below |

## Loading

1. Use a recent MODULAR-SYNTH/Cardinal **main** or **Synth** build with its packaged modules and example patches.
2. If the examples folder is packaged, choose **File → Open demo / example project** and select the `MODULAR_-` patch; otherwise load the `.vcv` directly from `patches/examples/`.
3. Route MIDI notes to every example **except Clockwork Pulses**. Granular Veil is deliberately a primarily monophonic texture because Clouds processes the mixed voice. Polyphonic Motion Pad saves its own eight-channel MIDI allocation.
4. For Clockwork Pulses, start the DAW transport; the patch uses **Host Time** and does not require live MIDI notes.
5. Begin with low speaker or headphone volume. The output gain is intentionally conservative, but patch signal levels are not yet perceptually validated.

## Scope and compatibility

- These are **patch examples**, not new DSP modules or a finished preset management system.
- The first three use bundled Fundamental, Bogaudio, Audible Instruments, JW Modules, Valley and Cardinal models. Newer examples additionally require this fork's registered `ModularSynth` collection (MorphVCO, StateFilter, Macro8 and StereoEcho).
- MIDI/transport mapping and sample-rate behavior are inherited from the built-in modules and host.
- The examples target `Cardinal/HostAudio2`. Some use two saved input routes; others feed a single host input. Polyphonic Motion Pad sends the same summed voice signal to both channels, **not** an independently panned stereo image. They are not standalone VST3 exports.
- They use plain-text VCV Rack 2.x patch JSON for reproducibility.

## Validation performed

The original three patches were initially parsed as JSON and checked for:
- unique module IDs and cable IDs;
- valid cable endpoint references and no duplicate destination jacks;
- finite parameter values and sequential parameter IDs;
- module/model names that occur in bundled repository example patches.

**Current offline checks:** `tools/patches/patch_inspector.py` validates structural graph integrity and source-backed original-module ports; `tools/patches/factory_patch_coverage.py` confirms every original `ModularSynth` model is represented and each original preset's advertised routes/settings exist. This is saved-source evidence only.

**Not yet verified:** loading the patches in a compiled MODULAR-SYNTH binary, rendering audio, listening for expected sonic results, clipping/CPU profiling, and loading/saving from real DAWs. Those are explicit acceptance checks before these patches are described as production-validated.

## Manual acceptance test

- Launch a newly built plugin and load each patch; no missing-module warning should appear.
- Pulse Bass: MIDI note-on produces audio and note-off releases smoothly; stereo channels are audible.
- Granular Veil: sustained MIDI notes produce a textured stereo signal and stop after release and grain tails.
- Clockwork Pulses: host play/stop behavior follows the DAW transport; its sequence sounds through both outputs.
- Morph VCO Performance: keyboard pitch and note gate control the single Morph VCO through ADSR/VCA.
- Morphing State Pad: macro Shape/Resonance/Drive controls and A/B snapshots affect timbre without unexpected gain jumps.
- Cinematic Drift Pad and Rhythmic Grit Bass: confirm bipolar cutoff CV, four macro routes and documented 4.0/0.20-second snapshot morph settings.
- Polyphonic Motion Pad: hold 2, 4 and 8 simultaneous MIDI notes; check each pitch follows its own channel, releases independently and filter cutoff keytracks each note. Check four Macro8 A-D recalls, output gain, and audible clipping.
- Stereo Echo Showcase: play MIDI; compare saved low-pass versus high-pass echo inputs and listen for left/right delay and note-off tails.
- Echo Motion Performance: recall all four Macro8 A/B/C/D scenes while playing MIDI; check Echo time, feedback and wet changes, wave timbre, stereo channels and release tails. Do not assume transitions are click-free until heard.
- For each patch: save under a new filename, reload, and compare module/cable counts and playback.
- Test at 44.1/48/96 kHz and block sizes 64/128/256 when practical. Verify silence on stop and no plugin crash.

## Polyphonic Motion Pad — source-grounded signal flow

[Open the saved patch](../patches/examples/MODULAR_-_Polyphonic_Motion_Pad.vcv) in a fork build with all three original `ModularSynth` modules. It contains **8 modules and 13 saved cables**, using only the bundled Cardinal Host MIDI/Audio, Fundamental ADSR/VCA-1 and original MorphVCO, StateFilter and Macro8. No third-party library download or external sample file is specified.

- `Cardinal/HostMIDI` saves **`channels=8`** and **`polyMode=1` (Reuse)**. In the checked-in HostMIDI implementation, pitch (output 0), gate (1) and retrigger (6) produce up to 8 separate voice lanes in this mode. The patch routes pitch both to `MorphVCO` pitch input 0 and `StateFilter` cutoff CV input 1 (1 V/oct note-by-note filter keytracking).
- Gate and retrigger separately feed the pinned Fundamental `ADSR` inputs 4 and 5. Its per-channel envelope output feeds the pinned Fundamental `VCA-1` CV input 0. Oscillator output 0 → StateFilter audio input 0 → filter low-pass output 0 → VCA audio input 1 forms the per-voice audio path.
- Both first-party modules set output channels from their polyphonic input counts (up to 16 lanes). The pinned Fundamental ADSR/VCA-1 sources process poly gates/audio/CV. `Cardinal/HostAudio2` calls `getVoltageSum()` on each connected input, summing voices rather than discarding channels above 0; VCA output 0 fans to its left/right inputs 0 and 1.
- Mono Macro8 outputs are broadcast across voice lanes by Rack's `getPolyVoltage()` convention. This is **global timbre motion shared by all voices**, while note pitch, gate and envelope/filter keytracking remain per-voice. It is not eight individually randomized or panned voices.

| Macro output | Saved name | Connection | Output range |
| --- | --- | --- | --- |
| 0 | Color | MorphVCO wave-morph CV input 2 | 0–10 V |
| 1 | Resonance | StateFilter resonance CV input 2 | 0–10 V |
| 2 | Warmth | StateFilter drive CV input 3 | 0–10 V |
| 3 | Width | MorphVCO PWM CV input 3 | **−5 to +5 V** (saved Macro8 range switch 4 on) |

Macro8 has **four populated A/B/C/D snapshots** (subtle/bright/pulse/soft variants) and a **1.8-second 99.9%-settling transition**. Recall one while holding an eight-note chord; use **LIVE** to return to the knobs. There is **no clocked or autonomous LFO** in this patch—motion is initiated by performer snapshot selection. The saved VCA gain is 0.22 and HostAudio2 level 0.15, intentionally modest but **not an established clipping guarantee**.

Source-only reproduction:

```sh
python3 tools/patches/patch_inspector.py validate patches/examples/MODULAR_-_Polyphonic_Motion_Pad.vcv
python3 tools/patches/factory_patch_coverage.py
python3 -m unittest discover -s tests -p 'test_factory_patch_coverage.py' -v
```

These checks inspect saved MIDI channel/mode values, every advertised cable, first-party port bounds, four versioned Macro8 snapshots and bipolar Width mode. **They do not execute MIDI voice allocation, DSP, DAW transport, patch reopen, eight-voice audio levels or sample-rate changes.** Before calling this preset production-tested, audition 1/2/4/8 simultaneous note-on/off events in a real fork-built host at 44.1, 48 and 96 kHz; verify voice stealing under a ninth note, retriggering, CPU load and monitoring level.

## Echo Motion Performance — manual A/B/C/D delay moves

[Open Echo Motion Performance](../patches/examples/MODULAR_-_Echo_Motion_Performance.vcv) in a fork build with all four registered original modules. The saved **9-module, 13-cable** source graph uses Cardinal HostMIDI/HostAudio2, Fundamental ADSR/VCA-1 and first-party MorphVCO, StateFilter, StereoEcho and Macro8 (plus an explanatory TextEditor). No external samples or BPM/tempo synchronization are configured.

MIDI pitch reaches `MorphVCO` input 0; gate reaches ADSR input 4. Oscillator output → gated VCA → StateFilter audio input 0, then low-pass output 0 → StereoEcho left input 0 and high-pass output 2 → Echo right input 1. The echo's output 0 and 1 connect separately to host audio jacks 0 and 1. This is **two different saved audio paths**, not evidence of audible width or a completed stereo audition.

| Macro8 output | Saved label | Routed first-party CV destination | Source-defined output/effect |
| --- | --- | --- | --- |
| 0 | Time | StereoEcho time input **2** | Unipolar 0–10 V; adds **100 ms/V** to the 120 ms base knob |
| 1 | Feedback | StereoEcho feedback input **3** | Unipolar 0–10 V; adds **10 percentage points/V** to the 10% base |
| 2 | Wet | StereoEcho mix input **4** | Unipolar 0–10 V; adds **10 percentage points/V** to the 12% base |
| 3 | Wave | MorphVCO wave morph input **2** | Unipolar 0–10 V; adds the normalized 0–1 morph span to its 0.05 base |

All four Macro8 range switches (saved params 15–18) select **unipolar** operation. With the four stored scenes, the additive CV formulas in `StereoEcho.cpp` imply these *nominal static settings*:

| Recall | Echo time | Feedback | Wet mix | Oscillator morph |
| --- | ---: | ---: | ---: | ---: |
| A — Slap | 190 ms | 18% | 28% | 0.17 |
| B — Chamber | 340 ms | 28% | 40% | 0.35 |
| C — Cascade | 550 ms | 41% | 48% | 0.53 |
| D — Ripples | 800 ms | 54% | 57% | 0.67 |

Macro8 saves four complete version-1, eight-value snapshots and a **1.2-second 99.9%-settling transition**. It opens in **LIVE** mode (`selectedSlot=-1`) with independently saved knob positions; press A/B/C/D to recall the stored values, or LIVE to use the knobs again. This is performer-initiated snapshot motion, **not** an autonomous LFO, MIDI automation or host-tempo delay. Changing delay time may affect playback pitch/timing; it has not been listened to or characterized in a host.

The VCA level knob is saved at **0.24** and HostAudio2 output level **0.14**, with StateFilter drive **0.035**, Echo ping-pong crossfeed **68%** and scene feedback never above **54%** based on saved normalized values. These are conservative intended settings, **not** a measured clipping, tail-length, CPU, memory or mix-safety guarantee. Start monitoring quietly.

To reproduce saved-source checks:

```sh
python3 tools/patches/patch_inspector.py validate patches/examples/MODULAR_-_Echo_Motion_Performance.vcv
python3 tools/patches/factory_patch_coverage.py
python3 tools/patches/patch_catalog.py --format markdown
python3 -m unittest discover -s tests -p 'test_echo_motion_patch.py' -v
```

Before advertising this preset as performance-tested, load it in a fork-built host, audition MIDI note-on/off and A–D/LIVE transitions, test both audio channels and gain, and save/reopen the patch. Do not infer audio results or 44.1/48/96 kHz runtime behavior from JSON alone.

## Future work

Add audio-rendered regression fixtures, MPE/aftertouch expressive performance patches, improved patch-browser tagging, and audio previews after real host audition and a testable plugin build.
