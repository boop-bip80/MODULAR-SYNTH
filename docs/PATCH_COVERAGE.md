# Factory patch coverage: source-only evidence matrix

This report tracks the **sixteen checked-in `MODULAR_-_*.vcv` examples** and asks two separate questions:

1. Does **every model declared by the first-party `ModularSynth` manifest** appear in at least one original example?
2. Are the **module instances, saved cables and settings** needed for each example's advertised patching workflow actually present?

The executable checker is `tools/patches/factory_patch_coverage.py`. It imports the existing `patch_inspector.py` rather than reimplementing JSON or cable validation. All checks run offline on source files; **none loads Cardinal, starts audio, or verifies third-party plugin binaries**.

## First-party model coverage

| First-party model from `plugins/ModularSynth/plugin.json` | Examples containing it | Source-backed relevance |
| --- | --- | --- |
| `MorphVCO` | `MODULAR_-_Morph_VCO_Performance.vcv`, `MODULAR_-_Morphing_State_Pad.vcv`, `MODULAR_-_Cinematic_Drift_Pad.vcv`, `MODULAR_-_Rhythmic_Grit_Bass.vcv`, `MODULAR_-_Polyphonic_Motion_Pad.vcv`, `MODULAR_-_Stereo_Echo_Showcase.vcv`, `MODULAR_-_Echo_Motion_Performance.vcv`, `MODULAR_-_Clocked_Modulation_Studio.vcv`, `MODULAR_-_Cinematic_Pulse_Score.vcv`, `MODULAR_-_Noir_Expressive_Lead.vcv` | Saved MIDI pitch and waveform paths, including ClockedLFO oscillator morph CV |
| `StateFilter` | `MODULAR_-_Morphing_State_Pad.vcv`, `MODULAR_-_Cinematic_Drift_Pad.vcv`, `MODULAR_-_Rhythmic_Grit_Bass.vcv`, `MODULAR_-_Polyphonic_Motion_Pad.vcv`, `MODULAR_-_Stereo_Echo_Showcase.vcv`, `MODULAR_-_Echo_Motion_Performance.vcv`, `MODULAR_-_Clocked_Modulation_Studio.vcv`, `MODULAR_-_Cinematic_Pulse_Score.vcv`, `MODULAR_-_Noir_Expressive_Lead.vcv` | Saved LP/HP and resonance/drive/CV routes, with source-backed first-party port indices |
| `FoldDrive` | `MODULAR_-_Fold_Drive_Cinematic_Motion.vcv` | MIDI poly audio → sine folding → StateFilter, plus free-running LFO TRI/SIN drive/bias and CC1 wet CV; all three FoldDrive CV port indices checked |
| `Macro8` | `MODULAR_-_Morphing_State_Pad.vcv`, `MODULAR_-_Cinematic_Drift_Pad.vcv`, `MODULAR_-_Rhythmic_Grit_Bass.vcv`, `MODULAR_-_Polyphonic_Motion_Pad.vcv`, `MODULAR_-_Echo_Motion_Performance.vcv`, `MODULAR_-_Cinematic_Pulse_Score.vcv`, `MODULAR_-_Noir_Expressive_Lead.vcv` | Three-to-five named CV outputs; versioned A/B or A–D serialized snapshots |
| `StereoEcho` | `MODULAR_-_Stereo_Echo_Showcase.vcv`, `MODULAR_-_Echo_Motion_Performance.vcv`, `MODULAR_-_Clocked_Modulation_Studio.vcv`, `MODULAR_-_Cinematic_Pulse_Score.vcv`, `MODULAR_-_Noir_Expressive_Lead.vcv` | Independent saved L/R input routes and modulation; no host playback claim |
| `ClockedLFO` | `MODULAR_-_Clocked_Modulation_Studio.vcv`, `MODULAR_-_Cinematic_Pulse_Score.vcv` | One beat/reset-clocked eight-lane example; one MIDI mono **free-running** rhythmic envelope example |
| `FMVoice` | `MODULAR_-_FM_Voice_Performance.vcv` | Saved MIDI pitch and gate route through the original two-operator voice and an ADSR/VCA to HostAudio2; no linked host/audio test | 
| `DualVCA` | `MODULAR_-_Morph_VCO_Performance.vcv` | Both independent A/B audio and CV routes, two bounded outputs into host left/right; no host runtime guarantee |

The analyzer obtains the model list from the manifest **at runtime**. If a new model is added without a first-party example instantiating it, the test fails until coverage is provided and reviewed.

## Advertised example capability checks

