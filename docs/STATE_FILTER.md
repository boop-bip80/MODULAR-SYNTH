# State Filter — original multimode filter (development)

The **State Filter** is a new first-party MODULAR-SYNTH module. It uses an entirely digital **trapezoidal-integrator (TPT) state-variable filter** core, with simultaneously available low-pass, band-pass, and high-pass outputs. This is **not** a transistor-level or circuit-accurate clone of any specific analog filter.

## Controls and patching

| Control / jack | Behavior |
| --- | --- |
| Cutoff | Log-frequency knob, 20 Hz–20 kHz nominal, centered at 1 kHz |
| Cutoff CV | 1 V/octave; adds to the cutoff knob |
| Resonance | 0–1 knob mapped nonlinearly to Q ≈ 0.5–12 |
| Resonance CV | Bipolar, 10 V for the full control span; combines with the knob |
| Drive | Bounded input tanh saturation; drive 0 bypasses nonlinear processing |
| Drive CV | Bipolar, 10 V for the full control span |
| Input | Audio-rate signal (5 V normalized to internal unit amplitude) |
| LP / BP / HP | Parallel low-, band-, and high-pass outputs |

Up to **16 independent channels** are processed, following Rack's polyphonic-jack convention. A polyphonic modulation source can increase the channel count even when audio input is mono.

### Technical safety behavior

- Pure DSP code in `plugins/ModularSynth/src/StateFilter.hpp` can be compiled without Rack or plugin host dependencies.
- The cutoff is limited to the lesser of 20 kHz or 45% of the current sample rate.
- Extreme controls and non-finite inputs are sanitized; outputs are bounded to ±10 V.
- Each active polyphonic lane carries independent integrator history; states are reset on Rack reset, host sample-rate changes and when a lane is retired by shrinking cable polyphony. Re-expanding a cable therefore cannot reactivate an old filter tail.
- State variables are bounded and tiny values flushed to zero to reduce denormal problems.
- No audio-thread locks or dynamic allocations are performed by the core.

### Current limitations

- The input drive uses a continuous dry/saturated crossfade near zero to prevent an abrupt gain jump.
- The cutoff/resonance coefficients are recomputed sample-by-sample, making audio-rate CV modulation possible but consuming CPU (one tangent per channel/sample).
- There is **no oversampling** or nonlinear zero-delay feedback; strong input drive can introduce aliasing.
- Coefficient modulation is not independently smoothed, so abrupt control movement can be audible.
- The high-resonance character is a digital SVF response, not an emulation of a commercial filter circuit.

## Static registration and host-build status

The integrated collection already declares `modelStateFilter` in
`plugins/ModularSynth/src/plugin.hpp`, registers it in
`plugins/plugins.cpp`, compiles `src/StateFilter.cpp` via `plugins/Makefile`,
and includes the SVG and manifest entry. Source registration tests inspect
these exact declarations. A successful **full Cardinal plugin build and live
host audition** are still outstanding and must not be inferred from that
static configuration.

## Reproducible DSP regression test

Compile from repository root:

```sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
  tests/statefilter_dsp_test.cpp -o /tmp/statefilter-core-test
/tmp/statefilter-core-test
```

The test exercises:
- Lowpass/highpass response for 100 Hz versus 8 kHz at a 500 Hz cutoff.
- DC steady-state and state reset.
- Non-finite/extreme inputs and controls at several sample rates.
- Recovery from invalid sample rates and sample-rate changes.
- Bounded nonlinear-drive effect.

**Executed in an isolated feature-branch checkout (2026-11-01):** GCC 13.3 optimized C++17 build with `-Wall -Wextra -Werror -pedantic` compiled and ran successfully (`StateFilter: all DSP regression tests passed`). An AddressSanitizer/UndefinedBehaviorSanitizer build also passed with leak detection disabled because LeakSanitizer could not inspect `/proc` in the sandbox. This is pure-core evidence, not proof of plugin integration.

**Not yet established:** full plugin-host integration, an audio-rate modulation listening test, host state restoration, CPU benchmarking, and cross-platform executable validation. These must be verified once this module is registered.
