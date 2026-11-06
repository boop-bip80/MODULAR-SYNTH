# MODULAR-SYNTH Factory Patches — original examples

These original patch arrangements are stored in `patches/examples/` for direct `.vcv` loading and, when packaged, Cardinal's **File → Open demo / example project** submenu. The original three use already bundled modules; newer performance patches demonstrate the fork's registered `MorphVCO`, `StateFilter`, `FoldDrive`, `DualVCA`, `Macro8`, `StereoEcho`, `ClockedLFO`, `FMVoice`, `ChanceHold`, `SlewGlide` and `ScaleQuantizer` modules. A patch file is not evidence that a particular installed binary can load or sound-test it.

| Patch | Purpose | Interaction |
| --- | --- | --- |
| `MODULAR_-_Pulse_Bass.vcv` | Keyboard-controlled oscillator → resonant filter → envelope/VCA bass voice | Play low notes via host MIDI; adjust VCF cutoff/resonance and ADSR |
| `MODULAR_-_Granular_Veil.vcv` | Detuned dual oscillators → slow envelope → Clouds stereo texture | Hold notes via host MIDI; experiment with Clouds' grain and texture controls |
| `MODULAR_-_Clockwork_Pulses.vcv` | Host-clocked 16-step sequence → Plaits → Plateau reverb, with LFO timbral variation | Start the host/DAW transport; alter sequence steps and Plaits controls |
| `MODULAR_-_Morph_VCO_Performance.vcv` | MIDI-controlled first-party Morph VCO with Fundamental ADSR and original Dual VCA stereo outputs | Play notes; adjust wave morph and Dual VCA curve |
| `MODULAR_-_FM_Voice_Performance.vcv` | MIDI-controlled two-operator FM Voice with ADSR/VCA | Play notes; move ratio, index and feedback; avoid extreme high-frequency aliasing |
| `MODULAR_-_Chance_Hold_FM_Drift.vcv` | Seeded probabilistic random CV glides the FM Voice modulation index during MIDI performance | Play MIDI with the 1 Hz, 75% Chance Hold source; adjust chance, glide and quantize to vary timbre |
| `MODULAR_-_Aurora_Glass_Bells.vcv` | Eight-voice FM bell patch with envelope-gated notes, attenuated random filter drift, LP/BP spectral stereo split and five Macro8 scene controls | Hold MIDI chords; recall Dawn/Prism/Halo/Dusk A–D scenes; Chance Hold wanders freely without DAW transport |
| `MODULAR_-_Night_Lanterns_Dual_Timbre.vcv` | Eight-voice dark MorphVCO/FoldDrive/StateFilter left layer opposite a near-harmonic FMVoice right layer, independently envelope-gated by DualVCA, through crossfeeding StereoEcho | Play MIDI chords; start the host transport for four-beat LFO pulse-width/fold-bias motion; recall Ember/Lantern/Flare/Dusk Macro8 A–D scenes |
| `MODULAR_-_Reed_Chamber_Organ.vcv` | Original eight-voice two-manual combo-organ *sketch*: detuned 8-foot and octave-up 4-foot MorphVCO voices, per-note ADSR/DualVCA, gentle low-pass tone shaping, 3 Hz free-running vibrato and two source-verified stereo echo paths | Play held MIDI chords or detached organ stabs; recall Chapel/Reed/Swirl/Shimmer A–D tone-color scenes; no transport necessary, and this is **not** a tonewheel or rotary-speaker physical model |
| `MODULAR_-_Luminous_Portamento_Duets.vcv` | Original eight-voice, two-manual octave texture using simultaneous linear/exponential SlewGlide pitch, separate LP/BP filtered voices and two source-verified stereo host paths | Play legato MIDI lines or sustained chords; recall Spark/Velvet/Comet/Orbit Macro8 scenes to morph glide times, color, resonance and echoes |
| `MODULAR_-_Morphing_State_Pad.vcv` | First-party Morph VCO → StateFilter, with three Macro8 CV routes | Recall A/B macro snapshots while holding a note |
| `MODULAR_-_Cinematic_Drift_Pad.vcv` | Long ADSR performance pad and four macros including bipolar cutoff CV | Alternate 4-second Macro8 A/B transitions |
| `MODULAR_-_Rhythmic_Grit_Bass.vcv` | Tightly gated bass with Macro8 cutoff modulation | Play short external MIDI rhythms; recall 0.20-second transitions |
| `MODULAR_-_Polyphonic_Motion_Pad.vcv` | **Eight-voice MIDI polyphonic** Morph VCO → per-note keytracked StateFilter → ADSR/VCA | Hold chords and recall four 1.8-second Macro8 snapshots; see polyphonic notes below |
| `MODULAR_-_Stereo_Echo_Showcase.vcv` | MIDI-gated Morph VCO and StateFilter LP/HP stereo split into StereoEcho | Play notes to explore saved 360 ms delay and crossfeed; adjust Echo knobs |
| `MODULAR_-_Echo_Motion_Performance.vcv` | Three Macro8 outputs change StereoEcho time, feedback and wet mix; fourth moves oscillator shape | Play MIDI and recall four A/B/C/D scenes with 1.2-second transitions; details below |
| `MODULAR_-_Clocked_Modulation_Studio.vcv` | Eight-channel MIDI with HostTime BEAT/RESET-fed ClockedLFO and animated filter/echo modulation | Start host transport for external beat lock; play MIDI notes; inspect LFO SIN/TRI/PULSE/EOC routes |
| `MODULAR_-_Cinematic_Pulse_Score.vcv` | Free-running LFO pulse gates a **second** ADSR/VCA on filter LP only; HP remains separate into stereo Echo, with four Macro8 scenes | Play MIDI and recall Hush/Motion/Surge/Return scenes; no host transport or BPM synchronization required |
| `MODULAR_-_Noir_Expressive_Lead.vcv` | Monophonic dark lead using MIDI channel aftertouch for oscillator timbre, mod wheel for Echo wet, and five Macro8 scene controls | Play single-note phrases, move aftertouch/mod wheel, then recall four Noir/Tension scenes; no host BPM sync |
| `MODULAR_-_Fold_Drive_Cinematic_Motion.vcv` | Eight MIDI voices through MorphVCO → FoldDrive → StateFilter → ADSR/VCA, with slow sine/triangle LFO fold modulation and mod-wheel wet control | Hold chords, move CC1 and channel pressure; LFO is intentionally free-running at 0.25 Hz, not beat-locked |
| `MODULAR_-_Major_Glow_Quantized_Performance.vcv` | MIDI pitch quantized to C major, note-change trigger retriggering a gated ADSR, DualVCA → StateFilter LP/HP stereo Echo, and four Macro8 delay/timbre scenes | Play a line that includes non-C-major notes, try SCALE/ROOT/HYST, and recall four echo scenes; requires MIDI, not transport |

