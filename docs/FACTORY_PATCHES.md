# MODULAR-SYNTH Factory Patches — first original set

This is the first small bank of original patch arrangements for MODULAR-SYNTH. They are stored in `patches/examples/` so the existing Cardinal **File → Demo patches** menu can discover them. All referenced module types were checked against modules already used by the repository's bundled examples; the patches do not require downloading third-party VCV Library modules.

| Patch | Purpose | Interaction |
| --- | --- | --- |
| `MODULAR_-_Pulse_Bass.vcv` | Keyboard-controlled oscillator → resonant filter → envelope/VCA bass voice | Play low notes via host MIDI; adjust VCF cutoff/resonance and ADSR |
| `MODULAR_-_Granular_Veil.vcv` | Detuned dual oscillators → slow envelope → Clouds stereo texture | Hold notes via host MIDI; experiment with Clouds' grain and texture controls |
| `MODULAR_-_Clockwork_Pulses.vcv` | Host-clocked 16-step sequence → Plaits → Plateau reverb, with LFO timbral variation | Start the host/DAW transport; alter sequence steps and Plaits controls |

## Loading

1. Use a recent MODULAR-SYNTH/Cardinal **main** or **Synth** build with its packaged modules and example patches.
2. Open **File → Demo patches** and select the `MODULAR_-` patch (or load the `.vcv` directly from `patches/examples/`).
3. For Pulse Bass and Granular Veil, route MIDI notes into the plugin. Granular Veil is intentionally a primarily monophonic texture, since its Clouds processing follows the voice mix.
4. For Clockwork Pulses, start the DAW transport; the patch uses **Host Time** and does not require live MIDI notes.
5. Begin with low speaker or headphone volume. The output gain is intentionally conservative, but patch signal levels are not yet perceptually validated.

## Scope and compatibility

- These are **patch examples**, not new DSP modules or a finished preset management system.
- Models used come from Cardinal's existing bundled Fundamental, Bogaudio, Audible Instruments, JW Modules, Valley, and Cardinal collections.
- MIDI/transport mapping and sample-rate behavior are inherited from the built-in modules and host.
- The examples are designed for the existing stereo host output variant. They are not standalone VST3 exports.
- They use plain-text VCV Rack 2.x patch JSON for reproducibility.

## Validation performed

The initial files were programmatically parsed as JSON and checked for:
- unique module IDs and cable IDs;
- valid cable endpoint references and no duplicate destination jacks;
- finite parameter values and sequential parameter IDs;
- module/model names that occur in bundled repository example patches.

**Not yet verified:** loading the three patches in a compiled MODULAR-SYNTH binary, rendering audio, listening for expected sonic results, clipping/CPU profiling, and loading/saving from real DAWs. Those are explicit acceptance checks before these patches are described as production-validated.

## Manual acceptance test

- Launch a newly built plugin and load each patch; no missing-module warning should appear.
- Pulse Bass: MIDI note-on produces audio and note-off releases smoothly; stereo channels are audible.
- Granular Veil: sustained MIDI notes produce a textured stereo signal and stop after release and grain tails.
- Clockwork Pulses: host play/stop behavior follows the DAW transport; its sequence sounds through both outputs.
- For each patch: save under a new filename, reload, and compare module/cable counts and playback.
- Test at 44.1/48/96 kHz and block sizes 64/128/256 when practical. Verify silence on stop and no plugin crash.

## Future work

Add audio-rendered regression fixtures, modulation-rich cinematic patches, MPE-friendly performance patches, improved patch-browser tagging, and audio previews once a testable plugin build is available.
