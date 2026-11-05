# Offline MorphVCO → StateFilter render (optional StereoEcho)

This standalone tool renders a **four-second, original sixteen-note stereo arpeggio** through the real first-party [MorphVCO](../plugins/ModularSynth/src/MorphVCO.hpp) and [StateFilter](../plugins/ModularSynth/src/StateFilter.hpp) pure DSP headers. It is a reproducible audio-regression artifact and a short demonstration of those cores, **not** a Cardinal/Rack plugin build or a host-render fidelity claim.

No Rack SDK, audio device, package downloads, external C++ libraries, or generated WAVs in Git are needed. The optional post-filter effect calls the actual first-party [StereoEchoDSP](../plugins/ModularSynth/src/StereoEcho.hpp) code; no imitation delay algorithm is used.

## Build and render

From repository root, with a C++17 compiler:

~~~sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic -I . \
  tools/audio-render/morph_filter_render.cpp -o /tmp/morph_filter_render

/tmp/morph_filter_render --sample-rate 48000 \
  --output /tmp/modular-synth-morph-filter-48000.wav

# Optional stereo-delay audition, same duration and file format:
/tmp/morph_filter_render --sample-rate 48000 --with-stereo-echo \
  --output /tmp/modular-synth-morph-filter-echo-48000.wav

# Let the real echo feedback decay for two more seconds after the melody:
/tmp/morph_filter_render --sample-rate 48000 --with-stereo-echo \
  --tail-seconds 2 --output /tmp/modular-synth-morph-filter-tail-48000.wav
~~~

The CLI supports `--sample-rate` 44100, 48000 (default), or 96000, and optional `--with-stereo-echo` (off by default). `--tail-seconds 0|1|2` (default `0`) adds one or two seconds of natural StereoEcho feedback decay after the four-second phrase; **positive tail lengths require `--with-stereo-echo`**. It requires `--output PATH` (use a `.wav` filename by convention); `--help` shows usage. Its status line reports `echo=off` or `echo=on` and the PCM data checksum. To protect existing recordings, it checks for an existing output file **or symlink (including a dangling symlink)** and refuses the write. This is a preflight check, **not an atomic guarantee** against a concurrent writer replacing the path between inspection and opening. Give each render a fresh filename in a private output directory.

The default result is standard **stereo PCM16 little-endian WAV**, exactly four seconds long. Positive echo-tail settings yield exactly **five or six seconds** with the same sample rate and format:

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
- Optional StereoEcho post-filter stereo delay: **187.5 ms** fixed time, **32%** feedback, **35%** wet, **70%** crossfeed. Each stereo sample is converted from normalized WAV amplitude to the DSP's ±5 V convention, passed through the same original StereoEcho DSP used by the Rack module, then converted back. The echo rings allocate once only when enabled, not per sample. By default the fixed **four-second** WAV truncates the remaining delay tails. With `--tail-seconds 1` or `2`, the oscillator/filter notes stop at precisely four seconds and the **same echo DSP** receives zero-valued input for the added duration; its actual feedback ring decays without fabricated notes or reverb. This is not tempo/BPM synchronization.
- Before PCM conversion, every sample is checked with the existing bitwise IEEE-754 finite guard (robust even with strict -ffast-math) and limited to **±0.75 full scale** to provide headroom.

The DSP is intentionally single-rate: **polyBLEP does not eliminate all oscillator aliasing**, and nonlinear drive has no oversampling. This is a functional sound/regression fixture, not a mastered release.

## Regression tests

~~~sh
python3 -m unittest discover -s tests -p test_audio_render.py -v
~~~

The test uses only Python's standard library, a local C++17 compiler and the three in-tree DSP headers. It builds both a normal -O2 and an aggressive -O3 -ffast-math renderer in a temporary directory, then checks:

1. **44.1, 48 and 96 kHz**: exact RIFF/PCM16 layout, 2 channels, four-second length, finite/active audio, evolving stereo, peak below 75% FS and healthy non-silent RMS.
2. Repeat each rate with the same executable: **byte-identical SHA-256** of the whole WAV, FNV-1a of PCM bytes equal to the renderer's own report, and different checksums across rates.
3. Every quarter-second note has non-silent PCM energy, the sixteen-note phrase varies dynamically, and note boundaries have no large discontinuities.
4. Existing files and dangling symlink outputs are rejected; the symlink test skips only where creating test symlinks is unsupported.
5. Strict fast-math 48 kHz dry and optional echo renders and basic CLI validation, including refusing to overwrite an existing file.
6. Optional echo at **44.1/48/96 kHz**: repeat-run WAV/checksum identity and distinct dry versus delayed output. Before the first 187.5 ms tap, the output must equal the expected 65% dry signal (within PCM quantization tolerance); later, delayed energy must appear.
7. Optional one- and two-second echo-tail renders at all three sample rates: deterministic full-file bytes, exact 5/6-second RIFF lengths, byte-for-byte preservation of the original first four seconds of PCM, active early echo tails and (for two seconds) clear decay toward the end. Invalid/negative/fractional tail lengths and nonzero tails without the echo flag are rejected.