## Loading

1. Use a recent MODULAR-SYNTH/Cardinal **main** or **Synth** build with its packaged modules and example patches.
2. If the examples folder is packaged, choose **File → Open demo / example project** and select the `MODULAR_-` patch; otherwise load the `.vcv` directly from `patches/examples/`.
3. Route MIDI notes to every example **except Clockwork Pulses**. Granular Veil is deliberately a primarily monophonic texture because Clouds processes the mixed voice. Polyphonic Motion Pad, Clocked Modulation Studio, Fold Drive Cinematic Motion, Aurora Glass Bells, Night Lanterns, Reed Chamber Organ and Luminous Portamento Duets save eight MIDI channels.
4. For Clockwork Pulses, start the DAW transport; it uses **Host Time** without live MIDI notes. For Clocked Modulation Studio and Night Lanterns, use transport **and MIDI** if testing external beat lock (their LFOs free-run without transport). Cinematic Pulse Score needs **MIDI only**: its LFO CLOCK/RESET jacks are unplugged and it does not follow BPM. Noir Expressive Lead also needs MIDI notes; MIDI channel pressure and CC1 mod wheel are optional expressive controls, subject to the keyboard/DAW's MIDI routing.
5. Begin with low speaker or headphone volume. The output gain is intentionally conservative, but patch signal levels are not yet perceptually validated.

## Scope and compatibility

- These are **patch examples**, not new DSP modules or a finished preset management system.
- The first three use bundled Fundamental, Bogaudio, Audible Instruments, JW Modules, Valley and Cardinal models. Newer examples additionally require this fork's registered `ModularSynth` collection (MorphVCO, StateFilter, FoldDrive, DualVCA, Macro8, StereoEcho, ClockedLFO, FMVoice, ChanceHold, SlewGlide and ScaleQuantizer).
- MIDI/transport mapping and sample-rate behavior are inherited from the built-in modules and host.
- The examples target `Cardinal/HostAudio2`. Some use two saved input routes; others feed a single host input. Polyphonic Motion Pad sends the same summed voice signal to both channels, **not** an independently panned stereo image. They are not standalone VST3 exports.
- They use plain-text VCV Rack 2.x patch JSON for reproducibility.

## Validation performed

The original three patches were initially parsed as JSON and checked for:
- unique module IDs and cable IDs;
- valid cable endpoint references and no duplicate destination jacks;
- finite parameter values and sequential parameter IDs;
- module/model names that occur in bundled repository example patches.

