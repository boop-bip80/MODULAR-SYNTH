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
- A readable inventory, a directed cable list and graph-connected components, including disconnected utility/note modules.

### Important limitations

The first-party manifest establishes that a model is **declared in source**, not that a particular binary was built. The simple C++ schema reader handles ordinal enum declarations and literal `configParam` ranges; if it cannot parse a module, the report explicitly warns that its bounds were not verified. It does **not** execute C++, infer every arbitrary Rack widget convention or check semantic voltage/audio compatibility.

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
