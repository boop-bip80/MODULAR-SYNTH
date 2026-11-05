# FM Voice — original two-operator phase-modulation source

Status: original first-party C++ DSP and a statically registered Rack model. This is **not** a claim of a completed Cardinal/DAW build, host audition, or released instrument.

## What it does

**FM Voice** provides a 16-lane polyphonic two-operator, sine-based **phase-modulation** voice: a sine modulator bends the instantaneous phase of a sine carrier. A signed one-sample feedback control switches between the original modulator loop and a new carrier loop without changing saved port/parameter IDs. Here "FM" is the common synthesizer shorthand; mathematically this is phase modulation, and there are no envelopes, presets, or DX7 algorithms in the module itself.

| Control/jack | Behavior |
| --- | --- |
| OCTAVE | Snapped −4 to +4 octaves |
| FINE | −100 to +100 cents |
| RATIO | Modulator/carrier frequency ratio 0.125…16, initial 1 |
| INDEX | Modulation depth, 0…8 radians, initial 0 |
| FEEDBACK | Signed feedback, −95…+95%, initial 0; negative = carrier loop, positive = original modulator loop |
| 1V/OCT input | Standard C4 at 0 V, +1 V doubles pitch |
| RATIO CV | +1 V doubles the modulator ratio, −1 V halves it |
| INDEX CV | +1 V adds 0.8 radians to index |
| FDBK CV | +1 V adds +9.5 percentage points; −1 V adds −9.5 points, within ±95% |
| FM OUT | Phase-modulated carrier, nominal ±5 V |
| MOD OUT | Modulator sine, with self-feedback only for positive FEEDBACK; nominal ±5 V |

Signed FEEDBACK values select *different one-sample loops*, not subtraction of modulator feedback. Example: −50% places 0.5× the previous carrier sample into the carrier phase; +50% places 0.5× the previous modulator sample into the modulator phase; 0% disables both paths. At INDEX=0, negative carrier feedback adds harmonics, whereas positive modulator feedback leaves the carrier a pure sine. Positive saved feedback values (0…95%) and the original +0.095 per volt CV scale retain their original numerical meaning. The Rack knob descriptor and FDBK CV input tooltip are deliberately unchanged to preserve instrument-builder v2 contract metadata, although the knob now supports negative values.

Values after CV addition are clamped to their documented ranges. At high pitches/ratios, the effective carrier phase-modulation index is also reduced by the bandwidth guard described below; the knob and saved value do not change. High-pitch **one-sample self-feedback** additionally tapers toward zero before the feedback oscillator's second harmonic reaches the 45%-sample-rate guard band. Index, ratio and feedback changes are smoothed for about 2 ms; **the separate index-guard ceiling drops immediately when a pitch increase demands a narrower bandwidth and recovers over roughly 2 ms when more bandwidth is available**. Pitch-triggered feedback attenuation also applies on the first new sample, even when the existing 2 ms feedback CV smoothing has not converged. Patch startup adopts saved values immediately. All four CV inputs can carry 16 independent Rack polyphony lanes; mono CV is shared across connected polyphonic voices. Retired lanes reset phase and control histories before re-expansion.

Try `Host MIDI pitch → FM Voice 1V/OCT`, `FM OUT → envelope-controlled VCA → Host Audio`. At ratio 2, index 2–3 radians and low feedback, the voice produces bell-like harmonic sidebands; sweep INDEX with a slow LFO for moving timbres. An ADSR/VCA is necessary if you want note envelopes.

## DSP, stability and limitations

The actual signal equations are:

```text
feedback_taper(f) = 1 for f <= 0.16*sample_rate
feedback_taper(f) = smoothstep decrease to 0 over 0.16...0.225*sample_rate
feedback_taper(f) = 0 for f >= 0.225*sample_rate
positive_feedback = max(0, smoothed_feedback) * feedback_taper(modulator_frequency)
negative_feedback = max(0, -smoothed_feedback) * feedback_taper(carrier_frequency)
m[n] = sin(2*pi*p_mod[n] + positive_feedback*m[n-1])
y[n] = sin(2*pi*p_carrier[n] + effective_index*m[n]
           + negative_feedback*y[n-1])
```

