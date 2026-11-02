# Dual VCA — original first-party utility module

Dual VCA is a **12 HP, two-channel, 16-lane-per-channel voltage-controlled
amplifier** in the MODULAR-SYNTH Originals collection. It is a clean digital
utility, not a modeled analogue amplifier.

## Patching and controls

| Control or jack | Behavior |
| --- | --- |
| A IN / B IN | Independent audio inputs; nominal ±5 V, bounded ±20 V before DSP |
| A CV / B CV | 0 V silence → +10 V full level; negative CV mutes; unplugged = full level |
| A LEVEL / B LEVEL | Independent 0–100% maximum output levels (default 100%) |
| A CURVE / B CURVE | Continuous 0–100% blend from linear CV gain to cubic CV gain |
| A / B outputs | Independent processed audio, hard bounded to ±10 V |
| SUM output | A+B mix hard bounded to ±10 V, without gain compensation |

For a playable keyboard patch, route oscillator audio to A IN and an ADSR
envelope to A CV, then A OUT to the host audio input. A second independent
voice can use the B path; or route both outputs to host stereo channels. At
5 V envelope CV, a 0% CURVE setting gives 50% of the knob gain; 100% CURVE
gives 12.5%. The 2 ms one-pole gain smoothing limits abrupt CV clicks but
also slightly softens very fast envelopes.

Both sides independently determine output lane count from their audio/CV
inputs (1–16 channels). SUM carries the larger lane count; absent lanes
contribute zero. Disappearing polyphonic lanes reset their smoothing state.
Rack reset is deferred to the audio callback through an atomic request.
No heap allocation, locks or nontrivial host work occur per sample.

## Safety and limitations

- Out-of-range controls are clamped. Connected NaN/Inf CV fails closed to
  silence; an invalid audio sample contributes zero. Invalid sample rate
  returns silence and resets the affected lane.
- Every A/B/SUM output is clipped at ±10 V. **SUM can clip** if the two
  independent paths are both loud; lower A/B LEVEL before mixing.
- CV response is intentionally unipolar; this module does not invert,
  ring-modulate or model analogue VCA distortion.
- Compile/runtime tests exercise the standalone DSP at 44.1 and 96 kHz,
  16-lane state, slew, curves, nonfinite controls and bounded mix.
  They do not prove Cardinal plugin loading, rendered panel, MIDI timing,
  subjective audio quality, host CPU cost or DAW save/reopen.

The updated [Morph VCO Performance](../patches/examples/MODULAR_-_Morph_VCO_Performance.vcv)
source patch uses both Dual VCA channels to feed stereo host outputs.
It is a saved routing demonstration, **not an auditioned host session**.
