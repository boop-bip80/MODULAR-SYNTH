# Clocked LFO — original 16-lane tempo-aware modulation

Clocked LFO (`ModularSynth/ClockedLFO`) is a new first-party control-voltage
source with independent 16-lane phase state, four bipolar waveforms and a
short end-of-cycle trigger. The [Rack-independent C++17
core](../plugins/ModularSynth/src/ClockedLFO.hpp) is original
GPL-3.0-or-later code. The [Rack wrapper and panel
layout](../plugins/ModularSynth/src/ClockedLFO.cpp) connect it to Cardinal's
existing statically compiled `ModularSynth` plugin collection.

This is **external-pulse tempo synchronization**, not direct DAW BPM or host
transport access. The LFO itself knows nothing about transport state. The
[Clocked Modulation Studio](../patches/examples/MODULAR_-_Clocked_Modulation_Studio.vcv)
factory patch connects Cardinal **HostTime BEAT output 3** to LFO **CLK
input 1** and **HostTime RESET output 1** to LFO **RESET input 2**. Thus a
playing host with valid bar/beat timing can supply pulses; when absent, each
LFO lane free-runs. A real Cardinal build/audio check remains outstanding.

## Controls and exact port indices

| Rack control | Index | Behavior |
| --- | ---: | --- |
| FREE RATE | param 0 | 1/64…16 Hz; default 0.5 Hz; effective DSP Hz clamps to 1/256…200 |
| CLOCK x | param 1 | Snapped ratio index 0…4, default 2: **1/4**, **1/2**, **1**, **2**, **4** cycles/clock period |
| PHASE | param 2 | Output-only phase offset 0…100%, default 0 |
| PULSE WIDTH | param 3 | Duty cycle 5…95%, default 50% |
| RATE CV | input 0 | Adds 1 octave per volt in free-run mode; ignored while externally locked |
| CLK | input 1 | External clock pulses; must rise to at least +2 V after falling to +1 V or less |
| RESET | input 2 | Rising edge to at least +2 V resets phase and divided-beat count |
| PHASE CV | input 3 | +0.1 output phase cycle per volt, wrapping at 1 |
| WIDTH CV | input 4 | +0.1 pulse duty per volt; effective width clamps to 5…95% |
| SIN / TRI / RAMP / PULSE | outputs 0 / 1 / 2 / 3 | Separate bipolar **±5 V** modulation signals |
| EOC | output 4 | Nominal **+10 V, 1 ms** trigger at a cycle wrap |
| TEMPO LOCK | light 0 | On when at least one active polyphonic lane has measured an external clock period |

The five output jacks each expose the number of lanes selected by the
largest connected audio/CV input (one to 16). A monophonic clock cable is
broadcast to all polyphonic lanes via Rack's documented normal-poly input
semantics. Per-lane RATE, PHASE, WIDTH, CLOCK and RESET CV values are
independent, and retiring a disappearing lane logically resets its state.

### Clock acquisition and dropout

Every lane measures the real **seconds** between accepted rising clock
edges, so changing sample rate preserves phase and does not mistakenly treat
sample counts as tempo. Two valid pulses acquire lock. The accepted interval
range is **20 ms…10 s** (50 Hz…0.1 Hz input clocks); faster glitches are
ignored. A Schmitt window (armed below 1 V, fired at 2 V) suppresses retriggers
from sustained gates. Each accepted pulse realigns the phase according to
the selected clock ratio. In 1/4 and 1/2 modes, divided beats occupy phase
positions 0, 1/4, 1/2, 3/4 or 0, 1/2. At 2× and 4×, additional internal
cycles occur between beats. If no accepted pulse arrives for more than
**four measured periods**, the lane returns to its free-run frequency
without resetting its phase. Disconnecting CLK also returns to free mode.

These are phase-locked *edges*, not a jitter-smoothed digital PLL; clock
jitter, RESET and changing clock ratios may deliberately move the phase
abruptly. Likewise, moving PHASE directly offsets the displayed waveforms,
so audio-rate PHASE CV can create discontinuities. This module is intended
for control modulation, **not a band-limited audio oscillator**.

### Finite and bounded behavior

- The DSP accepts sample rates from **1 kHz through 384 kHz**. Invalid,
  non-finite or outside-range rates return silent outputs and reset state.
- Bitwise IEEE-754 finite guards reject NaN/Inf inputs even under strict
  `-ffast-math`. Extreme CV, knob and phase values are bounded **before**
  `exp2()`, trigonometry, clock-period division and integer conversion.
- The internal phase stays in `[0,1)`; generated waveforms stay within
  ±5 V, and EOC is exactly 0 or +10 V. Frequency never exceeds 200 Hz.
- The core stores only scalar lane state. No allocation, resize, lock,
  file or host call occurs in `process()`/`reset()`. This statement is
  **source-level** and backed by a standalone C++ allocation probe, not a
  Rack runtime heap profiler.

## Saved example routing

`MODULAR_-_Clocked_Modulation_Studio.vcv` saves **10 modules and 16 cables**:

1. `HostTime/BEAT (out 3) → ClockedLFO/CLK (in 1)` and HostTime RESET (out 1)
   to the LFO reset input (in 2).
2. Eight-voice HostMIDI pitch goes to MorphVCO pitch and LFO RATE CV;
   its gate goes to the ADSR. LFO EOC triggers ADSR retrigger while gated.
3. LFO **SIN (out 0)** adds color to MorphVCO MORPH CV (in 2); **TRI
   (out 1)** sweeps StateFilter cutoff CV (in 1); **PULSE (out 3)** switches
   StereoEcho wet mix CV (in 4).
4. MorphVCO feeds an ADSR-controlled VCA, then StateFilter. Its separate
   low-pass/high-pass outputs feed StereoEcho left/right. Echo outputs feed
   HostAudio2 left/right at conservative stored gain.

The [factory patch coverage checker](../tools/patches/factory_patch_coverage.py)
verifies these port indices and saved cables against manifest and known
first-party source. It cannot certify the host's actual transport behavior
or audible mixing.

## Standalone verification

```sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
  tests/clocked_lfo_dsp_test.cpp -o /tmp/clocked-lfo-dsp
/tmp/clocked-lfo-dsp

python3 tests/run_dsp_tests.py
python3 -m unittest discover -s tests -p 'test_*.py' -q
python3 tools/patches/patch_inspector.py inspect \
  patches/examples/MODULAR_-_Clocked_Modulation_Studio.vcv
```

The deterministic standalone C++17 test covers quarter/half-cycle wave
samples, EOC duration, 1/4 and 2× beat division, 120-BPM-equivalent
**external** input pulses, clock glitches and dropout, Schmitt reset,
48→96 kHz rate changes, fractional period measurement, 16 isolated lanes,
hostile NaN/Inf CV/rate values, strict aggressive-fastmath behavior and zero
C++ `new`/`new[]` calls within the processing loop. Sanitized execution
with AddressSanitizer/UndefinedBehaviorSanitizer also passes, with
LeakSanitizer disabled in this environment because `/proc` inspection is
restricted. The factory patch remains a source-grounded saved graph,
**not** evidence of actual Cardinal/DAW playback.
