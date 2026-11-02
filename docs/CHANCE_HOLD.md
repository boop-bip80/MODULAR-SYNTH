# Chance Hold — probabilistic modulation and pitch-step generator

[Source wrapper](../plugins/ModularSynth/src/ChanceHold.cpp) ·
[Deterministic DSP core](../plugins/ModularSynth/src/ChanceHold.hpp) ·
[Standalone DSP regressions](../tests/chance_hold_dsp_test.cpp)

**Development status:** The source is registered in MODULAR-SYNTH Originals,
but a loadable fork plugin, MIDI/audio audition and DAW save/reopen remain
unverified. This is source-level behavior and a patching guide, not a release.

Chance Hold is a 16-lane clocked random control-voltage source. Each clock
event has a programmable probability of choosing a new voltage; a rejected
event leaves the last voltage unchanged. Independent outputs provide hard
steps, continuously gliding voltage and a trigger on each accepted sample.

## Knobs and jacks

| Control | Range and behavior |
| --- | --- |
| FREE RATE | Logarithmic internal clock, **1/16–32 Hz**, default 1 Hz |
| CHANCE | **0–100%**, default 75%; 0% never updates, 100% updates every edge |
| GLIDE | **0–2 s**, default 0.15 s, approximate 99% settling time |
| QUANTIZE | Off by default; when on, new values round to **1/12 V** steps (12 semitones per volt) |
| RATE CV | **1 V/oct** added to free clock, bounded to 1/256–128 Hz |
| CLK | Connected jack overrides internal clock; rising **≥2 V** after falling **≤1 V** generates one event |
| RESET | Rising **≥2 V**, rearmed **≤1 V**, resets clock, held voltage, glide, pulse and deterministic random sequence |
| PROB CV | **+10 V adds 100 percentage points**, clamped to 0–100% |
| GLIDE CV | **+10 V adds 2 seconds**, clamped to 0–2 s |
| STEP | Last accepted random voltage **−5…+5 V** |
| SMOOTH | Smoothed version of STEP **−5…+5 V** |
| HIT | **+10 V** trigger for approximately **1 ms** on an accepted event |
| Green LED | CLK jack connected (not an assertion of tempo lock) |

Internal free-running events cease completely when the CLK jack is connected.
Unplugging resumes the internal clock from phase zero. RESET wins over a
simultaneous CLK edge, so a held-high RESET gate cannot accidentally create
repeat triggers. The random stream is a fixed-seed xorshift32 per lane, suitable
for **reproducible patches**, not cryptographic randomness. Resetting or
reloading reproduces the same seed and sequence; there is no global random
state, heap allocation, clock lookup or file access on the audio thread.

When QUANTIZE changes, it affects the *next accepted sample*, not the previously
held voltage. For conventional 1 V/oct destinations, STEP with QUANTIZE on
makes chromatic jumps; SMOOTH creates portamento between those steps. GLIDE
does not change STEP or HIT. The step source intentionally is not a
sample playback/granular audio module.

## Example — evolving FM color

Open [Chance Hold FM Drift](../patches/examples/MODULAR_-_Chance_Hold_FM_Drift.vcv).
MIDI notes gate a two-operator FM Voice; Chance Hold runs its free clock and
sends SMOOTH to the FM Voice index CV. RATE 1 Hz, CHANCE 75%, GLIDE 0.4 s and
QUANTIZE on are saved. Rejected events keep the previous timbre; accepted
events glide the FM modulation index. Adjust CHANCE toward 100% for
constant motion and toward 0% for long static timbres.

The saved MIDI-to-audio route is checked as data, not measured for audible
output. Begin at low monitoring volume and verify the host build before use.

## Safety and compatibility

- Each of up to **16 polyphonic lanes** uses its own seeded DSP state, but
  all share the same panel controls. Retired lanes reset deterministically.
- All incoming CV, clock, reset and knob values are bounded, including
  NaN/Infinity handling; output signals are finite and bounded.
- Unsupported sample rates below 1 kHz or above 384 kHz reset the lane to
  safe zero outputs. Valid sample-rate changes preserve free-clock phase and
  elapsed glide time.
- The one-pole glide coefficient is recomputed only when the glide control or
  sample rate changes. No allocations or locks occur inside process().
- The sample-and-hold values are pseudorandom; don't interpret a passing
  source DSP test as DAW host stability, plugin format acceptance, or a
  cryptographic random source.
