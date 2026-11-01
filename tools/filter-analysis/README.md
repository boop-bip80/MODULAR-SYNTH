# StateFilter headless response analyzer

This standalone C++17 test/CLI exercises the *real* `StateFilter.hpp` signal-processing core, independent of Rack, Cardinal, or an audio device. It compares sine-fitted LP/BP/HP output amplitudes against the transfer function of the **linear digital TPT state-variable filter**, across:

- Sample rates: **44.1, 48, 96 kHz**
- Cutoffs: **250, 1,600, 7,500 Hz**
- Resonance knobs: **0.1342, 0.58** (approximately Q=0.707 and Q=4.37)
- Test frequencies: **¼×, 1×, 2½× cutoff**
- Outputs: **LP, BP, HP**

This is a 3 × 3 × 2 × 3 × 3 = **162-case** transfer-response matrix. It runs a 0.25 V sine through the core with drive at zero, discards 16 startup cycles, then fits quadrature sine/cosine coefficients over 64 cycles to obtain output amplitude. The least-squares method is deliberately independent of an FFT library and works with noninteger samples per period.

## Build and run

From repository root:

```sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic tests/filter_response_dsp_test.cpp -o /tmp/filter-response-test
/tmp/filter-response-test

c++ -std=c++17 -O3 -ffast-math -Wall -Wextra -Werror -pedantic tests/filter_response_dsp_test.cpp -o /tmp/filter-response-fastmath
/tmp/filter-response-fastmath

c++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic tools/filter-analysis/main.cpp -o /tmp/filter-analysis
/tmp/filter-analysis --check
/tmp/filter-analysis --csv
/tmp/filter-analysis --bench
```

`--check` exits 0 only if every row passes. `--csv` prints measured/predicted gains and error for plotting. `--bench` times one million actual filter process calls with an accumulated checksum; **throughput is informational**, not a fixed CI performance gate.

## Mathematical expectation

The core computes `g = tan(π f_c / f_s)` and damping `k = 1 / Q`, where `Q = 0.5 + 11.5 r²` for normalized resonance knob `r`. For probe frequency `f`, the bilinear frequency ratio is:

```text
w = tan(π f / f_s) / tan(π f_c / f_s)
D = sqrt((1 - w²)² + (w / Q)²)
|LP| = 1 / D
|BP| = w / D
|HP| = w² / D
```

These predictions account for frequency warping at each sample rate rather than treating the cutoff as an unwarped analog pole. Error limits are **0.75 dB** for amplitudes at/above 0.025× and **0.015 absolute gain** below that threshold, where dB amplifies numerical noise. The code uses the filter's IEEE exponent-bit finite guard, so NaNs do not falsely pass under GCC `-ffast-math`.

## Boundaries

This suite measures steady-state **small-signal linear magnitude response** only. It does not prove visual host integration, realtime latency, modulation behavior, analog/circuit accuracy, drive nonlinearity or alias suppression. The actual core clamps output voltages to ±10 V; the low input level and selected resonances keep tests away from clipping. Sample count and tolerance are deterministic, though exact floating-point results may vary mildly by compiler and architecture.
