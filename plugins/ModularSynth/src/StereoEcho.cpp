/*
 * MODULAR-SYNTH StereoEcho — original first-party polyphonic effect.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "plugin.hpp"
#include "StereoEcho.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <memory>

struct ModularSynthStereoEcho : Module {
    enum ParamIds {
        TIME_PARAM, FEEDBACK_PARAM, MIX_PARAM, CROSSFEED_PARAM,
        NUM_PARAMS
    };
    enum InputIds {
        LEFT_INPUT, RIGHT_INPUT,
        TIME_CV_INPUT, FEEDBACK_CV_INPUT, MIX_CV_INPUT,
        NUM_INPUTS
    };
    enum OutputIds { LEFT_OUTPUT, RIGHT_OUTPUT, NUM_OUTPUTS };
    enum LightIds { NUM_LIGHTS };

    std::array<modular_synth::dsp::StereoEchoDSP, 16> voices;
    int previousChannels = 0;
    std::atomic<bool> pendingReset{false};

    ModularSynthStereoEcho() {
        config(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS);
        configParam(TIME_PARAM, 1.0f, 1000.0f, 250.0f,
                    "Echo time", " ms");
        configParam(FEEDBACK_PARAM, 0.0f, 0.9f, 0.35f,
                    "Feedback", " %", 0.0f, 100.0f);
        configParam(MIX_PARAM, 0.0f, 1.0f, 0.4f,
                    "Wet mix", " %", 0.0f, 100.0f);
        configParam(CROSSFEED_PARAM, 0.0f, 1.0f, 0.5f,
                    "Stereo ping-pong crossfeed", " %", 0.0f, 100.0f);

        configInput(LEFT_INPUT, "Left audio input");
        configInput(RIGHT_INPUT, "Right audio input (uses left when unplugged)");
        configInput(TIME_CV_INPUT, "Echo time CV (additive 100 ms/V; accepts negative CV)");
        configInput(FEEDBACK_CV_INPUT, "Feedback CV (adds 10 percentage points/V)");
        configInput(MIX_CV_INPUT, "Wet mix CV (adds 10 percentage points/V)");
        configOutput(LEFT_OUTPUT, "Left mixed wet/dry audio");
        configOutput(RIGHT_OUTPUT, "Right mixed wet/dry audio");
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
        int channels = std::max(1, inputs[LEFT_INPUT].getChannels());
        channels = std::max(channels, inputs[RIGHT_INPUT].getChannels());
        channels = std::max(channels, inputs[TIME_CV_INPUT].getChannels());
        channels = std::max(channels, inputs[FEEDBACK_CV_INPUT].getChannels());
        channels = std::max(channels, inputs[MIX_CV_INPUT].getChannels());
        channels = std::min(channels, 16);

        // Retire disappearing voices, so reducing a polyphonic cable and
        // expanding it later cannot unexpectedly revive stale delay tails.
        for (int c = channels; c < previousChannels; ++c)
            voices[static_cast<std::size_t>(c)].reset();
        previousChannels = channels;

        outputs[LEFT_OUTPUT].setChannels(channels);
        outputs[RIGHT_OUTPUT].setChannels(channels);

        const double baseMs = params[TIME_PARAM].getValue();
        const double baseFeedback = params[FEEDBACK_PARAM].getValue();
        const double baseMix = params[MIX_PARAM].getValue();
        const double crossfeed = params[CROSSFEED_PARAM].getValue();
        for (int c = 0; c < channels; ++c) {
            const double left = inputs[LEFT_INPUT].getNormalPolyVoltage(0.0f, c);
            const double right = inputs[RIGHT_INPUT].getNormalPolyVoltage(
                static_cast<float>(left), c);
            const double timeCv = inputs[TIME_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            const double feedbackCv = inputs[FEEDBACK_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            const double mixCv = inputs[MIX_CV_INPUT].getNormalPolyVoltage(0.0f, c);

            using modular_synth::dsp::StereoEchoDSP;
            const double ms = baseMs +
                (StereoEchoDSP::finite(timeCv) ? timeCv * 100.0 : 0.0);
            const double feedback = baseFeedback +
                (StereoEchoDSP::finite(feedbackCv) ? feedbackCv * 0.1 : 0.0);
            const double wet = baseMix +
                (StereoEchoDSP::finite(mixCv) ? mixCv * 0.1 : 0.0);

            const auto sample = voices[static_cast<std::size_t>(c)].process(
                left, right, args.sampleRate, ms, feedback, wet, crossfeed);
            outputs[LEFT_OUTPUT].setVoltage(sample.left, c);
            outputs[RIGHT_OUTPUT].setVoltage(sample.right, c);
        }
    }
};

#ifndef HEADLESS
struct ModularSynthStereoEchoWidget : ModuleWidget {
    std::shared_ptr<Font> labelFont;

    explicit ModularSynthStereoEchoWidget(ModularSynthStereoEcho* const module) {
        setModule(module);
        setPanel(APP->window->loadSvg(asset::plugin(pluginInstance, "res/StereoEcho.svg")));
        labelFont = APP->window->loadFont(
            asset::system("res/fonts/ShareTechMono-Regular.ttf"));

        addChild(createWidget<ScrewSilver>(Vec(0.0f, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(0.0f, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(
            Vec(box.size.x - RACK_GRID_WIDTH, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));

        addParam(createParamCentered<RoundBlackKnob>(Vec(69.0f, 99.0f), module,
                                                     ModularSynthStereoEcho::TIME_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(171.0f, 99.0f), module,
                                                     ModularSynthStereoEcho::FEEDBACK_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(69.0f, 184.0f), module,
                                                     ModularSynthStereoEcho::MIX_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(171.0f, 184.0f), module,
                                                     ModularSynthStereoEcho::CROSSFEED_PARAM));

        addInput(createInputCentered<PJ301MPort>(Vec(34.0f, 273.0f), module,
                                                  ModularSynthStereoEcho::LEFT_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(91.0f, 273.0f), module,
                                                  ModularSynthStereoEcho::RIGHT_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(150.0f, 273.0f), module,
                                                  ModularSynthStereoEcho::TIME_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(207.0f, 273.0f), module,
                                                  ModularSynthStereoEcho::FEEDBACK_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(35.0f, 340.0f), module,
                                                  ModularSynthStereoEcho::MIX_CV_INPUT));

        addOutput(createOutputCentered<PJ301MPort>(Vec(115.0f, 340.0f), module,
                                                    ModularSynthStereoEcho::LEFT_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(180.0f, 340.0f), module,
                                                    ModularSynthStereoEcho::RIGHT_OUTPUT));
    }

    void draw(const DrawArgs& args) override {
        ModuleWidget::draw(args);
        if (!labelFont)
            return;
        nvgFontFaceId(args.vg, labelFont->handle);
        nvgTextAlign(args.vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);

        nvgFillColor(args.vg, nvgRGB(0xEC, 0xF4, 0xFF));
        nvgFontSize(args.vg, 17.0f);
        nvgText(args.vg, 120.0f, 21.0f, "STEREO ECHO", nullptr);
        nvgFillColor(args.vg, nvgRGB(0x96, 0xB3, 0xD4));
        nvgFontSize(args.vg, 10.5f);
        nvgText(args.vg, 120.0f, 41.0f, "MODULAR-SYNTH", nullptr);

        nvgFontSize(args.vg, 12.0f);
        nvgFillColor(args.vg, nvgRGB(0xDF, 0xE7, 0xFF));
        nvgText(args.vg, 69.0f, 61.0f, "TIME (MS)", nullptr);
        nvgText(args.vg, 171.0f, 61.0f, "FEEDBACK", nullptr);
        nvgText(args.vg, 69.0f, 144.0f, "DRY / WET", nullptr);
        nvgText(args.vg, 171.0f, 144.0f, "PING-PONG", nullptr);

        nvgFontSize(args.vg, 10.0f);
        nvgFillColor(args.vg, nvgRGB(0x9B, 0xDE, 0xE9));
        nvgText(args.vg, 34.0f, 241.0f, "IN L", nullptr);
        nvgText(args.vg, 91.0f, 241.0f, "IN R", nullptr);
        nvgText(args.vg, 150.0f, 241.0f, "TIME CV", nullptr);
        nvgText(args.vg, 207.0f, 241.0f, "FB CV", nullptr);
        nvgText(args.vg, 35.0f, 306.0f, "MIX CV", nullptr);

        nvgFontSize(args.vg, 11.0f);
        nvgFillColor(args.vg, nvgRGB(0xD6, 0xB5, 0xFF));
        nvgText(args.vg, 115.0f, 306.0f, "L OUT", nullptr);
        nvgText(args.vg, 180.0f, 306.0f, "R OUT", nullptr);
    }
};
#else
struct ModularSynthStereoEchoWidget : ModuleWidget {
    explicit ModularSynthStereoEchoWidget(ModularSynthStereoEcho* const module) {
        setModule(module);
    }
};
#endif

Model* modelStereoEcho =
    createModel<ModularSynthStereoEcho, ModularSynthStereoEchoWidget>("StereoEcho");
