/*
 * MODULAR-SYNTH ChanceHold — polyphonic clocked probabilistic S&H utility.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "plugin.hpp"
#include "ChanceHold.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <memory>

struct ModularSynthChanceHold : Module {
    enum ParamIds {
        RATE_PARAM, CHANCE_PARAM, GLIDE_PARAM, QUANTIZE_PARAM,
        NUM_PARAMS
    };
    enum InputIds {
        RATE_CV_INPUT, CLOCK_INPUT, RESET_INPUT, CHANCE_CV_INPUT, GLIDE_CV_INPUT,
        NUM_INPUTS
    };
    enum OutputIds {
        HOLD_OUTPUT, GLIDE_OUTPUT, TRIGGER_OUTPUT,
        NUM_OUTPUTS
    };
    enum LightIds { EXTERNAL_CLOCK_LIGHT, NUM_LIGHTS };

    std::array<modular_synth::dsp::ChanceHold, 16> voices;
    int previousChannels = 0;
    std::atomic<bool> pendingReset{false};

    ModularSynthChanceHold() {
        config(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS);
        configParam(RATE_PARAM, -4.0f, 5.0f, 0.0f,
                    "Free-run sample rate", " Hz", 2.0f);
        configParam(CHANCE_PARAM, 0.0f, 1.0f, 0.75f,
                    "Probability of taking a sample", " %", 0.0f, 100.0f);
        configParam(GLIDE_PARAM, 0.0f, 2.0f, 0.15f,
                    "Glide time (99% settling)", " s");
        configParam(QUANTIZE_PARAM, 0.0f, 1.0f, 0.0f,
                    "Quantize sampled voltage to 12 steps per volt");
        getParamQuantity(QUANTIZE_PARAM)->snapEnabled = true;

        configInput(RATE_CV_INPUT, "Free clock rate CV (1 V/oct)");
        configInput(CLOCK_INPUT, "External sample clock (2 V rising threshold)");
        configInput(RESET_INPUT, "Reproducible random sequence reset (2 V rising threshold)");
        configInput(CHANCE_CV_INPUT, "Sample probability CV (+10 V adds 100%)");
        configInput(GLIDE_CV_INPUT, "Glide duration CV (+10 V adds 2 seconds)");
        configOutput(HOLD_OUTPUT, "Stepped sample-and-hold CV (+/-5 V)");
        configOutput(GLIDE_OUTPUT, "Gliding sample-and-hold CV (+/-5 V)");
        configOutput(TRIGGER_OUTPUT, "Accepted-sample trigger (+10 V, 1 ms)");
        configLight(EXTERNAL_CLOCK_LIGHT, "External clock connected");

        // Independent deterministic seeds on every lane. No clock, RNG, or
        // allocation shared between voices; reset/load replays the sequence.
        for (int lane = 0; lane < 16; ++lane) {
            const auto seed = UINT32_C(0x6d2b79f5)
                ^ (UINT32_C(0x9e3779b9) * static_cast<unsigned>(lane + 1));
            voices[static_cast<std::size_t>(lane)].setSeed(seed);
        }
    }

    void onReset() override {
        pendingReset.store(true, std::memory_order_release);
    }

    void onReset(const ResetEvent& event) override {
        Module::onReset(event);
        pendingReset.store(true, std::memory_order_release);
    }

    void process(const ProcessArgs& args) override {
        if (pendingReset.load(std::memory_order_acquire) &&
                pendingReset.exchange(false, std::memory_order_acq_rel)) {
            for (auto& voice : voices)
                voice.reset();
            previousChannels = 0;
            lights[EXTERNAL_CLOCK_LIGHT].setBrightness(0.0f);
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

        const bool externalClock = inputs[CLOCK_INPUT].isConnected();
        const auto quantize = params[QUANTIZE_PARAM].getValue() >= 0.5f;
        for (int c = 0; c < channels; ++c) {
            modular_synth::dsp::ChanceHold::Input in;
            in.sampleRateHz = args.sampleRate;
            in.log2RateHz = params[RATE_PARAM].getValue();
            in.rateCvVolts = inputs[RATE_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            in.probability = params[CHANCE_PARAM].getValue();
            in.probabilityCvVolts = inputs[CHANCE_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            in.glideSeconds = params[GLIDE_PARAM].getValue();
            in.glideCvVolts = inputs[GLIDE_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            in.clockVoltage = inputs[CLOCK_INPUT].getNormalPolyVoltage(0.0f, c);
            in.resetVoltage = inputs[RESET_INPUT].getNormalPolyVoltage(0.0f, c);
            in.clockConnected = externalClock;
            in.semitoneQuantize = quantize;

            const auto out = voices[static_cast<std::size_t>(c)].process(in);
            outputs[HOLD_OUTPUT].setVoltage(out.held, c);
            outputs[GLIDE_OUTPUT].setVoltage(out.glide, c);
            outputs[TRIGGER_OUTPUT].setVoltage(out.trigger, c);
        }
        lights[EXTERNAL_CLOCK_LIGHT].setBrightness(externalClock ? 1.0f : 0.0f);
    }
};

#ifndef HEADLESS
struct ModularSynthChanceHoldWidget : ModuleWidget {
    std::shared_ptr<Font> labelFont;

    explicit ModularSynthChanceHoldWidget(ModularSynthChanceHold* const module) {
        setModule(module);
        setPanel(APP->window->loadSvg(asset::plugin(pluginInstance, "res/ChanceHold.svg")));
        labelFont = APP->window->loadFont(
            asset::system("res/fonts/ShareTechMono-Regular.ttf"));

        addChild(createWidget<ScrewSilver>(Vec(0.0f, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(0.0f, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(
            Vec(box.size.x - RACK_GRID_WIDTH, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));

        addParam(createParamCentered<RoundBlackKnob>(Vec(62.0f, 91.0f), module,
                                                    ModularSynthChanceHold::RATE_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(177.0f, 91.0f), module,
                                                    ModularSynthChanceHold::CHANCE_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(62.0f, 171.0f), module,
                                                    ModularSynthChanceHold::GLIDE_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(177.0f, 171.0f), module,
                                                    ModularSynthChanceHold::QUANTIZE_PARAM));
        addChild(createLightCentered<SmallLight<GreenLight>>(
            Vec(120.0f, 217.0f), module, ModularSynthChanceHold::EXTERNAL_CLOCK_LIGHT));

        addInput(createInputCentered<PJ301MPort>(Vec(26.0f, 265.0f), module,
                                                 ModularSynthChanceHold::RATE_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(73.0f, 265.0f), module,
                                                 ModularSynthChanceHold::CLOCK_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(120.0f, 265.0f), module,
                                                 ModularSynthChanceHold::RESET_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(167.0f, 265.0f), module,
                                                 ModularSynthChanceHold::CHANCE_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(214.0f, 265.0f), module,
                                                 ModularSynthChanceHold::GLIDE_CV_INPUT));

        addOutput(createOutputCentered<PJ301MPort>(Vec(48.0f, 344.0f), module,
                                                   ModularSynthChanceHold::HOLD_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(120.0f, 344.0f), module,
                                                   ModularSynthChanceHold::GLIDE_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(192.0f, 344.0f), module,
                                                   ModularSynthChanceHold::TRIGGER_OUTPUT));
    }

    void draw(const DrawArgs& args) override {
        ModuleWidget::draw(args);
        if (!labelFont)
            return;
        nvgFontFaceId(args.vg, labelFont->handle);
        nvgTextAlign(args.vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);
        nvgFillColor(args.vg, nvgRGB(0xE8, 0xF6, 0xFF));
        nvgFontSize(args.vg, 18.0f);
        nvgText(args.vg, 120.0f, 20.0f, "CHANCE HOLD", nullptr);
        nvgFillColor(args.vg, nvgRGB(0x9E, 0xC7, 0xDE));
        nvgFontSize(args.vg, 10.5f);
        nvgText(args.vg, 120.0f, 40.0f, "MODULAR-SYNTH", nullptr);

        nvgFillColor(args.vg, nvgRGB(0xE4, 0xF7, 0xFF));
        nvgFontSize(args.vg, 12.0f);
        nvgText(args.vg, 62.0f, 61.0f, "FREE RATE", nullptr);
        nvgText(args.vg, 177.0f, 61.0f, "CHANCE", nullptr);
        nvgText(args.vg, 62.0f, 141.0f, "GLIDE", nullptr);
        nvgText(args.vg, 177.0f, 141.0f, "QUANTIZE", nullptr);
        nvgFillColor(args.vg, nvgRGB(0xFF, 0xD3, 0x6B));
        nvgFontSize(args.vg, 10.5f);
        nvgText(args.vg, 120.0f, 193.0f, "EXT CLOCK", nullptr);

        nvgFontSize(args.vg, 10.0f);
        nvgFillColor(args.vg, nvgRGB(0x9E, 0xE8, 0xFF));
        nvgText(args.vg, 26.0f, 235.0f, "RATE", nullptr);
        nvgText(args.vg, 73.0f, 235.0f, "CLK", nullptr);
        nvgText(args.vg, 120.0f, 235.0f, "RESET", nullptr);
        nvgText(args.vg, 167.0f, 235.0f, "PROB", nullptr);
        nvgText(args.vg, 214.0f, 235.0f, "GLIDE", nullptr);
        nvgFillColor(args.vg, nvgRGB(0xFF, 0xDB, 0xA8));
        nvgText(args.vg, 48.0f, 314.0f, "STEP", nullptr);
        nvgText(args.vg, 120.0f, 314.0f, "SMOOTH", nullptr);
        nvgText(args.vg, 192.0f, 314.0f, "HIT", nullptr);
    }
};
#else
struct ModularSynthChanceHoldWidget : ModuleWidget {
    explicit ModularSynthChanceHoldWidget(ModularSynthChanceHold* const module) {
        setModule(module);
    }
};
#endif

Model* modelChanceHold =
    createModel<ModularSynthChanceHold, ModularSynthChanceHoldWidget>("ChanceHold");
