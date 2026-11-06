# Standalone DSP performance measurement

This source-only harness measures eight *original* MODULAR-SYNTH DSP engines:
MorphVCO, StateFilter, FMVoice, StereoEcho, FoldDrive, ClockedLFO and
ChanceHold, plus SlewGlide. It runs their actual
`plugins/ModularSynth/src/*.hpp` processing code, **without** Rack/Cardinal,
plugin wrappers, a DAW, audio drivers, UI, graph routing, or any host overhead.
Numbers here cannot establish a Cardinal plugin's CPU use or its audio-thread
deadline safety. There is no claim that the complete fork has built or passed
host validation.

## Run it

From the repository root, with a C++11 compiler:

```bash
c++ -std=gnu++11 -O3 -ffast-math -fno-finite-math-only \
  -Wall -Wextra -Werror tools/dsp-bench/main.cpp -o /tmp/modular-dsp-bench
/tmp/modular-dsp-bench --frames 32768 > /tmp/modular-dsp.csv
/tmp/modular-dsp-bench --frames 32768 --json > /tmp/modular-dsp.json

# Three fresh warm-state trials per scenario; report the median and dispersion:
/tmp/modular-dsp-bench --frames 32768 --repeats 3 --json > /tmp/modular-dsp-repeated.json

# Run the exact same binary/flags/workload on baseline and candidate commits:
python3 tools/dsp-bench/compare.py /tmp/baseline-dsp.json /tmp/candidate-dsp.json
python3 tools/dsp-bench/compare.py /tmp/baseline-dsp.json /tmp/candidate-dsp.json --json
```

The C++11 debug and production smoke tests, including 48 scenario records per
profile, run through:

```bash
python3 -B -m unittest tests/test_dsp_benchmark.py -v
python3 -B -m unittest tests/test_dsp_benchmark_compare.py -v
```

No dependency download, plugin SDK, test audio device, or host installation is
required. `--frames` accepts 256–1,000,000 frames **per voice**; each invocation
tests 48,000 and 96,000 Hz, with 1, 8, and 16 simultaneous voices. The default
produces 48 records (eight engines × two rates × three polyphony settings).
Use the same flags, compiler, system load, CPU governor, and core affinity when
comparing two code revisions; report all of these and repeat runs. Shared CI
VMs are noisy and unsuitable for absolute release-performance targets.
`--repeats` accepts 1–9; each repeat constructs **fresh** DSP objects and warms
their signal/ring states *before* timing. The default `--repeats 1` preserves
historical single-trial behavior with the expanded 48 scenario records. On repeated
runs, `elapsed_ms` and derived per-sample figures are based on the **median**
timed loop; min, nearest-rank 90th percentile and max reveal scheduling jitter.

## Method and columns

1. Construct all voices and preallocate StereoEcho delay rings **before**
   timing. The 16-voice echo includes approximately 23.4 MiB of ring storage.
2. Generate a fixed 1,024-sample two-harmonic input table outside timing.
   Process eight actual DSP cores with bounded, deterministic note/control
   settings (FM index/morph/low-pass cutoff, FoldDrive timbre, free and
   externally clocked LFO lanes, seeded ChanceHold probability and glide,
   and SlewGlide's alternating bipolar targets, continuously varying input,
   directional rise/fall times, changing rise/fall CV and per-voice offsets).
3. Warm each voice at the selected sample rate for 1/12 second, longer than
   the 55–73 ms echo setting, so the delay path is active during measurement.
   The measured stimulus/control timeline continues after warmup rather than
   restarting at zero and injecting a fake boundary transient.
4. Time the **whole warm-state, per-frame/per-voice loop**, including the
   deterministic input lookup, accumulation of returned energy, and the finite
   check—not a standalone oscillator kernel stripped of its outputs.
5. Verify strictly positive finite mean output energy and **zero calls to
   C++ `new`/`new[]` inside the loop**. A violation exits nonzero.