| Original example | Saved graph/data claims required by the test | Third-party limits |
| --- | --- | --- |
| Pulse Bass | Host MIDI to oscillator and ADSR; oscillator to filter; filter and envelope to VCA; VCA to host; both saved HostAudio2 input jack indices used | Bogaudio VCF and Fundamental module port semantics are not independently validated here |
| Granular Veil | Two **distinct** Bogaudio oscillator instances both receive MIDI and feed one mixer; ADSR→VCA→Clouds; Clouds→two host input jacks | Clouds' grain quality/stereo behavior and third-party port ranges remain unverified |
| Clockwork Pulses | HostTime→GridSeq and Plaits; GridSeq and LFO→Plaits; Plaits→Plateau→both host input jacks | No DAW transport or GridSeq/Plaits/Plateau DSP execution |
| Morph VCO Performance | MIDI pitch→`MorphVCO` input 0, oscillator output 0 fans into `DualVCA` audio A/B ports 0/2, MIDI gate→Fundamental ADSR→Dual VCA CV ports 1/3, separate A/B outputs→HostAudio2 left/right | Fundamental ADSR and new first-party DualVCA audio are source-wired, not tested in a host |
| FM Voice Performance | HostMIDI pitch output 0→FMVoice PITCH input 0, gate output 1→Fundamental ADSR gate input 4; FMVoice carrier output 0→Fundamental VCA audio input 1, ADSR output 0→VCA CV input 0, VCA output 0→HostAudio2 Left/M input 0 | FMVoice endpoints and saved graph are source-checked; ADSR/VCA audio, bandlimiting, host MIDI and actual sound are not verified |
| Morphing State Pad | MIDI pitch/gate; `Macro8` outputs 0/1/2 to MorphVCO shape and StateFilter resonance/drive inputs; oscillator output 0→filter input 0; filter LP output 0→VCA→host; two saved Macro8 snapshots with 8 finite 0–1 values each | Visual UI, real-time morph interpolation, note/audio playback, and actual patch save/reopen remain unverified |
| Cinematic Drift Pad | The MorphVCO/StateFilter/Macro8 trio used by this patch, MIDI/ADSR/VCA path, Macro8 outputs 0–3 for Texture/Resonance/Warmth/Cutoff including cutoff CV into filter input 1; two saved snapshots; output 3 bipolar mode (param 18); 4.0-second morph time (param 8) | No autonomous LFO or audio-rendered cinematic quality is inferred from graph |
| Rhythmic Grit Bass | The same three patch-local originals (MorphVCO/StateFilter/Macro8), four macro connections including bipolar cutoff; two saved snapshots named Growl/Resonance/Drive/Cutoff; 0.20-second morph time | Rhythm comes from external MIDI/DAW; no built-in sequencer or actual bass sound is asserted |
| Polyphonic Motion Pad | HostMIDI saved for 8 Reuse-mode polyphonic channels; MIDI pitch fans to MorphVCO pitch and StateFilter 1 V/oct cutoff; per-lane gate/retrigger feeds ADSR→VCA; global Macro8 Color/Resonance/Warmth/Width with four populated A–D snapshots, bipolar Width mode and 1.8-second transition; same poly VCA output wired to both nominal host inputs | Saved channel/mode and cable graph can be checked, but actual MIDI voice allocation, eighth-voice sound and sample-rate behavior require host audition |
| Stereo Echo Showcase | MIDI-driven MorphVCO and ADSR/VCA feeds StateFilter; LP and HP outputs feed StereoEcho L/R inputs 0/1, and Echo outputs 0/1 feed the corresponding host jacks | Source graph proves two separate saved routes, not heard stereo processing, delay behavior or audio safety |
| Echo Motion Performance | MIDI pitch/gate→MorphVCO and ADSR/VCA→StateFilter; filter LP/HP→StereoEcho L/R→host; Macro8 outputs 0/1/2→Echo CV inputs **2/3/4** and output 3→MorphVCO shape; all four CV outputs **unipolar**; four A–D versioned scenes and 1.2-second morph time | Saved additive CV settings and source code bound nominal 190–800 ms delay, 18–54% feedback and 28–57% wet; no host audition or click-free transition claim |
| Clocked Modulation Studio | HostTime BEAT output 3→ClockedLFO clock input 1; RESET 1→LFO reset 2; eight-channel MIDI pitch/gate, LFO sine/triangle/pulse/EOC to oscillator/filter/Echo/ADSR; independent LP/HP Echo→HostAudio left/right | Beat/transport and note allocation are source-backed routes only, no tested DAW sync or audio quality |
| Cinematic Pulse Score | Mono MIDI pitch/gate→MorphVCO and **first** ADSR/VCA→filter; **free-running** ClockedLFO PULSE out 3→**second** ADSR gate 4→second VCA CV 0 on filtered LP→Echo L; filter HP bypasses rhythm VCA→Echo R; LFO SINE0→Morph CV2; four Macro8 CVs for filter resonance/drive and Echo feedback/wet, four A–D unipolar scenes, 2.6 s morph | Helper binds both ADSR/VCA chains by distinct saved IDs, verifies LFO free 0.8 Hz with no HostTime/CLOCK/RESET cable; no audible pulse/film-score or timing guarantee |
| Noir Expressive Lead | Mono HostMIDI pitch/gate, aftertouch output **3→MorphVCO morph CV 2**, mod wheel output **5→Echo wet CV 4**, oscillator→filter LP→enveloped VCA→Echo L (Right normalled); Macro8 outputs 0–4 to time/feedback/resonance/drive/PWM, four A–D scenes, 0.65 s morph, Echo L/R→host jacks | Source-verified checked-in HostMIDI/HostAudio2 jack indices and original CV cable routes only; no controller messages, DAW or sound tested |
| Fold Drive Cinematic Motion | HostMIDI **8-channel Reuse** pitch/gate/retrigger; oscillator → FoldDrive IN 0 → StateFilter LP → MIDI-gated ADSR/VCA → both host jacks; free-running ClockedLFO **TRI 1→FoldDrive DRV 1**, **SIN 0→BIAS 2**, MIDI mod-wheel **5→MIX 3** and aftertouch **3→MorphVCO MORPH 2**; LFO free rate 0.25 Hz and no clock/reset cable | Source-backed saved module/route data and FoldDrive port semantics only; no alias/CPU, true eight-voice audio or DAW automation measurement |

