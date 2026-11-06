# Scale Quantizer — musical and engineering contract

`ModularSynth/ScaleQuantizer` is an original 12 HP, sixteen-lane pitch-control
utility. It accepts one-volt-per-octave control voltage and returns the nearest
permitted semitone, plus a short voltage trigger when its selected note changes.
It is **CV-only**: it does not create audio or send MIDI messages.

## Patching

| Control/port | Meaning | Range and default |
| --- | --- | --- |
| PITCH input | Incoming pitch, 1 V/oct | ±10 V; missing cable is 0 V |
| TRANS CV input | Pitch offset added before selecting a scale degree | 1 V/oct; ±10 V protected |
| ROOT CV input | Transposes the *scale tonic* by rounded semitone steps | 1/12 V per tonic semitone; ±10 V protected |
| ROOT knob | Root pitch class; C = 0, C# = 1, … B = 11 | 0…11; default C |
| SCALE knob | Eight selectable pitch-class masks | 0…7; default chromatic |
| TRANS knob | Fixed incoming-pitch transpose | −12…+12 semitones; default 0 |
| HYST knob | Hysteresis margin relative to the previous selected note | 0…50 cents; default 12 |
| QUANT output | Nearest permitted note as a 1 V/oct control voltage | ±10 V (internally integer semitone / 12) |
| CHANGE output | Trigger on first new selected note and subsequent changes | +10 V for 2 ms; otherwise 0 V |

SCALE positions:

1. Chromatic: 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11.
2. Major: 0, 2, 4, 5, 7, 9, 11.
3. Natural minor: 0, 2, 3, 5, 7, 8, 10.
4. Dorian: 0, 2, 3, 5, 7, 9, 10.
5. Harmonic minor: 0, 2, 3, 5, 7, 8, 11.
6. Major pentatonic: 0, 2, 4, 7, 9.
7. Minor pentatonic: 0, 3, 5, 7, 10.
8. Whole tone: 0, 2, 4, 6, 8, 10.

Each interval is measured in semitones above ROOT; pitch classes wrap across
octaves and work identically for negative and positive voltages. At an exactly
equidistant note boundary, the lower pitch wins, unless hysteresis retains a
valid previously selected pitch. ROOT CV transposes the set of permitted
notes; it does **not** transpose the incoming pitch voltage itself.

## Stable retuning

The previous selected semitone remains until a newly nearest note improves
pitch distance by more than the HYST margin. For example, with 20 cents
hysteresis, advancing from C toward C# does not switch at 50 cents; it
switches once the advancing pitch is beyond 60 cents. Moving back requires
crossing 40 cents. Changing ROOT or SCALE immediately invalidates any previous
note not in the new scale. At zero hysteresis, ties retain the previous note.

A first accepted note asserts CHANGE for two milliseconds; holding that note
does not retrigger. The trigger is sample-rate-derived, lasts at least one
sample, and restarts on new selected notes. Because quantization uses musical
semitones and not a continuous sample stream, it is best used before a VCO's
PITCH jack. Routing it to an audio input will produce stepped DC, not sound.

## Implemented protections and verification scope

- Sixteen fixed-memory DSP lanes; audio callback performs no heap allocations,
  locking, file access, logging, or third-party calls.
- Incoming voltages and final pitch are bounded to ±10 V; invalid or nonfinite
  controls are replaced with safe finite defaults. Invalid engine sample rates
  fail closed and clear note/trigger state.
- Falling polyphony resets retired lanes. Editor/host reset only publishes an
  atomic request, consumed on the engine callback; no editor thread writes
  process-owned note histories.
- C++11 standalone deterministic regressions and test-only HEADLESS Rack shim
  exercise scale masks, negative pitch classes, roots, controls, hysteresis,
  trigger durations, reset, sixteen-lane stress, and no audio allocations.

These are **source-backed engineering checks**, not proof of a deployed
Cardinal module, real Rack ABI compatibility, or audible live-host behavior.
