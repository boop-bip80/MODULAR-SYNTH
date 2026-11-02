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

**Wet mix, feedback and stereo crossfeed** now use independent bounded one-pole automation slews, each reaching about **99.9% of the new setting within 10 ms** at the host sample rate. This limits abrupt changes in the audible dry/wet balance and the stereo feedback matrix. The first process call after construction, a reset or a host sample-rate switch adopts its requested control settings immediately; unchanged saved patches therefore begin at their set values, not a previous value. The feedback state always remains between 0 and 90% while slewing. This is *parameter smoothing*, not a click-free guarantee for arbitrary audio transients or a pitch-preserving delay algorithm. Rapid MIDI/CV modulation of those controls is intentionally filtered by the 10 ms time constant.

Changing the host sample rate discards old delay history and recalculates milliseconds at the new rate. DSP reset performs an **O(1) logical history invalidation** rather than clearing megabytes in the audio callback. Invalid, NaN or extreme sample rates cause silence and a safe reset. Rates from 1 kHz through 384 kHz are accepted; the full 1000 ms delay range is available **through 192 kHz**, while at 384 kHz the maximum *effective* delay is **500 ms** due to the fixed buffer capacity. The panel knob still displays its nominal millisecond setting, so consider this limitation if your host runs above 192 kHz.

## Feedback and signal safety

The feedback matrix blends each channel's own delayed sample with the opposite delayed sample. Both matrix rows sum to one; combining that with capped feedback ≤0.90 ensures the **linear loop is contractive**, even at 100% ping-pong. Incoming signals are sanitized to ±20 V, stored ring samples are bounded to ±20 V, and the final outputs to ±10 V. All non-finite values are tested by IEEE-754 bit inspection, which remains effective under **strict -ffast-math**.

The internal hard voltage bound is a safety limit, **not** a model of an analog saturation circuit. If intentionally driven into that bound, hard clipping can introduce distortion and aliasing. For clean echo trails, use ordinary ±5 V levels and moderate feedback.

### Feedback tail extinction and denormal safety

The feedback rings now write **exact zero** whenever the *sanitized internal sample* has magnitude below **1×10⁻²⁰ V** (−400 dB relative to 1 V). This is many orders of magnitude below any meaningful audio signal and is applied before floating-point narrowing; normal-level signals are unchanged.

Why: at 90% feedback, repeated multiplication of the very smallest IEEE-754 float can round back to that same subnormal value, trapping a microscopic feedback pulse indefinitely. A pre-fix standalone probe (48 kHz, 1 ms, 90% feedback, fully wet, single 4 V impulse, five seconds) observed **4,156 subnormal output frames** and a repeated **5.60519386×10⁻⁴⁵ V** echo at repeats 1,000 through 5,000. In the fixed DSP, the identical regression observed **zero subnormals** and the last nonzero sample at **frame 21,648** (0.451 seconds); all later feedback samples were exactly zero. The tiny threshold avoids denormal processing in the feedback path. The same inaudibly low **1×10⁻²⁰ V** (−400 dB) threshold now also applies to the incoming dry signal **before audio arithmetic** and the final mixed output, preventing microscopic dry-path inputs or wet/dry cancellation residuals from reaching the host as subnormal floats. Unlike an ordinary noise gate, this does not track amplitude, create envelopes, or affect practical audio levels; test signals at 1×10⁻¹² V pass unchanged within float rounding. This is a deliberate ultra-low-level truncation, not bit-perfect transparency below the floor, and **no host CPU improvement has been measured**.

## Exact memory and CPU implications

Stereo Echo reserves all delay memory **once when the module is constructed**. Its pure DSP process and reset paths do not allocate, lock, resize a vector, clear a large buffer, call a file API, or wait for another thread.

- Each lane has two float rings of **192,002 frames**.
- Memory per stereo voice: **1,536,016 bytes** (approximately **1.465 MiB**).
- 16-lane maximum: **24,576,256 bytes**, approximately **23.44 MiB**, *plus small C++ objects, vector metadata, and Rack UI memory*.
- This memory is reserved even when using just one mono/stereo pair. Several Stereo Echo instances can meaningfully increase host RAM consumption.
- Each active lane/sample performs four interpolated-history ring reads, two sample writes, feedback/dry-wet arithmetic and finite bounds. Cost scales as **O(active polyphonic lanes × sample rate)**; the exponential smoothing coefficient is recalculated only when sample rate changes.

