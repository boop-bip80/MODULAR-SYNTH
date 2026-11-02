# Fold Drive — original timbre processor

`ModularSynth/FoldDrive` is a first-party, C++17 wavefolder designed for
expressive pad, bass and cinematic timbre changes. The source implementation
does not depend on Rack; the separately compiled wrapper registers the model
with Cardinal's first-party static plugin loader. A checked-in SVG is an
original **12 HP × 3U** panel, and the module has **16 independent audio/CV
lanes**.

This page describes the implementation in
[`FoldDrive.hpp`](../plugins/ModularSynth/src/FoldDrive.hpp) and
[`FoldDrive.cpp`](../plugins/ModularSynth/src/FoldDrive.cpp). It is **not a
host audio measurement or listening review**.

## Musically useful controls

| Control / port | Effective range and response |
| --- | --- |
| IN (input 0) | Nominal ±5 V audio; nonfinite samples become 0 V, finite extremes clamp to ±10 V |
| DRIVE (parameter 0) | 0…100%, 30% default; gain before sine folding is `1 + 8 × drive²`, approaching ninefold harmonic action at full drive |
| BIAS (parameter 1) | −100…+100%, 0% default; shifts fold phase and introduces asymmetry; zero-input baseline is subtracted |
| WET MIX (parameter 2) | 0…100%, 65% default, equal-voltage linear dry/wet crossfade |
| DRV CV (input 1) | Adds +0.1 of normalized DRIVE per volt; ±10 V covers the full nominal range |
| BIA CV (input 2) | Adds +0.1 bias units per volt; positive and negative inputs available |
| MIX CV (input 3) | Adds +0.1 WET MIX per volt, then clamps to 0…100% |
| OUT (output 0) | Exactly one audio output, hard bounded **−10…+10 V** after mixing |

Control sums are clamped to their ranges and smoothed with an exponential
one-pole update, time constant approximately 3 ms. This reduces immediate
automation edges but is **not a guarantee of click-free sound**, especially
for discontinuous audio sources or host-level gain changes.

For normalized audio `x = clamp(IN, −10, +10) / 5`, with effective drive `d`,
bias `b`, and wet `m`, the instantaneous transfer is:

```text
gain       = 1 + 8*d*d
folded     = sin((pi/2) * (gain*x + b)) - sin((pi/2) * b)
shaped     = x + d * (folded - x)
out        = clamp(IN + m * (5*shaped - IN), -10, +10)
```

The input in this expression is already clamped to ±10 V. `d`, `b` and
`m` are the smoothed settings, not instantaneous CV values. At DRIVE=0 the
transfer is dry, and at MIX=0 the output is dry regardless of drive/bias.
At BIAS=0 positive/negative folding is odd-symmetric. A nonzero BIAS can
make odd and even partials without emitting DC merely because the input is
exactly zero. The fold can still have a nonzero *time-averaged* level on
complex asymmetric input; no automatic DC blocker is implemented here.

## Preset to explore

[Fold Drive Cinematic Motion](../patches/examples/MODULAR_-_Fold_Drive_Cinematic_Motion.vcv)
is a source-checked **9-module / 13-cable** first-party patch:

1. `HostMIDI` saves 8-channel Reuse polyphony. Pitch → `MorphVCO` 1 V/oct,
   gate and retrigger → `Fundamental/ADSR` inputs 4/5.
2. `MorphVCO` morphed audio → `FoldDrive` input 0 → `StateFilter` input 0;
   filter low-pass → `VCA-1` audio input 1.
3. ADSR envelope → VCA CV input 0; attenuated VCA output → both nominal
   `Cardinal/HostAudio2` jacks. Saved VCA gain **0.18**, host gain **0.12**.
4. Free-running `ClockedLFO` at **0.25 Hz** sends TRI output 1 → FoldDrive
   drive CV 1 and SIN output 0 → bias CV 2. MIDI channel pressure controls
   VCO morph, and CC1 mod wheel controls FoldDrive MIX CV input 3.

The LFO has no Clock/Reset cables and **is not tempo-synchronized**. The
example graph and first-party port bounds pass `patch_inspector.py` and
`factory_patch_coverage.py`; the Fundamental jack labels are source-inspected
elsewhere but are not independently certified by the generic inspector.

## Safety, polyphony and explicit limitations

- **Numerical bounds:** Every processed frame is between −10 V and +10 V,
  including invalid audio, CV and parameter values. Invalid sample rates
  silence and reset a lane. IEEE-754 exponent-bit guards remain effective
  even under the runner's aggressive `-ffast-math` profile.
- **Voice lifecycle:** Sources with 1–16 channels and each connected CV
  input contribute to output voice count (clamped to 16). Monophonic CV
  broadcasts across audio lanes using Rack's `getNormalPolyVoltage` convention.
  Retired lanes reset their smoothed state; a newly reconnected lane starts
  from its first valid CV settings rather than stale prior automation. A
  Rack/host reset callback **atomically requests** reset; the audio thread
  consumes the request at the next process tick, avoiding UI/audio races.
- **Real-time characteristics:** The DSP path allocates no heap memory,
  takes no locks, reads no files, and does not instantiate external code.
  Two `sin` evaluations per voice/frame are required when folding.
- **Aliasing:** This is sine transfer shaping, **not a bandlimited,
  oversampled, or antialiased wavefolder**. Higher DRIVE, brighter inputs,
  and high-pitched notes produce stronger above-Nyquist partials that can
  fold into the audible band. Filter after FoldDrive or use less drive
  for cleaner upper registers. No alias-power reduction is claimed.
- **Headroom:** Hard ±10 V bounds are per lane, not a bound on an 8/16-note
  summed host output. VCA and host gain remain important; saved settings
  are not a measured unclipped master level.
- **Validation:** A standalone C++ DSP regression exercises transparency,
  asymmetry, fold polarity, CV smoothing, reset, hostile inputs and 280k
  bounded samples. A separate HEADLESS wrapper exercises concurrent
  reset requests, 1/8/16 channels and **8,192 allocation-free process ticks**.
  Source/headless checks do not certify DAW load, audio,
  plugin CPU, or live automation. Before production, compile a real host,
  test 44.1/48/96 kHz, listen with low output gain and profile alias/CPU.

All module code, source tests, SVG panel and factory patch here are original
MODULAR-SYNTH contributors' work, SPDX `GPL-3.0-or-later`. Inherited
Cardinal/Rack/Fundamental components retain their existing attribution.
