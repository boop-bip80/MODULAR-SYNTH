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

Values after CV addition are clamped to their documented ranges. Index, ratio and feedback changes are smoothed for about 2 ms; patch startup adopts saved values immediately. All four CV inputs can carry 16 independent Rack polyphony lanes; mono CV is shared across connected polyphonic voices. Retired lanes reset phase and control histories before re-expansion.

Try `Host MIDI pitch → FM Voice 1V/OCT`, `FM OUT → envelope-controlled VCA → Host Audio`. At ratio 2, index 2–3 radians and low feedback, the voice produces bell-like harmonic sidebands; sweep INDEX with a slow LFO for moving timbres. An ADSR/VCA is necessary if you want note envelopes.

## DSP, stability and limitations

The actual signal equations are:

```text
m[n] = sin(2*pi*p_mod[n] + feedback*m[n-1])
y[n] = sin(2*pi*p_carrier[n] + index*m[n])
```

The carrier and modulator phase accumulators wrap in [0,1). The individual frequency steps clamp at 45% of sample rate, and both sine outputs are bounded to unit amplitude before the Rack ±5 V scaling. Non-finite controls are sanitized using IEEE-754 bit checks that also work under aggressive `-ffast-math`; invalid sample rates produce silence. The DSP processing loop allocates no memory, takes no locks and does not touch GUI/disk/network resources.

**Aliasing limitation:** FM/phase-modulation sidebands and self-feedback are **not bandlimited**; high ratios, indices and feedback can alias severely even when each underlying oscillator is below Nyquist. This implementation intentionally does not claim oversampling or professional anti-aliasing. Listen and measure before using extreme settings in a release.

A running oscillator preserves phase when sample rate changes. Rack reset zeroes phase and feedback memory. No inter-lane voice allocator, oversampling, through-zero frequency, detuning matrix, MIDI velocity mapping, automatic envelopes or host performance benchmarks are implemented.

## Reproducible source checks

From the repo root:

```sh
python3 tests/run_dsp_tests.py --sanitize auto
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tools/ui-check/validate_panels.py
```

The standalone regression `tests/fm_voice_dsp_test.cpp` covers C4 and ±1 V/oct pitch, index-zero sine identity, nonzero FM timbre, 2 ms control convergence, invalid/non-finite parameters, sample-rate phase continuity, poly-lane independence, bounded output and exact reset replay. The HEADLESS Rack shim smoke and pinned real-Rack-header syntax check cover wrapper compatibility **only if actually executed**. Neither is a substitute for successful plugin linking, visual/browser inspection, a DAW save/reload, audio audition or CPU measurement.
