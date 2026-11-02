/*
 * MODULAR-SYNTH Dual VCA — original 16-lane dual audio/CV amplifier.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "plugin.hpp"
#include "DualVCA.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <memory>

struct ModularSynthDualVCA : Module {
    enum ParamIds {
        LEVEL_A_PARAM, CURVE_A_PARAM, LEVEL_B_PARAM, CURVE_B_PARAM,
        NUM_PARAMS
    };
    enum InputIds {
        AUDIO_A_INPUT, CV_A_INPUT, AUDIO_B_INPUT, CV_B_INPUT,
        NUM_INPUTS
    };
    enum OutputIds {
        AUDIO_A_OUTPUT, AUDIO_B_OUTPUT, SUM_OUTPUT,
        NUM_OUTPUTS
    };
    enum LightIds { NUM_LIGHTS };

    std::array<modular_synth::dsp::DualVCA, 16> voicesA;
    std::array<modular_synth::dsp::DualVCA, 16> voicesB;
    int previousAChannels = 0;
    int previousBChannels = 0;
    std::atomic<bool> pendingReset{false};

    ModularSynthDualVCA() {
        config(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS);
        configParam(LEVEL_A_PARAM, 0.0f, 1.0f, 1.0f,
                    "A maximum gain", " %", 0.0f, 100.0f);
        configParam(CURVE_A_PARAM, 0.0f, 1.0f, 0.0f,
                    "A CV response curve (linear to cubic)", " %", 0.0f, 100.0f);
        configParam(LEVEL_B_PARAM, 0.0f, 1.0f, 1.0f,
                    "B maximum gain", " %", 0.0f, 100.0f);
        configParam(CURVE_B_PARAM, 0.0f, 1.0f, 0.0f,
                    "B CV response curve (linear to cubic)", " %", 0.0f, 100.0f);

        configInput(AUDIO_A_INPUT, "A audio (nominal +/-5 V)");
        configInput(CV_A_INPUT, "A gain envelope (0 to +10 V; unpatched is unity)");
        configInput(AUDIO_B_INPUT, "B audio (nominal +/-5 V)");
        configInput(CV_B_INPUT, "B gain envelope (0 to +10 V; unpatched is unity)");
        configOutput(AUDIO_A_OUTPUT, "A gain-controlled audio (+/-10 V limit)");
        configOutput(AUDIO_B_OUTPUT, "B gain-controlled audio (+/-10 V limit)");
        configOutput(SUM_OUTPUT, "A plus B bounded mix (+/-10 V limit)");
    }

    void onReset(const ResetEvent& e) override {
        Module::onReset(e);
        // Audio thread owns all voice state. UI/host only requests a reset,
        // avoiding races with process() state updates.
        pendingReset.store(true, std::memory_order_release);
    }

    void process(const ProcessArgs& args) override {
        if (pendingReset.exchange(false, std::memory_order_acq_rel)) {
            for (auto& voice : voicesA)
                voice.reset();
            for (auto& voice : voicesB)
                voice.reset();
            previousAChannels = 0;
            previousBChannels = 0;
        }

        const int channelsA = std::min(16, std::max(
            1, std::max(inputs[AUDIO_A_INPUT].getChannels(),
                        inputs[CV_A_INPUT].getChannels())));
        const int channelsB = std::min(16, std::max(
            1, std::max(inputs[AUDIO_B_INPUT].getChannels(),
                        inputs[CV_B_INPUT].getChannels())));
        const int sumChannels = std::max(channelsA, channelsB);

        for (int c = channelsA; c < previousAChannels; ++c)
            voicesA[static_cast<std::size_t>(c)].reset();
        for (int c = channelsB; c < previousBChannels; ++c)
            voicesB[static_cast<std::size_t>(c)].reset();
        previousAChannels = channelsA;
        previousBChannels = channelsB;

        outputs[AUDIO_A_OUTPUT].setChannels(channelsA);
        outputs[AUDIO_B_OUTPUT].setChannels(channelsB);
        outputs[SUM_OUTPUT].setChannels(sumChannels);

        for (int c = 0; c < sumChannels; ++c) {
            float a = 0.0f;
            float b = 0.0f;
            if (c < channelsA) {
                modular_synth::dsp::DualVCA::Input in;
                in.sampleRateHz = args.sampleRate;
                in.inputVoltage = inputs[AUDIO_A_INPUT].getNormalPolyVoltage(0.0f, c);
                in.level = params[LEVEL_A_PARAM].getValue();
                in.cvVolts = inputs[CV_A_INPUT].getNormalPolyVoltage(0.0f, c);
                in.curve = params[CURVE_A_PARAM].getValue();
                in.cvConnected = inputs[CV_A_INPUT].isConnected();
                a = voicesA[static_cast<std::size_t>(c)].process(in);
                outputs[AUDIO_A_OUTPUT].setVoltage(a, c);
            }
            if (c < channelsB) {
                modular_synth::dsp::DualVCA::Input in;
                in.sampleRateHz = args.sampleRate;
                in.inputVoltage = inputs[AUDIO_B_INPUT].getNormalPolyVoltage(0.0f, c);
                in.level = params[LEVEL_B_PARAM].getValue();
                in.cvVolts = inputs[CV_B_INPUT].getNormalPolyVoltage(0.0f, c);
                in.curve = params[CURVE_B_PARAM].getValue();
                in.cvConnected = inputs[CV_B_INPUT].isConnected();
                b = voicesB[static_cast<std::size_t>(c)].process(in);
                outputs[AUDIO_B_OUTPUT].setVoltage(b, c);
            }
            outputs[SUM_OUTPUT].setVoltage(
                modular_synth::dsp::DualVCA::boundedSum(a, b), c);
        }
    }
};

#ifndef HEADLESS
struct ModularSynthDualVCAWidget : ModuleWidget {
    std::shared_ptr<Font> labelFont;

    explicit ModularSynthDualVCAWidget(ModularSynthDualVCA* const module) {
        setModule(module);
        setPanel(APP->window->loadSvg(asset::plugin(pluginInstance, "res/DualVCA.svg")));
        labelFont = APP->window->loadFont(
            asset::system("res/fonts/ShareTechMono-Regular.ttf"));

        addChild(createWidget<ScrewSilver>(Vec(0.0f, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(0.0f, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(
            Vec(box.size.x - RACK_GRID_WIDTH, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));

        addParam(createParamCentered<RoundBlackKnob>(Vec(48.0f, 99.0f), module,
                                                      ModularSynthDualVCA::LEVEL_A_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(132.0f, 99.0f), module,
                                                      ModularSynthDualVCA::LEVEL_B_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(48.0f, 179.0f), module,
                                                      ModularSynthDualVCA::CURVE_A_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(132.0f, 179.0f), module,
                                                      ModularSynthDualVCA::CURVE_B_PARAM));

        addInput(createInputCentered<PJ301MPort>(Vec(24.0f, 268.0f), module,
                                                  ModularSynthDualVCA::AUDIO_A_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(68.0f, 268.0f), module,
                                                  ModularSynthDualVCA::CV_A_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(112.0f, 268.0f), module,
                                                  ModularSynthDualVCA::AUDIO_B_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(156.0f, 268.0f), module,
                                                  ModularSynthDualVCA::CV_B_INPUT));

        addOutput(createOutputCentered<PJ301MPort>(Vec(35.0f, 347.0f), module,
                                                    ModularSynthDualVCA::AUDIO_A_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(90.0f, 347.0f), module,
                                                    ModularSynthDualVCA::AUDIO_B_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(145.0f, 347.0f), module,
                                                    ModularSynthDualVCA::SUM_OUTPUT));
    }

    void draw(const DrawArgs& args) override {
        ModuleWidget::draw(args);
        if (!labelFont)
            return;
        nvgFontFaceId(args.vg, labelFont->handle);
        nvgTextAlign(args.vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);
        nvgFillColor(args.vg, nvgRGB(0xEE, 0xFA, 0xFF));
        nvgFontSize(args.vg, 18.0f);
        nvgText(args.vg, 90.0f, 22.0f, "DUAL VCA", nullptr);
        nvgFillColor(args.vg, nvgRGB(0x9F, 0xC8, 0xD8));
        nvgFontSize(args.vg, 10.5f);
        nvgText(args.vg, 90.0f, 41.0f, "MODULAR-SYNTH", nullptr);

        nvgFillColor(args.vg, nvgRGB(0xDD, 0xF8, 0xFF));
        nvgFontSize(args.vg, 12.0f);
        nvgText(args.vg, 48.0f, 61.0f, "A LEVEL", nullptr);
        nvgText(args.vg, 132.0f, 61.0f, "B LEVEL", nullptr);
        nvgText(args.vg, 48.0f, 141.0f, "A CURVE", nullptr);
        nvgText(args.vg, 132.0f, 141.0f, "B CURVE", nullptr);

        nvgFillColor(args.vg, nvgRGB(0x9F, 0xE9, 0xF8));
        nvgFontSize(args.vg, 10.0f);
        nvgText(args.vg, 24.0f, 238.0f, "A IN", nullptr);
        nvgText(args.vg, 68.0f, 238.0f, "A CV", nullptr);
        nvgText(args.vg, 112.0f, 238.0f, "B IN", nullptr);
        nvgText(args.vg, 156.0f, 238.0f, "B CV", nullptr);

        nvgFillColor(args.vg, nvgRGB(0xEB, 0xC5, 0xFF));
        nvgFontSize(args.vg, 11.0f);
        nvgText(args.vg, 35.0f, 319.0f, "A", nullptr);
        nvgText(args.vg, 90.0f, 319.0f, "B", nullptr);
        nvgText(args.vg, 145.0f, 319.0f, "SUM", nullptr);
    }
};
#else
struct ModularSynthDualVCAWidget : ModuleWidget {
    explicit ModularSynthDualVCAWidget(ModularSynthDualVCA* const module) {
        setModule(module);
    }
};
#endif

Model* modelDualVCA =
    createModel<ModularSynthDualVCA, ModularSynthDualVCAWidget>("DualVCA");