**Current offline checks:** `tools/patches/patch_inspector.py` validates structural graph integrity, source-backed original-module ports and checked-in Cardinal HostMIDI/HostTime/HostAudio2 port contracts; `tools/patches/factory_patch_coverage.py` confirms every original `ModularSynth` model is represented and each original preset's advertised routes/settings exist. Other bundled modules' ports remain unverified. This is saved-source evidence only.

**Per-host-channel routing scrutiny:** `tools/patches/patch_audio_routes.py` now reports `source_verified_host_inputs` and `unverified_wired_host_inputs` separately for every connected HostAudio2 jack. This closes an evidence gap: a known MorphVCO signal path into **Left** must not be counted as evidence for a different **Right** cable carrying control CV or going through an opaque third-party processor. The existing `--require-source-verified-signal-route` checks whether each known first-party generator reaches *some* HostAudio2 input; it does not require source-level proof for all host jacks. The new independent **opt-in** `--require-source-verified-host-inputs` returns 1 when no HostAudio2 input is wired or when any wired host jack lacks a complete source-verified first-party signal-port chain (invalid saved patches still return 2).

```sh
python3 tools/patches/patch_audio_routes.py patches/examples/MODULAR_-_Morph_VCO_Performance.vcv --require-source-verified-host-inputs
python3 tools/patches/patch_audio_routes.py patches/examples/MODULAR_-_Aurora_Glass_Bells.vcv --json
```

In the checked-in source, Morph VCO Performance has **2/2 wired host inputs** supported by a typed MorphVCO → DualVCA → HostAudio2 chain. Major Glow Quantized Performance also has **2/2** typed paths through DualVCA, StateFilter and StereoEcho to the independent host L/R jacks. Aurora Glass Bells has **0/2** under this deliberately narrow first-party gate because the audio passes through bundled **Fundamental/VCA-1**, whose internal audio-port transfer is not covered by the verified first-party contracts. Its two saved host cables and patch structure are valid; **0/2 is not evidence of silence or a malfunction**. Nor does 2/2 prove an audible signal, independent stereo content, gain safety, or DAW compatibility. Do not apply this strict gate as a blanket rejection of factory patches using legitimate but opaque bundled modules.

**Not yet verified:** loading the patches in a compiled MODULAR-SYNTH binary, rendering audio, listening for expected sonic results, clipping/CPU profiling, and loading/saving from real DAWs. Those are explicit acceptance checks before these patches are described as production-validated.

## Manual acceptance test

- Launch a newly built plugin and load each patch; no missing-module warning should appear.
- Pulse Bass: MIDI note-on produces audio and note-off releases smoothly; stereo channels are audible.
- Granular Veil: sustained MIDI notes produce a textured stereo signal and stop after release and grain tails.
- Clockwork Pulses: host play/stop behavior follows the DAW transport; its sequence sounds through both outputs.
- Morph VCO Performance: keyboard pitch and note gate control the Morph VCO through Fundamental ADSR and original Dual VCA A/B envelope channels, with separate saved stereo host cables.
- FM Voice Performance: MIDI pitch drives the two-operator FMVoice while a bundled ADSR/VCA handles note-on/off amplitude. Check 1/8/16 voices, ratio/index/feedback changes, high-register aliasing and low-level output before signing off; **host listening is not yet done**.
- Aurora Glass Bells: hold 1/2/4/8 notes and check individual ADSR gate/retrigger/release, the DualVCA A attenuator scaling of Chance Hold's free-running filter-cutoff drift, LP-versus-BP stereo output, four A–D scenes (Dawn, Prism, Halo, Dusk), and note-off echo tails. Ensure an empty DAW transport does **not** stop random cutoff motion; audition gain and eight simultaneous echo lanes before any performance claim.
- Morphing State Pad: macro Shape/Resonance/Drive controls and A/B snapshots affect timbre without unexpected gain jumps.
- Cinematic Drift Pad and Rhythmic Grit Bass: confirm bipolar cutoff CV, four macro routes and documented 4.0/0.20-second snapshot morph settings.
- Polyphonic Motion Pad: hold 2, 4 and 8 simultaneous MIDI notes; check each pitch follows its own channel, releases independently and filter cutoff keytracks each note. Check four Macro8 A-D recalls, output gain, and audible clipping.
- Stereo Echo Showcase: play MIDI; compare saved low-pass versus high-pass echo inputs and listen for left/right delay and note-off tails.
- Echo Motion Performance: recall all four Macro8 A/B/C/D scenes while playing MIDI; check Echo time, feedback and wet changes, wave timbre, stereo channels and release tails. Do not assume transitions are click-free until heard.
- Clocked Modulation Studio: start/stop host transport with 8-channel MIDI; verify ClockedLFO beat lock versus free run and inspect left/right audio at low levels.
- Cinematic Pulse Score: hold mono MIDI notes; check free-run rhythmic LP gating only on the left, independent continuous HP on right, LFO sine waveform change, A–D scenes and LIVE. Verify no host sync is advertised or expected.
- Noir Expressive Lead: play single-note MIDI phrases, test **channel pressure** on MorphVCO wave morph and **CC1 mod wheel** on Echo wet CV; recall Macro8 A–D and LIVE while varying the five documented macro routes. Verify note-off closes VCA, stereo echo tails remain finite and both channels reach the host. Do not assume your controller or DAW sends channel aftertouch without explicitly checking.
- Fold Drive Cinematic Motion: hold 2/4/8 simultaneous MIDI notes and test the **FoldDrive IN → OUT** audio segment between MorphVCO and StateFilter; inspect ClockedLFO TRI → DRIVE CV and SIN → BIAS CV, then move MIDI CC1 → MIX CV and channel pressure → oscillator MORPH CV. Its LFO must free-run at 0.25 Hz without host beat cables. Check quiet output, per-voice release, clipping and high-register alias audibly; no such listening test has been performed yet.
- Major Glow Quantized Performance: play ascending C-major and chromatic phrases; confirm non-scale notes land on the nearest C-major pitch, and the quantizer's CHANGE output retriggers ADSR only when the selected note changes. Try changing ROOT/SCALE/TRANS and 12-cent hysteresis; verify MIDI GATE still opens/closes the envelope. Recall Macro8 A–D, check LP/HP paths through Echo to both host jacks, release tails, gain and clipping at safe monitor volume. Its four scene morphs are manual, not host-tempo-synced.
- For each patch: save under a new filename, reload, and compare module/cable counts and playback.
- Test at 44.1/48/96 kHz and block sizes 64/128/256 when practical. Verify silence on stop and no plugin crash.