Feedback is bounded to ±0.95 before a 2 ms smoothing stage (including sign changes). Each feedback recurrence uses the preceding output sample for its own oscillator, never a separate delay or per-block allocation. Both feedback histories clear on reset or when a polyphonic lane is retired. Abrupt carrier pitch changes or a strong feedback CV step may still sound transient; the sign routing itself is continuous at zero, but no click-free guarantee is made.

The carrier and modulator phase accumulators wrap in [0,1). The individual frequency steps clamp at 45% of sample rate, and both sine outputs are bounded to unit amplitude before the Rack ±5 V scaling. Non-finite controls are sanitized using IEEE-754 bit checks that also work under aggressive `-ffast-math`; invalid sample rates produce silence. Direct-DSP frequencies below `1e-12` Hz are treated as zero phase increment to avoid pathological subnormal phase arithmetic; this is far below the minimum frequency reachable through the module's clamped Rack pitch input, so normal musical output is unchanged. Oscillator phase is frozen, not reset, until frequency recovers. The DSP processing loop allocates no memory, takes no locks and does not touch GUI/disk/network resources.

**Aliasing limitation:** FM/phase-modulation sidebands and self-feedback are **not completely bandlimited**. There is no oversampling or full anti-aliasing solution. The index ceiling reduces selected upper FM sidebands and the feedback taper attenuates selected folded self-feedback harmonics, but higher-order harmonics and audio/CV transients can still alias. The feedback taper also intentionally makes very high notes with extreme feedback less bright. Listen and measure before using extreme settings in a release.

### High-frequency sideband guard

For a sinusoidal modulator without feedback, significant PM sidebands extend roughly to carrier frequency plus `(index + 1) × modulator frequency` (a Carson-style bandwidth estimate). The DSP limits the **effective** index as follows:

```text
guard_hz = 0.45 * sample_rate_hz
target_ceiling = clamp((guard_hz - carrier_hz) / modulator_hz - 1, 0, 8)
if target_ceiling < current_ceiling:
    current_ceiling = target_ceiling  # immediate anti-alias safety reduction
else:
    current_ceiling = one_pole_2ms(current_ceiling, target_ceiling)
effective_index = min(smoothed_index, current_ceiling)
```

When modulator frequency is zero, the index is not restricted. For extremely small but positive modulator frequencies the calculation saturates to the full 8-radian ceiling *before* division, preventing floating-point overflow from incorrectly yielding zero index. The guard adopts a tighter ceiling on the **first** high-note sample, preventing the previous 2 ms of excessive phase modulation at the new pitch. When pitch decreases, its ceiling only *rises* through a roughly 2 ms one-pole release. A sudden downward timbre step is possible when moving to a much higher note; this does **not** prevent clicks from the pitch jump, feedback aliases or higher-order sidebands. Individual operator frequency steps remain capped at 45% of sample rate; their ratio product is computed without intermediate floating-point overflow even for extreme finite inputs. At lower pitches/ratios the ceiling stays above 8 radians and changes nothing. At high pitch, the same saved INDEX knob setting may sound less bright because the DSP attenuates high-order sidebands.

**Controlled tests, not a blanket claim:** With 3 kHz carrier, 12 kHz sine modulator (ratio 4), index 3 and 48 kHz sampling, the 27 kHz second upper sideband folds into the 21 kHz bin. A 4,800-sample coherent DFT measures that specific bin at ~0.995 normalized amplitude in the former unrestricted equation versus ~0.0737 with the guard — **22.6 dB lower**. A second coherent 6 kHz carrier/12 kHz modulator case reduces its folded 18 kHz bin by ~17.35 dB. In the **first 96 samples (2 ms) after an abrupt 440→3000 Hz jump at ratio 4**, a separate coherent DFT compares the previous symmetric-slew guard with the immediate-downward guard: the folded 21 kHz bin drops from ~0.995 to ~0.0737 normalized amplitude, **22.6 dB lower for this selected transient**. The standalone test also checks that 440 Hz carrier/880 Hz modulator at index 8 remains unchanged, that high-note CV changes immediately cap the index while phase is retained, and that low-note recovery restores brightness gradually. The estimate does **not** bound every higher Bessel sideband, self-feedback harmonic or transient; no multiband spectral or DAW guarantee is made.

