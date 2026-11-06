# Slew Glide — original polyphonic asymmetric CV slew

`SlewGlide` is a fork-authored, statically registered MODULAR-SYNTH utility
with an independent DSP state per lane (up to 16 channels). It is intended for
expressive pitch portamento, smooth performer controls, filter sweeps and
user-programmed CV envelopes. The source is GPL-3.0-or-later and uses no
external DSP dependency or sample content.

## Signal path and musical meaning

| Jack/control | Definition |
| --- | --- |
| `CV IN` | Bipolar signal, limited to ±10 V before smoothing |
| `RISE` | 0…5 s knob, default 0.20 s, for upward voltage changes |
| `FALL` | 0…5 s knob, default 0.30 s, for downward voltage changes |
| `RISE CV` | +10 V adds 5 s to rise; negative CV shortens it; final time limited to 0…5 s |
| `FALL CV` | +10 V adds 5 s to fall; negative CV shortens it; final time limited to 0…5 s |
| `LINEAR` | Slews at a constant **10 V / time** (a 20 V excursion takes twice the knob time) |
| `EXP` | One-pole low pass approaching **99%** of a fixed target after configured time |
| `MOVING` | +10 V while either slew remains in progress. Schmitt thresholds open above 0.0002 V deviation and close at or below 0.0001 V, preventing gate chatter from tiny CV jitter |

At zero time, both outputs track CV IN immediately. If the source changes
continuously, neither the linear 10 V traversal time nor the exponential
99%-settling reference guarantees a fixed note-to-note transition duration:
both definitions assume a held, fixed target. The exponential output snaps
exactly to target once the remaining difference is at most 0.000001 V, avoiding
denormal tails. The MOVING gate uses a 0.0001–0.0002 V hysteresis band: when
already open it stays high until both outputs are within 0.0001 V; when closed
it ignores changes of 0.0002 V or less. This is a CV-activity indicator, not
an end-of-cycle trigger. Exact linear/exponential outputs are unchanged by
this gate-only stability fix.

The Rack wrapper carries no files, dynamic allocations, thread locks or
network I/O into `process()`. The host's `onReset()` callbacks only publish an
atomic request; the audio callback consumes it and resets the per-lane state.
When polyphony is reduced, now-unused lanes are cleared so resurrected voices
never inherit stale pitch.

Invalid or extreme control values are bounded or replaced by safe defaults;
sample rates outside 1,000…384,000 Hz fail closed and clear state. These
bounds are deliberate for predictable audio-thread work, but no live DAW
automation/audio audition or true host CPU measurements are yet available.

## Suggested musician patching

1. **Slow lead portamento:** `HostMIDI pitch → SlewGlide CV IN → SlewGlide
   LINEAR → MorphVCO PITCH`. Start RISE=0.12 s and FALL=0.18 s. Keep the
   original MIDI gate → ADSR → VCA envelope path; unlike a synth envelope,
   SlewGlide does not make a gate-driven attack/release note.
2. **Lyrical filter motion:** `Macro8 bipolar output → SlewGlide CV IN →
   EXP → StateFilter FREQ CV`; try RISE=0.5 s and FALL=1.3 s. Because the
   StateFilter CV jack is 1 octave per volt, limit Macro8's bipolar voltage
   range appropriately.
3. **CV activity modulation:** route MOVING to a trigger/logic *gate input*
   if the destination accepts 0/10 V gates; it describes whether slew has
   completed, not a 1-ms end-of-cycle trigger or a tempo pulse.

## Test evidence and limitations

- `tests/slew_glide_dsp_test.cpp` exercises exact rise/fall traversal, CV
  overrides, exponential 99% approach, zero-time bypass, signed 10 V bounds,
  reset replay, extreme/subnormal input values, 48-to-96 kHz wall-clock
  continuity, Schmitt activity-gate noise rejection, 16-lane deterministic
  stress and zero heap allocations across compiler profiles.
- `tests/rack_wrapper_smoke.cpp` exercises real wrapper source with a **test
  Rack shim**, including host reset and channel retirement. The wrapper smoke
  additionally proves retired lane 15 restarts from a fresh DSP state after
  polyphony shrinks then returns. The genuine header/link gate is configured
  separately against pinned Rack/DPF/Jansson.
- The SVG passes source geometry/asset checks; a rendered Rack visual check,
  audible host signal, actual DAW save/reopen and production plugin binary
  remain separate acceptance requirements.