## Polyphonic Motion Pad — source-grounded signal flow

[Open the saved patch](../patches/examples/MODULAR_-_Polyphonic_Motion_Pad.vcv) in a fork build containing the **three original `ModularSynth` models used by this patch**: MorphVCO, StateFilter and Macro8. It contains **8 modules and 13 saved cables**, using only the bundled Cardinal Host MIDI/Audio, Fundamental ADSR/VCA-1 and those first-party models. No third-party library download or external sample file is specified.

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

[Open Echo Motion Performance](../patches/examples/MODULAR_-_Echo_Motion_Performance.vcv) in a fork build containing the **four original models required by this particular patch**: MorphVCO, StateFilter, StereoEcho and Macro8. The saved **9-module, 13-cable** source graph uses Cardinal HostMIDI/HostAudio2, Fundamental ADSR/VCA-1 and those four first-party models (plus an explanatory TextEditor). ClockedLFO is the collection's fifth model but is not used here. No external samples or BPM/tempo synchronization are configured.

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

## Cinematic Pulse Score — free-running rhythmic score study

[Open the source patch](../patches/examples/MODULAR_-_Cinematic_Pulse_Score.vcv) in a fork build with **all five original modules** and bundled Fundamental ADSR/VCA-1. This 12-module, 17-cable example is deliberately different from the **host-clocked eight-voice** Clocked Modulation Studio: it uses **one saved HostMIDI channel** and **no HostTime module or cable to ClockedLFO CLOCK/RESET**. Its free-running rate is approximately **0.8 Hz**, with a saved 28% pulse duty; this is **not tempo/BPM synchronization**.

The two envelopes and VCAs have independent source-backed roles:

1. **MIDI voice:** HostMIDI pitch output 0 → MorphVCO input 0; MIDI gate output 1 → Fundamental ADSR #1 gate input 4. MorphVCO audio output 0 → VCA #1 audio input 1, ADSR #1 output 0 → VCA #1 CV input 0; VCA #1 output 0 → StateFilter audio input 0.
2. **Rhythmic left:** ClockedLFO **PULSE output 3** (nominal ±5 V) → ADSR #2 gate input 4; that envelope output 0 → VCA #2 CV input 0. StateFilter **LP output 0** → VCA #2 audio input 1 → StereoEcho **left input 0**. In checked-in Fundamental source, ADSR gate detects ≥1 V, so the positive LFO pulse phase is treated as an envelope gate; VCA CV is bounded to 0–10 V in its gain calculation.
3. **Independent right / timbre:** StateFilter **HP output 2** goes directly to StereoEcho **right input 1**, bypassing the rhythmic second VCA. Echo L/R outputs 0/1 go separately to HostAudio2 inputs 0/1. ClockedLFO **SIN output 0** → MorphVCO wave-morph input 2 (±5 V moves its saved 0.5 knob across the full nominal 0–1 span).

