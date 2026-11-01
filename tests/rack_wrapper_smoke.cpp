/*
 * Compile and execute the ACTUAL first-party wrapper sources against the
 * narrowly defined test double in tests/rack_stub/ (HEADLESS only).
 * This cannot verify a Cardinal plugin, upstream Rack ABI, UI or DAW host.
 */
#ifndef HEADLESS
#error "Test only: compile with -DHEADLESS; never ship this shim"
#endif

#include "../plugins/ModularSynth/src/MorphVCO.cpp"
#include "../plugins/ModularSynth/src/StateFilter.cpp"
#include "../plugins/ModularSynth/src/Macro8.cpp"
#include "../plugins/ModularSynth/src/StereoEcho.cpp"
#include "../plugins/ModularSynth/src/ClockedLFO.cpp"

#include <cmath>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

namespace {

void require(bool okay, const std::string& message) {
    if (!okay)
        throw std::runtime_error(message);
}

void outputsFinite(const rack::Module& module, int count, int lanes, const char* label) {
    for (int port = 0; port < count; ++port) {
        const auto& output = module.outputs[static_cast<std::size_t>(port)];
        require(output.getChannels() == lanes,
                std::string(label) + " output channel count mismatch");
        for (int lane = 0; lane < lanes; ++lane)
            require(std::isfinite(output.getVoltage(lane)),
                    std::string(label) + " emitted non-finite sample");
    }
}

void smokeMorph(const rack::ProcessArgs& args) {
    ModularSynthMorphVCO module;
    require(module.params.size() == ModularSynthMorphVCO::NUM_PARAMS, "Morph params");
    require(module.inputs.size() == ModularSynthMorphVCO::NUM_INPUTS, "Morph inputs");
    module.inputs[ModularSynthMorphVCO::PITCH_INPUT].setChannels(8);
    for (int c = 0; c < 8; ++c)
        module.inputs[ModularSynthMorphVCO::PITCH_INPUT].setVoltage(c * 0.25f, c);
    for (int sample = 0; sample < 256; ++sample)
        module.process(args);
    outputsFinite(module, ModularSynthMorphVCO::NUM_OUTPUTS, 8, "MorphVCO");
    module.onReset();
    module.inputs[ModularSynthMorphVCO::PITCH_INPUT].setChannels(1);
    module.process(args);
    outputsFinite(module, ModularSynthMorphVCO::NUM_OUTPUTS, 1, "MorphVCO reset");
}

void smokeFilter(const rack::ProcessArgs& args) {
    ModularSynthStateFilter module;
    require(module.params.size() == ModularSynthStateFilter::NUM_PARAMS, "Filter params");
    module.inputs[ModularSynthStateFilter::AUDIO_INPUT].setChannels(4);
    for (int c = 0; c < 4; ++c)
        module.inputs[ModularSynthStateFilter::AUDIO_INPUT].setVoltage(c % 2 ? -1.0f : 1.0f, c);
    for (int sample = 0; sample < 256; ++sample)
        module.process(args);
    outputsFinite(module, ModularSynthStateFilter::NUM_OUTPUTS, 4, "StateFilter");
    module.onReset();
    module.inputs[ModularSynthStateFilter::AUDIO_INPUT].setChannels(1);
    module.process(args);
    outputsFinite(module, ModularSynthStateFilter::NUM_OUTPUTS, 1, "StateFilter reset");
}

void smokeMacro(const rack::ProcessArgs& args) {
    ModularSynthMacro8 module;
    require(module.outputs.size() == ModularSynthMacro8::NUM_OUTPUTS, "Macro outputs");
    module.params[ModularSynthMacro8::MACRO_1_PARAM].setValue(0.75f);
    for (int sample = 0; sample < 128; ++sample)
        module.process(args);
    outputsFinite(module, ModularSynthMacro8::NUM_OUTPUTS, 1, "Macro8");

    // Store scene A using the real wrapper's audio-thread button path.
    module.params[ModularSynthMacro8::STORE_MODE_PARAM].setValue(1.0f);
    module.params[ModularSynthMacro8::SLOT_A_PARAM].setValue(1.0f);
    module.process(args);

    // Exercise the actual wrapper serialization, using an explicitly fake
    // in-memory JSON API. This is not a real Rack/Jansson roundtrip.
    std::unique_ptr<json_t> saved(module.dataToJson());
    require(saved != nullptr && json_is_object(saved.get()), "Macro8 save JSON");
    require(json_array_size(json_object_get(saved.get(), "names")) == 8,
            "Macro8 name serialization");
    const auto* bank = json_object_get(saved.get(), "snapshots");
    require(json_array_size(bank) == 4 && json_array_size(json_array_get(bank, 0)) == 8,
            "Macro8 stored scene serialization");
    ModularSynthMacro8 restored;
    restored.dataFromJson(saved.get());
    restored.process(args);
    outputsFinite(restored, ModularSynthMacro8::NUM_OUTPUTS, 1, "Macro8 load");
}

void smokeEcho(const rack::ProcessArgs& args) {
    // Large delay buffers belong on the heap to avoid an artificial test
    // harness stack fault unrelated to the Rack module's engine allocation.
    auto module = std::make_unique<ModularSynthStereoEcho>();
    require(module->params.size() == ModularSynthStereoEcho::NUM_PARAMS, "Echo params");
    module->inputs[ModularSynthStereoEcho::LEFT_INPUT].setChannels(2);
    module->inputs[ModularSynthStereoEcho::LEFT_INPUT].setVoltage(1.0f, 0);
    module->inputs[ModularSynthStereoEcho::LEFT_INPUT].setVoltage(-1.0f, 1);
    for (int sample = 0; sample < 128; ++sample)
        module->process(args);
    outputsFinite(*module, ModularSynthStereoEcho::NUM_OUTPUTS, 2, "StereoEcho");
    // The right jack is deliberately unplugged; it should normal to left.
    require(!module->inputs[ModularSynthStereoEcho::RIGHT_INPUT].isConnected(),
            "Echo right normal test setup");
    for (int c = 0; c < 2; ++c) {
        const float left = module->outputs[ModularSynthStereoEcho::LEFT_OUTPUT].getVoltage(c);
        const float right = module->outputs[ModularSynthStereoEcho::RIGHT_OUTPUT].getVoltage(c);
        require(std::abs(left - right) < 1.0e-5f,
                "StereoEcho unpatched-right normal must match left output initially");
    }
    module->onReset();
    module->process(args);
    outputsFinite(*module, ModularSynthStereoEcho::NUM_OUTPUTS, 2, "Echo reset");
}

void smokeClock(const rack::ProcessArgs& args) {
    ModularSynthClockedLFO module;
    require(module.params.size() == ModularSynthClockedLFO::NUM_PARAMS, "LFO params");
    module.inputs[ModularSynthClockedLFO::RATE_CV_INPUT].setChannels(3);
    for (int sample = 0; sample < 256; ++sample)
        module.process(args);
    outputsFinite(module, ModularSynthClockedLFO::NUM_OUTPUTS, 3, "ClockedLFO");
    module.onReset();
    module.inputs[ModularSynthClockedLFO::RATE_CV_INPUT].setChannels(1);
    module.process(args);
    outputsFinite(module, ModularSynthClockedLFO::NUM_OUTPUTS, 1, "LFO reset");
}

} // namespace

int main() {
    try {
        require(modelMorphVCO && modelStateFilter && modelMacro8 && modelStereoEcho &&
                    modelClockedLFO, "Five first-party models must instantiate");
        const rack::ProcessArgs args{};
        smokeMorph(args);
        smokeFilter(args);
        smokeMacro(args);
        smokeEcho(args);
        smokeClock(args);
        std::cout << "PASS: 5 HEADLESS wrapper compile/process/port/reset smokes (test shim)\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
