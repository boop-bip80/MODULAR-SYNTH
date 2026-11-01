# StateFilter CV modulation and stability stress regression

This standalone C++17 suite executes **the real `StateFilter.hpp` core** during rapidly changing control values. It complements the static frequency-response matrix under `tools/filter-analysis/` and the original `tests/statefilter_dsp_test.cpp`; it does not require Rack or Cardinal.

## What the regression measures

| Scenario | Actual check |
| --- | --- |
| Rapid polyphonic CV | 16 independent filter cores × 49,152 samples = **786,432 process calls**, cycling 44.1 → 96 → 48 kHz every 4,096 frames |
| Hostile control inputs | Randomized cutoff/resonance/drive CV on **every sample**; periodic very large positive/negative CV, NaN, ±Infinity, and extreme audio voltages |
| Bounded output | All LP/BP/HP samples must be IEEE-finite and within **±10.0001 V** (the core clips to ±10 V) |
| Sample-rate reset | Sixteen previously active voices must match fresh-state outputs within **1 µV** on the first sample after each 44.1 → 96 → 48 → 44.1 kHz switch |
| Per-voice history | Voice 7 in a 16-voice bank is compared to a separate isolated core, and an impulse in voice 0 must leave 15 silent voices exactly silent |
| Quiet-input decay | After a DC stimulus and 30,000 silent samples at 48 kHz, the two integrator states must be flushed to **exactly zero** and continued output remain silent |
| Drive continuity | Per-sample drive automation through 0, 1e-7, 1e-6, 1e-5 and 1e-4 must deviate by **less than 0.001 V** from an otherwise identical drive=0 baseline |

The CV helper in this test explicitly duplicates the documented control conversion in `StateFilter.cpp`: 1 V/oct cutoff with limited exponent, and 10 V full span for resonance/drive. It then passes the computed parameters into the actual core. This tests numerical behavior under **CV-equivalent modulation**; it **does not directly execute the Rack host wrapper** or verify physical jacks and GUI.

The finite assertions use IEEE-754 exponent checks rather than `std::isfinite`, because GCC strict `-ffast-math` can assume all floating-point numbers are finite.

## Reproduce

From the repository root:

```sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
  tests/statefilter_modulation_dsp_test.cpp -o /tmp/statefilter-modulation
/tmp/statefilter-modulation

c++ -std=c++17 -O3 -ffast-math -Wall -Wextra -Werror -pedantic \
  tests/statefilter_modulation_dsp_test.cpp -o /tmp/statefilter-modulation-fast
/tmp/statefilter-modulation-fast

c++ -std=c++17 -O1 -g -ffast-math -fsanitize=address,undefined \
  -fno-omit-frame-pointer -Wall -Wextra -Werror -pedantic \
  tests/statefilter_modulation_dsp_test.cpp -o /tmp/statefilter-modulation-sanitized
ASAN_OPTIONS=detect_leaks=0 /tmp/statefilter-modulation-sanitized
```

The test exits nonzero for any failed assertion and prints rate, voice, and frame when available.

## Interpretation and limitations

Finite bounded output is a **numerical-safety** property, not a guarantee of click-free sound under hard modulation. The filter deliberately recomputes coefficients per sample and does not smooth abrupt frequency/resonance changes; fast CV can sound rough. Input saturation has no oversampling, so this test does not establish alias suppression or analog fidelity. This is not a CPU benchmark, long-term hardware soak, host/plugin integration test, or validation of audio-thread deadlines.

Additional DSP core tests and actual listening tests are still valuable. The reproducible commands above describe executable assertions; see PR checks and execution logs for the toolchain-specific pass evidence.
