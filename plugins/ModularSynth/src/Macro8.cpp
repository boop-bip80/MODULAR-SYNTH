/*
 * MODULAR-SYNTH Macro8 — first-party performance macro and snapshot module
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "plugin.hpp"
#include "Macro8.hpp"

#include <engine/Engine.hpp>
#include <ui/MenuItem.hpp>
#include <ui/MenuSeparator.hpp>
#include <ui/TextField.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <memory>
#include <string>

namespace {

std::string macro8CleanName(const std::string& source) {
    std::string name;
    name.reserve(12);
    for (unsigned char c : source) {
        if (name.size() >= 12)
            break;
        if (c >= 32 && c <= 126)
            name.push_back(static_cast<char>(c));
    }
    return name;
}

std::string macro8SafeName(const std::string& source, int index) {
    std::string name = macro8CleanName(source);
    if (name.empty())
        name = "Macro " + std::to_string(index + 1);
    return name;
}

} // namespace

struct ModularSynthMacro8 : Module {
    enum ParamIds {
        MACRO_1_PARAM, MACRO_2_PARAM, MACRO_3_PARAM, MACRO_4_PARAM,
        MACRO_5_PARAM, MACRO_6_PARAM, MACRO_7_PARAM, MACRO_8_PARAM,
        MORPH_TIME_PARAM,
        STORE_MODE_PARAM,
        SLOT_A_PARAM, SLOT_B_PARAM, SLOT_C_PARAM, SLOT_D_PARAM,
        LIVE_PARAM,
        RANGE_1_PARAM, RANGE_2_PARAM, RANGE_3_PARAM, RANGE_4_PARAM,
        RANGE_5_PARAM, RANGE_6_PARAM, RANGE_7_PARAM, RANGE_8_PARAM,
        NUM_PARAMS
    };
    enum InputIds { NUM_INPUTS };
    enum OutputIds {
        MACRO_1_OUTPUT, MACRO_2_OUTPUT, MACRO_3_OUTPUT, MACRO_4_OUTPUT,
        MACRO_5_OUTPUT, MACRO_6_OUTPUT, MACRO_7_OUTPUT, MACRO_8_OUTPUT,
        NUM_OUTPUTS
    };
    enum LightIds {
        SLOT_A_LIGHT, SLOT_B_LIGHT, SLOT_C_LIGHT, SLOT_D_LIGHT,
        LIVE_LIGHT, STORE_LIGHT,
        NUM_LIGHTS
    };

    modular_synth::dsp::Macro8Smoother smoother;
    modular_synth::dsp::Macro8SnapshotBank snapshots;
    // Rack's SchmittTrigger is default-constructible but not value-initializable
    // in the pinned SDK (its union constructor is inaccessible).
    std::array<dsp::SchmittTrigger, 4> slotTriggers;
    dsp::SchmittTrigger liveTrigger;
    std::atomic<int> selectedSlot{-1}; // -1 = live performer knobs
    // Rack reset/patch-restore callbacks may run off the engine thread.
    // Publish a request; only process() may touch smoother/trigger state.
    std::atomic<bool> resetAudioStateRequested{false};
    // Names are published as immutable strings. Rack hosts may serialize
    // state on a non-UI thread while the editor draws or edits a label.
    // Shared_ptr atomic load/store is only used OUTSIDE process().
    std::array<std::shared_ptr<const std::string>, 8> macroNames{};

    std::string nameAt(int index) const {
        const auto ptr = std::atomic_load_explicit(
            &macroNames[static_cast<std::size_t>(index)], std::memory_order_acquire);
        return ptr ? *ptr : ("Macro " + std::to_string(index + 1));
    }

    void setNameAt(int index, const std::string& text) {
        std::shared_ptr<const std::string> value =
            std::make_shared<const std::string>(macro8SafeName(text, index));
        std::atomic_store_explicit(
            &macroNames[static_cast<std::size_t>(index)],
            std::move(value), std::memory_order_release);
    }

    ModularSynthMacro8() {
        config(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS);
        for (int i = 0; i < 8; ++i)
            setNameAt(i, "Macro " + std::to_string(i + 1));

        for (int i = 0; i < 8; ++i) {
            const std::string label = "Macro " + std::to_string(i + 1);
            configParam(MACRO_1_PARAM + i, 0.0f, 1.0f, 0.0f,
                        label + " position", " %", 0.0f, 100.0f);
            configOutput(MACRO_1_OUTPUT + i,
                         label + " CV (0 to +10 V unipolar; -5 to +5 V bipolar)");
            configSwitch(RANGE_1_PARAM + i, 0.0f, 1.0f, 0.0f,
                         label + " output range",
                         {"Unipolar: 0 to +10 V", "Bipolar: -5 to +5 V"});
        }
        configParam(MORPH_TIME_PARAM, 0.0f, 5.0f, 0.25f,
                    "Snapshot transition time (99.9% settling)", " s");
        configSwitch(STORE_MODE_PARAM, 0.0f, 1.0f, 0.0f,
                     "Snapshot button action", {"Recall", "Store"});
        configButton(SLOT_A_PARAM, "Snapshot A (store or recall per mode)");
        configButton(SLOT_B_PARAM, "Snapshot B (store or recall per mode)");
        configButton(SLOT_C_PARAM, "Snapshot C (store or recall per mode)");
        configButton(SLOT_D_PARAM, "Snapshot D (store or recall per mode)");
        configButton(LIVE_PARAM, "Return to live macro knobs");

        configLight(SLOT_A_LIGHT, "Snapshot A active");
        configLight(SLOT_B_LIGHT, "Snapshot B active");
        configLight(SLOT_C_LIGHT, "Snapshot C active");
        configLight(SLOT_D_LIGHT, "Snapshot D active");
        configLight(LIVE_LIGHT, "Live macro knobs active");
        configLight(STORE_LIGHT, "Snapshot store mode armed");
    }

    void onReset(const ResetEvent& e) override {
        Module::onReset(e);
        snapshots.clear();
        selectedSlot.store(-1, std::memory_order_release);
        resetAudioStateRequested.store(true, std::memory_order_release);
    }

    void process(const ProcessArgs& args) override {
        // The overwhelmingly common path is a read-only atomic load; avoid
        // a cache-line-writing exchange on every single audio sample.
        if (resetAudioStateRequested.load(std::memory_order_acquire) &&
            resetAudioStateRequested.exchange(false, std::memory_order_acq_rel)) {
            // Discard voltage from the previous patch/reset on the audio
            // thread. Prime held buttons so reloading while one is down
            // cannot immediately STORE over a freshly restored snapshot.
            smoother.reset();
            for (int slot = 0; slot < 4; ++slot) {
                auto& trigger = slotTriggers[static_cast<std::size_t>(slot)];
                trigger.reset();
                trigger.process(params[SLOT_A_PARAM + slot].getValue());
            }
            liveTrigger.reset();
            liveTrigger.process(params[LIVE_PARAM].getValue());
        }
        const bool storing = params[STORE_MODE_PARAM].getValue() >= 0.5f;

        // Button edge detection and capture run only on the audio thread.
        for (int slot = 0; slot < 4; ++slot) {
            if (!slotTriggers[static_cast<std::size_t>(slot)].process(
                    params[SLOT_A_PARAM + slot].getValue()))
                continue;

            if (storing) {
                float knobValues[8];
                for (int i = 0; i < 8; ++i)
                    knobValues[i] = params[MACRO_1_PARAM + i].getValue();
                snapshots.store(slot, knobValues);
            } else if (snapshots.has(slot)) {
                selectedSlot.store(slot, std::memory_order_relaxed);
            }
        }
        if (liveTrigger.process(params[LIVE_PARAM].getValue()))
            selectedSlot.store(-1, std::memory_order_relaxed);

        float target[8];
        int active = selectedSlot.load(std::memory_order_acquire);
        // A bounded snapshot read returns false rather than spinning if a
        // patch-save/restore on another thread is updating the slot.
        bool usingSnapshot = active >= 0 && snapshots.load(active, target);
        if (!usingSnapshot && active >= 0 && snapshots.mayExist(active)) {
            // The other thread is temporarily publishing new snapshot bytes.
            // Hold the current audible values for this one sample, retaining
            // selection. A subsequent process tick will retry the snapshot.
            for (int i = 0; i < 8; ++i)
                target[i] = static_cast<float>(smoother.current[static_cast<std::size_t>(i)]);
            usingSnapshot = true;
        }
        if (!usingSnapshot) {
            active = -1;
            selectedSlot.store(-1, std::memory_order_relaxed);
            for (int i = 0; i < 8; ++i)
                target[i] = params[MACRO_1_PARAM + i].getValue();
        }

        smoother.process(args.sampleTime, params[MORPH_TIME_PARAM].getValue(), target);

        for (int i = 0; i < 8; ++i) {
            const bool bipolar = params[RANGE_1_PARAM + i].getValue() >= 0.5f;
            outputs[MACRO_1_OUTPUT + i].setChannels(1);
            outputs[MACRO_1_OUTPUT + i].setVoltage(
                modular_synth::dsp::Macro8Smoother::voltage(
                    smoother.current[static_cast<std::size_t>(i)], bipolar));
        }

        for (int i = 0; i < 4; ++i)
            lights[SLOT_A_LIGHT + i].setBrightness(active == i ? 1.0f : 0.0f);
        lights[LIVE_LIGHT].setBrightness(active < 0 ? 1.0f : 0.0f);
        lights[STORE_LIGHT].setBrightness(storing ? 1.0f : 0.0f);
    }

    json_t* dataToJson() override {
        json_t* const root = json_object();
        json_object_set_new(root, "macro8Version", json_integer(1));

        json_t* const names = json_array();
        for (int i = 0; i < 8; ++i) {
            const std::string label = nameAt(i);
            json_array_append_new(names, json_string(label.c_str()));
        }
        json_object_set_new(root, "names", names);

        json_t* const bank = json_array();
        for (int slot = 0; slot < 4; ++slot) {
            float values[8];
            bool loaded = snapshots.load(slot, values);
            // dataToJson is not an audio callback: bounded retries allow a
            // concurrent eight-value STORE to finish instead of saving null.
            for (int retry = 0; !loaded && retry < 4096 && snapshots.mayExist(slot); ++retry)
                loaded = snapshots.load(slot, values);
            if (!loaded) {
                json_array_append_new(bank, json_null());
                continue;
            }
            json_t* const row = json_array();
            for (float value : values)
                json_array_append_new(row, json_real(value));
            json_array_append_new(bank, row);
        }
        json_object_set_new(root, "snapshots", bank);
        json_object_set_new(root, "selectedSlot",
                            json_integer(selectedSlot.load(std::memory_order_relaxed)));
        return root;
    }

    void dataFromJson(json_t* root) override {
        if (!json_is_object(root))
            return;

        const json_t* const version = json_object_get(root, "macro8Version");
        if (!json_is_integer(version) || json_integer_value(version) != 1)
            return; // Unknown schema: preserve defaults rather than guess.

        const json_t* const names = json_object_get(root, "names");
        if (json_is_array(names)) {
            for (int i = 0; i < 8; ++i) {
                const json_t* const value = json_array_get(names, i);
                if (json_is_string(value))
                    setNameAt(i, json_string_value(value));
            }
        }

        snapshots.clear();
        const json_t* const bank = json_object_get(root, "snapshots");
        if (json_is_array(bank)) {
            for (int slot = 0; slot < 4; ++slot) {
                const json_t* const row = json_array_get(bank, slot);
                if (!json_is_array(row) || json_array_size(row) != 8)
                    continue;
                float values[8];
                bool valid = true;
                for (int i = 0; i < 8; ++i) {
                    const json_t* const value = json_array_get(row, i);
                    if (!json_is_number(value)) {
                        valid = false;
                        break;
                    }
                    values[i] = static_cast<float>(json_number_value(value));
                }
                if (valid)
                    snapshots.store(slot, values);
            }
        }

        const json_t* const selected = json_object_get(root, "selectedSlot");
        int slot = -1;
        if (json_is_integer(selected)) {
            const json_int_t value = json_integer_value(selected);
            if (value >= 0 && value < 4)
                slot = static_cast<int>(value);
        }
        selectedSlot.store(slot >= 0 && snapshots.has(slot) ? slot : -1,
                           std::memory_order_release);
        resetAudioStateRequested.store(true, std::memory_order_release);
    }
};

#ifndef HEADLESS

// Context-menu text fields synchronize on the UI thread, including keyboard
// editing and paste. They never allocate or read strings in process().
struct Macro8NameField : ui::TextField {
    ModularSynthMacro8* module = nullptr;
    int index = 0;

    Macro8NameField(ModularSynthMacro8* m, int i) : module(m), index(i) {
        box.size.x = 185.0f;
        text = module->nameAt(index);
    }
    void step() override {
        if (module) {
            const std::string clean = macro8CleanName(text);
            if (clean != text)
                setText(clean);
            if (module->nameAt(index) != macro8SafeName(clean, index))
                module->setNameAt(index, clean);
        }
        ui::TextField::step();
    }
};

struct ModularSynthMacro8Widget : ModuleWidget {
    std::shared_ptr<Font> labelFont;

    explicit ModularSynthMacro8Widget(ModularSynthMacro8* const module) {
        setModule(module);
        setPanel(APP->window->loadSvg(asset::plugin(pluginInstance, "res/Macro8.svg")));
        labelFont = APP->window->loadFont(asset::system("res/fonts/ShareTechMono-Regular.ttf"));

        addChild(createWidget<ScrewSilver>(Vec(0, 0)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, 0)));
        addChild(createWidget<ScrewSilver>(Vec(0, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH,
                                              RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));

        constexpr float columns[4] = {40.0f, 113.0f, 187.0f, 260.0f};
        for (int i = 0; i < 8; ++i) {
            const int row = i / 4;
            const float x = columns[i % 4];
            const float knobY = row == 0 ? 82.0f : 172.0f;
            const float outputY = row == 0 ? 125.0f : 215.0f;
            addParam(createParamCentered<RoundSmallBlackKnob>(
                Vec(x, knobY), module, ModularSynthMacro8::MACRO_1_PARAM + i));
            addOutput(createOutputCentered<PJ301MPort>(
                Vec(x, outputY), module, ModularSynthMacro8::MACRO_1_OUTPUT + i));
        }
        addParam(createParamCentered<RoundSmallBlackKnob>(
            Vec(78, 266), module, ModularSynthMacro8::MORPH_TIME_PARAM));
        addParam(createParamCentered<CKSS>(
            Vec(207, 267), module, ModularSynthMacro8::STORE_MODE_PARAM));
        addChild(createLightCentered<SmallLight<RedLight>>(
            Vec(239, 267), module, ModularSynthMacro8::STORE_LIGHT));

        constexpr float slots[5] = {34.0f, 91.0f, 148.0f, 205.0f, 262.0f};
        for (int i = 0; i < 4; ++i) {
            addParam(createParamCentered<LEDButton>(
                Vec(slots[i], 329), module, ModularSynthMacro8::SLOT_A_PARAM + i));
            addChild(createLightCentered<SmallLight<BlueLight>>(
                Vec(slots[i], 350), module, ModularSynthMacro8::SLOT_A_LIGHT + i));
        }
        addParam(createParamCentered<LEDButton>(
            Vec(slots[4], 329), module, ModularSynthMacro8::LIVE_PARAM));
        addChild(createLightCentered<SmallLight<GreenLight>>(
            Vec(slots[4], 350), module, ModularSynthMacro8::LIVE_LIGHT));
    }

    void draw(const DrawArgs& args) override {
        ModuleWidget::draw(args);
        if (!labelFont)
            return;
        nvgFontFaceId(args.vg, labelFont->handle);
        nvgTextAlign(args.vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);
        nvgFillColor(args.vg, nvgRGB(0xF6, 0xF2, 0xFF));
        nvgFontSize(args.vg, 18.0f);
        nvgText(args.vg, 150, 19, "MACRO 8", nullptr);
        nvgFontSize(args.vg, 10.0f);
        nvgFillColor(args.vg, nvgRGB(0x8F, 0xC9, 0xEA));
        nvgText(args.vg, 150, 36, "PERFORMANCE / SNAPSHOTS", nullptr);

        constexpr float columns[4] = {40.0f, 113.0f, 187.0f, 260.0f};
        const auto* const macro = dynamic_cast<const ModularSynthMacro8*>(module);
        nvgFontSize(args.vg, 10.5f);
        nvgFillColor(args.vg, nvgRGB(0xD6, 0xD9, 0xF7));
        for (int i = 0; i < 8; ++i) {
            const std::string label = macro
                ? macro->nameAt(i)
                : ("Macro " + std::to_string(i + 1));
            // Editable names can contain twelve characters. At the default
            // 10.5px mono size those can extend into adjacent 73px columns.
            // Fit the *measured* NanoVG advance to a 65px text lane without
            // changing the stored name, knob centers or module ID layout.
            nvgFontSize(args.vg, 10.5f);
            float bounds[4] = {};
            nvgTextBounds(args.vg, 0.0f, 0.0f, label.c_str(), nullptr, bounds);
            constexpr float maxLabelWidth = 65.0f;
            const float measuredWidth = bounds[2] - bounds[0];
            if (measuredWidth > maxLabelWidth)
                nvgFontSize(args.vg, 10.5f * maxLabelWidth / measuredWidth);
            nvgText(args.vg, columns[i % 4], i < 4 ? 55.0f : 145.0f,
                    label.c_str(), nullptr);
        }
        nvgFontSize(args.vg, 11.0f);
        nvgFillColor(args.vg, nvgRGB(0x92, 0xD0, 0xF7));
        nvgText(args.vg, 78, 243, "MORPH TIME", nullptr);
        nvgText(args.vg, 207, 242, "RECALL / STORE", nullptr);
        nvgFontSize(args.vg, 11.0f);
        nvgFillColor(args.vg, nvgRGB(0xE4, 0xCF, 0xFF));
        constexpr float slots[5] = {34.0f, 91.0f, 148.0f, 205.0f, 262.0f};
        constexpr const char* labels[5] = {"A", "B", "C", "D", "LIVE"};
        for (int i = 0; i < 5; ++i)
            nvgText(args.vg, slots[i], 304, labels[i], nullptr);
    }

    void appendContextMenu(ui::Menu* menu) override {
        auto* const macro = dynamic_cast<ModularSynthMacro8*>(module);
        if (!macro)
            return;

        menu->addChild(new ui::MenuSeparator);
        menu->addChild(createMenuLabel("MODULAR-SYNTH / Macro8"));
        menu->addChild(createMenuLabel("Store: switch to STORE, then press A-D"));
        menu->addChild(createMenuLabel("Recall: switch to RECALL, then press A-D"));
        menu->addChild(createMenuItem("Return to live knobs", "", [macro]() {
            macro->selectedSlot.store(-1, std::memory_order_release);
        }));
        menu->addChild(createSubmenuItem("Rename performance controls", "",
            [macro](ui::Menu* submenu) {
                for (int i = 0; i < 8; ++i) {
                    submenu->addChild(createMenuLabel("Macro " + std::to_string(i + 1)));
                    submenu->addChild(new Macro8NameField(macro, i));
                }
            }));
        menu->addChild(createSubmenuItem("CV output ranges", "",
            [macro](ui::Menu* submenu) {
                for (int i = 0; i < 8; ++i) {
                    submenu->addChild(createSubmenuItem(
                        "Macro " + std::to_string(i + 1), "",
                        [macro, i](ui::Menu* rangeMenu) {
                            rangeMenu->addChild(createCheckMenuItem(
                                "Unipolar: 0 to +10 V", "",
                                [macro, i]() {
                                    return macro->params[ModularSynthMacro8::RANGE_1_PARAM + i].getValue() < 0.5f;
                                },
                                [macro, i]() {
                                    APP->engine->setParamValue(macro, ModularSynthMacro8::RANGE_1_PARAM + i, 0.0f);
                                }));
                            rangeMenu->addChild(createCheckMenuItem(
                                "Bipolar: -5 to +5 V", "",
                                [macro, i]() {
                                    return macro->params[ModularSynthMacro8::RANGE_1_PARAM + i].getValue() >= 0.5f;
                                },
                                [macro, i]() {
                                    APP->engine->setParamValue(macro, ModularSynthMacro8::RANGE_1_PARAM + i, 1.0f);
                                }));
                        }));
                }
            }));
    }
};
#else
struct ModularSynthMacro8Widget : ModuleWidget {
    explicit ModularSynthMacro8Widget(ModularSynthMacro8* const module) {
        setModule(module);
    }
};
#endif

Model* modelMacro8 = createModel<ModularSynthMacro8, ModularSynthMacro8Widget>("Macro8");