An earlier isolated x86-64 GCC 13.3 C++17 -O3 -ffast-math *pre-denormal-floor* benchmark exercising 16 lanes for one simulated second measured:

| Sample rate | Voice sample updates | Measured total CPU time | Approx. ns / voice update |
| --- | ---: | ---: | ---: |
| 48 kHz | 768,000 | 15.5 ms | 20.2 ns |
| 96 kHz | 1,536,000 | 29.7 ms | 19.3 ns |
| 192 kHz | 3,072,000 | 51.7 ms | 16.8 ns |

These historical values describe the pre-floor code, **not a post-fix speed comparison**. They are only standalone hot-loop numbers; they exclude Rack graph scheduling, UI, other modules, cache contention and DAW buffer deadlines.

A separate **post-fix deterministic stress run** executed **16,800,000 lane updates** across 44.1/48/96/192/384 kHz, with per-sample randomized stereo audio, bounded/unbounded CV, repeated full-ring wraps, rate changes, finite guards, bitwise hashing and reference-lane comparisons. On the current executor (2026-11-01), this took about **1.9 s at -O2**, **1.5 s with production optimization**, and **1.5 s under aggressive -ffast-math**. Its elapsed times include the pseudorandom generator and validation work and are **not** a pure DSP throughput benchmark. Hashes vary between compiler profiles; deterministic bitwise replay is required only within the same executable.

The standalone allocation probe intercepts C++ `new`/`new[]` and observed **zero calls** while processing, resetting and switching rates, after the voice rings were constructed. This does **not** instrument arbitrary C `malloc` calls or the Rack wrapper. There is no measured host realtime CPU percentage or deadline guarantee.

## DSP regression

~~~sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
  tests/stereo_echo_dsp_test.cpp -o /tmp/stereo-echo-test
/tmp/stereo-echo-test

# Deterministic 16-lane long-run, rate/CV, denormal and allocation stress:
c++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
  tests/stereo_echo_stress_dsp_test.cpp -o /tmp/stereo-echo-stress
/tmp/stereo-echo-stress

# CI auto-discovers both tests (strict O2, production and aggressive fastmath):
python3 tests/run_dsp_tests.py

# Optional sanitizer run; disable LeakSanitizer only if /proc is restricted:
c++ -std=c++17 -O1 -g -fno-omit-frame-pointer \
  -fsanitize=address,undefined -fno-sanitize-recover=all \
  tests/stereo_echo_stress_dsp_test.cpp -o /tmp/stereo-echo-stress-sanitized
ASAN_OPTIONS=detect_leaks=0 /tmp/stereo-echo-stress-sanitized
~~~

The standalone tests cover:

- Exact left/right impulse timing at 44.1/48/96/192 kHz, no early or extra echoes.
- 48.5-sample fractional-delay interpolation over precisely two adjacent samples.
- Dry, 50% mix and fully wet behavior; 50% ping-pong feedback decay across four echoes.
- 25 ms delay-time smoothing, history invalidation across host sample-rate changes, and 16 independent lane states.
- 10 ms feedback/wet/crossfeed control smoothing, reset/sample-rate initialization and a bounded first-sample wet automation transient.
- Fixed ring-memory bounds and an impulse arriving at exactly 192,000 history samples at both 192/384 kHz, 384 kHz reduced maximum time, extreme CV/audio values, NaN/Inf sanitation under strict fast-math and recovery after invalid rates.
- Deterministic 16-lane stress for **210,000 frames at each of 44.1/48/96/192/384 kHz** (16.8 million lane updates), including repeated ring wraps, rapid delay-time sweeps, non-finite controls, output ±10 V bounds and bitwise independent replay of lane 0.
- Quantitative 25 ms time-slew settling at 48/192/384 kHz, sample-rate history invalidation including 44.1 kHz fractional taps, 384 kHz 500 ms maximum, invalid-rate recovery and no C++ allocations in process/reset.
- Five-second impulse feedback decay at 90% and 1 ms, including exact tail extinction after 21,648 frames and zero subnormal samples under strict and aggressive compiler modes.
- Dry-path subnormal and tiny normal input rejection, output cancellation-residue floor, exact zero output under sustained microscopic input across wet settings, and preservation of ordinary low-level signals under strict/fast-math profiles.

