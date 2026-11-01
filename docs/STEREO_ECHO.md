# Stereo Echo — original first-party effect (development)

**Stereo Echo** adds an original 16-lane polyphonic stereo delay to the MODULAR-SYNTH module family. Its audio engine is the standalone, GPL-3.0-or-later [StereoEchoDSP](../plugins/ModularSynth/src/StereoEcho.hpp), with two fractional-delay rings per voice, controllable cross-channel feedback, dry/wet mixing, and millisecond-accurate time at the current host sample rate.

It does **not** require a DAW timeline, BPM clock, transport state, or third-party delay library. Milliseconds are a direct time measurement, **not beat synchronization**.

## Controls and patches

| Panel control / port | Behavior |
| --- | --- |
| TIME | 1–1000 ms delay, default 250 ms; each voice follows the current host sample rate |
| FEEDBACK | 0–90% decay per echo, default 35%; never allowed above 0.90 internally |
| DRY / WET | 0–100% mixture of original and delayed stereo signal, default 40% |
| PING-PONG | 0% same-channel feedback, 100% fully alternate left/right, default 50% |
| IN L, IN R | Two audio inputs; when right is unpatched it uses the left signal |
| TIME CV | Bipolar, **+100 ms per 1 V** added to the knob, then safely bounded |
| FB CV | Bipolar, **+10 percentage points per 1 V** added to feedback, then bounded to 0–90% |
| MIX CV | Bipolar, **+10 percentage points per 1 V** added to wet mix, bounded to 0–100% |
| L OUT, R OUT | Stereo wet/dry outputs, bounded to ±10 V |

Up to **16 independent polyphonic stereo lanes** are supported. A polyphonic CV input can increase channel count even when audio input is mono. A retired lane is reset when the cable's polyphony decreases, so re-expanding it later does not resurrect a stale echo. For a fully wet ping-pong test: patch an impulse into IN L, leave IN R silent, set PING-PONG to 100%, FEEDBACK to 50%; successive echoes alternate L/R at amplitudes 1, 0.5, 0.25, 0.125.

### Time modulation and sample-rate changes

The delay read tap uses **linear interpolation** for fractional samples. Delay-time automation slews with a one-pole response that reaches about **99.9% of the new sample position in 25 ms**. This reduces abrupt zipper clicks but deliberate time sweeps can still pitch-bend and smear transients; there is no dual-head time-stretching or high-quality interpolation filter.

Changing the host sample rate discards old delay history and recalculates milliseconds at the new rate. DSP reset performs an **O(1) logical history invalidation** rather than clearing megabytes in the audio callback. Invalid, NaN or extreme sample rates cause silence and a safe reset. Rates from 1 kHz through 384 kHz are accepted; the full 1000 ms delay range is available **through 192 kHz**, while at 384 kHz the maximum *effective* delay is **500 ms** due to the fixed buffer capacity. The panel knob still displays its nominal millisecond setting, so consider this limitation if your host runs above 192 kHz.

## Feedback and signal safety

The feedback matrix blends each channel's own delayed sample with the opposite delayed sample. Both matrix rows sum to one; combining that with capped feedback ≤0.90 ensures the **linear loop is contractive**, even at 100% ping-pong. Incoming signals are sanitized to ±20 V, stored ring samples are bounded to ±20 V, and the final outputs to ±10 V. All non-finite values are tested by IEEE-754 bit inspection, which remains effective under **strict -ffast-math**.

The internal hard voltage bound is a safety limit, **not** a model of an analog saturation circuit. If intentionally driven into that bound, hard clipping can introduce distortion and aliasing. For clean echo trails, use ordinary ±5 V levels and moderate feedback.

## Exact memory and CPU implications

Stereo Echo reserves all delay memory **once when the module is constructed**. Its pure DSP process and reset paths do not allocate, lock, resize a vector, clear a large buffer, call a file API, or wait for another thread.

- Each lane has two float rings of **192,002 frames**.
- Memory per stereo voice: **1,536,016 bytes** (approximately **1.465 MiB**).
- 16-lane maximum: **24,576,256 bytes**, approximately **23.44 MiB**, *plus small C++ objects, vector metadata, and Rack UI memory*.
- This memory is reserved even when using just one mono/stereo pair. Several Stereo Echo instances can meaningfully increase host RAM consumption.
- Each active lane/sample performs four interpolated-history ring reads, two sample writes, feedback/dry-wet arithmetic and finite bounds. Cost scales as **O(active polyphonic lanes × sample rate)**; the exponential smoothing coefficient is recalculated only when sample rate changes.

An isolated x86-64 GCC 13.3 C++17 -O3 -ffast-math benchmark exercising 16 lanes for one simulated second measured:

| Sample rate | Voice sample updates | Measured total CPU time | Approx. ns / voice update |
| --- | ---: | ---: | ---: |
| 48 kHz | 768,000 | 15.5 ms | 20.2 ns |
| 96 kHz | 1,536,000 | 29.7 ms | 19.3 ns |
| 192 kHz | 3,072,000 | 51.7 ms | 16.8 ns |

This is **only a standalone hot-loop result in the current executor**; it excludes Rack graph scheduling, UI, other modules, cache contention, and actual DAW buffer deadlines. Do not interpret it as a tested plugin CPU percentage or realtime guarantee.

## DSP regression

~~~sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
  tests/stereo_echo_dsp_test.cpp -o /tmp/stereo-echo-test
/tmp/stereo-echo-test

# After integration, the repository CI runner auto-discovers this test:
python3 tests/run_dsp_tests.py
~~~

The standalone tests cover:

- Exact left/right impulse timing at 44.1/48/96/192 kHz, no early or extra echoes.
- 48.5-sample fractional-delay interpolation over precisely two adjacent samples.
- Dry, 50% mix and fully wet behavior; 50% ping-pong feedback decay across four echoes.
- 25 ms delay-time smoothing, history invalidation across host sample-rate changes, and 16 independent lane states.
- Fixed ring-memory bounds and an impulse arriving at exactly 192,000 history samples at both 192/384 kHz, 384 kHz reduced maximum time, extreme CV/audio values, NaN/Inf sanitation under strict fast-math and recovery after invalid rates.

**Actually executed (2026-11-01):** GCC 13.3 C++17 -O2 and -O3 -ffast-math/-fno-finite-math-only and strict -O3 -ffast-math compiled and ran the full core test successfully. AddressSanitizer/UndefinedBehaviorSanitizer also passed with LeakSanitizer disabled due sandbox /proc inspection restrictions. The Rack plugin wrapper has not been successfully built or auditioned inside Cardinal yet.

## Integration ownership

This feature branch adds only new, isolated files. The integrating maintainer should:

1. Add an extern for modelStereoEcho to the first-party plugin.hpp registry.
2. Register modelStereoEcho in the ModularSynth plugin initializer in plugins/plugins.cpp.
3. Add ModularSynth/src/StereoEcho.cpp to the source build list in plugins/Makefile and verify res/StereoEcho.svg is packaged.
4. Add a StereoEcho manifest entry in plugins/ModularSynth/plugin.json, with Delay and Polyphonic category tags according to the host's current schema.
5. Run the real Cardinal plugin build, headless build, UI/panel test, patch persistence test and an auditory host check before describing the module as release-ready.

**Not established:** real host CPU usage, transport/BPM synchronization (not implemented), phase-coherent tempo changes, plugin panel correctness in all targets, automation behavior in a DAW, or subjective sound quality.