| Macro8 output / name | Saved source cable | Normalized scene voltage mode |
| --- | --- | --- |
| 0 — Tension | StateFilter resonance CV input **2** | 0…+10 V unipolar |
| 1 — Warmth | StateFilter drive CV input **3** | 0…+10 V unipolar |
| 2 — Repeats | StereoEcho feedback CV input **3** | 0…+10 V unipolar |
| 3 — Space | StereoEcho wet-mix CV input **4** | 0…+10 V unipolar |

Each destination adds **0.1 normalized units per CV volt**, so a 0–1 saved macro snapshot adds that normalized value. These are the *static nominal* totals calculated from saved source parameters (not measured sound):

| Snapshot | Filter resonance | Filter drive | Echo feedback | Echo wet |
| --- | ---: | ---: | ---: | ---: |
| A — Hush | 8% | 2% | 16% | 20% |
| B — Motion | 12% | 5% | 24% | 28% |
| C — Surge | 20% | 9% | 35% | 40% |
| D — Return | 11% | 4% | 25% | 30% |

Macro8 saves **four complete version-1 A–D scenes**, range switches 0–3 unipolar, a **2.6-second 99.9%-settling** scene transition and `selectedSlot=-1` (starts LIVE; press a scene to recall). StereoEcho time is a fixed **460 ms knob** with no time-CV cable; LFO pulse repetition is nominally **1.25 seconds** independent of the echo time. The first VCA gain is saved at **0.30**, rhythmic VCA gain at **0.48**, HostAudio2 level at **0.14**, and Echo crossfeed at **0.68**. They aim for moderate starting levels, **not** a measured clipping, mix-balance or sound-quality guarantee.

Reproduce offline evidence:

```sh
python3 tools/patches/patch_inspector.py validate patches/examples/MODULAR_-_Cinematic_Pulse_Score.vcv
python3 tools/patches/factory_patch_coverage.py
python3 tools/patches/patch_catalog.py --format markdown
python3 -m unittest discover -s tests -p 'test_cinematic_pulse_score.py' -v
```

Before using it live, audition one-note MIDI gate/release, LFO pulse-gated left versus unpulsed right, A–D/LIVE transitions and level/headroom, plus patch save/reopen in a real compiled fork. No actual host audio, sample-rate, CPU or tempo-sync tests were performed by this source-only validation.

## Noir Expressive Lead — cinematic keyboard expression

[Open the source patch](../patches/examples/MODULAR_-_Noir_Expressive_Lead.vcv). This **9-module, 15-cable**, **single-channel MIDI** voice uses MorphVCO → StateFilter low-pass → Fundamental ADSR-controlled VCA → StereoEcho → the two HostAudio2 input jacks. Echo Right input is deliberately unplugged, so StereoEcho uses its code-defined Left-to-Right normalization; two output cables do **not** by themselves establish audible stereo width.

The expressive controls use actual `Cardinal/HostMIDI` source output IDs: **Pitch 0** drives MorphVCO input 0, **Gate 1** drives ADSR input 4, **Aftertouch 3** drives MorphVCO wave-morph CV input 2 (0–10 V maps to one normalized morph span), and **Mod Wheel 5** drives StereoEcho wet CV input 4 (0–10 V adds 0–100 percentage points to the 5% wet base). Not all keyboards send channel aftertouch; no minimum external controller capabilities or actual MIDI messages have been tested.

| Macro8 output | Saved name | Destination | Nominal source scaling |
| --- | --- | --- | --- |
| 0 | Delay Time | StereoEcho TIME CV input **2** | 100 ms/V added to a 180 ms base |
| 1 | Echo FB | StereoEcho feedback CV input **3** | 10 percentage points/V added to a 12% base |
| 2 | Resonance | StateFilter resonance CV input **2** | 0–10 V adds normalized 0–1 to the 8% base |
| 3 | Drive | StateFilter drive CV input **3** | 0–10 V adds normalized 0–1 to the 4% base |
| 4 | Pulse Width | MorphVCO PWM CV input **3** | 0–10 V adds normalized 0–1 to its 42% base |

All five range switches are saved **unipolar**. The four named A–D Macro8 snapshot rows take **0.65 seconds to approximately 99.9% settle**. Nominal Echo time changes from **260 ms** (A) to **600 ms** (D), with nominal feedback from **20%** to **44%**; the mod wheel independently controls wetness. The source graph saves a moderate VCA gain **0.32**, HostAudio2 level **0.22**, and low 5% default wet signal. These are *source settings*, **not** measured headroom or a completed playable-host audition. The preset is free-running/manual, not tempo-synced.

For source-only QA:

```sh
python3 tools/patches/patch_inspector.py validate patches/examples/MODULAR_-_Noir_Expressive_Lead.vcv
python3 tools/patches/factory_patch_coverage.py
python3 -m unittest discover -s tests -p 'test_noir_expressive_lead.py' -v
```

