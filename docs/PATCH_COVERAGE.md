# Factory patch coverage: source-only evidence matrix

This report tracks the **eight checked-in `MODULAR_-_*.vcv` examples** and asks two separate questions:

1. Does **every model declared by the first-party `ModularSynth` manifest** appear in at least one original example?
2. Are the **module instances, saved cables and settings** needed for each example's advertised patching workflow actually present?

The executable checker is `tools/patches/factory_patch_coverage.py`. It imports the existing `patch_inspector.py` rather than reimplementing JSON or cable validation. All checks run offline on source files; **none loads Cardinal, starts audio, or verifies third-party plugin binaries**.

## First-party model coverage

| First-party model from `plugins/ModularSynth/plugin.json` | Examples containing it | Source-backed relevance |
| --- | --- | --- |
| `MorphVCO` | `MODULAR_-_Morph_VCO_Performance.vcv`, `MODULAR_-_Morphing_State_Pad.vcv`, `MODULAR_-_Cinematic_Drift_Pad.vcv`, `MODULAR_-_Rhythmic_Grit_Bass.vcv`, `MODULAR_-_Polyphonic_Motion_Pad.vcv` | Saved MIDI pitch and audio routing; pad additionally wires Macro8 shape CV |
| `StateFilter` | `MODULAR_-_Morphing_State_Pad.vcv`, `MODULAR_-_Cinematic_Drift_Pad.vcv`, `MODULAR_-_Rhythmic_Grit_Bass.vcv`, `MODULAR_-_Polyphonic_Motion_Pad.vcv` | MorphVCO feeds audio input, low-pass output feeds VCA, two Macro8 outputs target resonance/drive CV |
| `Macro8` | `MODULAR_-_Morphing_State_Pad.vcv`, `MODULAR_-_Cinematic_Drift_Pad.vcv`, `MODULAR_-_Rhythmic_Grit_Bass.vcv`, `MODULAR_-_Polyphonic_Motion_Pad.vcv` | Three or four named CV outputs connected; two or four versioned eight-value snapshots saved |

The analyzer obtains the model list from the manifest **at runtime**. If a new model is added without a first-party example instantiating it, the test fails until coverage is provided and reviewed.

## Advertised example capability checks

| Original example | Saved graph/data claims required by the test | Third-party limits |
| --- | --- | --- |
| Pulse Bass | Host MIDI to oscillator and ADSR; oscillator to filter; filter and envelope to VCA; VCA to host; both saved HostAudio2 input jack indices used | Bogaudio VCF and Fundamental module port semantics are not independently validated here |
| Granular Veil | Two **distinct** Bogaudio oscillator instances both receive MIDI and feed one mixer; ADSR→VCA→Clouds; Clouds→two host input jacks | Clouds' grain quality/stereo behavior and third-party port ranges remain unverified |
| Clockwork Pulses | HostTime→GridSeq and Plaits; GridSeq and LFO→Plaits; Plaits→Plateau→both host input jacks | No DAW transport or GridSeq/Plaits/Plateau DSP execution |
| Morph VCO Performance | MIDI pitch→`MorphVCO` input 0, `MorphVCO` output 0→VCA, MIDI gate→ADSR→VCA and VCA→host | The third-party ADSR/VCA behavior is not rendered |
| Morphing State Pad | MIDI pitch/gate; `Macro8` outputs 0/1/2 to MorphVCO shape and StateFilter resonance/drive inputs; oscillator output 0→filter input 0; filter LP output 0→VCA→host; two saved Macro8 snapshots with 8 finite 0–1 values each | Visual UI, real-time morph interpolation, note/audio playback, and actual patch save/reopen remain unverified |
| Cinematic Drift Pad | All three original modules, MIDI/ADSR/VCA path, Macro8 outputs 0–3 for Texture/Resonance/Warmth/Cutoff including cutoff CV into filter input 1; two saved snapshots; output 3 bipolar mode (param 18); 4.0-second morph time (param 8) | No autonomous LFO or audio-rendered cinematic quality is inferred from graph |
| Rhythmic Grit Bass | All three original modules, same four macro connections including bipolar cutoff; two saved snapshots named Growl/Resonance/Drive/Cutoff; 0.20-second morph time | Rhythm comes from external MIDI/DAW; no built-in sequencer or actual bass sound is asserted |
| Polyphonic Motion Pad | HostMIDI saved for 8 Reuse-mode polyphonic channels; MIDI pitch fans to MorphVCO pitch and StateFilter 1 V/oct cutoff; per-lane gate/retrigger feeds ADSR→VCA; global Macro8 Color/Resonance/Warmth/Width with four populated A–D snapshots, bipolar Width mode and 1.8-second transition; same poly VCA output wired to both nominal host inputs | Saved channel/mode and cable graph can be checked, but actual MIDI voice allocation, eighth-voice sound and sample-rate behavior require host audition |

