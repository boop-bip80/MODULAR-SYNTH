# FM Voice — original two-operator phase-modulation source

Status: original first-party C++ DSP and a statically registered Rack model. This is **not** a claim of a completed Cardinal/DAW build, host audition, or released instrument.

## What it does

**FM Voice** provides a 16-lane polyphonic two-operator, sine-based **phase-modulation** voice: a sine modulator bends the instantaneous phase of a sine carrier. A one-sample modulator feedback path adds harmonic complexity. Here "FM" is the common synthesizer shorthand; mathematically this is phase modulation, and there are no envelopes, presets, or DX7 algorithms in the module itself.

| Control/jack | Behavior |
| --- | --- |
| OCTAVE | Snapped −4 to +4 octaves |
| FINE | −100 to +100 cents |
| RATIO | Modulator/carrier frequency ratio 0.125…16, initial 1 |
| INDEX | Modulation depth, 0…8 radians, initial 0 |
| FEEDBACK | Modulator one-sample self-feedback, 0…95%, initial 0 |
| 1V/OCT input | Standard C4 at 0 V, +1 V doubles pitch |
| RATIO CV | +1 V doubles the modulator ratio, −1 V halves it |
| INDEX CV | +1 V adds 0.8 radians to index |
| FDBK CV | +1 V adds 9.5 percentage points of feedback |
| FM OUT | Phase-modulated carrier, nominal ±5 V |
| MOD OUT | Self-feedback modulator sine, nominal ±5 V |

Values after CV addition are clamped to their documented ranges. At high pitches/ratios, the effective carrier phase-modulation index is also reduced by the bandwidth guard described below; the knob and saved value do not change. Index, ratio and feedback changes are smoothed for about 2 ms; patch startup adopts saved values immediately. All four CV inputs can carry 16 independent Rack polyphony lanes; mono CV is shared across connected polyphonic voices. Retired lanes reset phase and control histories before re-expansion.

Try `Host MIDI pitch → FM Voice 1V/OCT`, `FM OUT → envelope-controlled VCA → Host Audio`. At ratio 2, index 2–3 radians and low feedback, the voice produces bell-like harmonic sidebands; sweep INDEX with a slow LFO for moving timbres. An ADSR/VCA is necessary if you want note envelopes.

## DSP, stability and limitations

The actual signal equations are:

```text
m[n] = sin(2*pi*p_mod[n] + feedback*m[n-1])
y[n] = sin(2*pi*p_carrier[n] + index*m[n])
```

The carrier and modulator phase accumulators wrap in [0,1). The individual frequency steps clamp at 45% of sample rate, and both sine outputs are bounded to unit amplitude before the Rack ±5 V scaling. Non-finite controls are sanitized using IEEE-754 bit checks that also work under aggressive `-ffast-math`; invalid sample rates produce silence. The DSP processing loop allocates no memory, takes no locks and does not touch GUI/disk/network resources.

**Aliasing limitation:** FM/phase-modulation sidebands and self-feedback are **not bandlimited**. There is no oversampling or complete anti-aliasing solution. Even with the guard below, high ratios, index and feedback can generate aliased components. Listen and measure before using extreme settings in a release.

### High-frequency sideband guard

For a sinusoidal modulator without feedback, significant PM sidebands extend roughly to carrier frequency plus `(index + 1) × modulator frequency` (a Carson-style bandwidth estimate). The DSP limits the **effective** index as follows:

```text
guard_hz = 0.45 * sample_rate_hz
target_ceiling = clamp((guard_hz - carrier_hz) / modulator_hz - 1, 0, 8)
smoothed_ceiling = one_pole_2ms(target_ceiling)
effective_index = min(smoothed_index, smoothed_ceiling)
```

When modulator frequency is zero, the index is not restricted. The computed guard ceiling is itself smoothed over approximately 2 ms across pitch/rate changes (but adopted instantly on a fresh or reset voice), so an abrupt CV change does not directly step the modulation index. This does not prevent clicks from abrupt pitch changes or guarantee immediate protection throughout the 2 ms transition. Individual operator frequency steps remain capped at 45% of sample rate; their ratio product is computed without intermediate floating-point overflow even for extreme finite inputs. At lower pitches/ratios the ceiling stays above 8 radians and changes nothing. At high pitch, the same saved INDEX knob setting may sound less bright because the DSP attenuates high-order sidebands, preserving headroom to the output Nyquist limit.

**Controlled test, not a blanket claim:** With 3 kHz carrier, 12 kHz sine modulator (ratio 4), index 3 and 48 kHz sampling, the 27 kHz second upper sideband folds into the 21 kHz bin. A 4,800-sample coherent DFT measures that specific bin at ~0.995 normalized amplitude in the former unrestricted equation versus ~0.0737 with the guard — **22.6 dB lower**. A second coherent 6 kHz carrier/12 kHz modulator case reduces its folded 18 kHz bin by ~17.35 dB. The standalone test also checks that 440 Hz carrier/880 Hz modulator at index 8 is unchanged, and that effective index changes by no more than 0.085 rad/sample through an abrupt 440→6000 Hz pitch/ratio jump while oscillator phase is retained. The estimate does **not** bound every higher Bessel sideband, self-feedback harmonic or modulation transient; no multiband spectral or DAW guarantee is made.

A running oscillator preserves phase when sample rate changes. Rack reset zeroes phase and feedback memory. No inter-lane voice allocator, oversampling, through-zero frequency, detuning matrix, MIDI velocity mapping, automatic envelopes or host performance benchmarks are implemented.

## Reproducible source checks

From the repo root:

```sh
python3 tests/run_dsp_tests.py --sanitize auto
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tools/ui-check/validate_panels.py
```

The standalone regression `tests/fm_voice_dsp_test.cpp` covers C4 and ±1 V/oct pitch, index-zero sine identity, nonzero FM timbre, 2 ms control convergence, invalid/non-finite parameters, sample-rate phase continuity, poly-lane independence, bounded output, exact reset replay, the high-frequency index ceiling and its selected-bin 21 kHz alias-power reduction. The HEADLESS Rack shim smoke and pinned real-Rack-header syntax check cover wrapper compatibility **only if actually executed**. Neither is a substitute for successful plugin linking, visual/browser inspection, a DAW save/reload, audio audition or CPU measurement.