**Actually executed (2026-11-01):** The repository's **8 standalone DSP tests × 3 compiler profiles (24 executions) passed** including the new StereoEcho long-run stress. The new test also compiled and ran with `-O2 -pedantic -Wall -Wextra -Werror` and combined AddressSanitizer/UndefinedBehaviorSanitizer, with LeakSanitizer disabled only because this sandbox denies /proc inspection. Baseline tests, strict `-O3 -ffast-math` and production `-fno-finite-math-only` all passed. The Rack plugin wrapper has **not** been successfully built or auditioned inside Cardinal.

## Exact module indices and suggested factory routing

The Rack enums are contiguous and begin at zero; these numeric values are important for a factory patch JSON/VCV cable:

| Type | Enum name | Index |
| --- | --- | ---: |
| Param | TIME_PARAM | 0 |
| Param | FEEDBACK_PARAM | 1 |
| Param | MIX_PARAM | 2 |
| Param | CROSSFEED_PARAM | 3 |
| Input | LEFT_INPUT | 0 |
| Input | RIGHT_INPUT | 1 |
| Input | TIME_CV_INPUT | 2 |
| Input | FEEDBACK_CV_INPUT | 3 |
| Input | MIX_CV_INPUT | 4 |
| Output | LEFT_OUTPUT | 0 |
| Output | RIGHT_OUTPUT | 1 |

The plugin slug is ModularSynth, module slug StereoEcho. The shipped `MODULAR_-_Stereo_Echo_Showcase.vcv` stereo example saves these signal routes:

1. HostMIDI pitch (output 0) → MorphVCO pitch (input 0); HostMIDI gate (output 1) → Fundamental ADSR gate (input 4).
2. MorphVCO MORPH_OUTPUT (0) → Fundamental VCA-1 audio (input 1); ADSR envelope (output 0) → VCA-1 CV (input 0); VCA-1 audio (output 0) → StateFilter AUDIO_INPUT (0).
3. StateFilter LOWPASS_OUTPUT (0) → StereoEcho LEFT_INPUT (0); StateFilter HIGHPASS_OUTPUT (2) → StereoEcho RIGHT_INPUT (1).
4. StereoEcho LEFT_OUTPUT (0) / RIGHT_OUTPUT (1) → HostAudio2 inputs 0 / 1.

The saved LP/HP split routes nominally different filter outputs to the two delay inputs, so the source graph provides distinct signals for crossfeed processing; **the resulting stereo image has not been auditioned in a fork-built host**. **Important:** leaving RIGHT_INPUT unpatched normals it to LEFT_INPUT, which is convenient dual-mono routing but produces identical left/right histories. With two identical channels, ping-pong crossfeed alone cannot create stereo width. For classic L-only alternating echoes, patch a zero-volt source into RIGHT_INPUT instead.

## Integration status and remaining host checks

StereoEcho is registered in the first-party plugin header, Cardinal's static plugin loader and Makefile source list, and the ModularSynth manifest. The original `StereoEcho.svg` panel is part of the resource glob; the `MODULAR_-_Stereo_Echo_Showcase.vcv` factory example wires StateFilter low/high-pass outputs to distinct StereoEcho channels and both delay outputs to HostAudio2. Source-backed registration, panel geometry/contrast and saved factory routing checks run in Python.

**Still required before a release-ready claim:** the complete Cardinal plugin build (including headless target), an actual host instance loading the module and factory patch, parameter serialization/restore in Rack and audible evaluation of latency, time sweeps and stereo feedback.

**Not established:** real host CPU usage, transport/BPM synchronization (not implemented), phase-coherent tempo changes, plugin panel correctness in all targets, automation behavior in a DAW, or subjective sound quality.
