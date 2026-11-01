# Getting started with MODULAR-SYNTH

> **Musician's guide · Early development · Updated 2026-11-01**
>
> MODULAR-SYNTH is a [DISTRHO Cardinal](https://github.com/DISTRHO/Cardinal)-derived modular synthesizer in active development. This guide covers the **three original first-party modules** now registered in source—Morph VCO, State Filter and Macro8—and the accompanying performance patches. The guide does not imply that a publicly tested fork release exists.

## 1. What can I use today?

| Item | What exists | What is still unverified |
| --- | --- | --- |
| First-party modules | `ModularSynth/MorphVCO`, `StateFilter`, `Macro8` are registered in source and configured for the Cardinal build | Installation, GUI operation, listening quality and DAW roundtrips on real binaries |
| Factory patches | Plain-text `.vcv` files under `patches/examples/`; the first-party patch inspector checks their structure and available source-backed bounds | Audible sound, MIDI responsiveness, CPU use, clipping, patch/DAW reopen in a plugin |
| Module Forge | A C++ sine-module scaffolder, manifest checker and reviewable local integration tool | An in-app compiler, runtime hot loader, standalone instrument exporter or sandbox for arbitrary code |
| Plugin formats | The inherited Cardinal/DPF project has AU, CLAP, LV2, VST2, VST3 and standalone build variants | Whether a **MODULAR-SYNTH** build for a particular platform/host has passed real testing |
| Downloads | The [fork releases page](https://github.com/boop-bip80/MODULAR-SYNTH/releases) and [fork Actions page](https://github.com/boop-bip80/MODULAR-SYNTH/actions) are the authoritative locations | **No fork-owned release was published as of this guide's update.** Workflow jobs may be queued, cancelled or fail; an existing workflow is not a passing build |

The upstream [Cardinal releases](https://github.com/DISTRHO/Cardinal/releases) contain **upstream Cardinal**, not our new modules. Do not install an upstream build and expect to find Morph VCO, State Filter or Macro8. For a current source build, follow [the inherited build instructions](BUILDING.md) with recursive submodules, then verify your own resulting plugin and host before recording music. Do not treat this document as a promise of a ready-made download or a screenshot of a working fork binary.

## 2. Start with a patch

If you already have a **successfully built** MODULAR-SYNTH plugin containing all three models:

1. In your DAW, add the **Cardinal Synth** instrument variant to an instrument track. It has stereo audio output and accepts host MIDI. The standalone/main variants may also work with appropriate routing, but do not assume the FX variant receives MIDI the same way in every host.
2. Enable the track's MIDI input, monitoring and any necessary record-arm state. Send notes from a keyboard or a MIDI clip.
3. Open the patch File menu. If the example bank was packaged, choose **Demo patches**, or use **Open…** and browse to a `.vcv` file under `patches/examples/`.
4. Start with [`MODULAR_-_Morph_VCO_Performance.vcv`](../patches/examples/MODULAR_-_Morph_VCO_Performance.vcv). Play one note, release it, and verify that the ADSR closes the VCA.
5. Turn the **Morph** knob on the Morph VCO; its waveform moves through sine, saw and pulse regions. Lower volume before increasing resonance, drive or more complex patch gain.
6. Save a copy of the patch using the patch File menu, then save your DAW project. Reopen both and check that the patch, MIDI mapping and sound return—this is a **manual acceptance check**, not a verified result.

### The essential MIDI-to-audio wiring

When creating a patch from scratch, place these modules in order. The port numbers are zero-based internal source IDs; the UI displays meaningful jack labels. The exact connections come from the committed Cardinal Synth template and our original modules' source:

| Cable | Source jack | Destination jack | Why |
| --- | --- | --- | --- |
| 1 | `Cardinal/HostMIDI` **Pitch**, output 0 | `ModularSynth/MorphVCO` **Pitch**, input 0 | Keyboard notes set oscillator pitch at 1 V/oct |
| 2 | `Cardinal/HostMIDI` **Gate**, output 1 | `Fundamental/ADSR` **Gate**, input 4 | Note-on and note-off control the envelope |
| 3 | `ModularSynth/MorphVCO` **Morph Out**, output 0 | `ModularSynth/StateFilter` **Audio In**, input 0 | Audio enters the filter |
| 4 | `ModularSynth/StateFilter` **Low-pass Out**, output 0 | `Fundamental/VCA-1` **Audio In**, input 1 | Filtered audio enters the amplifier |
| 5 | `Fundamental/ADSR` **Out**, output 0 | `Fundamental/VCA-1` **CV In**, input 0 | Envelope controls loudness |
| 6 | `Fundamental/VCA-1` **Out**, output 0 | `Cardinal/HostAudio2` **Left/Mono In**, input 0 | Sound reaches the DAW's output |

There is **no direct MIDI-to-audio connection**. Without the VCA audio, CV and host-output cables, the oscillator can be running while the DAW remains silent. `Fundamental/ADSR` and `VCA-1` are inherited modules, not original work by this fork.

For the simplest Morph VCO performance example, the filter is omitted and Morph VCO output 0 goes directly to the VCA audio input. In the integrated performance patches, the filter is included.

## 3. Meet the original modules

### Morph VCO — musical audio source

- **Controls:** Octave (parameter 0), Fine tune (1), Wave Morph (2), Pulse Width (3), exponential FM depth (4).
- **Inputs:** 1 V/oct Pitch (0), FM (1), Morph CV (2), Pulse Width CV (3).
- **Outputs:** Morph oscillator (0), Sine oscillator (1).
- **Behavior:** Up to 16 Rack polyphony lanes, one shared phase per lane, finite pitch handling and polyBLEP reduction of saw/pulse discontinuities. That is **not** a guarantee of alias-free sound at every pitch.
- **Voltage:** The code emits approximately ±5 V peak on its audio outputs before downstream processing; adjust the receiving VCA/host level.

The base note is C4 at 0 V in the source, approximately 261.626 Hz. The FM input is scaled internally by its depth control; a disconnected FM cable and a zero depth setting leave the ordinary pitch path intact.

Source: [`MorphVCO.cpp`](../plugins/ModularSynth/src/MorphVCO.cpp), [DSP core](../plugins/ModularSynth/src/MorphVCO.hpp).

### State Filter — shape the spectrum

- **Controls:** Cutoff (parameter 0), Resonance (1), Input Drive (2).
- **Inputs:** Audio (0), Cutoff CV (1), Resonance CV (2), Drive CV (3).
- **Outputs:** Low-pass (0), Band-pass (1), High-pass (2), simultaneously available.
- **Behavior:** Up to 16 channels of trapezoidal-integrator state-variable filtering. The cutoff input follows a **1 V/oct** frequency ratio; resonance and drive CV each use 10 V for their full normalized span.
- **Safety:** The core bounds frequency, resonance, drive and output voltages. Those safeguards do not remove the need to monitor output level.

Cutoff's stored parameter is a logarithmic frequency control, not a number of hertz. A large CV change can sweep many octaves, so begin with small shifts or use Macro8's bipolar range around its center.

Source: [`StateFilter.cpp`](../plugins/ModularSynth/src/StateFilter.cpp), [DSP core](../plugins/ModularSynth/src/StateFilter.hpp).

### Macro8 — perform with CV and snapshots

Macro8 is a **controller, not an audio oscillator or amplifier**. Its eight outputs can drive the Morph VCO and State Filter's modulation inputs or other suitable CV destinations.

- **Eight knobs, eight CV outputs:** Output IDs 0–7 map to Macro 1–8. Every knob stores a normalized value from 0 to 1.
- **Voltage range per output:** By default, a knob produces **0–10 V**. Its matching Range switch can choose **-5 to +5 V**. A bipolar knob at 0.5 is approximately 0 V.
- **Transition time:** The Morph Time control (parameter 8) smooths movement toward recalled values. Its configured 0–5 s parameter describes approximately 99.9% settling, not an exact linear crossfade.
- **Four snapshot buttons:** A–D can store and recall eight knob values. **Store** mode is for writing slots; **Recall** mode is for playing them. **LIVE** returns to the physical knobs.
- **Names and state:** Macro names and the four-slot bank are serialized in a versioned `macro8Version=1` module-data structure; a DAW project roundtrip still needs verification.

#### Your first snapshot morph

1. Put Macro8 beside Morph VCO and State Filter.
2. Cable Macro8 output 0 to Morph VCO **Morph CV input 2**.
3. Cable Macro8 output 1 to State Filter **Resonance CV input 2**, and optionally output 2 to **Drive CV input 3**.
4. To vary cutoff musically, connect output 3 to State Filter **Cutoff CV input 1** and set Macro 4's Range switch to **bipolar**. Begin around the knob's 0.5 midpoint.
5. Set macro knobs to a soft sound. Switch Macro8 to **Store**, click A, then change the knobs to a brighter sound and click B.
6. Switch Macro8 back to **Recall**. Click A, then B; the outputs approach each snapshot over the Morph Time setting. Click **LIVE** to regain control of live knob values.
7. Save the patch and reopen it. Check the names, snapshots, mode and selected slot before relying on the performance.

Because the Store toggle changes what the A–D buttons do, always verify the mode before clicking a slot you want to preserve.

Source: [`Macro8.cpp`](../plugins/ModularSynth/src/Macro8.cpp), [snapshot/DSP core](../plugins/ModularSynth/src/Macro8.hpp).

## 4. Choose a sound-design patch

| Patch | Musical use | What to play or change |
| --- | --- | --- |
| [Morphing State Pad](../patches/examples/MODULAR_-_Morphing_State_Pad.vcv) | First complete MorphVCO + StateFilter + Macro8 performance setup | MIDI note/chord; recall A/B for a roughly one-second timbral transition |
| [Cinematic Drift Pad](../patches/examples/MODULAR_-_Cinematic_Drift_Pad.vcv) | Sustained bed and slowly shifting harmonic texture | Hold a chord; manually recall A/B for a four-second macro transition |
| [Rhythmic Grit Bass](../patches/examples/MODULAR_-_Rhythmic_Grit_Bass.vcv) | Tight low-register, modulated bass | Program short DAW MIDI notes; recall A/B for quick 0.20-second growl changes |

There is also the simpler [Morph VCO Performance](../patches/examples/MODULAR_-_Morph_VCO_Performance.vcv) patch, which introduces the oscillator before adding State Filter and Macro8.

The **Cinematic Drift** patch is driven by held MIDI and *manual* snapshot morphs, not a self-running LFO; the **Rhythmic Grit** patch's rhythm comes from incoming MIDI, not an internal sequencer. Their documented gains are reduced, but they have not been listening-tested in a finished fork binary. See [Patch Workflow](PATCH_WORKFLOW.md) for detailed cable inventories, parameter choices and inspection caveats. Older examples using community modules are documented separately in [Factory Patches](FACTORY_PATCHES.md).

## 5. Validate a patch before recording

The included inspector runs offline with Python 3.10+ and **does not require a compiled audio plugin**:

```sh
python3 tools/patches/patch_inspector.py inspect patches/examples/MODULAR_-_Morphing_State_Pad.vcv
python3 tools/patches/patch_inspector.py validate \
  patches/examples/MODULAR_-_Cinematic_Drift_Pad.vcv \
  patches/examples/MODULAR_-_Rhythmic_Grit_Bass.vcv
python3 -m unittest discover -s tests -p 'test_patch_tools.py' -v
```

`inspect` shows module inventory, cable graph, connected groups and errors/warnings. `validate` returns failure on structural errors; `--json` provides machine-readable output. The inspector checks first-party source-derived counts and ranges where it can determine them. It **does not** guarantee actual plugin/module availability, audible sound, correct semantic signal type or third-party port bounds. For pinned Fundamental/Cardinal modules with unavailable machine-readable schemas, it reports honest warnings.

Use a real instrument build and listen after validation. Save/reload the patch and your DAW project, try 44.1/48/96 kHz and different buffer sizes as practical, then record observations. Passing JSON checks is only the beginning.

## 6. Troubleshooting

| Symptom | Check |
| --- | --- |
| **Original modules missing** | You may be using an upstream Cardinal release or a build predating their registration. Use a verified build of this fork containing `ModularSynth`; check submodules and build logs. |
| **No sound at all** | Confirm the DAW track receives MIDI and the instrument is monitored. Check HostMIDI Pitch → MorphVCO Pitch, HostMIDI Gate → ADSR Gate, ADSR Out → VCA CV, audio path → VCA Audio → HostAudio2 Left/Mono. |
| **Oscillator sounds constantly** | The oscillator can run without a note; route it through a correctly gated ADSR/VCA rather than directly to HostAudio2. Verify note-off reaches HostMIDI and closes the envelope. |
| **Very quiet or unexpectedly loud** | Check the VCA level, HostAudio2 gain, track gain and filter resonance/drive. The example patches start conservatively; lower volume before changing them. |
| **Pitch seems wrong** | Check the MIDI channel/keyboard octave, MorphVCO Octave/Fine, and unintended FM input/depth or pitch CV cables. Pitch is 1 V/oct, not 1 V per semitone. |
| **Filter stuck bright/dark** | Check the Cutoff CV connection and whether Macro8 output 3 is bipolar. A large 0–10 V cutoff CV can move frequency many octaves. |
| **Snapshots do not change the sound** | Check that Macro8 is in Recall mode, the selected slots contain data, and its outputs are actually cabled to CV destinations. LIVE deliberately returns to knob values. |
| **Patch changed after reopening** | Save a dedicated `.vcv` copy and the DAW session, reopen both and compare modules, cables, snapshots and controls. Report reproducible differences rather than assuming compatibility. |
| **Missing third-party module warning** | Some examples rely on bundled, pinned Fundamental or other Cardinal modules. Verify a recursive checkout and the specific build selection; the inspector cannot attest to every third-party binary. |

## 7. Make your own oscillator with Module Forge

Module Forge currently generates a **starter source module**. It does not compile or install it automatically. From the repository root:

```sh
python3 tools/module-forge/module_forge.py new \
  --slug OrbitSine --name "Orbit Sine" --out module-forge-output
python3 tools/module-forge/module_forge.py check module-forge-output/OrbitSine
```

Review the generated C++ and SVG artwork. To preview the changes that would integrate it into the static `ModularSynth` collection:

```sh
python3 tools/module-forge/integrate.py module-forge-output/OrbitSine --repo-root .
```

Only after reviewing the diff and preserving your own changes should you opt in to applying the integration:

```sh
python3 tools/module-forge/integrate.py module-forge-output/OrbitSine --repo-root . --apply
```

The integration tool edits the first-party source, panel, build and registration files; it refuses unsafe/mismatched plans and attempts rollback if a write fails. You must still build, test and audition the result. Read the full [Module Forge developer guide](MODULE_FORGE.md), including recovery and compatibility notes, before using `--apply`. Do not use this workflow on untrusted DSP code without review.

## 8. Credits and next steps

- This project derives from [DISTRHO Cardinal](https://github.com/DISTRHO/Cardinal), based on [VCV Rack](https://github.com/VCVRack/Rack), with the [DISTRHO Plugin Framework](https://github.com/DISTRHO/DPF) and many third-party modules.
- The original `ModularSynth` collection, Module Forge work and example arrangements are separate new contributions; do not present inherited module collections or upstream binaries as our own.
- Cardinal's code is GPL-3.0-or-later, and bundled module/panel/font licenses vary. See [the repository license inventory](LICENSES.md) and preserve source/artwork attribution.
- Follow [the six-phase development roadmap](DEVELOPMENT_ROADMAP.md) and [the current fork's Actions](https://github.com/boop-bip80/MODULAR-SYNTH/actions) for evidence. A sound-quality judgment requires tested audio output, not screenshots or file presence.

**If you are a musician evaluating this now:** treat it as an early source project and experimental instrument, with promising original building blocks but no verified downloadable fork release yet.
