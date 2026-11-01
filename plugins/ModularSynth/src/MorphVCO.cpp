/*
 * MODULAR-SYNTH Morph VCO — original first-party module
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "plugin.hpp"
#include "MorphVCO.hpp"

#include <algorithm>
#include <cmath>
#include <memory>

struct ModularSynthMorphVCO : Module {
    enum ParamIds {
        OCTAVE_PARAM,
        FINE_PARAM,
        MORPH_PARAM,
        PULSE_WIDTH_PARAM,
        FM_DEPTH_PARAM,
        NUM_PARAMS
    };
    enum InputIds {
        PITCH_INPUT,
        FM_INPUT,
        MORPH_CV_INPUT,
        PWM_CV_INPUT,
        NUM_INPUTS
    };
    enum OutputIds {
        MORPH_OUTPUT,
        SINE_OUTPUT,
        NUM_OUTPUTS
    };
    enum LightIds {
        NUM_LIGHTS
    };

    // Rack uses at most 16 polyphony lanes per jack.
    modular_synth::dsp::MorphOscillator voices[16];

    ModularSynthMorphVCO() {
        config(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS);
        configParam(OCTAVE_PARAM, -4.0f, 4.0f, 0.0f, "Octave");
        getParamQuantity(OCTAVE_PARAM)->snapEnabled = true;
        configParam(FINE_PARAM, -100.0f, 100.0f, 0.0f, "Fine tune", " cents");
        configParam(MORPH_PARAM, 0.0f, 1.0f, 0.0f, "Wave morph");
        configParam(PULSE_WIDTH_PARAM, 0.05f, 0.95f, 0.5f, "Pulse width");
        configParam(FM_DEPTH_PARAM, 0.0f, 1.0f, 0.0f, "Exponential FM depth");
        configInput(PITCH_INPUT, "Pitch (1 V/oct)");
        configInput(FM_INPUT, "Exponential FM (5 V / octave at full depth)");
        configInput(MORPH_CV_INPUT, "Wave morph (0 to 10 V)");
        configInput(PWM_CV_INPUT, "Pulse width modulation (10 V full span)");
        configOutput(MORPH_OUTPUT, "Morph oscillator");
        configOutput(SINE_OUTPUT, "Sine oscillator");
    }

    void onReset() override {
        for (auto& voice : voices)
            voice.reset();
    }

    void process(const ProcessArgs& args) override {
        int channels = std::max(1, inputs[PITCH_INPUT].getChannels());
        channels = std::max(channels, inputs[FM_INPUT].getChannels());
        channels = std::max(channels, inputs[MORPH_CV_INPUT].getChannels());
        channels = std::max(channels, inputs[PWM_CV_INPUT].getChannels());
        channels = std::min(channels, 16);

        outputs[MORPH_OUTPUT].setChannels(channels);
        outputs[SINE_OUTPUT].setChannels(channels);

        const double baseOctave = params[OCTAVE_PARAM].getValue();
        const double fineOctave = params[FINE_PARAM].getValue() / 1200.0;
        const float baseMorph = params[MORPH_PARAM].getValue();
        const float baseWidth = params[PULSE_WIDTH_PARAM].getValue();
        const double fmDepth = params[FM_DEPTH_PARAM].getValue();

        for (int c = 0; c < channels; ++c) {
            const double pitchCV = inputs[PITCH_INPUT].getNormalPolyVoltage(0.0f, c);
            const double fmCV = inputs[FM_INPUT].getNormalPolyVoltage(0.0f, c);
            const double pitchOctave = baseOctave + fineOctave + pitchCV + (fmCV / 5.0) * fmDepth;
            // Keep pitch and FM sanitization independent of compiler
            // fast-math assumptions; the DSP helper clamps to +/-20 octaves.
            // Frequency is then capped by the oscillator below Nyquist.
            const double hz = modular_synth::dsp::MorphOscillator::frequencyForPitch(pitchOctave);
            const float morph = baseMorph + inputs[MORPH_CV_INPUT].getNormalPolyVoltage(0.0f, c) * 0.1f;
            const float width = baseWidth + inputs[PWM_CV_INPUT].getNormalPolyVoltage(0.0f, c) * 0.1f;

            const auto sample = voices[c].process(hz, args.sampleRate, morph, width);
            outputs[MORPH_OUTPUT].setVoltage(5.0f * sample.morph, c);
            outputs[SINE_OUTPUT].setVoltage(5.0f * sample.sine, c);
        }
    }
};

#ifndef HEADLESS
struct ModularSynthMorphVCOWidget : ModuleWidget {
    std::shared_ptr<Font> labelFont;

    explicit ModularSynthMorphVCOWidget(ModularSynthMorphVCO* const module) {
        setModule(module);
        setPanel(APP->window->loadSvg(asset::plugin(pluginInstance, "res/MorphVCO.svg")));
        // Existing Cardinal modules use this bundled, known font. Keep a
        // real Font handle rather than assuming NanoVG font ID zero exists.
        labelFont = APP->window->loadFont(asset::system("res/fonts/ShareTechMono-Regular.ttf"));

        addChild(createWidget<ScrewSilver>(Vec(0.0f, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(0.0f, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH,
                                                RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));

        addParam(createParamCentered<RoundBlackKnob>(Vec(50.0f, 82.0f), module,
                                                      ModularSynthMorphVCO::OCTAVE_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(130.0f, 82.0f), module,
                                                      ModularSynthMorphVCO::FINE_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(52.0f, 164.0f), module,
                                                      ModularSynthMorphVCO::MORPH_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(128.0f, 164.0f), module,
                                                      ModularSynthMorphVCO::PULSE_WIDTH_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(90.0f, 229.0f), module,
                                                      ModularSynthMorphVCO::FM_DEPTH_PARAM));

        addInput(createInputCentered<PJ301MPort>(Vec(28.0f, 301.0f), module,
                                                  ModularSynthMorphVCO::PITCH_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(69.0f, 301.0f), module,
                                                  ModularSynthMorphVCO::FM_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(111.0f, 301.0f), module,
                                                  ModularSynthMorphVCO::MORPH_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(152.0f, 301.0f), module,
                                                  ModularSynthMorphVCO::PWM_CV_INPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(55.0f, 352.0f), module,
                                                    ModularSynthMorphVCO::MORPH_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(125.0f, 352.0f), module,
                                                    ModularSynthMorphVCO::SINE_OUTPUT));
    }

    void draw(const DrawArgs& args) override {
        ModuleWidget::draw(args);

        if (!labelFont)
            return;
        nvgFontFaceId(args.vg, labelFont->handle);
        nvgTextAlign(args.vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);
        nvgFillColor(args.vg, nvgRGB(0xF3, 0xF1, 0xFF));
        nvgFontSize(args.vg, 17.0f);
        nvgText(args.vg, 90.0f, 21.0f, "MORPH VCO", nullptr);

        nvgFontSize(args.vg, 10.5f);
        nvgFillColor(args.vg, nvgRGB(0xB4, 0xB7, 0xD7));
        nvgText(args.vg, 90.0f, 38.0f, "MODULAR-SYNTH", nullptr);

        nvgFontSize(args.vg, 11.0f);
        nvgFillColor(args.vg, nvgRGB(0xDB, 0xDE, 0xFF));
        nvgText(args.vg, 50.0f, 53.0f, "OCTAVE", nullptr);
        nvgText(args.vg, 130.0f, 53.0f, "FINE", nullptr);
        nvgText(args.vg, 52.0f, 136.0f, "WAVE", nullptr);
        nvgText(args.vg, 128.0f, 136.0f, "WIDTH", nullptr);
        nvgText(args.vg, 90.0f, 202.0f, "FM DEPTH", nullptr);

        nvgFontSize(args.vg, 10.0f);
        nvgFillColor(args.vg, nvgRGB(0x93, 0xCF, 0xFF));
        nvgText(args.vg, 28.0f, 271.0f, "1V/OCT", nullptr);
        nvgText(args.vg, 69.0f, 271.0f, "FM", nullptr);
        nvgText(args.vg, 111.0f, 271.0f, "MORPH", nullptr);
        nvgText(args.vg, 152.0f, 271.0f, "PWM", nullptr);

        nvgFontSize(args.vg, 11.0f);
        nvgFillColor(args.vg, nvgRGB(0xD6, 0xAD, 0xFF));
        nvgText(args.vg, 55.0f, 329.0f, "WAVE", nullptr);
        nvgText(args.vg, 125.0f, 329.0f, "SINE", nullptr);
    }
};
#else
struct ModularSynthMorphVCOWidget : ModuleWidget {
    explicit ModularSynthMorphVCOWidget(ModularSynthMorphVCO* const module) {
        setModule(module);
    }
};
#endif

Model* modelMorphVCO = createModel<ModularSynthMorphVCO, ModularSynthMorphVCOWidget>("MorphVCO");
