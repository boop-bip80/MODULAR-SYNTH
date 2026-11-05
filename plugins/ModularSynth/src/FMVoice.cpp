/*
 * MODULAR-SYNTH FM Voice — original first-party two-operator oscillator
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "plugin.hpp"
#include "FMVoice.hpp"

#include <algorithm>
#include <atomic>
#include <memory>

struct ModularSynthFMVoice : Module {
    enum ParamIds {
        OCTAVE_PARAM,
        FINE_PARAM,
        RATIO_PARAM,
        INDEX_PARAM,
        FEEDBACK_PARAM,
        NUM_PARAMS
    };
    enum InputIds {
        PITCH_INPUT,
        RATIO_CV_INPUT,
        INDEX_CV_INPUT,
        FEEDBACK_CV_INPUT,
        NUM_INPUTS
    };
    enum OutputIds {
        CARRIER_OUTPUT,
        MODULATOR_OUTPUT,
        NUM_OUTPUTS
    };
    enum LightIds {
        NUM_LIGHTS
    };

    modular_synth::dsp::FMVoice voices[16];
    int previousChannels = 0;
    std::atomic<bool> pendingReset{false};

    ModularSynthFMVoice() {
        config(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS);
        configParam(OCTAVE_PARAM, -4.0f, 4.0f, 0.0f, "Octave offset");
        getParamQuantity(OCTAVE_PARAM)->snapEnabled = true;
        configParam(FINE_PARAM, -100.0f, 100.0f, 0.0f, "Fine tune", " cents");
        configParam(RATIO_PARAM, 0.125f, 16.0f, 1.0f,
                    "Modulator/carrier frequency ratio", " x");
        configParam(INDEX_PARAM, 0.0f, 8.0f, 0.0f,
                    "Phase modulation index", " rad");
        // Preserve the original parameter ID, positive saved values, knob
        // descriptor and CV jack contract. Negative positions now select
        // one-sample carrier feedback; positive remains modulator feedback.
        configParam(FEEDBACK_PARAM, -0.95f, 0.95f, 0.0f,
                    "Modulator self-feedback", " %", 0.0f, 100.0f);
        configInput(PITCH_INPUT, "Pitch CV (1 V/oct; C4 at 0 V)");
        configInput(RATIO_CV_INPUT, "Ratio CV (1 V doubles ratio)");
        configInput(INDEX_CV_INPUT, "Index CV (1 V adds 0.8 rad)");
        configInput(FEEDBACK_CV_INPUT, "Feedback CV (10 V adds 95%)");
        configOutput(CARRIER_OUTPUT, "Two-operator FM audio (nominal +/-5 V)");
        configOutput(MODULATOR_OUTPUT, "Modulator sine audio (nominal +/-5 V)");
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
        }
        int channels = std::max(1, inputs[PITCH_INPUT].getChannels());
        channels = std::max(channels, inputs[RATIO_CV_INPUT].getChannels());
        channels = std::max(channels, inputs[INDEX_CV_INPUT].getChannels());
        channels = std::max(channels, inputs[FEEDBACK_CV_INPUT].getChannels());
        channels = std::min(channels, 16);

        // Retired poly lanes cannot resume stale phase or control history.
        for (int c = channels; c < previousChannels; ++c)
            voices[c].reset();
        previousChannels = channels;
        outputs[CARRIER_OUTPUT].setChannels(channels);
        outputs[MODULATOR_OUTPUT].setChannels(channels);

        const double basePitch = params[OCTAVE_PARAM].getValue()
                                 + params[FINE_PARAM].getValue() / 1200.0;
        const double baseRatio = params[RATIO_PARAM].getValue();
        const double baseIndex = params[INDEX_PARAM].getValue();
        const double baseFeedback = params[FEEDBACK_PARAM].getValue();

        for (int c = 0; c < channels; ++c) {
            const double pitch = basePitch +
                inputs[PITCH_INPUT].getNormalPolyVoltage(0.0f, c);
            const double ratioVolts =
                inputs[RATIO_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            const double ratio = baseRatio * std::exp2(
                modular_synth::dsp::FMVoice::bounded(ratioVolts, 0.0, -8.0, 8.0));
            const double index = baseIndex
                + 0.8 * inputs[INDEX_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            const double feedback = baseFeedback
                + 0.095 * inputs[FEEDBACK_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            const modular_synth::dsp::FMVoice::Input input = {
                modular_synth::dsp::FMVoice::frequencyForPitch(pitch),
                args.sampleRate, ratio, index, feedback
            };
            const auto output = voices[c].process(input);
            outputs[CARRIER_OUTPUT].setVoltage(5.0f * output.carrier, c);
            outputs[MODULATOR_OUTPUT].setVoltage(5.0f * output.modulator, c);
        }
    }
};

#ifndef HEADLESS
struct ModularSynthFMVoiceWidget : ModuleWidget {
    std::shared_ptr<Font> labelFont;

    explicit ModularSynthFMVoiceWidget(ModularSynthFMVoice* const module) {
        setModule(module);
        setPanel(APP->window->loadSvg(asset::plugin(pluginInstance, "res/FMVoice.svg")));
        labelFont = APP->window->loadFont(
            asset::system("res/fonts/ShareTechMono-Regular.ttf"));

        addChild(createWidget<ScrewSilver>(Vec(0.0f, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(0.0f, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH,
                                                RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));

        addParam(createParamCentered<RoundBlackKnob>(Vec(50.0f, 83.0f), module,
                                                     ModularSynthFMVoice::OCTAVE_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(130.0f, 83.0f), module,
                                                     ModularSynthFMVoice::FINE_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(50.0f, 164.0f), module,
                                                     ModularSynthFMVoice::RATIO_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(130.0f, 164.0f), module,
                                                     ModularSynthFMVoice::INDEX_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(90.0f, 228.0f), module,
                                                     ModularSynthFMVoice::FEEDBACK_PARAM));

        addInput(createInputCentered<PJ301MPort>(Vec(28.0f, 301.0f), module,
                                                 ModularSynthFMVoice::PITCH_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(69.0f, 301.0f), module,
                                                 ModularSynthFMVoice::RATIO_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(111.0f, 301.0f), module,
                                                 ModularSynthFMVoice::INDEX_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(152.0f, 301.0f), module,
                                                 ModularSynthFMVoice::FEEDBACK_CV_INPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(55.0f, 352.0f), module,
                                                   ModularSynthFMVoice::CARRIER_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(125.0f, 352.0f), module,
                                                   ModularSynthFMVoice::MODULATOR_OUTPUT));
    }

    void draw(const DrawArgs& args) override {
        ModuleWidget::draw(args);
        if (!labelFont)
            return;

        nvgFontFaceId(args.vg, labelFont->handle);
        nvgTextAlign(args.vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);
        nvgFillColor(args.vg, nvgRGB(0xF4, 0xF3, 0xFE));
        nvgFontSize(args.vg, 17.0f);
        nvgText(args.vg, 90.0f, 21.0f, "FM VOICE", nullptr);
        nvgFontSize(args.vg, 10.5f);
        nvgFillColor(args.vg, nvgRGB(0xB9, 0xBF, 0xDE));
        nvgText(args.vg, 90.0f, 38.0f, "MODULAR-SYNTH", nullptr);

        nvgFontSize(args.vg, 11.0f);
        nvgFillColor(args.vg, nvgRGB(0xDF, 0xE4, 0xFF));
        nvgText(args.vg, 50.0f, 53.0f, "OCTAVE", nullptr);
        nvgText(args.vg, 130.0f, 53.0f, "FINE", nullptr);
        nvgText(args.vg, 50.0f, 136.0f, "RATIO", nullptr);
        nvgText(args.vg, 130.0f, 136.0f, "INDEX", nullptr);
        nvgText(args.vg, 90.0f, 200.0f, "FEEDBACK", nullptr);

        nvgFontSize(args.vg, 10.0f);
        nvgFillColor(args.vg, nvgRGB(0x9D, 0xD6, 0xFD));
        nvgText(args.vg, 28.0f, 271.0f, "1V/OCT", nullptr);
        nvgText(args.vg, 69.0f, 271.0f, "RATIO", nullptr);
        nvgText(args.vg, 111.0f, 271.0f, "INDEX", nullptr);
        nvgText(args.vg, 152.0f, 271.0f, "FDBK", nullptr);

        nvgFontSize(args.vg, 11.0f);
        nvgFillColor(args.vg, nvgRGB(0xE2, 0xB1, 0xFC));
        nvgText(args.vg, 55.0f, 329.0f, "FM OUT", nullptr);
        nvgText(args.vg, 125.0f, 329.0f, "MOD", nullptr);
    }
};
#else
struct ModularSynthFMVoiceWidget : ModuleWidget {
    explicit ModularSynthFMVoiceWidget(ModularSynthFMVoice* const module) {
        setModule(module);
    }
};
#endif

Model* modelFMVoice = createModel<ModularSynthFMVoice, ModularSynthFMVoiceWidget>("FMVoice");
