# Offline DSP sound-design auditions

These C++17 command-line renderers exercise the **original first-party DSP
classes** without the Rack host, audio device or plugin wrapper. They produce
fixed-duration stereo, 16-bit PCM WAV files for listening and regression tests.
They do **not** verify that a Cardinal or DAW plugin can load, save automation,
or produce real-time audio.

From the repository root:

```sh
c++ -std=c++17 -O2 -I . tools/audio-render/fm_voice_render.cpp -o /tmp/ms-fm-render
/tmp/ms-fm-render --output /tmp/ms-fm-minor7.wav --sample-rate 48000 --harmony minor7
/tmp/ms-fm-render --output /tmp/ms-fm-quartal.wav --sample-rate 48000 --harmony quartal --unison 4
/tmp/ms-fm-render --output /tmp/ms-fm-reference.wav --sine-reference --harmony minor7

c++ -std=c++17 -O2 -I . tools/audio-render/morph_filter_render.cpp -o /tmp/ms-morph-render
/tmp/ms-morph-render --output /tmp/ms-morph-echo.wav --with-stereo-echo --tail-seconds 2
```

FMVoice's four-second, sixteen-step original phrase supports:

- `--harmony off` (default): the historical mono-pitch melody, with precisely
  the same samples as before the harmony feature.
- `--harmony minor7`: independent root, minor third, fifth, minor seventh
  oscillators; chord tones enter in 15 ms staggered increments.
- `--harmony quartal`: root plus three ascending perfect fourths. Both chord
  modes use fixed four-tone voicings above each step's melody note and are
  normalized for headroom.
- `--unison 1|2|4`: separate detuned layers *per* chord tone; four chord tones
  and four unison layers exercise sixteen independent FMVoice states per stereo
  channel without per-sample allocation. The default is one layer.
- `--sine-reference`: use the same pitch, timing and stereo arrangement with
  index and feedback disabled, making chord pitches inspectable without FM
  sidebands.
- `--sample-rate 44100|48000|96000`: exact deterministic integer PCM16
  envelopes across all supported rates.

The renderers refuse existing output entries (including dangling symlinks),
validate the sample rate and options, check for nonfinite DSP output and report
peak, RMS and FNV-1a checksums of the little-endian PCM payload. These checks
do not replace headphones, controlled listening comparisons or host CPU tests.

Run their source-level audio regression tests with:

```sh
python3 -B -m unittest discover -s tests -p 'test_fm_voice_audio_render.py' -v
python3 -B -m unittest discover -s tests -p 'test_audio_render.py' -v
```
