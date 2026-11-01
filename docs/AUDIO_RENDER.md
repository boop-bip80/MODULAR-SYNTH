# Offline MorphVCO → StateFilter render

This standalone tool renders a **four-second, original sixteen-note stereo arpeggio** through the real first-party [MorphVCO](../plugins/ModularSynth/src/MorphVCO.hpp) and [StateFilter](../plugins/ModularSynth/src/StateFilter.hpp) pure DSP headers. It is a reproducible audio-regression artifact and a short demonstration of those cores, **not** a Cardinal/Rack plugin build or a host-render fidelity claim.

No Rack SDK, audio device, package downloads, external C++ libraries, or generated WAVs in Git are needed.

## Build and render

From repository root, with a C++17 compiler:

~~~sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic -I . \
  tools/audio-render/morph_filter_render.cpp -o /tmp/morph_filter_render

/tmp/morph_filter_render --sample-rate 48000 \
  --output /tmp/modular-synth-morph-filter-48000.wav
~~~

The CLI supports --sample-rate 44100, 48000 (default), or 96000. It requires --output PATH.wav; --help shows usage. To protect existing recordings, it refuses to overwrite an existing output file. Give each render a fresh filename.

The result is standard **stereo PCM16 little-endian WAV**, exactly four seconds long:

| Rate | Frames | Audio data bytes | Approx. file size |
| --- | ---: | ---: | ---: |
| 44,100 Hz | 176,400 | 705,600 | 689 KiB |
| 48,000 Hz | 192,000 | 768,000 | 750 KiB |
| 96,000 Hz | 384,000 | 1,536,000 | 1.46 MiB |

The program streams two samples per frame directly to disk, so it does not allocate a full audio buffer. Its printed pcm_fnv1a64 is the hexadecimal **FNV-1a 64-bit checksum of the PCM data bytes** (not the RIFF header). It also reports frame count, normalized peak, and RMS. The checksum helps identify exact render changes; it does not claim that different operating systems, math libraries or CPU architectures produce bit-identical floating-point audio.

### Sound design

- One phase-continuous MorphVCO follows the original sixteen-step pitch sequence. Morph and pulse width evolve smoothly throughout the phrase.
- A second MorphVCO supplies a lower voice. Each goes into an independent real StateFilter DSP core with animated cutoff and modest resonance/drive.
- Each quarter-second note has short attack/release shaping to reduce transition clicks. Left/right mixes use different amounts of low-pass and band-pass output.
- Before PCM conversion, every sample is checked with the existing bitwise IEEE-754 finite guard (robust even with strict -ffast-math) and limited to **±0.75 full scale** to provide headroom.

The DSP is intentionally single-rate: **polyBLEP does not eliminate all oscillator aliasing**, and nonlinear drive has no oversampling. This is a functional sound/regression fixture, not a mastered release.

## Regression tests

~~~sh
python3 -m unittest discover -s tests -p test_audio_render.py -v
~~~

The test uses only Python's standard library, a local C++17 compiler and the two in-tree DSP headers. It builds both a normal -O2 and an aggressive -O3 -ffast-math renderer in a temporary directory, then checks:

1. **44.1, 48 and 96 kHz**: exact RIFF/PCM16 layout, 2 channels, four-second length, finite/active audio, evolving stereo, peak below 75% FS and healthy non-silent RMS.
2. Repeat each rate with the same executable: **byte-identical SHA-256** of the whole WAV, FNV-1a of PCM bytes equal to the renderer's own report, and different checksums across rates.
3. Strict fast-math 48 kHz render and basic CLI validation, including refusing to overwrite an existing file.

All generated files live inside Python's temporary directory and are discarded after the tests. They should **not be committed to the repository**; a CI workflow may attach an example WAV as an ephemeral artifact in the future.

### Measured reference (GCC 13.3, x86-64, 2026-11-01)

The standalone renderer compiled and executed at -O2 -Werror -pedantic and -O3 -ffast-math -Werror using the merged MorphVCO/StateFilter headers. Both profiles produced these same PCM checksums in this environment:

| Rate | Normalized peak | RMS | PCM FNV-1a 64-bit |
| --- | ---: | ---: | --- |
| 44,100 Hz | 0.409692 | 0.079479 | f6a4969075fde7e5 |
| 48,000 Hz | 0.409087 | 0.079511 | c3bca79532bd36ad |
| 96,000 Hz | 0.411449 | 0.079644 | 3f2866f12b21f63d |

These hashes are informative reference points, **not cross-platform golden test requirements**. The automated test compares repeated renders of the same executable and checks decoded PCM properties to avoid flaky CI across libm implementations.

**Not tested by this harness:** Cardinal/VST host integration, plugin UI, realtime latency, polyphonic Rack wrapper routing, auditory perception across speakers, and long-duration performance.
