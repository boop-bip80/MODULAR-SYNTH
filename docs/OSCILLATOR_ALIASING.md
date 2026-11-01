# MorphVCO spectral alias-power regression

This analysis measures a **frequency-domain alias-energy estimate** for the original MODULAR-SYNTH MorphVCO polyBLEP **saw and 50%-duty pulse** versus equivalent **naive discontinuous saw/pulse** sampled from the exact same oscillator phase. It uses the real [MorphVCO DSP core](../plugins/ModularSynth/src/MorphVCO.hpp), a small first-party C++17 radix-2 FFT, and no Rack/DAW or external analysis packages.

It is deliberately different from comparing waveform RMS error: waveform RMS error can reflect legitimate timbral change, while this test isolates spectral energy at FFT frequencies that **cannot be legitimate harmonics** of the configured periodic oscillator.

## Run the analyzer

From repository root:

~~~sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic -I . \
  tools/spectral-analysis/morphvco_alias.cpp -o /tmp/morphvco-alias

/tmp/morphvco-alias --sample-rate 48000 --waveform saw
/tmp/morphvco-alias --sample-rate 96000 --waveform pulse
/tmp/morphvco-alias
~~~

By default the CLI emits CSV on stdout for both sample rates, both waveforms, six musical notes (A3–A8), and a separate stress tone at 0.42 × sample rate (84% of Nyquist). The CSV contains nominal and actual coherent pitch, bin index, naive and polyBLEP **alias RMS**, improvement in dB, alias fraction of total signal power, and total RMS (important for the near-Nyquist caveat).

## What the numbers mean

1. Generate exactly 65,536 samples, with fundamental at an **odd integer FFT bin** chosen nearest the requested note. Since the FFT size is a power of two, odd bin numbers are coprime with the FFT size; this gives an exact integer-period experiment and avoids many high-order alias/harmonic collisions. The actual analysis pitch differs by at most one FFT bin from the named note.
2. Before each real MorphVCO.process call, read its phase to calculate the naive saw (2 × phase − 1) or naive 50% pulse (±1). This makes both versions share precisely the same phase, pitch and sample interval. A static morph of 0.5 selects the polyBLEP saw; morph 1.0 selects the polyBLEP pulse. Pulse width stays 0.5.
3. Apply a **periodic Hann window**, then radix-2 FFT. Normalize one-sided bin power by the exact Hann squared-energy sum. Count legitimate integer harmonics below Nyquist as expected bins, including a ±2-bin guard against tiny floating-point/window leakage. The 50% pulse has **odd legitimate harmonics only**. DC and its immediate neighbor are excluded.
4. Sum power in the **remaining bins**. Alias RMS is the square root of this normalized power. The improvement is 10 × log10(naive alias power / polyBLEP alias power). For a coherent single sine wave, this test measures essentially zero alias power; an intentionally off-harmonic sine registers as non-harmonic energy.

### Critical interpretation limit

This is a **lower-bound / isolated-bin estimate of alias power**, not the exact total analog-to-digital alias energy. High-order aliases that *fold directly onto a legitimate harmonic bin* are inseparable by this mask and are not counted. Small nonideal spectral leakage or implementation artifacts can also affect the floor. The Hann guard reduces, but cannot abolish, these limitations. Power in expected bins may contain a mixture of legitimate harmonics and aliases.

This analysis says nothing about realtime host integration, audio-rate CV/FM/PWM modulation, perceived sound, or whether high-frequency passband amplitude is preserved.

## Measured results

GCC 13.3 x86-64, C++17 optimized standalone run, 2026-11-01:

| Sample rate | Note / waveform | Naive alias RMS | polyBLEP alias RMS | Alias-power reduction |
| --- | --- | ---: | ---: | ---: |
| 48 kHz | A4 saw | 0.060973 | 0.009558 | **16.10 dB** |
| 48 kHz | A4 pulse | 0.086627 | 0.013925 | **15.88 dB** |
| 48 kHz | A6 saw | 0.122489 | 0.019651 | **15.89 dB** |
| 48 kHz | A7 pulse | 0.258736 | 0.052812 | **13.80 dB** |
| 96 kHz | A3 saw | 0.024198 | 0.002044 | **21.46 dB** |
| 96 kHz | A4 pulse | 0.061240 | 0.009809 | **15.91 dB** |
| 96 kHz | A8 saw | 0.176394 | 0.030974 | **15.11 dB** |

Across all **24 musical comparisons** (2 sample rates × 6 pitches × 2 waveforms), the measured isolated alias-band power reduction was greater than **13.8 dB** in this run. The regression threshold is intentionally looser: **at least 8 dB** of improvement, guarding against compiler/CPU numerical differences while testing a substantial DSP effect.

### High-pitch caveat

For a stress tone at 0.42 × sample rate, the isolated alias-bin reduction looks extremely strong (about **31.5 dB** for the saw at either rate), **but that alone is misleading as a quality metric**. At 48 kHz the same polyBLEP saw's total RMS falls from about **0.577** (naive) to **0.243** (polyBLEP); the desired fundamental is substantially attenuated at this near-Nyquist frequency. This is a known practical limit of a single-sample polyBLEP approximation. A lower alias measurement does **not** prove an accurate, equally loud, or subjectively better high-note waveform.

The near-Nyquist experiment is **reported and safety-checked**, but it does not have a required minimum reduction or amplitude-fidelity pass criterion.

## Regression and reproducibility

~~~sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic -I . \
  tests/morphvco_alias_dsp_test.cpp -o /tmp/morphvco-alias-dsp-test
/tmp/morphvco-alias-dsp-test

# The project runner auto-discovers this *_dsp_test.cpp file:
python3 tests/run_dsp_tests.py
~~~

The C++ test validates:

- Correct FFT/Hann power normalization via the Parseval identity.
- A legitimate coherent sine has negligible measured alias energy, an unrelated sine is classified as non-harmonic, and a 50%-pulse even harmonic is excluded from the expected-harmonic mask.
- 24 musical saw/pulse cases have nonzero naive alias RMS, at least 8 dB lower polyBLEP isolated alias power, improved alias fraction, and enough retained total signal power that a silent oscillator cannot pass.
- A near-Nyquist stress tone remains finite and non-silent without a misleading timbre-preservation requirement.

All core tests **compiled and executed successfully** under GCC C++17 normal -O2, the project's -O3 -ffast-math -fno-finite-math-only profile, and strict -O3 -ffast-math, using in-memory source plus the actual merged MorphVCO DSP header. An -O1 AddressSanitizer/UndefinedBehaviorSanitizer run also passed with LeakSanitizer disabled (the sandbox cannot inspect /proc). This is standalone DSP evidence, **not** a full Cardinal plugin or auditory validation.

The CLI output can be saved outside Git for deeper analysis. No FFT plots, WAV files, or generated CSV artifacts are committed.
