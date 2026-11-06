/*
 * MODULAR-SYNTH ScaleQuantizer — 16-lane scale-aware 1 V/oct CV quantization.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "plugin.hpp"
#include "ScaleQuantizer.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <memory>

struct ModularSynthScaleQuantizer : Module {
    enum ParamIds { ROOT_PARAM, SCALE_PARAM, TRANSPOSE_PARAM, HYST_PARAM, NUM_PARAMS };
    enum InputIds { PITCH_INPUT, TRANSPOSE_CV_INPUT, ROOT_CV_INPUT, NUM_INPUTS };
    enum OutputIds { PITCH_OUTPUT, CHANGE_OUTPUT, NUM_OUTPUTS };
    enum LightIds { NUM_LIGHTS };

    std::array<modular_synth::dsp::ScaleQuantizer, 16> voices;
    int previousChannels = 0;
    std::atomic<bool> pendingReset{false};

    ModularSynthScaleQuantizer() {
        config(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS);
        configSwitch(ROOT_PARAM, 0.0f, 11.0f, 0.0f, "Root pitch class",
                     {"C", "C#", "D", "D#", "E", "F", "F#", "G",
                      "G#", "A", "A#", "B"});
        configSwitch(SCALE_PARAM, 0.0f, 7.0f, 0.0f, "Scale",
                     {"Chromatic", "Major", "Natural Minor", "Dorian",
                      "Harmonic Minor", "Major Pentatonic", "Minor Pentatonic",
                      "Whole Tone"});
        configParam(TRANSPOSE_PARAM, -12.0f, 12.0f, 0.0f, "Transpose (semitones)");
        getParamQuantity(TRANSPOSE_PARAM)->snapEnabled = true;
        configParam(HYST_PARAM, 0.0f, 50.0f, 12.0f, "Pitch-change hysteresis", " cents");
        configInput(PITCH_INPUT, "Pitch CV (1 V/oct, +/-10 V)");
        configInput(TRANSPOSE_CV_INPUT, "Transpose CV (1 V/oct)");
        configInput(ROOT_CV_INPUT, "Root offset CV (1 V/oct, semitone-quantized)");
        configOutput(PITCH_OUTPUT, "Quantized pitch (1 V/oct)");
        configOutput(CHANGE_OUTPUT, "Pitch-change trigger (+10 V for 2 ms)");
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

        const int root = static_cast<int>(std::round(params[ROOT_PARAM].getValue()));
        const int scale = static_cast<int>(std::round(params[SCALE_PARAM].getValue()));
        const int transpose = static_cast<int>(std::round(params[TRANSPOSE_PARAM].getValue()));
        const double hysteresis = params[HYST_PARAM].getValue();
        for (int c = 0; c < channels; ++c) {
            modular_synth::dsp::ScaleQuantizer::Input in;
            in.sampleRateHz = args.sampleRate;
            in.pitchVolts = inputs[PITCH_INPUT].getNormalPolyVoltage(0.0f, c);
            in.transposeCvVolts = inputs[TRANSPOSE_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            in.rootCvVolts = inputs[ROOT_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            in.root = root;
            in.scale = scale;
            in.transposeSemitones = transpose;
            in.hysteresisCents = hysteresis;
            const auto result = voices[static_cast<std::size_t>(c)].process(in);
            outputs[PITCH_OUTPUT].setVoltage(result.pitchVolts, c);
            outputs[CHANGE_OUTPUT].setVoltage(result.changedGate, c);
        }
    }
};

#ifndef HEADLESS
struct ModularSynthScaleQuantizerWidget : ModuleWidget {
    std::shared_ptr<Font> labelFont;

    explicit ModularSynthScaleQuantizerWidget(ModularSynthScaleQuantizer* const module) {
        setModule(module);
        setPanel(APP->window->loadSvg(asset::plugin(pluginInstance, "res/ScaleQuantizer.svg")));
        labelFont = APP->window->loadFont(asset::system("res/fonts/ShareTechMono-Regular.ttf"));

        addChild(createWidget<ScrewSilver>(Vec(0.0f, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(0.0f, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH,
                                                RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addParam(createParamCentered<RoundBlackKnob>(
            Vec(45.0f, 110.0f), module, ModularSynthScaleQuantizer::ROOT_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(
            Vec(135.0f, 110.0f), module, ModularSynthScaleQuantizer::SCALE_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(
            Vec(45.0f, 187.0f), module, ModularSynthScaleQuantizer::TRANSPOSE_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(
            Vec(135.0f, 187.0f), module, ModularSynthScaleQuantizer::HYST_PARAM));
        addInput(createInputCentered<PJ301MPort>(
            Vec(30.0f, 269.0f), module, ModularSynthScaleQuantizer::PITCH_INPUT));
        addInput(createInputCentered<PJ301MPort>(
            Vec(90.0f, 269.0f), module, ModularSynthScaleQuantizer::TRANSPOSE_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(
            Vec(150.0f, 269.0f), module, ModularSynthScaleQuantizer::ROOT_CV_INPUT));
        addOutput(createOutputCentered<PJ301MPort>(
            Vec(60.0f, 341.0f), module, ModularSynthScaleQuantizer::PITCH_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(
            Vec(120.0f, 341.0f), module, ModularSynthScaleQuantizer::CHANGE_OUTPUT));
    }

    void draw(const DrawArgs& args) override {
        ModuleWidget::draw(args);
        if (!labelFont)
            return;
        nvgFontFaceId(args.vg, labelFont->handle);
        nvgTextAlign(args.vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);
        nvgFillColor(args.vg, nvgRGB(0xEB, 0xF7, 0xFF));
        nvgFontSize(args.vg, 15.0f);
        nvgText(args.vg, 90.0f, 20.0f, "SCALE QUANT", nullptr);
        nvgFillColor(args.vg, nvgRGB(0xA5, 0xD2, 0xEA));
        nvgFontSize(args.vg, 10.0f);
        nvgText(args.vg, 90.0f, 40.0f, "MODULAR-SYNTH", nullptr);
        nvgFontSize(args.vg, 11.0f);
        nvgFillColor(args.vg, nvgRGB(0xED, 0xF8, 0xFF));
        nvgText(args.vg, 45.0f, 76.0f, "ROOT", nullptr);
        nvgText(args.vg, 135.0f, 76.0f, "SCALE", nullptr);
        nvgText(args.vg, 45.0f, 153.0f, "TRANS", nullptr);
        nvgText(args.vg, 135.0f, 153.0f, "HYST", nullptr);
        nvgFillColor(args.vg, nvgRGB(0x96, 0xE8, 0xF4));
        nvgText(args.vg, 32.0f, 240.0f, "PITCH", nullptr);
        nvgText(args.vg, 90.0f, 240.0f, "TRANS", nullptr);
        nvgText(args.vg, 150.0f, 240.0f, "ROOT", nullptr);
        nvgFillColor(args.vg, nvgRGB(0xFF, 0xD6, 0xAA));
        nvgText(args.vg, 60.0f, 312.0f, "QUANT", nullptr);
        nvgText(args.vg, 120.0f, 312.0f, "CHANGE", nullptr);
    }
};
#else
struct ModularSynthScaleQuantizerWidget : ModuleWidget {
    explicit ModularSynthScaleQuantizerWidget(ModularSynthScaleQuantizer* const module) {
        setModule(module);
    }
};
#endif

Model* modelModularSynthScaleQuantizer = createModel<ModularSynthScaleQuantizer,
    ModularSynthScaleQuantizerWidget>("ScaleQuantizer");
