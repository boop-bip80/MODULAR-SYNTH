# Patch workflow: offline inspection and the Morph VCO example

This workflow is part of Phase 1. It makes bundled plain-text `.vcv` patches easier to review and catches basic graph mistakes before loading them in an audio host. **It is not a Rack audio renderer, plugin loader or guarantee that a patch sounds correct.**

## Commands

Run from the repository root with Python 3.10+ and no extra pip dependencies:

```sh
python3 tools/patches/patch_inspector.py validate patches/examples/MODULAR_-_Morph_VCO_Performance.vcv
python3 tools/patches/patch_inspector.py inspect patches/examples/MODULAR_-_Morph_VCO_Performance.vcv
python3 tools/patches/patch_inspector.py inspect patches/examples/MODULAR_-_Morph_VCO_Performance.vcv --json
python3 tools/patches/patch_inspector.py validate patches/templates/synth.vcv
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

`validate` exits 0 when structurally valid and 1 on errors. `inspect` additionally shows all connections in a readable module/port graph. `--json` emits machine-readable reports for CI and editors. Multiple patch paths can be supplied in one command. For a different source root, use `--repo-root`.

The tool catches:

- Broken UTF-8/JSON, duplicate JSON object keys, and JSON `NaN` / `Infinity`.
- Missing or malformed `version`, module and cable arrays.
- Duplicate/invalid module IDs, cable IDs and per-module parameter IDs.
- Missing cable endpoints, invalid/negative port indices and two cables routed into the **same input jack**.
- Non-numeric and non-finite parameter values.
- Unknown first-party `plugin/model` combinations based on checked-in Cardinal and ModularSynth manifests.
- First-party ModularSynth input/output/parameter count violations and declared `configParam` range violations **when the simple source schema can be read**.
- Checked-in Cardinal **HostMIDI** (12 inputs/12 outputs), **HostTime** (eight outputs) and **HostAudio2** (two input/output jacks and saved level range 0–2) bounds, guarded by expected source declarations. Other Cardinal models remain unverified unless a reviewed schema is added.
- A readable inventory, a directed cable list and graph-connected components, including disconnected utility/note modules.

### Important limitations

The first-party manifest establishes that a model is **declared in source**, not that a particular binary was built. The C++ schema reader handles original-module ordinal enums and literal `configParam` ranges plus three narrow Cardinal host declarations. If a source signature no longer matches, the report explicitly warns that its bounds were not verified. It does **not** execute C++, infer every arbitrary Rack widget convention or check semantic voltage/audio compatibility. HostAudio2's two declared jacks are present in source but actual terminal processing depends on the plugin variant; no audio-output behavior is inferred.

Third-party modules are a different case: this repository uses pinned git submodules, and their source manifests or port boundaries are not generally available to the offline inspector. Module names observed in committed stock Cardinal patch templates are recognized as historical references but **still get unverified bounds warnings**. An unknown third-party module is a warning by default, not a false assertion of correctness. Use `--strict-unknown` to make all non-first-party plugin/model pairs errors; because factory patches use bundled third-party modules, this strict mode is best for testing isolated first-party-only patches.

The inspector also cannot prove:

- DSP correctness, sound output, synthesis quality, host output volume or absence of audio clipping.
- Real plugin/module availability in a specific compiled binary, asset-file compatibility, patch migration or DAW state roundtrips.
- Correct metadata/ports for arbitrary third-party modules; these remain unverified until a matching pinned manifest/schema is supplied.
- Whether a patch creates a desirable sound. Run an actual host smoke test and measure audio output.

## Play the first-party Morph VCO patch

Open [`patches/examples/MODULAR_-_Morph_VCO_Performance.vcv`](../patches/examples/MODULAR_-_Morph_VCO_Performance.vcv) in a build of **this fork** that contains `ModularSynth/MorphVCO` (upstream Cardinal builds do **not** contain it). The patch is based on the bundled Cardinal Synth template, with its original VCO replaced by the new first-party Morph VCO.

1. Insert the **Cardinal Synth** plugin (or use a compatible standalone/main variant).
2. From the patch File menu, open `MODULAR_-_Morph_VCO_Performance.vcv`.
3. Route your DAW keyboard or MIDI controller into Cardinal's MIDI input; the saved Host MIDI mapping uses channel 1/all defaults inherited from the working Synth template.
4. Play and release notes. **HostMIDI pitch** drives Morph VCO's 1 V/oct pitch input; **HostMIDI gate** drives the ADSR. The ADSR opens the VCA, and the oscillator's morph output goes into the VCA audio input.
5. Try the **MORPH** knob: sine to saw to pulse; use **PULSE WIDTH** to shape the pulse region. The patch leaves FM depth at zero initially, so a disconnected FM jack does not change pitch.
6. Stop playback before altering output routing or monitoring high-gain chains. VCA level is 0.5 and the Cardinal HostAudio2 level is 0.35 in the saved patch, deliberately below full scale.

### Wiring inventory

| Source | Destination | Meaning |
| --- | --- | --- |
| `Cardinal/HostMIDI` output 0 | `ModularSynth/MorphVCO` input 0 | Note pitch (1 V/oct) |
| `Cardinal/HostMIDI` output 1 | `Fundamental/ADSR` input 4 | Note gate |
| `Fundamental/ADSR` output 0 | `Fundamental/VCA-1` input 0 | Amplitude envelope |
| `ModularSynth/MorphVCO` output 0 | `Fundamental/VCA-1` input 1 | Oscillator audio |
| `Fundamental/VCA-1` output 0 | `Cardinal/HostAudio2` input 0 | Audio to the host |

`Fundamental/ADSR` and `Fundamental/VCA-1` are known bundled modules copied from the upstream Synth template, not newly created by MODULAR-SYNTH. The TextEditor module is intentionally unconnected and contains a quick in-patch guide.

**Audio validation status:** The patch graph was constructed from committed Cardinal templates and MorphVCO source port definitions. Its audio output, keyboard response and host reload behavior must still be verified with a built plugin; no test result is implied by the presence of the JSON file.

## Adding or changing a patch

1. Create a new plain-text `.vcv` file under `patches/examples/` with a descriptive name and unique, stable numeric module/cable IDs.
2. Run `validate` and `inspect`; fix all structural errors.
3. Pay attention to warnings about third-party modules and unknown port bounds; check pinned module source when necessary.
4. Load it in a fork-built plugin. Verify voice/gate handling, sound level, patch save/reopen and DAW project reload.
5. Include a short explanation of signal flow, required MIDI/CV connections, licenses for any samples/assets, and any known runtime limitations.
6. If new module identifiers, port definitions or parameter IDs change, add regression tests and update the example or document migration behavior.

The validation script should remain **strict about what it knows and honest about what it cannot know**. Do not silence meaningful warnings by inventing module or port schema data.

To review a patch after a save/reload or handoff, compare the two saved `.vcv`
files with [`patch_compare.py`](PATCH_COMPARISON.md). Its conservative state diff
now detects changed HostMIDI mappings, arbitrary module `data`, bypass/version
metadata and unknown top-level patch state as well as parameters and cables;
only documented view-only layout fields are ignored. This is useful evidence of
serialized differences, **not** proof that a DAW successfully restored or
executed the patch, and it cannot detect changes in external referenced assets.


## Second example — Morphing State Pad

Open [`patches/examples/MODULAR_-_Morphing_State_Pad.vcv`](../patches/examples/MODULAR_-_Morphing_State_Pad.vcv) in a fork build containing **all three** first-party models: `MorphVCO`, `StateFilter` and `Macro8`. An upstream Cardinal release or an older fork build without the models will not load this patch correctly.

This performance-oriented patch combines the original Morph VCO, the three-mode trapezoidal-integrator State Filter and Macro8's eight controllable CV outputs/four-slot snapshot bank. Only three macro outputs are initially wired. The MIDI gate drives a stock Fundamental ADSR, the audio route goes through its stock VCA, and HostAudio2's stored gain is reduced to 0.30. No external samples, network resources or non-bundled plugins are required.

| Source | Destination | Behavior |
| --- | --- | --- |
| `Cardinal/HostMIDI` output 0 | `ModularSynth/MorphVCO` input 0 | MIDI note pitch |
| `Cardinal/HostMIDI` output 1 | `Fundamental/ADSR` input 4 | MIDI note gate |
| `ModularSynth/Macro8` output 0 | `ModularSynth/MorphVCO` input 2 | Unipolar Shape macro CV |
| `ModularSynth/Macro8` output 1 | `ModularSynth/StateFilter` input 2 | Unipolar Resonance macro CV |
| `ModularSynth/Macro8` output 2 | `ModularSynth/StateFilter` input 3 | Unipolar Drive macro CV |
| `ModularSynth/MorphVCO` output 0 | `ModularSynth/StateFilter` input 0 | Morphing oscillator into filter |
| `ModularSynth/StateFilter` output 0 | `Fundamental/VCA-1` input 1 | Low-pass filtered audio |
| `Fundamental/ADSR` output 0 | `Fundamental/VCA-1` input 0 | Gate envelope controls loudness |
| `Fundamental/VCA-1` output 0 | `Cardinal/HostAudio2` input 0 | Controlled audio to the DAW |

### Playing and morphing

1. Route MIDI to the Cardinal Synth plugin and play sustained notes. No MIDI should mean the ADSR closes the VCA.
2. Adjust Macro8's first three macro knobs, named **Shape**, **Resonance** and **Drive**. Each defaults to the 0-to-10 V output range; Morph VCO and State Filter scale these CV inputs internally. The macro knobs and defaults were chosen to avoid an excessive initial drive/resonance setting.
3. Macro8 includes two stored example snapshots, **A** (soft) and **B** (brighter/more resonant). While in Recall mode, click A and B to hear the macros transition over the configured 1.0-second settling period. Use **LIVE** to return to the live knob values.
4. To store your own sound, switch to Macro8 **Store** mode, set the macro knobs, click a snapshot button, and switch back to Recall. Confirm you understand the selected mode before replacing the example slots.
5. The State Filter's low-pass output is intentionally used; you can experiment with band-pass/high-pass routing only after lowering monitoring level.

### Validation and limitations

- Source-backed schema assertions cover registered first-party models, including 5-parameter/4-input/2-output MorphVCO, 3-parameter/4-input/3-output StateFilter, and 23-parameter/0-input/8-output Macro8.
- The inspector extracts literal parameter ranges, Rack button ranges, and the simple indexed bank definitions used by Macro8. Complex C++ config logic remains explicitly unverified.
- The example stores Macro8's documented `macro8Version=1`, names and eight-value snapshot arrays so patch save/reopen can be manually checked.
- **No listening test, DAW reload test or headless audio render is claimed here.** The graph and parameter bounds are structural only. After a successful fork build, verify MIDI note-on/note-off, snapshot recall and interpolation, gain safety, and project roundtrip in an actual DAW.

To check this particular file:

```sh
python3 tools/patches/patch_inspector.py inspect patches/examples/MODULAR_-_Morphing_State_Pad.vcv
python3 -m unittest discover -s tests -p 'test_patch_tools.py' -v
```


## Further cinematic presets — controlled motion and rhythmic bass

Two additional first-party performance patches use the same source-template host and envelope components as Morphing State Pad: `Cardinal/HostMIDI`, `Fundamental/ADSR`, `Fundamental/VCA-1` and `Cardinal/HostAudio2`. They also use the **three original `ModularSynth` models required by these patches**: `MorphVCO`, `StateFilter` and `Macro8`.

In both patches, the audio path is **MIDI pitch → MorphVCO → StateFilter low-pass → VCA → HostAudio2**, while **MIDI gate → ADSR → VCA CV** provides note-off silence. Macro8 outputs 0/1/2/3 respectively modulate oscillator morph, filter resonance, filter drive and filter cutoff. Output 3 uses its **bipolar -5 to +5 V mode**; the first three outputs are unipolar 0 to 10 V. The templates use conservative VCA and HostAudio gains.

These are plain-text `.vcv` files using pinned/bundled modules, not premixed WAV assets or independent exported plugins.

### Cinematic Drift Pad

[`MODULAR_-_Cinematic_Drift_Pad.vcv`](../patches/examples/MODULAR_-_Cinematic_Drift_Pad.vcv)

- Purpose: a soft, sustained harmonic bed whose timbre can change slowly through Macro8 snapshot transitions.
- ADSR attack 0.55, decay 0.80, sustain 0.85, release 0.85 (normalized module knobs); the values are not literal seconds.
- MorphVCO starts at concert-register pitch with a slightly sharpened fine tuning; StateFilter low-pass starts around the mid-frequency region.
- **Macro8 morph time = 4.0 seconds** (approximately 99.9% settling), with snapshot A quieter/darker and snapshot B brighter/more resonant and driven.
- VCA gain = 0.26, HostAudio2 level = 0.24. Start with low monitoring volume, especially when recalling brighter snapshots.

For evolving motion, sustain a MIDI chord or note and alternate Macro8 **A** and **B** in Recall mode; use **LIVE** to return to the physical macro knobs. This patch has **manual snapshot morphing**, not a free-running LFO or autonomous generative sequence. It is designed as a starting point for cinematic texture performance, not a claim of reviewed cinematic audio quality.

### Rhythmic Grit Bass

[`MODULAR_-_Rhythmic_Grit_Bass.vcv`](../patches/examples/MODULAR_-_Rhythmic_Grit_Bass.vcv)

- Purpose: a low-register bass voice for tightly gated short notes, syncopation and evolving grit.
- MorphVCO octave = -2; StateFilter low-pass cutoff is set lower than the pad, with moderately higher resonance and drive.
- Short ADSR attack 0.005, decay 0.14, sustain 0.25 and release 0.11 (normalized knob values). Play short MIDI notes.
- **Macro8 morph time = 0.20 seconds**, with snapshot A cleaner/subbier and B brighter, raspier and more resonant.
- VCA gain = 0.32 and HostAudio2 level = 0.23 to reduce monitoring level before experimenting with resonant snapshots.

The rhythmic sequence comes from your **DAW or MIDI keyboard**, not from a built-in step sequencer; this template does not generate notes by itself. Use the A/B buttons for short growl sweeps, and keep your monitoring level conservative when increasing resonance or drive.

### Structural checks and manual audio checklist

From the repository root:

```sh
python3 tools/patches/patch_inspector.py validate \
  patches/examples/MODULAR_-_Cinematic_Drift_Pad.vcv \
  patches/examples/MODULAR_-_Rhythmic_Grit_Bass.vcv
python3 tools/patches/patch_inspector.py inspect patches/examples/MODULAR_-_Cinematic_Drift_Pad.vcv
python3 -m unittest discover -s tests -p 'test_patch_tools.py' -v
```

The tests require each new patch to have eight modules, ten valid cables, four specific Macro8 CV routes, bipolar output 3 for cutoff, finite and range-checked first-party parameters, two eight-value snapshots, and low stored audio gains. The inspector now verifies three inherited Cardinal host port contracts directly from checked-in source, while Fundamental and other Cardinal module ports remain unverified.

For **actual** acceptance, build this fork with the three original modules **required by these patches** (MorphVCO, StateFilter and Macro8), load both patches in Cardinal Synth, verify MIDI note-on/note-off and host output, check A/B/LIVE transitions, confirm no unexpected clipping, and save/reopen the DAW project. **Those listening and host tests are not claimed by these JSON validation steps.**