For real acceptance, use a fork-built plugin with a controller that sends channel aftertouch and mod wheel; confirm note/release, responsive wave CV and echo wetness, both host channels, sensible levels, A–D/LIVE recall and DAW reopen at several sample rates. Source checks do not assert any of those outcomes.

## Aurora Glass Bells — polyphonic FM and bounded generative drift

[Open the source preset](../patches/examples/MODULAR_-_Aurora_Glass_Bells.vcv). This **11-module, 17-cable** arrangement uses six original `ModularSynth` models: FMVoice, ChanceHold, DualVCA, Macro8, StateFilter and StereoEcho; plus bundled HostMIDI/HostAudio2, Fundamental ADSR/VCA-1 and an explanatory text module. It needs no external sample or DAW transport. The checked-in graph has eight HostMIDI Reuse lanes (channel count 8, polyMode 1), and saves discrete MIDI pitch, gate and retrigger cables to FMVoice and ADSR.

The intended musical arc is a chord-friendly, slowly evolving glass-bell spectrum:

1. Per-note `FMVoice` carrier output 0 → `Fundamental/VCA-1` audio input 1, with MIDI-gated `ADSR` output 0 → VCA CV input 0. A 0.22 saved VCA level limits the starting amplitude before `StateFilter` audio input 0.
2. `ChanceHold` free-runs at **0.25 Hz** with **65% probability** of sampling on a clock and **1.4-second glide**, with its external CLOCK and RESET disconnected. Its smooth ±5 V output goes to `DualVCA` A input 0. The A CV input is deliberately unplugged (source-normalled unity) with A gain **0.24**, so the static CV gain stage limits nominal filter-cutoff modulation to ±1.2 V, or ±1.2 octaves at `StateFilter` cutoff input 1. The DualVCA B section is unused.
3. `StateFilter` low-pass output 0 and band-pass output 1 independently feed `StereoEcho` left and right inputs. Echo L/R outputs connect to the two distinct `HostAudio2` input jacks. This is an *intentional saved spectral stereo split*; actual host width and summing have not been measured.

Macro8 has **five unipolar CV routes** and complete version-1 A–D snapshots with 1.6-second settling. Its source-bound CV scales imply the following *nominal static* scene targets (before random filter drift):

| Scene | FM index | Resonance | Echo wet | Echo time | Echo feedback |
| --- | ---: | ---: | ---: | ---: | ---: |
| A — Dawn | 1.39 rad | 16% | 23% | 290 ms | 24% |
| B — Prism | 1.95 rad | 19% | 29% | 420 ms | 29% |
| C — Halo | 2.51 rad | 24% | 37% | 580 ms | 36% |
| D — Dusk | 1.71 rad | 27% | 30% | 350 ms | 26% |

Those values follow Macro8 output 0 → FM index CV 2 (0.8 rad/V), output 1 → filter resonance CV 2 (0.1 normalized/V), outputs 2/3/4 → Echo wet/time/feedback CV 4/2/3 (0.1 normalized/V, 100 ms/V, 0.1 normalized/V). The base Echo time is 210 ms, base feedback 20%, base wet 18%, and crossfeed 70%. The final HostAudio2 level is saved at **0.16**. These source values are not headroom measurements.

Reproduce source-only tests:

```sh
python3 tools/patches/patch_inspector.py validate patches/examples/MODULAR_-_Aurora_Glass_Bells.vcv
python3 tools/patches/patch_audio_routes.py patches/examples/MODULAR_-_Aurora_Glass_Bells.vcv --require-host-input --require-generator-route
python3 tools/patches/factory_patch_coverage.py
python3 -m unittest discover -s tests -p 'test_aurora_glass_bells.py' -v
```

No one has yet verified this patch's MIDI voice allocation, perceived musicality, 1/2/4/8-voice CPU/memory load, audio headroom, echo tails, host plugin loading or DAW save/reopen. Audition at low volume in a fork-built host before calling it performance-ready, including aftertouch/pedal transitions where supported and sample rates 44.1/48/96 kHz.

## Night Lanterns — dual-timbre polyphony with four-beat movement

[Open the source preset](../patches/examples/MODULAR_-_Night_Lanterns_Dual_Timbre.vcv). This original **13-module, 26-cable** graph needs no samples. The eight saved HostMIDI channels feed two independent 1 V/oct voices: a MorphVCO tuned an octave lower for a darker register and a near-2:1 FMVoice for a more bell-like overtone layer. Fundamental ADSR receives distinct MIDI gate and retrigger events and feeds both `DualVCA` envelope jacks. The MorphVCO passes through FoldDrive and StateFilter low-pass before DualVCA A, while FMVoice feeds DualVCA B directly. A and B reach separate StereoEcho inputs, with Echo L/R connected to separate HostAudio2 jacks. These are **two different source-verified signal chains**, not a measured stereo image.