All generated files live inside Python's temporary directory and are discarded after the tests. They should **not be committed to the repository**; a CI workflow may attach an example WAV as an ephemeral artifact in the future.

### Measured reference (GCC 13.3, x86-64, 2026-11-01)

The original dry/default standalone renderer compiled and executed at -O2 -Werror -pedantic and -O3 -ffast-math -Werror using the merged MorphVCO/StateFilter headers. Both profiles produced these PCM checksums in that historical environment. The optional echo mode was not part of this reference measurement:

| Rate | Normalized peak | RMS | PCM FNV-1a 64-bit |
| --- | ---: | ---: | --- |
| 44,100 Hz | 0.409692 | 0.079479 | f6a4969075fde7e5 |
| 48,000 Hz | 0.409087 | 0.079511 | c3bca79532bd36ad |
| 96,000 Hz | 0.411449 | 0.079644 | 3f2866f12b21f63d |

These hashes are informative reference points, **not cross-platform golden test requirements**. The automated test compares repeated renders of the same executable and checks decoded PCM properties to avoid flaky CI across libm implementations.

**Not tested by this harness:** Cardinal/VST host integration, plugin UI, realtime latency, polyphonic Rack wrapper routing, auditory perception across speakers, and long-duration performance.


---

## Separate FMVoice sound-check renderer

The independent [FMVoice offline renderer](../tools/audio-render/fm_voice_render.cpp)
exercises the **actual first-party two-operator FMVoice DSP header**, with
ratio/index/feedback motion, a four-second sixteen-note original phrase and a
slightly detuned stereo pair. Unlike the MorphVCO → StateFilter demo above,
this tests the source-only FM oscillator in isolation. It does **not** claim
that the Rack wrapper, MIDI inputs, patch or DAW host has been executed.

Build with a standard C++17 compiler and render both FM and a
zero-index/zero-feedback **sine reference**:

~~~sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic -I . \
  tools/audio-render/fm_voice_render.cpp -o /tmp/fm_voice_render

/tmp/fm_voice_render --sample-rate 48000 \
  --output /tmp/modular-fm-48000.wav
/tmp/fm_voice_render --sample-rate 48000 --sine-reference \
  --output /tmp/modular-sine-reference-48000.wav

# Add four independently detuned FM layers per stereo channel:
/tmp/fm_voice_render --sample-rate 48000 --unison 4 \
  --output /tmp/modular-fm-unison4-48000.wav
~~~

The supported rates are **44.1, 48 and 96 kHz**. Both modes write stereo,
little-endian PCM16 WAVs, exactly four seconds long. Per-note 15 ms attack and
40 ms release windows bound transitions. The FM default varies the frequency
ratio, modulation index and feedback, while the reference uses the same
FMVoice implementation with its phase modulation disabled; neither mode
changes FMVoice source or loads a saved `.vcv` patch.

The optional `--unison 1|2|4` mode selects one (default), two or four
**independent FMVoice DSP instances per stereo channel**. Two layers spread
±5 cents around the nominal note; four spread ±8 cents, with slight
per-layer FM-ratio and modulation-index differences. The right channel
retains the existing four-cent offset from the left. All active layers are
averaged before envelope shaping so adding voices does not multiply output
gain; the standard ±0.75 full-scale limiter still applies. `--unison 1`
is byte-identical to omitting the flag when built with the same compiler.
The option works with `--sine-reference` too, where detuning produces an
original multi-oscillator sine comparison rather than additional FM
sidebands. The number of DSP oscillators, and thus approximate CPU work,
increases linearly with the selected unison count. This is a *source-only*
audition feature; it is not a Rack module control or polyphonic MIDI chord.

The status line reports `mode=fm` or `mode=sine`, rate, frame count,
normalized peak, RMS and an FNV-1a hash of the PCM bytes. Independent tests
check the hash against the decoded WAV, two identical renders at each rate,
non-silent energy in **all 16 note windows**, stereo differences, bounded
note-edge sample discontinuities, finite amplitude/headroom, a measurable PCM
difference between FM and sine-reference modes, and a strict
`-O3 -ffast-math` render. Avoid treating a changed digest as a subjective
sound-quality verdict; it identifies a changed output.
The tests additionally exercise all three sample rates with deterministic
two-/four-layer unison, distinguish each voice-count PCM result, check
note-window energy/stereo separation/transition bounds and headroom,
compare explicit `--unison 1` to the default, and run four-layer FM with
`-O3 -ffast-math`. Invalid unison counts are rejected before writing.

