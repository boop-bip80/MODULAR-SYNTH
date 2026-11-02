/*
 * MODULAR-SYNTH Fold Drive — original first-party module.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "plugin.hpp"
#include "FoldDrive.hpp"

#include <algorithm>
#include <atomic>
#include <memory>

struct ModularSynthFoldDrive : Module {
    enum ParamIds {
        DRIVE_PARAM,
        BIAS_PARAM,
        MIX_PARAM,
        NUM_PARAMS
    };
    enum InputIds {
        AUDIO_INPUT,
        DRIVE_CV_INPUT,
        BIAS_CV_INPUT,
        MIX_CV_INPUT,
        NUM_INPUTS
    };
    enum OutputIds {
        AUDIO_OUTPUT,
        NUM_OUTPUTS
    };
    enum LightIds {
        NUM_LIGHTS
    };

    modular_synth::dsp::FoldDrive voices[16];
    int previousChannels = 0;
    // Rack reset callbacks may run on a UI/host thread. Only process() owns
    // mutable DSP voices/channel state; the callback publishes a request.
    std::atomic<bool> pendingReset{false};

    ModularSynthFoldDrive() {
        config(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS);
        configParam(DRIVE_PARAM, 0.0f, 1.0f, 0.3f,
                    "Sine fold drive", " %", 0.0f, 100.0f);
        configParam(BIAS_PARAM, -1.0f, 1.0f, 0.0f,
                    "Fold asymmetry bias", " %", 0.0f, 100.0f);
        configParam(MIX_PARAM, 0.0f, 1.0f, 0.65f,
                    "Wet mix", " %", 0.0f, 100.0f);
        configInput(AUDIO_INPUT, "Audio signal (nominal +/-5 V)");
        configInput(DRIVE_CV_INPUT, "Drive CV (+10 V adds 100%; 3 ms slew)");
        configInput(BIAS_CV_INPUT, "Bias CV (+10 V adds +100%; 3 ms slew)");
        configInput(MIX_CV_INPUT, "Wet mix CV (+10 V adds 100%; 3 ms slew)");
        configOutput(AUDIO_OUTPUT, "Folded/dry mixed audio (+/-10 V maximum)");
    }

    void onReset(const ResetEvent& e) override {
        Module::onReset(e);
        pendingReset.store(true, std::memory_order_release);
    }

    void process(const ProcessArgs& args) override {
        if (pendingReset.load(std::memory_order_acquire)
                && pendingReset.exchange(false, std::memory_order_acq_rel)) {
            for (auto& voice : voices)
                voice.reset();
            previousChannels = 0;
        }

        int channels = std::max(1, inputs[AUDIO_INPUT].getChannels());
        channels = std::max(channels, inputs[DRIVE_CV_INPUT].getChannels());
        channels = std::max(channels, inputs[BIAS_CV_INPUT].getChannels());
        channels = std::max(channels, inputs[MIX_CV_INPUT].getChannels());
        channels = std::min(channels, 16);

        // Retire vanished lanes so reconnecting CV/poly audio never restores
        // stale smoothed control values from a previously active voice.
        for (int c = channels; c < previousChannels; ++c)
            voices[c].reset();
        previousChannels = channels;
        outputs[AUDIO_OUTPUT].setChannels(channels);

        const double drive = params[DRIVE_PARAM].getValue();
        const double bias = params[BIAS_PARAM].getValue();
        const double mix = params[MIX_PARAM].getValue();

        for (int c = 0; c < channels; ++c) {
            const double input = inputs[AUDIO_INPUT].getNormalPolyVoltage(0.0f, c);
            const double driveCV = inputs[DRIVE_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            const double biasCV = inputs[BIAS_CV_INPUT].getNormalPolyVoltage(0.0f, c);
            const double mixCV = inputs[MIX_CV_INPUT].getNormalPolyVoltage(0.0f, c);

            // Guard each source *before* adding it to a finite knob value;
            // NaN/Inf CV cannot poison the sum under aggressive fast-math.
            const auto safeCV = [](double cv) {
                return modular_synth::dsp::FoldDrive::ieeeFinite(cv) ? cv * 0.1 : 0.0;
            };
            const float output = voices[c].process(input, args.sampleRate,
                                                    drive + safeCV(driveCV),
                                                    bias + safeCV(biasCV),
                                                    mix + safeCV(mixCV));
            outputs[AUDIO_OUTPUT].setVoltage(output, c);
        }
    }
};

#ifndef HEADLESS
struct ModularSynthFoldDriveWidget : ModuleWidget {
    std::shared_ptr<Font> labelFont;

    explicit ModularSynthFoldDriveWidget(ModularSynthFoldDrive* const module) {
        setModule(module);
        setPanel(APP->window->loadSvg(asset::plugin(pluginInstance, "res/FoldDrive.svg")));
        labelFont = APP->window->loadFont(asset::system("res/fonts/ShareTechMono-Regular.ttf"));

        addChild(createWidget<ScrewSilver>(Vec(0.0f, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, 0.0f)));
        addChild(createWidget<ScrewSilver>(Vec(0.0f, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH,
                                                RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));

        addParam(createParamCentered<RoundBlackKnob>(Vec(48.0f, 100.0f), module,
                                                      ModularSynthFoldDrive::DRIVE_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(132.0f, 100.0f), module,
                                                      ModularSynthFoldDrive::BIAS_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(Vec(90.0f, 177.0f), module,
                                                      ModularSynthFoldDrive::MIX_PARAM));

        addInput(createInputCentered<PJ301MPort>(Vec(27.0f, 271.0f), module,
                                                  ModularSynthFoldDrive::AUDIO_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(69.0f, 271.0f), module,
                                                  ModularSynthFoldDrive::DRIVE_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(111.0f, 271.0f), module,
                                                  ModularSynthFoldDrive::BIAS_CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(153.0f, 271.0f), module,
                                                  ModularSynthFoldDrive::MIX_CV_INPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(90.0f, 350.0f), module,
                                                    ModularSynthFoldDrive::AUDIO_OUTPUT));
    }

    void draw(const DrawArgs& args) override {
        ModuleWidget::draw(args);
        if (!labelFont)
            return;

        nvgFontFaceId(args.vg, labelFont->handle);
        nvgTextAlign(args.vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);

        nvgFillColor(args.vg, nvgRGB(0xF3, 0xF1, 0xFF));
        nvgFontSize(args.vg, 18.0f);
        nvgText(args.vg, 90.0f, 22.0f, "FOLD DRIVE", nullptr);
        nvgFillColor(args.vg, nvgRGB(0xB4, 0xB7, 0xD7));
        nvgFontSize(args.vg, 10.5f);
        nvgText(args.vg, 90.0f, 40.0f, "MODULAR-SYNTH", nullptr);

        nvgFillColor(args.vg, nvgRGB(0xDB, 0xDE, 0xFF));
        nvgFontSize(args.vg, 12.0f);
        nvgText(args.vg, 48.0f, 60.0f, "DRIVE", nullptr);
        nvgText(args.vg, 132.0f, 60.0f, "BIAS", nullptr);
        nvgText(args.vg, 90.0f, 139.0f, "WET MIX", nullptr);

        nvgFillColor(args.vg, nvgRGB(0x93, 0xCF, 0xFF));
        nvgFontSize(args.vg, 10.0f);
        nvgText(args.vg, 27.0f, 237.0f, "IN", nullptr);
        nvgText(args.vg, 69.0f, 237.0f, "DRV", nullptr);
        nvgText(args.vg, 111.0f, 237.0f, "BIA", nullptr);
        nvgText(args.vg, 153.0f, 237.0f, "MIX", nullptr);

        nvgFillColor(args.vg, nvgRGB(0xD6, 0xAD, 0xFF));
        nvgFontSize(args.vg, 11.0f);
        nvgText(args.vg, 90.0f, 320.0f, "OUT", nullptr);
    }
};
#else
struct ModularSynthFoldDriveWidget : ModuleWidget {
    explicit ModularSynthFoldDriveWidget(ModularSynthFoldDrive* const module) {
        setModule(module);
    }
};
#endif

Model* modelFoldDrive = createModel<ModularSynthFoldDrive, ModularSynthFoldDriveWidget>("FoldDrive");