The transport's `HostTime` BEAT output 3 and RESET output 1 connect to ClockedLFO inputs 1/2. Its saved ratio 0 selects **one cycle per four incoming beat pulses**; sine modulates oscillator pulse width and triangle modulates FoldDrive bias. When no transport pulses arrive, the saved free rate −2 gives a nominal 0.25 Hz fallback. This patch intentionally combines slow periodic motion with performer-initiated Macro8 scene transitions instead of generating random notes or misrepresenting direct DAW BPM access inside the LFO.

All eight named Macro8 CV channels use unipolar 0–10 V, one per target: MorphVCO morph (0→input 2), FM index (1→input 2), filter resonance (2→input 2), FoldDrive drive (3→input 1), Echo wet (4→input 4), Echo time (5→input 2), Echo feedback (6→input 3), and FoldDrive wet (7→input 3). Its four saved snapshots settle nominally within **2 seconds** under the source one-pole smoother:

| Scene | Morph position | FM index | Fold drive | Echo wet | Echo time | Echo feedback |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A — Ember | 0.34 | 0.80 rad | 22% | 23% | 360 ms | 18% |
| B — Lantern | 0.50 | 1.36 rad | 29% | 28% | 440 ms | 22% |
| C — Flare | 0.77 | 1.92 rad | 42% | 38% | 540 ms | 27% |
| D — Dusk | 0.38 | 1.04 rad | 23% | 30% | 620 ms | 24% |

These scene values are computed from *saved knobs and first-party CV scales*, not from rendered audio. The A/B DualVCA maximum gains are saved at **0.16/0.13**, the Echo crossfeed at **0.58**, and the host output at **0.15**. They are intended to give a cautious starting level but do **not** establish clipping or eight-voice summed headroom. Start at low monitoring volume.

Source-only verification:

```sh
python3 tools/patches/patch_inspector.py validate patches/examples/MODULAR_-_Night_Lanterns_Dual_Timbre.vcv
python3 tools/patches/patch_audio_routes.py patches/examples/MODULAR_-_Night_Lanterns_Dual_Timbre.vcv --require-host-input --require-generator-route
python3 tools/patches/factory_patch_coverage.py
python3 -m unittest discover -s tests -p 'test_night_lanterns_patch.py' -v
```

Acceptance still requires opening the patch in a fork-built Cardinal/DAW host, auditioning 1/2/4/8 notes with transport start/stop, verifying stereo levels and release tails, and save/reopen at 44.1/48/96 kHz. The source checks do not exercise any of that.

## Luminous Portamento Duets — linear and exponential glides in stereo

[Open the source patch](../patches/examples/MODULAR_-_Luminous_Portamento_Duets.vcv).
This **12-module, 23-cable** original example is an eight-voice keyboard study
in a two-manual, octave-spaced sonority. It intentionally demonstrates the
simultaneous output curves of the new **SlewGlide**, not a physical instrument
model or measured stereo mix.

- HostMIDI saves **8-channel Reuse polyphony**. Its pitch output 0 drives
  SlewGlide **signal input 0**, with independent MIDI gate 1 and retrigger 6
  cables into one bundled Fundamental ADSR.
- SlewGlide **linear output 0** tunes the left MorphVCO pitch input 0
  (octave 0, fine 0 cents); **exponential output 1** tunes a separate right
  MorphVCO (octave +1, fine −3 cents). Different glide curves therefore
  reach two distinct oscillator instances, each passing through its own
  StateFilter. The left LP output feeds DualVCA A; the right BP feeds
  DualVCA B. Shared ADSR output 0 gates both, followed by separate
  StereoEcho left/right inputs and **source-verified distinct HostAudio2
  jacks 0 and 1**.
- Macro8 outputs 0 and 1 modulate SlewGlide rise/fall CV inputs 1 and 2.
  Its other six outputs control the two oscillator morph inputs, two
  filter resonance CVs, echo wet and echo feedback. All eight macros use
  saved **unipolar** output ranges. The SlewGlide **MOVING** +10 V gate
  output remains available but intentionally unpatched.

The two SlewGlide time knobs start at **0.12 s rise / 0.18 s fall**. Positive
macro CV adds **0.5 seconds per volt**, so the source-defined A–D snapshot
values imply the following directional times *after a scene has settled*:

| Recall | Nominal rise | Nominal fall | Character |
| --- | ---: | ---: | --- |
| A — Spark | 0.16 s | 0.23 s | Relatively short transitions |
| B — Velvet | 0.395 s | 0.63 s | Lyric line and held chord changes |
| C — Comet | 1.02 s | 1.58 s | Long, slowly resolving motion |
| D — Orbit | 1.72 s | 1.23 s | Asymmetric rising and falling slides |