| Column | Meaning |
| --- | --- |
| `engine` | Which first-party DSP core ran |
| `voices` | 1, 8, or 16 independent engine objects |
| `sample_rate_hz` | 48,000 or 96,000 samples/second |
| `frames` | Process calls per voice, excluding warmup |
| `elapsed_ms` | Host wall-clock elapsed time of measured loop |
| `ns_per_voice_sample` | Wall-clock nanoseconds divided by `frames × voices` |
| `realtime_factor` | `elapsed_seconds / (frames / sample_rate_hz)`; below one means the isolated loop ran faster than its audio duration on this machine |
| `mean_output_energy` | Deterministic average squared outputs; sanity signal, not audio quality |
| `cpp_new_calls` | C++ `new`/`new[]` calls while timing was active |
| `prepared_bytes_hint` | `sizeof(DSP object) + declared echo ring bytes`, per voice; excludes allocator metadata, libraries and host |
| `prepared_cpp_new_bytes` | Exact requested byte sizes intercepted by global C++ `new`/`new[]` during fresh DSP object construction (separate from the timed loop); excludes direct `malloc`, allocator overhead, shared libraries and RSS |
| `repetitions` | Independent construction/warmup/timing repetitions for one scenario (1–9) |
| `min_elapsed_ms` | Minimum observed loop wall time, including stimulus/check overhead |
| `p90_elapsed_ms` | Nearest-rank 90th-percentile observed loop time, not a realtime deadline guarantee |
| `max_elapsed_ms` | Maximum observed loop wall time; a scheduling-outlier indicator |

## Compare two source revisions conservatively

`tools/dsp-bench/compare.py` validates both JSON captures before comparing
them: exactly one record for each of the 48 engine/polyphony/rate scenarios,
matching measured frame counts, finite positive timings/energy, zero C++
sample-loop allocations, valid quantiles and nonduplicated JSON properties.
It rejects malformed, truncated or inconsistent input with exit code 2 and
does not silently compare mismatched workloads. Previously captured **24-**
and **42-scenario** JSON are still accepted and labelled `legacy-24` and
`extended-42` respectively. The new eight-engine profile is `extended-48`.
Comparison is permitted *within* any of these three exact, complete profiles,
but **never across profiles**—including 24↔42, 24↔48 and 42↔48, in either
direction. Incomplete/hybrid 42- or 48-row inventories are rejected rather
than guessed into a known profile. Legacy single-trial JSON without dispersion
fields is accepted as one low-information capture. To compare against a
42-row pre-SlewGlide revision, rerun both source revisions using the same
benchmark workload or backport the eighth scenario; the comparator will not
manufacture or extrapolate missing SlewGlide timings.

The report includes per-scenario elapsed nanoseconds per voice sample,
observed speedup/slowdown, energy ratio and preparation heap-byte difference,
plus the *equal-scenario-weight geometric mean* of timing ratios. An interval
label of `nonoverlap-faster`, `nonoverlap-slower` or `overlapping-ranges` only
describes the observed min/max trial ranges; it is **not** a confidence interval
or statistical significance claim. A different machine, process priority,
compiler or driver can invalidate a time comparison. **No performance
regression threshold is enforced by this tool or CI**; use repeated controlled
capture, not a single noisy CI VM, to investigate a candidate regression.

This harness counts only C++ `new` and `new[]`, **not** direct `malloc`, custom
allocators, page faults, driver buffers, host allocations, or UI/memory activity.
In particular, a `cpp_new_calls=0` result does not prove a plugin's callback
has no allocations. The `realtime_factor` includes the signal/measurement
logic and varies with CPU, frequency scaling, thermal state, OS scheduling,
compiler, vectorization, cache effects and other processes. Do not use it as
a fixed CI pass/fail threshold, a DAW CPU percentage or a minimum hardware
promise.
Similarly, `prepared_cpp_new_bytes` is a count of requested construction
allocations, **not peak resident memory**, malloc arena size or total plugin
memory pressure. The construction byte count can guide a source-voice memory
audit, but real process high-water marks require platform profilers and a
linked host. The benchmark still has **no audio device or real-time callback**.

## Next acceptance steps

The harness is suitable for **trend investigation**, e.g. measuring before/
after the same DSP change on the same host under controlled load. Product
readiness additionally requires a genuinely built Cardinal plugin/standalone,
loaded project tests in representative DAWs, MIDI/control automation, save/
reopen roundtrips, 1/8/16-voice CPU profiling on the actual host audio thread,
buffer-deadline/underrun measurements at 64/128/256 samples and human audition
of representative patches. None of those is performed by this tool.