### Feedback harmonic guard and multi-rate spectral matrix

One-sample negative feedback shapes the **carrier** sine and positive feedback shapes the **modulator** sine. Neither path is protected by the PM index ceiling at INDEX=0. For each actual oscillator frequency `f`, the feedback multiplier stays exactly 1 through `0.16 × sample_rate`, smoothly decreases to zero between `0.16` and `0.225 × sample_rate`, and remains zero above `0.225 × sample_rate`. Thus the second harmonic is suppressed before it exceeds the earlier 45%-of-sample-rate guard band. The same frequency-dependent taper applies from the **first** frame of an upward pitch step. Original low-note recurrence, knob/CV range, saved parameter IDs and bipolar feedback semantics are unchanged. This is a timbral tradeoff, not a claim that third and higher harmonics are always guarded.

The new offline `tests/fm_voice_spectral_matrix_dsp_test.cpp` separately analyzes **16 coherent PM fold cases** (four normalized frequency/ratio scenes × 44.1/48/96/192 kHz). Their selected folded bins are reduced by at least **17.35 dB** against the original unguarded sine-PM equation. It also measures **eight feedback fold cases** (positive and negative 0.95 one-sample loops × the same sample rates): at normalized oscillator frequency `0.3125 × sample_rate`, the old second harmonic folded from `0.625` into `0.375 × sample_rate` at ~0.313 amplitude; the new high-note sine has negligible energy in that distinct bin, exceeding a **33 dB** tested attenuation threshold. Reported values are capped at **60 dB** near the coherent-DFT numerical floor, rather than presenting numerical cancellation as a physically meaningful 200+ dB filter. Additional first-frame pitch-jump, deterministic six-stage CV/envelope stress over 16 lanes and fade-continuity checks pass without any host GUI or DAW signal. **These are isolated selected-bin experiments, not alias-band integral or user-perceived sound-quality scores.**

A running oscillator preserves phase when sample rate changes. Rack reset zeroes phase and feedback memory. No inter-lane voice allocator, oversampling, through-zero frequency, detuning matrix, MIDI velocity mapping, automatic envelopes or host performance benchmarks are implemented.

## Reproducible source checks

From the repo root:

```sh
python3 tests/run_dsp_tests.py --sanitize auto
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tools/ui-check/validate_panels.py
```

The standalone regression `tests/fm_voice_dsp_test.cpp` covers C4 and ±1 V/oct pitch, index-zero sine identity, nonzero FM timbre, 2 ms control convergence, invalid/non-finite parameters, sample-rate phase continuity, poly-lane independence, bounded output, exact reset replay, the high-frequency index ceiling and its selected-bin 21 kHz alias-power reduction, legacy positive-feedback recurrence, signed topologies, measured second harmonic, sign-crossing slew/continuity and independent 16-lane reset replay. `tests/fm_voice_spectral_matrix_dsp_test.cpp` adds the independent four-sample-rate coherent fold comparison, high-pitch positive/negative feedback alias taper, first-frame CV jump and finite 16-voice envelope/CV stages. Additional boundary and event-stress regressions cover subnormal direct-DSP frequencies, overflow-safe small-modulator guards, sample-rate changes, CV extremes and deterministic 16-lane replay. The HEADLESS Rack shim smoke and pinned real-Rack-header syntax check cover wrapper compatibility **only if actually executed**. Neither is a substitute for successful plugin linking, visual/browser inspection, a DAW save/reload, audio audition or CPU measurement.
