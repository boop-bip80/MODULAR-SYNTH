# Morph VCO — first-party DSP contract and validation

Status: First-party oscillator module in the `ModularSynth` static collection. This document describes the implementation and tests, **not** a claim that a full DAW host build has passed.

## Controls and CV

| Control or jack | Behavior |
| --- | --- |
| Octave | -4 to +4 octaves, snapped to integer octaves |
| Fine | -100 to +100 cents |
| Wave | 0 = sine, 0.5 = saw, 1 = pulse; continuously interpolated |
| Width | Pulse duty 5% to 95% |
| FM depth | 0–1; full depth maps 5 V FM CV to one octave |
| 1V/OCT input | C4 at 0 V (261.6255653 Hz); +1 V doubles frequency |
| FM input | Exponential pitch modulation, scaled by FM depth |
| Morph CV input | 0 to 10 V covers a full wave-shape range |
| PWM CV input | Adds 0.1 duty fraction per volt |
| Wave output | Morph oscillator at nominal ±5 V |
| Sine output | Independent full-amplitude sine from the same phase accumulator |

Each jack supports up to 16 Rack polyphony channels. Monophonic CV signals are broadcast to polyphonic lanes using the Rack port API. Each active lane has its own persistent phase, shape smoothing and PWM smoothing. When input polyphony shrinks, retired lanes are reset so re-expanding a cable does not resume frozen oscillator phases or previous shape controls; remaining active lanes stay phase-continuous.

Frequency input is limited to a maximum of 45% of the sample rate, keeping the oscillator phase increment below Nyquist. The pitch helper clamps input to ±20 octaves before exponentiation, avoiding overflow on extreme CV. Invalid frequency or host sample rate produces silence; invalid pitch CV defaults to C4, morph to sine, and width to 50%.

The DSP is allocation-free on the audio thread and has no locks, disk or UI activity. It preserves phase when the sample rate or shape changes. User reset explicitly resets phase. Shape and duty cycle are slewed over approximately 2.5 ms to reduce control zipper noise.

## Waveform and aliasing limits

The saw and pulse edges use **polyBLEP discontinuity correction**, which reduces aliasing from sharp edges. It does **not** eliminate all aliasing, especially near Nyquist; no oversampling or hard sync is implemented yet.

The pulse waveform intentionally has a duty-dependent DC component. At 25% duty, its unscaled mean is approximately -0.5 (about -2.5 V on the Wave output). Insert a high-pass/DC-blocking module if needed.

The C4 output nominally reaches ±5 V, but unusual high-frequency/PWM transient shapes may briefly depart from that nominal range. This is CV/audio modular behavior and should be reviewed against any downstream hard limit.

## Standalone regression tests

From the repository root:

```sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror \
  tests/morphvco_dsp_smoke.cpp -o /tmp/morphvco_dsp_smoke
/tmp/morphvco_dsp_smoke

# Representative Cardinal optimization flag order:
c++ -std=gnu++17 -O3 -ffast-math -fno-finite-math-only -Wall -Wextra -Werror \
  tests/morphvco_dsp_smoke.cpp -o /tmp/morphvco_dsp_cardinal
/tmp/morphvco_dsp_cardinal
```

The C++17 test is independent of Rack, plugins, audio hardware, and other third-party libraries.

It covers:

- A4 cycle count at 48 kHz (440 Hz within one-cycle tolerance).
- ±1 V/oct ratios and saturation at extreme CV.
- NaN/Inf handling even when compiled with strict `-ffast-math`.
- Phase continuity across a 48→96 kHz host sample-rate change.
- Smoothing and eventual convergence of morph and PWM.
- 16 independent voice phase states and phase normalization.
- Waveform continuity across sine/saw/pulse morph boundaries.
- DC expectation of a 25% duty pulse.
- polyBLEP active at leading and trailing edges.
- Relative error reduction vs ideal truncated Fourier-series reference.

### Measured reference-waveform error

One cycle of 3 kHz at 48 kHz (16 samples per cycle), compared with the first seven Fourier harmonics below Nyquist:

| Waveform | Naive RMS error | polyBLEP RMS error | Relative reduction |
| --- | ---: | ---: | ---: |
| Saw | 0.26113 | 0.07542 | 71.1% |
| 50% pulse | 0.37278 | 0.11819 | 68.3% |

These are waveform errors against an explicitly truncated harmonic reference, **not** measured alias-energy reduction in dB. They are regression metrics, not a guarantee of spectral purity at all frequencies.

Local verification on 2026-11-01: C++17 O2, Cardinal-style O3 fast-math with final `-fno-finite-math-only`, and O3 with plain `-ffast-math` all built and ran successfully. AddressSanitizer/UBSan also passed with leak detection disabled because LeakSanitizer cannot inspect processes under the current container's ptrace policy.

## Known gaps

- No full Rack/Cardinal plugin-host build or listening test is included in this DSP-only verification.
- No anti-aliased hard-sync, oversampling, through-zero FM or overshoot limiter.
- No multi-platform CPU benchmarks or profile-guided optimization.
- Regression comparison should eventually be extended with an oversampled spectral reference and automated alias-to-signal measurements.

Implementation: `plugins/ModularSynth/src/MorphVCO.hpp` (DSP), `MorphVCO.cpp` (Rack integration/UI), `tests/morphvco_dsp_smoke.cpp` (standalone regression).