The analyzer checks required graph **connectivity by module type**; pinned port indices are grounded in the original-module, checked-in Cardinal HostMIDI/HostAudio, and source-inspected pinned Fundamental ADSR/VCA-1 declarations. The **existing inspector** independently verifies numeric port bounds for original `ModularSynth` modules, but does not automatically verify every Fundamental port. Saved stereo routes demonstrate two nominal `HostAudio2` input cables, **not** that a compiled host plays independently panned stereo. The existing inspector separately checks structural cable IDs, unique destinations, first-party port bounds and parameter ranges. Its warnings about third-party models are preserved and displayed as warning counts; they must not be treated as proof of module availability.

The State Pad, Cinematic Drift Pad, Rhythmic Grit Bass and Polyphonic Motion Pad data checks verify `macro8Version=1`, eight nonempty names with each patch's documented first three or four labels (Shape/Resonance/Drive, Texture/Resonance/Warmth/Cutoff, Growl/Resonance/Drive/Cutoff, or Color/Resonance/Warmth/Width), four snapshot slots, with two populated eight-control snapshots in the first three and **four** in Polyphonic Motion Pad, all with finite normalized values. It does not execute `Macro8::dataFromJson` or hear the recalled state.

## Sample rates and runtime assumptions

Each of the current eight factory example JSON objects has `cables`, `modules`, `version` and `zoom` at the root; **none stores a top-level host audio sample rate**. This checker therefore cannot reject or certify a patch on a fabricated 44.1/48/96 kHz assumption. MIDI timing, DAW transport, plugin load, patch migration, output loudness, clipping and DSP sample-rate behavior require a real host/build or a dedicated audio test. The original [factory-patch manual acceptance checklist](FACTORY_PATCHES.md) remains necessary.

## Run the source checks

From repository root with Python 3.10+ (standard library only):

```sh
python3 tools/patches/factory_patch_coverage.py
python3 tools/patches/factory_patch_coverage.py --json
python3 -m unittest discover -s tests -p 'test_factory_patch_coverage.py' -v
python3 tools/patches/patch_inspector.py validate patches/examples/MODULAR_-_Morphing_State_Pad.vcv
```

The checker exits **0** when every manifest module is represented, every listed example exists and every declared capability claim matches source; **1** for coverage/claim errors; **2** for a malformed manifest or unrecoverable inspection setup. A new `MODULAR_-_` example intentionally requires a corresponding declarative claim specification—this prevents silently advertising a new factory preset without reviewing its saved graph.

The Python regression includes negative fixtures for a missing original model, missing LFO route, disconnected MIDI-driven granular oscillator, invalid first-party cable port, removed Macro8 snapshot, incorrect bipolar cutoff/PWM mode, mono HostMIDI setting, missing poly keytracking, wrong snapshot morph time, missing fourth snapshot, missing advertised file and newly unreviewed example.

## What this does not establish

- Third-party models have correct compiled version, input/output port semantics, or host availability.
- The patches render sound, sound as described, avoid unwanted clipping, or perform correctly at 44.1/48/96 kHz.
- All historical/upstream example patches are valid. The coverage gate is scoped deliberately to our `MODULAR_-_` examples.
- Parameter/CV semantics and polyphony of third-party modules. Their source-backed schemas would require separately reviewed evidence.

This is a **first-party coverage and saved-graph QA test**, not an audio smoke test or sample-rate benchmark.
