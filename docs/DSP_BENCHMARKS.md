# Standalone DSP performance measurement

This source-only harness measures four *original* MODULAR-SYNTH DSP engines:
MorphVCO, StateFilter, FMVoice, and StereoEcho. It runs their actual
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
```

The C++11 debug and production smoke tests, including 24 scenario records per
profile, run through:

```bash
python3 -B -m unittest tests/test_dsp_benchmark.py -v
```

No dependency download, plugin SDK, test audio device, or host installation is
required. `--frames` accepts 256–1,000,000 frames **per voice**; each invocation
tests 48,000 and 96,000 Hz, with 1, 8, and 16 simultaneous voices. The default
produces 24 records (four engines × two rates × three polyphony settings).
Use the same flags, compiler, system load, CPU governor, and core affinity when
comparing two code revisions; report all of these and repeat runs. Shared CI
VMs are noisy and unsuitable for absolute release-performance targets.

## Method and columns

1. Construct all voices and preallocate StereoEcho delay rings **before**
   timing. The 16-voice echo includes approximately 23.4 MiB of ring storage.
2. Generate a fixed 1,024-sample two-harmonic input table outside timing.
   Process the four actual DSP cores with bounded, deterministic note/control
   settings (FM index/morph/low-pass cutoff exercise automation).
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

This harness counts only C++ `new` and `new[]`, **not** direct `malloc`, custom
allocators, page faults, driver buffers, host allocations, or UI/memory activity.
In particular, a `cpp_new_calls=0` result does not prove a plugin's callback
has no allocations. The `realtime_factor` includes the signal/measurement
logic and varies with CPU, frequency scaling, thermal state, OS scheduling,
compiler, vectorization, cache effects and other processes. Do not use it as
a fixed CI pass/fail threshold, a DAW CPU percentage or a minimum hardware
promise.

## Next acceptance steps

The harness is suitable for **trend investigation**, e.g. measuring before/
after the same DSP change on the same host under controlled load. Product
readiness additionally requires a genuinely built Cardinal plugin/standalone,
loaded project tests in representative DAWs, MIDI/control automation, save/
reopen roundtrips, 1/8/16-voice CPU profiling on the actual host audio thread,
buffer-deadline/underrun measurements at 64/128/256 samples and human audition
of representative patches. None of those is performed by this tool.