SlewGlide's *linear* time means **10 V of travel** (a normal 1 V octave
interval covers only one-tenth of that nominal time); *exponential* time
means approximately **99% convergence to a fixed target**. They are not
interchangeable timing curves. Macro8 morph duration is 1.25 seconds, so
actual CV can itself transition between these scene targets.

The saved DualVCA maximum gains are **0.18/0.14**, HostAudio2 output gain
**0.14**, and StereoEcho base time **380 ms** with modest feedback/wet
values. These are source settings, **not an acoustic headroom guarantee**.
Begin monitoring quietly. Play single legato transitions first, then chords;
no host transport is required.

Source-only acceptance:

```sh
python3 tools/patches/patch_inspector.py validate patches/examples/MODULAR_-_Luminous_Portamento_Duets.vcv
python3 tools/patches/patch_audio_routes.py patches/examples/MODULAR_-_Luminous_Portamento_Duets.vcv --require-source-verified-stereo --require-source-verified-signal-route
python3 tools/patches/factory_patch_coverage.py
python3 -m unittest discover -s tests -p 'test_luminous_portamento_patch.py' -v
```

This proves saved endpoint contracts and directed first-party signal paths,
not audible glide, level balance, Rack rendering or DAW save/reopen. Before
releasing this patch, audition one/eight voices at 44.1/48/96 kHz, monitor
stereo meters and tails, and verify session reload.

## Reed Chamber Organ — two manuals, gentle vibrato and four tone-color scenes

[Open the source preset](../patches/examples/MODULAR_-_Reed_Chamber_Organ.vcv).
The **11-module, 23-cable** sketch is intended for eight-voice keyboard chords
and short detached stabs, rather than cinematic pads or FM bells. Both original
MorphVCOs receive the same per-note 1 V/oct HostMIDI signal, but their saved
octave controls are 0 and +1 (nominal **8-foot and 4-foot manuals**), with −2
and +4 cents of fine tuning. Both have deliberately mild waveform morph and
small FM-depth settings. This is an *original generic combo-organ study*;
it does **not** physically model Hammond tonewheels, drawbars or a Leslie cabinet.

The lower manual follows a gentle StateFilter low-pass path into DualVCA A;
the upper manual goes directly into DualVCA B. Both gates receive the same
Fundamental ADSR triggered by HostMIDI gate and retrigger. Gain maxima are
**0.16** and **0.10**, respectively; their paths reach individual StereoEcho
input jacks, then separate HostAudio2 L/R inputs with a stored host output
level of **0.17**. This is a conservative *intention*, not a measurement of
eight-note summing or clipping. The free-running ClockedLFO is set to exactly
3 Hz, with no host clock/transport cables. Its sine wave drives both MorphVCO
exponential FM inputs at just 0.8% and 1.2% depth for small coherent vibrato.

Macro8 changes the two wave morphs, filter cutoff and resonance, echo wet/time/
feedback and upper-manual pulse width. Four unipolar source snapshots morph
smoothly over a saved **1.2 s** interval. Representative settings inferred
from first-party source mappings are:

| Snapshot | Lower/upper morph | Filter cutoff (approx.) | Echo wet | Echo time | Echo feedback |
| --- | ---: | ---: | ---: | ---: | ---: |
| A — Chapel | 0.16 / 0.24 | 1.62 kHz | 9% | 180 ms | 11.5% |
| B — Reed | 0.35 / 0.42 | 2.38 kHz | 13% | 200 ms | 13% |
| C — Swirl | 0.26 / 0.34 | 1.93 kHz | 20% | 280 ms | 19% |
| D — Shimmer | 0.21 / 0.50 | 2.93 kHz | 16% | 360 ms | 16% |

The table is **not a rendered-sound or dynamic-CV measurement**. Verify
the source graph and full stereo generator-to-host provenance with:

```sh
python3 tools/patches/patch_inspector.py validate patches/examples/MODULAR_-_Reed_Chamber_Organ.vcv
python3 tools/patches/patch_audio_routes.py patches/examples/MODULAR_-_Reed_Chamber_Organ.vcv --show-signal-traces --require-source-verified-stereo
python3 -m unittest discover -s tests -p 'test_reed_chamber_organ.py' -v
```

Before performance use, load in a fork-built host at low monitor volume,
audition 1/2/4/8 polyphonic note events, verify actual timbre and release
tails at 44.1/48/96 kHz, then save/reopen in the DAW. Those gates remain open.

## Future work

Add audio-rendered regression fixtures, MPE/polyphonic-expression performance patches, improved patch-browser tagging, and audio previews after real host audition and a testable plugin build.
