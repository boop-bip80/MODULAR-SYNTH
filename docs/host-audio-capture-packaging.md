# Packaging externally recorded host-audio evidence

The optional `modular-real-host-audio` CI gate requires **real, externally
recorded audio from a Linux DAW/plugin host**. The packaging tool only copies
existing files, hashes their exact bytes, checks a clean Git source commit and
independently supplied plugin SHA-256, and runs the existing offline validator.
It cannot load a plugin or prove that a DAW actually produced the WAV files.

1. Check out the exact source commit used to build the plugin, with no tracked
   modifications or untracked files (`git status --porcelain` must be empty).
   Preserve its full lowercase `git rev-parse HEAD` SHA.
2. Independently build and save the actual Linux LV2/VST2/VST3 shared-object
   `.so` binary intended for testing. Record its SHA-256 **before packaging**:
   `sha256sum /captures/actual/CardinalSynth.so`. The hosted gate will compare
   the evidence plugin SHA-256 with the **freshly rebuilt** CI binary; this
   match is mandatory. An independently compiled but nonidentical binary will
   fail the gate even if it makes valid audio.
3. In a real host, load that plugin and a saved nonempty `.vcv` patch. Record
   active and negative-control **stereo PCM WAV** bounces from the host,
   32–192 kHz and 0.75–45 seconds, matching sample rate, duration and bit
   depth. Active audio must have measurable output on both channels and no
   persistent clipping; control should be at least 12 dB quieter. For `synth`,
   retain the actual standard MIDI file with note-on events used for playback
   and bounce with no notes for the control. For `effect`, retain the *stereo*
   dry WAV used as input and bounce with no input for the control. The wet and
   dry files must differ, but a difference alone does not prove true hosting.
4. Use the packager from the clean checkout. All supplied evidence files should
   reside outside the checkout; use absolute paths. Replace the sample paths,
   SHA and host metadata below with the actual recording details:

   ```bash
   python3 tools/ci/package_host_audio_capture.py \
     --repo "$PWD" --source-sha "$(git rev-parse HEAD)" \
     --plugin /captures/CardinalSynth.so \
     --plugin-sha256 ACTUAL_INDEPENDENT_LOWERCASE_64_CHAR_SHA256 \
     --patch /captures/recorded-session.vcv \
     --mode synth --stimulus /captures/played-notes.mid \
     --render /captures/host-active.wav --baseline /captures/host-no-midi.wav \
     --host-name 'DAW name' --host-version 'version' \
     --plugin-format VST3 --capture-method 'DAW session and offline bounce' \
     --output-dir /captures/modular-host-audio-evidence
   ```

5. Inspect the new directory: `capture.json`, `plugin.so`, `patch.vcv`,
   `stimulus.mid` (or `stimulus.wav` for effect), `render.wav` and
   `baseline.wav`. The tool refuses symlinks, duplicate underlying files,
   malformed/oversized evidence, dirty or wrong source checkouts, mismatched
   supplied plugin digests, and already-existing output directories. Failure
   produces **no published directory**. Its success is offline preflight,
   **not** DAW provenance authentication.
6. Using an authorized GitHub Actions artifact upload workflow, upload those
   directory contents **at the artifact root** with the exact artifact name
   `modular-real-host-audio`. Run the repo's opt-in build workflow with
   `host_audio_capture_run_id` set to the run ID that published that artifact.
   The hosted job downloads and validates the package against its own source
   commit and freshly built plugin bytes. Do not enable this input for a
   synthetic fixture, an unverified third-party recording, or a package whose
   exact CI artifact digest cannot match.

The unit tests deliberately use generated audio **only as validator fixtures**.
No provided script fabricates a real-host recording; actual playback, capture,
DAW provenance and listening acceptance always require independent operator
work and evidence.
