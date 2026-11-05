# Offline Macro8 scene-sequence preview

`instrument_builder.py sequence` predicts **nominal control voltages** across
successive saved Macro8 scene changes. It is useful when planning a performance
with multiple snapshots that may interrupt one another before the previous
transition has finished.

It reads a fully integrity-checked `.msinstrument` source ZIP (including its
original `.vcv` patch), not a loaded Rack/Cardinal plugin. It does not export
MIDI, CV clips or a playable instrument, and it cannot measure a DAW session.

## Example

From the repository root, with an existing trusted source bundle:

```bash
python3 tools/instrument-builder/instrument_builder.py sequence \
  Performance.msinstrument --from A \
  --events '0:B,0.25:A,0.5:D' \
  --at '0,0.125,0.25,0.375,0.5,0.75,1.25' \
  --sample-rate 48000

# Use JSON to make your own source-only CV/timing visualization:
python3 tools/instrument-builder/instrument_builder.py sequence \
  Performance.msinstrument --from A \
  --events '0:B,0.25:A,0.5:D' \
  --at '0,0.125,0.25,0.375,0.5,0.75,1.25' \
  --sample-rate 48000 --json
```

The example assumes that scene A has settled before time zero. At time zero
the target switches to B. A quarter-second later the target becomes A again,
**without** first snapping the predicted CV to B. At half a second it begins
morphing toward D from whatever value is predicted at that instant.

Each `--events` entry is `SECONDS:SCENE`, where the scene is `LIVE`, `A`, `B`,
`C` or `D`. The `--at` list contains chronological seconds at which to sample
all eight controls. `--module-id` is required when the source patch has more
than one Macro8. Saved empty snapshot slots cannot be targeted.

## Timing convention and numerical model

- Event and query times are rounded to the nearest sample. Events and queries
  must each have *strictly increasing, distinct* sample indices; ambiguity
  within a single sample is rejected.
- A target change at sample `N` takes effect **before the next sample is
  processed**. Querying *at* sample `N` observes the CV immediately before
  that next update; `activeTarget` identifies the newly selected destination.
- For a fixed saved morph time `T` and sample rate `R`, over `K` processed
  samples, the estimator uses the Macro8 DSP's one-pole relationship
  `current = target + exp(-ln(1000) * K / (R * T)) * (current - target)`.
  With `T=0`, a target is reached on the next processed sample.
- The math is evaluated analytically between requested boundaries. It does
  not allocate a buffer for a potentially hour-long sample-by-sample render.
- `predictedNormalized` is an estimated saved control in `[0, 1]`;
  `predictedNominalVolts` is `10 * value` for unipolar controls and
  `10 * value - 5` for bipolar controls. These are *nominal mapping values*,
  not sampled output voltages.

To limit accidental oversized inputs, the CLI accepts at most 128 scene
events and 256 query times, from 0 to 3,600 seconds, at 8–384 kHz. It rejects
invalid, duplicate/unsorted, nonfinite or sub-sample-colliding timestamps.
Neither the source bundle nor its historical v1/v2 schema is rewritten.

## What the result cannot establish

The estimator assumes no external CV modulation of Macro8 values and no
changes to its saved morph knob while running. Actual host sample-time
rounding, parameter automation, cable signal paths, module bypass, user
interaction, and DSP/DAW audio are outside this source-only preview. For a
listening or recording claim, verify the performance inside the built host.
