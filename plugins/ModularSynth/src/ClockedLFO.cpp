/*
 * MODULAR-SYNTH Clocked LFO — original first-party modulation source.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "plugin.hpp"
#include "ClockedLFO.hpp"

#include <algorithm>
#include <array>
#include <memory>

struct ModularSynthClockedLFO : Module {
    enum ParamIds {
        RATE_PARAM, RATIO_PARAM, PHASE_PARAM, WIDTH_PARAM,
        NUM_PARAMS
    };
    enum InputIds {
        RATE_CV_INPUT, CLOCK_INPUT, RESET_INPUT, PHASE_CV_INPUT, WIDTH_CV_INPUT,
        NUM_INPUTS
    };
    enum OutputIds {
        SINE_OUTPUT, TRIANGLE_OUTPUT, RAMP_OUTPUT, PULSE_OUTPUT, EOC_OUTPUT,
        NUM_OUTPUTS
    };
    enum LightIds { CLOCK_LOCK_LIGHT, NUM_LIGHTS };

    std::array<modular_synth::dsp::ClockedLFO, 16> voices;
    int previousChannels = 0;

    ModularSynthClockedLFO() {
        config(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS);
        configParam(RATE_PARAM, -6.0f, 4.0f, -1.0f,
                    "Free-run frequency", " Hz", 2.0f);
        configParam(RATIO_PARAM, 0.0f, 4.0f, 2.0f,
                    "Clock ratio (1/4, 1/2, 1, 2, 4 cycles per beat)");
        getParamQuantity(RATIO_PARAM)->snapEnabled = true;
        configParam(PHASE_PARAM, 0.0f, 1.0f, 0.0f,
                    "Output phase offset", " %", 0.0f, 100.0f);
        configParam(WIDTH_PARAM, 0.05f, 0.95f, 0.5f,
                    "Pulse width", " %", 0.0f, 100.0f);

        configInput(RATE_CV_INPUT, "Free-rate CV (1 V/oct)");
        configInput(CLOCK_INPUT, "External tempo pulse (2 V rising threshold)");
        configInput(RESET_INPUT, "Phase reset trigger (2 V rising threshold)");
        configInput(PHASE_CV_INPUT, "Output phase CV (10 V per cycle)");
        configInput(WIDTH_CV_INPUT, "Pulse width CV (10 V full range)");
        configOutput(SINE_OUTPUT, "Sine LFO (+/-5 V)");
        configOutput(TRIANGLE_OUTPUT, "Triangle LFO (+/-5 V)");
        configOutput(RAMP_OUTPUT, "Rising ramp LFO (+/-5 V)");
        configOutput(PULSE_OUTPUT, "Pulse LFO (+/-5 V)");
        configOutput(EOC_OUTPUT, "End-of-cycle trigger (+10 V, 1 ms)");
        configLight(CLOCK_LOCK_LIGHT, "External tempo clock locked");
    }

    void onReset() override {
        for (auto& voice : voices)
            voice.reset();
        previousChannels = 0;
        lights[CLOCK_LOCK_LIGHT].setBrightness(0.0f);
    }

    void process(const ProcessArgs& args) override {
        int channels = 1;
        for (int id = 0; id < NUM_INPUTS; ++id)
            channels = std::max(channels, inputs[id].getChannels());
        channels = std::min(channels, 16);

        for (int c = channels; c < previousChannels; ++c)
            voices[static_cast<std::size_t>(c)].reset();
        previousChannels = channels;

        for (int id = 0; id < NUM_OUTPUTS; ++id)
            outputs[id].setChannels(channels);

        const bool hasClock = inputs[CLOCK_INPUT].isConnected();
        bool anyLocked = false;
        for (int c = 0; c < channels; ++c) {
            modular_synth::dsp::ClockedLFO::Input in;
            in.sampleRateHz = args.sampleRate;
            in.log2RateHz = params[RATE_PARAM].getValue();
            in.rateCvVolts = inputs[RATE_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            in.ratioIndex = params[RATIO_PARAM].getValue();
            in.phaseOffset = params[PHASE_PARAM].getValue();
            in.phaseCvVolts = inputs[PHASE_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            in.pulseWidth = params[WIDTH_PARAM].getValue();
            in.widthCvVolts = inputs[WIDTH_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            in.clockVoltage = inputs[CLOCK_INPUT].getNormalPolyVoltage(0.0f, c);
            in.resetVoltage = inputs[RESET_INPUT].getNormalPolyVoltage(0.0f, c);
            in.clockConnected = hasClock;

            const auto sample = voices[static_cast<std::size_t>(c)].process(in);
            outputs[SINE_OUTPUT].setVoltage(sample.sine, c);
            outputs[TRIANGLE_OUTPUT].setVoltage(sample.triangle, c);
            outputs[RAMP_OUTPUT].setVoltage(sample.ramp, c);
            outputs[PULSE_OUTPUT].setVoltage(sample.pulse, c);
            outputs[EOC_OUTPUT].setVoltage(sample.endOfCycle, c);
            anyLocked |= sample.clockLocked;
        }
        lights[CLOCK_LOCK_LIGHT].setBrightness(anyLocked ? 1.0f : 0.0f);
    }
};

#ifndef HEADLESS
struct ModularSynthClockedLFOWidget : ModuleWidget {
    std::shared_ptr<Font> labelFont;

    explicit ModularSynthClockedLFOWidget(ModularSynthClockedLFO* const module) {
        setModule(module);
        setPanel(APP->window->loadSvg(asset::plugin(pluginInstance, "res/ClockedLFO.svg")));
        labelFont = APP->window->loadFont(
            asset::system("res/fonts/ShareTechMono-Regular.ttf"));

        addChild(createWidget<ScrewSilver>(Vec(0.0f, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(0.0f, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(
            Vec(box.size.x - RACK_GRID_WIDTH, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));

        addParam(createParamCentered<RoundBlackKnob>(Vec(62.0f, 91.0f), module,
                                                    ModularSynthClockedLFO::RATE_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(177.0f, 91.0f), module,
                                                    ModularSynthClockedLFO::RATIO_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(62.0f, 171.0f), module,
                                                    ModularSynthClockedLFO::PHASE_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(177.0f, 171.0f), module,
                                                    ModularSynthClockedLFO::WIDTH_PARAM));
        addChild(createLightCentered<SmallLight<GreenLight>>(
            Vec(120.0f, 217.0f), module, ModularSynthClockedLFO::CLOCK_LOCK_LIGHT));

        addInput(createInputCentered<PJ301MPort>(Vec(26.0f, 265.0f), module,
                                                 ModularSynthClockedLFO::RATE_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(73.0f, 265.0f), module,
                                                 ModularSynthClockedLFO::CLOCK_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(120.0f, 265.0f), module,
                                                 ModularSynthClockedLFO::RESET_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(167.0f, 265.0f), module,
                                                 ModularSynthClockedLFO::PHASE_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(214.0f, 265.0f), module,
                                                 ModularSynthClockedLFO::WIDTH_CV_INPUT));

        addOutput(createOutputCentered<PJ301MPort>(Vec(26.0f, 344.0f), module,
                                                   ModularSynthClockedLFO::SINE_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(73.0f, 344.0f), module,
                                                   ModularSynthClockedLFO::TRIANGLE_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(120.0f, 344.0f), module,
                                                   ModularSynthClockedLFO::RAMP_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(167.0f, 344.0f), module,
                                                   ModularSynthClockedLFO::PULSE_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(214.0f, 344.0f), module,
                                                   ModularSynthClockedLFO::EOC_OUTPUT));
    }

    void draw(const DrawArgs& args) override {
        ModuleWidget::draw(args);
        if (!labelFont)
            return;
        nvgFontFaceId(args.vg, labelFont->handle);
        nvgTextAlign(args.vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);
        nvgFillColor(args.vg, nvgRGB(0xE8, 0xFF, 0xF8));
        nvgFontSize(args.vg, 18.0f);
        nvgText(args.vg, 120.0f, 20.0f, "CLOCKED LFO", nullptr);
        nvgFillColor(args.vg, nvgRGB(0xA0, 0xCB, 0xCA));
        nvgFontSize(args.vg, 10.5f);
        nvgText(args.vg, 120.0f, 40.0f, "MODULAR-SYNTH", nullptr);

        nvgFillColor(args.vg, nvgRGB(0xE5, 0xF5, 0xFF));
        nvgFontSize(args.vg, 12.0f);
        nvgText(args.vg, 62.0f, 61.0f, "FREE RATE", nullptr);
        nvgText(args.vg, 177.0f, 61.0f, "CLOCK x", nullptr);
        nvgText(args.vg, 62.0f, 141.0f, "PHASE", nullptr);
        nvgText(args.vg, 177.0f, 141.0f, "PULSE WIDTH", nullptr);
        nvgFillColor(args.vg, nvgRGB(0x7B, 0xF1, 0xBF));
        nvgFontSize(args.vg, 10.5f);
        nvgText(args.vg, 120.0f, 193.0f, "TEMPO LOCK", nullptr);

        nvgFontSize(args.vg, 10.0f);
        nvgFillColor(args.vg, nvgRGB(0x9E, 0xE8, 0xFF));
        nvgText(args.vg, 26.0f, 235.0f, "RATE", nullptr);
        nvgText(args.vg, 73.0f, 235.0f, "CLK", nullptr);
        nvgText(args.vg, 120.0f, 235.0f, "RESET", nullptr);
        nvgText(args.vg, 167.0f, 235.0f, "PHASE", nullptr);
        nvgText(args.vg, 214.0f, 235.0f, "WIDTH", nullptr);
        nvgFillColor(args.vg, nvgRGB(0xEE, 0xC4, 0xFF));
        nvgText(args.vg, 26.0f, 314.0f, "SIN", nullptr);
        nvgText(args.vg, 73.0f, 314.0f, "TRI", nullptr);
        nvgText(args.vg, 120.0f, 314.0f, "RAMP", nullptr);
        nvgText(args.vg, 167.0f, 314.0f, "PULSE", nullptr);
        nvgText(args.vg, 214.0f, 314.0f, "EOC", nullptr);
    }
};
#else
struct ModularSynthClockedLFOWidget : ModuleWidget {
    explicit ModularSynthClockedLFOWidget(ModularSynthClockedLFO* const module) {
        setModule(module);
    }
};
#endif

Model* modelClockedLFO =
    createModel<ModularSynthClockedLFO, ModularSynthClockedLFOWidget>("ClockedLFO");