~~~sh
python3 -m unittest discover -s tests -p test_fm_voice_audio_render.py -v
~~~

As with the existing renderer, output files and symlink destinations are
preflight-protected from overwriting, but this does not provide atomic
protection against a concurrent writer. Use a private output folder. No
generated WAV files are committed. FMVoice's bandwidth guard is not an ideal
bandlimiter; the tests do **not** certify alias-free output, accurate analog
emulation, real-time CPU, linked Cardinal audio, UI behavior, listening
quality or DAW project roundtrips.

---

## FM Voice → Dual VCA → Stereo Echo bell phrase

The new `fm_vca_echo_render.cpp` is a **separate opt-in executable**. Existing
`fm_voice_render` and `morph_filter_render` source, CLI and baseline WAV bytes
remain untouched. From the repository root:

```sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic -I . \
  tools/audio-render/fm_vca_echo_render.cpp -o /tmp/fm_vca_echo_render

# Original four-second, sixteen-note C-minor bell motif, plus one second of
# true StereoEcho feedback decay (stereo, little-endian 16-bit PCM):
/tmp/fm_vca_echo_render --sample-rate 48000 \
  --output /tmp/fm-vca-echo-48k.wav

# Extended two-second tail at 96 kHz:
/tmp/fm_vca_echo_render --sample-rate 96000 --tail-seconds 2 \
  --output /tmp/fm-vca-echo-96k.wav

# Compare the same FMVoice and DualVCA signal without echo:
/tmp/fm_vca_echo_render --dry-reference --tail-seconds 0 \
  --output /tmp/fm-vca-dry-48k.wav
```

Existing output paths, including symlinks, are rejected by a preflight rather
than overwritten. This check is not atomic against a concurrent process
replacing the path; use fresh names in a private directory. The program prints
the sample rate, exact PCM frame count,
peak, RMS and an FNV-1a checksum of the output PCM (not of the WAV header).
The renderer is deterministic across repeated runs on the same compiler,
build profile and platform. **Cross-platform/fast-math hashes are not promised
to match**: different legitimate floating-point optimizations can alter the
last few quantized samples.

### Actual source signal chain

1. Two independent `FMVoice` DSP instances generate slightly detuned left
   and right two-operator phase-modulation oscillators, with a four-ratio
   progression and gentle index/feedback motion.
2. The voice outputs are converted to nominal Rack-like ±5 V audio and fed
   into two actual `DualVCA::process()` instances. A fixed original
   attack/decay/release envelope controls the **CV input in volts**; the DSP's
   2 ms gain smoothing and cubic/linear curve blend remain active.
3. The two VCA outputs feed the real `StereoEchoDSP` at 187.5 ms, 34% feedback,
   35% wet and 72% stereo crossfeed. Audio-voltage output converts back to
   normalized PCM amplitude with deliberately conservative final gain.
4. At the four-second phrase boundary, both oscillator/VCA signals stop. For
   `--tail-seconds 1|2`, real zeros are fed to the same echo state so the
   feedback ring naturally decays. No extra notes or fabricated tails occur.

`--dry-reference` bypasses only the echo and requires `--tail-seconds 0`.
The first 160 ms of a wet render are approximately 65% of the corresponding
dry PCM signal, before the first 187.5 ms delay tap arrives. Past the tap,
the wet signal measurably differs from scaled dry output. This property is
enforced by tests rather than inferred from a filename.

Both `DualVCA` and `FMVoice` process sample-by-sample without allocating
buffers. The echo allocates its two fixed-size rings **before** the sample
loop; no DSP processing call allocates memory, takes a lock or performs disk
I/O. The *offline WAV writer* deliberately performs file I/O per frame; it
is **not** an audio-thread implementation or a host CPU benchmark.

### Verification

```sh
python3 -m unittest discover -s tests \
  -p 'test_fm_vca_echo_audio_render.py' -v
```

The test compiles the actual three DSP classes under ordinary and aggressive
fast-math optimization. It verifies 48/96 kHz RIFF/PCM structure, repeatable
hashes and bytes, 16 active note windows, evolving stereo output, bounded
headroom and note transitions, measurable delayed audio, exact extension
prefixes for 0/1/2-second tails, decaying feedback and safe CLI/no-overwrite
behavior. The test does **not** model hearing preference, validate a real
saved Rack patch, or prove host latency, automation, MIDI, GUI or plugin
installation. Live Cardinal/DAW audition remains an open release gate.
