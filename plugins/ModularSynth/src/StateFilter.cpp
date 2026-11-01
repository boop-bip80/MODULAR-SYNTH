/*
 * MODULAR-SYNTH State Filter — original first-party module.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "plugin.hpp"
#include "StateFilter.hpp"

#include <algorithm>
#include <cmath>
#include <memory>

struct ModularSynthStateFilter : Module {
    enum ParamIds {
        CUTOFF_PARAM,
        RESONANCE_PARAM,
        DRIVE_PARAM,
        NUM_PARAMS
    };
    enum InputIds {
        AUDIO_INPUT,
        CUTOFF_CV_INPUT,
        RESONANCE_CV_INPUT,
        DRIVE_CV_INPUT,
        NUM_INPUTS
    };
    enum OutputIds {
        LOWPASS_OUTPUT,
        BANDPASS_OUTPUT,
        HIGHPASS_OUTPUT,
        NUM_OUTPUTS
    };
    enum LightIds {
        NUM_LIGHTS
    };

    modular_synth::dsp::StateFilter voices[16];
    int previousChannels = 0;

    ModularSynthStateFilter() {
        config(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS);
        // The knob stores log2(hz/1000). Display is actual frequency in Hz.
        configParam(CUTOFF_PARAM, -5.643856f, 4.321928f, 0.0f,
                    "Cutoff", " Hz", 2.0f, 1000.0f);
        configParam(RESONANCE_PARAM, 0.0f, 1.0f, 0.0f,
                    "Resonance amount", " %", 0.0f, 100.0f);
        configParam(DRIVE_PARAM, 0.0f, 1.0f, 0.0f,
                    "Input drive amount", " %", 0.0f, 100.0f);
        configInput(AUDIO_INPUT, "Audio signal input");
        configInput(CUTOFF_CV_INPUT, "Cutoff CV (1 V/oct; adds to knob)");
        configInput(RESONANCE_CV_INPUT, "Resonance CV (10 V full span; adds to knob)");
        configInput(DRIVE_CV_INPUT, "Drive CV (10 V full span; adds to knob)");
        configOutput(LOWPASS_OUTPUT, "Low-pass filtered audio");
        configOutput(BANDPASS_OUTPUT, "Band-pass filtered audio");
        configOutput(HIGHPASS_OUTPUT, "High-pass filtered audio");
    }

    void onReset() override {
        for (auto& voice : voices)
            voice.reset();
        previousChannels = 0;
    }

    void process(const ProcessArgs& args) override {
        int channels = std::max(1, inputs[AUDIO_INPUT].getChannels());
        channels = std::max(channels, inputs[CUTOFF_CV_INPUT].getChannels());
        channels = std::max(channels, inputs[RESONANCE_CV_INPUT].getChannels());
        channels = std::max(channels, inputs[DRIVE_CV_INPUT].getChannels());
        channels = std::min(channels, 16);

        // Retire disappearing channels before writing outputs. Otherwise a
        // re-expanded lane can emit stale integrator energy from a voice
        // that was disconnected many samples earlier.
        for (int c = channels; c < previousChannels; ++c)
            voices[c].reset();
        previousChannels = channels;

        outputs[LOWPASS_OUTPUT].setChannels(channels);
        outputs[BANDPASS_OUTPUT].setChannels(channels);
        outputs[HIGHPASS_OUTPUT].setChannels(channels);

        const double baseOctaves = params[CUTOFF_PARAM].getValue();
        const double baseResonance = params[RESONANCE_PARAM].getValue();
        const double baseDrive = params[DRIVE_PARAM].getValue();

        for (int c = 0; c < channels; ++c) {
            const double input = inputs[AUDIO_INPUT].getNormalPolyVoltage(0.0f, c);
            const double cutoffCV = inputs[CUTOFF_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            const double resonanceCV = inputs[RESONANCE_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            const double driveCV = inputs[DRIVE_CV_INPUT].getNormalPolyVoltage(0.0f, c);

            // Limit the exponent before exp2(), even under malicious/extreme CV.
            const double octave = modular_synth::dsp::StateFilter::finiteClamp(
                baseOctaves + (modular_synth::dsp::StateFilter::ieeeFinite(cutoffCV) ? cutoffCV : 0.0),
                0.0, -30.0, 30.0);
            const double frequency = 1000.0 * std::exp2(octave);
            const double resonance = baseResonance
                + (modular_synth::dsp::StateFilter::ieeeFinite(resonanceCV) ? resonanceCV * 0.1 : 0.0);
            const double drive = baseDrive
                + (modular_synth::dsp::StateFilter::ieeeFinite(driveCV) ? driveCV * 0.1 : 0.0);

            const auto sample = voices[c].process(input, args.sampleRate,
                                                   frequency, resonance, drive);
            outputs[LOWPASS_OUTPUT].setVoltage(sample.low, c);
            outputs[BANDPASS_OUTPUT].setVoltage(sample.band, c);
            outputs[HIGHPASS_OUTPUT].setVoltage(sample.high, c);
        }
    }
};

#ifndef HEADLESS
struct ModularSynthStateFilterWidget : ModuleWidget {
    std::shared_ptr<Font> labelFont;

    explicit ModularSynthStateFilterWidget(ModularSynthStateFilter* const module) {
        setModule(module);
        setPanel(APP->window->loadSvg(asset::plugin(pluginInstance, "res/StateFilter.svg")));
        labelFont = APP->window->loadFont(asset::system("res/fonts/ShareTechMono-Regular.ttf"));

        addChild(createWidget<ScrewSilver>(Vec(0.0f, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(0.0f, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH,
                                                RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));

        addParam(createParamCentered<RoundBlackKnob>(Vec(59.0f, 99.0f), module,
                                                      ModularSynthStateFilter::CUTOFF_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(150.0f, 99.0f), module,
                                                      ModularSynthStateFilter::RESONANCE_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(105.0f, 177.0f), module,
                                                      ModularSynthStateFilter::DRIVE_PARAM));

        addInput(createInputCentered<PJ301MPort>(Vec(28.0f, 269.0f), module,
                                                  ModularSynthStateFilter::AUDIO_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(79.0f, 269.0f), module,
                                                  ModularSynthStateFilter::CUTOFF_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(131.0f, 269.0f), module,
                                                  ModularSynthStateFilter::RESONANCE_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(182.0f, 269.0f), module,
                                                  ModularSynthStateFilter::DRIVE_CV_INPUT));

        addOutput(createOutputCentered<PJ301MPort>(Vec(49.0f, 350.0f), module,
                                                    ModularSynthStateFilter::LOWPASS_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(105.0f, 350.0f), module,
                                                    ModularSynthStateFilter::BANDPASS_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(161.0f, 350.0f), module,
                                                    ModularSynthStateFilter::HIGHPASS_OUTPUT));
    }

    void draw(const DrawArgs& args) override {
        ModuleWidget::draw(args);
        if (!labelFont)
            return;

        nvgFontFaceId(args.vg, labelFont->handle);
        nvgTextAlign(args.vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);

        nvgFillColor(args.vg, nvgRGB(0xF3, 0xF1, 0xFF));
        nvgFontSize(args.vg, 17.0f);
        nvgText(args.vg, 105.0f, 22.0f, "STATE FILTER", nullptr);
        nvgFillColor(args.vg, nvgRGB(0xB4, 0xB7, 0xD7));
        nvgFontSize(args.vg, 10.5f);
        nvgText(args.vg, 105.0f, 40.0f, "MODULAR-SYNTH", nullptr);

        nvgFillColor(args.vg, nvgRGB(0xDB, 0xDE, 0xFF));
        nvgFontSize(args.vg, 12.0f);
        nvgText(args.vg, 59.0f, 60.0f, "CUTOFF", nullptr);
        nvgText(args.vg, 150.0f, 60.0f, "RESONANCE", nullptr);
        nvgText(args.vg, 105.0f, 139.0f, "DRIVE", nullptr);

        nvgFillColor(args.vg, nvgRGB(0x93, 0xCF, 0xFF));
        nvgFontSize(args.vg, 10.0f);
        nvgText(args.vg, 28.0f, 234.0f, "IN", nullptr);
        nvgText(args.vg, 79.0f, 234.0f, "FREQ", nullptr);
        nvgText(args.vg, 131.0f, 234.0f, "RES", nullptr);
        nvgText(args.vg, 182.0f, 234.0f, "DRV", nullptr);

        nvgFillColor(args.vg, nvgRGB(0xD6, 0xAD, 0xFF));
        nvgFontSize(args.vg, 11.0f);
        nvgText(args.vg, 49.0f, 321.0f, "LP", nullptr);
        nvgText(args.vg, 105.0f, 321.0f, "BP", nullptr);
        nvgText(args.vg, 161.0f, 321.0f, "HP", nullptr);
    }
};
#else
struct ModularSynthStateFilterWidget : ModuleWidget {
    explicit ModularSynthStateFilterWidget(ModularSynthStateFilter* const module) {
        setModule(module);
    }
};
#endif

Model* modelStateFilter = createModel<ModularSynthStateFilter, ModularSynthStateFilterWidget>("StateFilter");