The analyzer checks required graph **connectivity by module type**, now including the two-operator FMVoice example; pinned port indices are grounded in the original-module, checked-in Cardinal HostMIDI/HostAudio/HostTime, and source-inspected pinned Fundamental ADSR/VCA-1 declarations. The **existing inspector** independently verifies numeric port bounds for original `ModularSynth` modules and checked-in Cardinal HostMIDI/HostTime/HostAudio2, but does not automatically verify every Fundamental port. Saved stereo routes demonstrate two nominal `HostAudio2` input cables, **not** that a compiled host plays independently panned stereo. The existing inspector separately checks structural cable IDs, unique destinations, source-backed port bounds and parameter ranges. Its warnings about third-party models are preserved and displayed as warning counts; they must not be treated as proof of module availability.

The State Pad, Cinematic Drift Pad, Rhythmic Grit Bass, Polyphonic Motion Pad, Echo Motion Performance , Cinematic Pulse Score and Noir Expressive Lead data checks verify `macro8Version=1`, eight nonempty names with each patch's documented first three to five labels, and four snapshot slots. The first three save two populated snapshots; Polyphonic Motion, Echo Motion , Cinematic Pulse Score and Noir Expressive Lead save **four**. All saved snapshot values must be finite and normalized 0–1. It does not execute `Macro8::dataFromJson` or hear the recalled state.

## Sample rates and runtime assumptions

Each of the sixteen factory example JSON objects has `cables`, `modules`, `version` and `zoom` at the root; **none stores a top-level host audio sample rate**. This checker therefore cannot reject or certify a patch on a fabricated 44.1/48/96 kHz assumption. MIDI timing, DAW transport, plugin load, patch migration, output loudness, clipping and DSP sample-rate behavior require a real host/build or a dedicated audio test. The original [factory-patch manual acceptance checklist](FACTORY_PATCHES.md) remains necessary.

## Run the source checks

From repository root with Python 3.10+ (standard library only):

```sh
python3 tools/patches/factory_patch_coverage.py
python3 tools/patches/factory_patch_coverage.py --json
python3 -m unittest discover -s tests -p 'test_factory_patch_coverage.py' -v
python3 tools/patches/patch_inspector.py validate patches/examples/MODULAR_-_Morphing_State_Pad.vcv
```

The checker exits **0** when every manifest module is represented, every listed example exists and every declared capability claim matches source; **1** for coverage/claim errors; **2** for a malformed manifest or unrecoverable inspection setup. A new `MODULAR_-_` example intentionally requires a corresponding declarative claim specification—this prevents silently advertising a new factory preset without reviewing its saved graph.

The Python regression includes negative fixtures for a missing original model, missing LFO route, disconnected MIDI-driven granular oscillator, invalid first-party cable port, removed Macro8 snapshot, incorrect bipolar cutoff/PWM mode, mono HostMIDI setting, missing poly keytracking, wrong snapshot morph time, missing fourth snapshot, missing advertised file and newly unreviewed example. The Echo Motion tests also deliberately sever each of its three StereoEcho CV routes, switch one Macro8 CV range to bipolar, remove the fourth snapshot, disconnect MIDI gate or the right host audio route. All must fail the source-only coverage gate. The Cinematic Pulse Score tests additionally remove exact MIDI/LFO-to-separate-ADSR and both ADSR-to-VCA role links, LFO sine, Macro8 CVs, LP rhythmic and HP direct stereo paths, plus corrupt a fourth scene, range mode, free-run LFO rate or prohibited CLOCK/RESET cable; they require distinct patch-local IDs so a duplicated VCA model cannot satisfy the claim accidentally.

## What this does not establish

- Third-party models have correct compiled version, input/output port semantics, or host availability.
- The patches render sound, sound as described, avoid unwanted clipping, or perform correctly at 44.1/48/96 kHz.
- All historical/upstream example patches are valid. The coverage gate is scoped deliberately to our `MODULAR_-_` examples.
- Parameter/CV semantics and polyphony of third-party modules. Their source-backed schemas would require separately reviewed evidence.

This is a **first-party coverage and saved-graph QA test**, not an audio smoke test or sample-rate benchmark.
