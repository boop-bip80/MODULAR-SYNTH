# Real-host audio capture acceptance gate

This is an acceptance **tool**, not evidence that MODULAR-SYNTH already works in a DAW. Existing hosted plugin-validation checks instantiate and exercise Cardinal in Carla dummy bridge mode; they do not establish that a person loaded a fork-owned patch, played MIDI and heard stereo audio. The `verify_host_audio_capture.py` script validates a **user-supplied** recording package and rejects silent, mono, clipped, unresponsive or unverifiable captures. The named host and recording method remain operator attestations: an arbitrary file can be falsely labeled as a DAW recording, and a passing report is **not** proof of its origin.

## Collect one capture package

For a first-party synth preset:

1. Build and verify an ELF Linux LV2/VST2/VST3 plugin from an **exact** fork commit; record that 40-character source SHA. Do not substitute a `.so` from a different build. If you want to prove a specific installed artifact, also check its actual build distribution SHA/manifest separately.
2. Copy the **actual compiled plugin `.so`** and **actual saved `.vcv` patch** into an evidence directory. Record their SHA-256 digests. Include the host name/version, platform, plugin format and exact recording method.
3. Prepare a standard MIDI file with at least one nonzero-velocity Note On. Capture a stereo 16/24/32-bit integer PCM WAV, 32–192 kHz, 0.75–45 seconds, with that MIDI playing. Use a separate `idle.wav` capture of the *same patch and same duration* **with no MIDI**. Keep host settings and audio gain identical. A looping/free-running generator that sounds with no MIDI is not suitable for this particular gate; choose a note-triggered patch.
4. For an effect instead, prepare `dry.wav` as the actual stereo input stimulus. Record the effect `wet.wav` and a second no-input `idle.wav` at identical sample format, sample rate and duration. The wet audio must not simply be a byte-for-byte dry copy.
5. Compute SHA-256 of all five evidence files. Preserve the directory and report together for review. Do not edit recordings after computing digests.

Example local package:

```text
host-evidence/
  capture.json
  plugin.so
  performance.vcv
  notes.mid
  played.wav
  idle.wav
```

The `capture.json` schema is deliberately exact; all paths are relative to its own directory and may not cross symlinks:

```json
{
  "schema": "modular-host-audio-v1",
  "source_sha": "0123456789abcdef0123456789abcdef01234567",
  "host": {
    "name": "REAPER",
    "version": "record the actual tested version",
    "os": "Linux x86_64",
    "plugin_format": "VST3",
    "capture_method": "exact steps used to load the patch and render both cases"
  },
  "plugin": {"path": "plugin.so", "sha256": "<64 lowercase SHA-256 hex characters>"},
  "patch": {"path": "performance.vcv", "sha256": "<64 lowercase SHA-256 hex characters>"},
  "mode": "synth",
  "stimulus": {"path": "notes.mid", "sha256": "<64 lowercase SHA-256 hex characters>"},
  "render": {"path": "played.wav", "sha256": "<64 lowercase SHA-256 hex characters>"},
  "baseline": {"path": "idle.wav", "sha256": "<64 lowercase SHA-256 hex characters>"}
}
```

For `"mode": "effect"`, replace `notes.mid` with the stereo dry WAV; all other fields remain unchanged. Use an ELF Linux plugin file, not a wrapper directory. Match source SHA to the exact build represented by the supplied plugin (the tool independently verifies SHA consistency with the declared value, not GitHub artifact provenance).

## Evaluate and interpret the result

```bash
python3 -B tools/ci/verify_host_audio_capture.py \
  --manifest host-evidence/capture.json \
  --expected-sha 0123456789abcdef0123456789abcdef01234567 \
  --json
```

A passing report establishes **within the provided evidence** (the ELF header check is only a basic file-format check; actual plugin loadability and provenance require separate proof):

- Every included evidence file exists, is bounded, is a regular non-symlink file and hashes to the declared SHA-256.
- Synth stimulus is a structurally valid MIDI file with actual Note On data, or an effect has audible stereo input.
- Active/idle recordings have equal stereo PCM format, sample rate and length; output is audible on *both* channels (RMS/peak and active sample fractions measured), with no prolonged hard clipping.
- Active output is at least 12 dB louder than the no-MIDI/no-input control, so the capture demonstrates a responsive signal path rather than merely an always-playing oscillator.
- For effects, wet output samples differ from the dry input. This is a very small processing sanity gate, **not** a quality assessment.

The script exits nonzero if any check fails and supplies a machine-readable reason. In particular, it does not silently skip missing fixtures or treat a Carla dummy bridge pass as audio output. Unit tests generate artificial recordings and validate that the tool rejects missing, silent, mono, clipped, mismatched and tampered inputs; **those synthetic fixtures must never be represented as real plugin/DAW recordings**.

Remaining separate gates: independent verification that the recording truly came from the specified DAW/plugin binary, human listening and musical judgment, MIDI/automation parameter sweeps, hot-load/deletion stress, CPU and latency measurements, save/reopen, and a fork-owned cross-platform release.
