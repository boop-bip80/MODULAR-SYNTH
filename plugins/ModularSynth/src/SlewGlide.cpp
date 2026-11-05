/*
 * MODULAR-SYNTH SlewGlide — polyphonic linear/exponential CV slew utility.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "plugin.hpp"
#include "SlewGlide.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <memory>

struct ModularSynthSlewGlide : Module {
    enum ParamIds { RISE_PARAM, FALL_PARAM, NUM_PARAMS };
    enum InputIds { SIGNAL_INPUT, RISE_CV_INPUT, FALL_CV_INPUT, NUM_INPUTS };
    enum OutputIds { LINEAR_OUTPUT, EXPONENTIAL_OUTPUT, MOVING_OUTPUT, NUM_OUTPUTS };
    enum LightIds { NUM_LIGHTS };

    std::array<modular_synth::dsp::SlewGlide, 16> voices;
    int previousChannels = 0;
    std::atomic<bool> pendingReset{false};

    ModularSynthSlewGlide() {
        config(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS);
        configParam(RISE_PARAM, 0.0f, 5.0f, 0.20f,
                    "Rise time (linear: 10 V traversal; exponential: 99% settle)", " s");
        configParam(FALL_PARAM, 0.0f, 5.0f, 0.30f,
                    "Fall time (linear: 10 V traversal; exponential: 99% settle)", " s");
        configInput(SIGNAL_INPUT, "Voltage to glide (+/-10 V)");
        configInput(RISE_CV_INPUT, "Rise CV (+10 V adds 5 seconds)");
        configInput(FALL_CV_INPUT, "Fall CV (+10 V adds 5 seconds)");
        configOutput(LINEAR_OUTPUT, "Linear slew (+/-10 V)");
        configOutput(EXPONENTIAL_OUTPUT, "Exponential slew (+/-10 V)");
        configOutput(MOVING_OUTPUT, "Slew-in-progress gate (+10 V)");
    }

    void onReset() override {
        pendingReset.store(true, std::memory_order_release);
    }

    void onReset(const ResetEvent& event) override {
        Module::onReset(event);
        pendingReset.store(true, std::memory_order_release);
    }

    void process(const ProcessArgs& args) override {
        if (pendingReset.exchange(false, std::memory_order_acq_rel)) {
            for (auto& voice : voices)
                voice.reset();
            previousChannels = 0;
        }
        int channels = 1;
        for (int id = 0; id < NUM_INPUTS; ++id)
            channels = std::max(channels, inputs[id].getChannels());
        channels = std::min(channels, 16);

        for (int c = channels; c < previousChannels; ++c)
            voices[static_cast<std::size_t>(c)].reset();
        previousChannels = channels;
        for (int id = 0; id < NUM_OUTPUTS; ++id)
            outputs[id].setChannels(channels);

        for (int c = 0; c < channels; ++c) {
            modular_synth::dsp::SlewGlide::Input in;
            in.sampleRateHz = args.sampleRate;
            in.voltage = inputs[SIGNAL_INPUT].getNormalPolyVoltage(0.0f, c);
            in.riseSeconds = params[RISE_PARAM].getValue();
            in.fallSeconds = params[FALL_PARAM].getValue();
            in.riseCvVolts = inputs[RISE_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            in.fallCvVolts = inputs[FALL_CV_INPUT].getNormalPolyVoltage(0.0f, c);

            const auto out = voices[static_cast<std::size_t>(c)].process(in);
            outputs[LINEAR_OUTPUT].setVoltage(out.linear, c);
            outputs[EXPONENTIAL_OUTPUT].setVoltage(out.exponential, c);
            outputs[MOVING_OUTPUT].setVoltage(out.movingGate, c);
        }
    }
};

#ifndef HEADLESS
struct ModularSynthSlewGlideWidget : ModuleWidget {
    std::shared_ptr<Font> labelFont;

    explicit ModularSynthSlewGlideWidget(ModularSynthSlewGlide* const module) {
        setModule(module);
        setPanel(APP->window->loadSvg(asset::plugin(pluginInstance, "res/SlewGlide.svg")));
        labelFont = APP->window->loadFont(asset::system("res/fonts/ShareTechMono-Regular.ttf"));

        addChild(createWidget<ScrewSilver>(Vec(0.0f, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(0.0f, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH,
                                                RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));

        addParam(createParamCentered<RoundBlackKnob>(
            Vec(48.0f, 118.0f), module, ModularSynthSlewGlide::RISE_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(
            Vec(132.0f, 118.0f), module, ModularSynthSlewGlide::FALL_PARAM));

        addInput(createInputCentered<PJ301MPort>(
            Vec(30.0f, 249.0f), module, ModularSynthSlewGlide::SIGNAL_INPUT));
        addInput(createInputCentered<PJ301MPort>(
            Vec(90.0f, 249.0f), module, ModularSynthSlewGlide::RISE_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(
            Vec(150.0f, 249.0f), module, ModularSynthSlewGlide::FALL_CV_INPUT));

        addOutput(createOutputCentered<PJ301MPort>(
            Vec(30.0f, 337.0f), module, ModularSynthSlewGlide::LINEAR_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(
            Vec(90.0f, 337.0f), module, ModularSynthSlewGlide::EXPONENTIAL_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(
            Vec(150.0f, 337.0f), module, ModularSynthSlewGlide::MOVING_OUTPUT));
    }

    void draw(const DrawArgs& args) override {
        ModuleWidget::draw(args);
        if (!labelFont)
            return;
        nvgFontFaceId(args.vg, labelFont->handle);
        nvgTextAlign(args.vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);
        nvgFillColor(args.vg, nvgRGB(0xE8, 0xF6, 0xFF));
        nvgFontSize(args.vg, 17.0f);
        nvgText(args.vg, 90.0f, 20.0f, "SLEW GLIDE", nullptr);
        nvgFillColor(args.vg, nvgRGB(0x9E, 0xC7, 0xDE));
        nvgFontSize(args.vg, 10.0f);
        nvgText(args.vg, 90.0f, 40.0f, "MODULAR-SYNTH", nullptr);

        nvgFillColor(args.vg, nvgRGB(0xE4, 0xF7, 0xFF));
        nvgFontSize(args.vg, 12.5f);
        nvgText(args.vg, 48.0f, 79.0f, "RISE", nullptr);
        nvgText(args.vg, 132.0f, 79.0f, "FALL", nullptr);
        nvgFontSize(args.vg, 10.0f);
        nvgFillColor(args.vg, nvgRGB(0x9E, 0xE8, 0xFF));
        nvgText(args.vg, 30.0f, 218.0f, "CV IN", nullptr);
        nvgText(args.vg, 90.0f, 218.0f, "RISE CV", nullptr);
        nvgText(args.vg, 150.0f, 218.0f, "FALL CV", nullptr);
        nvgFillColor(args.vg, nvgRGB(0xFF, 0xDB, 0xA8));
        nvgText(args.vg, 30.0f, 307.0f, "LINEAR", nullptr);
        nvgText(args.vg, 90.0f, 307.0f, "EXP", nullptr);
        nvgText(args.vg, 150.0f, 307.0f, "MOVING", nullptr);
    }
};
#else
struct ModularSynthSlewGlideWidget : ModuleWidget {
    explicit ModularSynthSlewGlideWidget(ModularSynthSlewGlide* const module) {
        setModule(module);
    }
};
#endif

Model* modelSlewGlide =
    createModel<ModularSynthSlewGlide, ModularSynthSlewGlideWidget>("SlewGlide");
