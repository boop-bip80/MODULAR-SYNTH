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
#include "../plugins/ModularSynth/src/FMVoice.cpp"
#include "../plugins/ModularSynth/src/ChanceHold.cpp"

#include <cmath>
#include <atomic>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <new>
#include <stdexcept>
#include <string>
#include <thread>

// Guard steady-state process() against accidental heap work. The wrapper
// module's setup and fake JSON serializer may allocate; the audio tick may not.
namespace { std::atomic<std::size_t> heapAllocations{0}; }

void* operator new(std::size_t n) {
    heapAllocations.fetch_add(1, std::memory_order_relaxed);
    if (void* p = std::malloc(n == 0 ? 1 : n))
        return p;
    throw std::bad_alloc();
}
void* operator new[](std::size_t n) {
    heapAllocations.fetch_add(1, std::memory_order_relaxed);
    if (void* p = std::malloc(n == 0 ? 1 : n))
        return p;
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }

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

void regressionMacroResetAndReload(const rack::ProcessArgs& args) {
    constexpr int knob = ModularSynthMacro8::MACRO_1_PARAM;
    constexpr int out = ModularSynthMacro8::MACRO_1_OUTPUT;

    ModularSynthMacro8 playing;
    playing.params[ModularSynthMacro8::MORPH_TIME_PARAM].setValue(5.0f);
    playing.params[knob].setValue(1.0f);
    playing.process(args);
    require(playing.outputs[out].getVoltage() == 10.0f,
            "Macro8 lifecycle setup must start at +10 V");

    // A Rack module reset must drop the old smoothed value on the next
    // engine tick. Without deferred audio-thread reset, 5s morph keeps
    // emitting almost +10 V after the knob has been reset to zero.
    playing.params[knob].setValue(0.0f);
    playing.onReset(rack::ResetEvent{});
    const std::size_t beforeResetTick = heapAllocations.load(std::memory_order_relaxed);
    playing.process(args);
    const std::size_t afterResetTick = heapAllocations.load(std::memory_order_relaxed);
    require(afterResetTick == beforeResetTick,
            "Macro8 deferred reset audio tick must not allocate");
    require(playing.outputs[out].getVoltage() == 0.0f,
            "Macro8 onReset must discard pre-reset CV on next audio tick");

    ModularSynthMacro8 scene;
    scene.params[knob].setValue(0.3f);
    scene.params[ModularSynthMacro8::STORE_MODE_PARAM].setValue(1.0f);
    scene.params[ModularSynthMacro8::SLOT_A_PARAM].setValue(1.0f);
    scene.process(args);  // Capture A=0.3 via real audio-thread STORE path.
    scene.params[ModularSynthMacro8::SLOT_A_PARAM].setValue(0.0f);
    scene.params[ModularSynthMacro8::STORE_MODE_PARAM].setValue(0.0f);
    scene.process(args);  // Rearm A button.
    scene.params[ModularSynthMacro8::SLOT_A_PARAM].setValue(1.0f);
    scene.process(args);  // Recall A, then serialize selected scene.
    require(scene.selectedSlot.load(std::memory_order_acquire) == 0,
            "Macro8 lifecycle fixture must serialize selected snapshot A");
    std::unique_ptr<json_t> saved(scene.dataToJson());

    // Reload a selected snapshot while a 5-second morph still holds +10 V
    // from another patch. The very first tick must start at the SAVED scene
    // target (+3 V), not bleed previous-patch output into the new patch.
    playing.params[ModularSynthMacro8::MORPH_TIME_PARAM].setValue(0.0f);
    playing.params[knob].setValue(1.0f);
    playing.process(args);
    require(playing.outputs[out].getVoltage() == 10.0f,
            "Macro8 reload fixture must restore previous +10 V state");
    playing.params[ModularSynthMacro8::MORPH_TIME_PARAM].setValue(5.0f);
    playing.params[knob].setValue(0.0f);
    playing.params[ModularSynthMacro8::STORE_MODE_PARAM].setValue(1.0f);
    playing.params[ModularSynthMacro8::SLOT_A_PARAM].setValue(1.0f);
    playing.dataFromJson(saved.get());
    const std::size_t beforeReloadTick = heapAllocations.load(std::memory_order_relaxed);
    playing.process(args);
    const std::size_t afterReloadTick = heapAllocations.load(std::memory_order_relaxed);
    require(afterReloadTick == beforeReloadTick,
            "Macro8 deferred JSON reload audio tick must not allocate");
    require(std::abs(playing.outputs[out].getVoltage() - 3.0f) < 1.0e-5f,
            "Macro8 JSON reload must immediately start at saved selected scene");
    require(playing.selectedSlot.load(std::memory_order_acquire) == 0,
            "Macro8 JSON reload must preserve selected scene A");
    float snapshot[8]{};
    require(playing.snapshots.load(0, snapshot) &&
                std::abs(snapshot[0] - 0.3f) < 1.0e-6f,
            "Held scene button must not overwrite freshly restored snapshot A");

    // The held button must remain inhibited until a real release/repress;
    // afterward STORE should still work with the new live knob position.
    for (int n = 0; n < 100; ++n)
        playing.process(args);
    require(playing.snapshots.load(0, snapshot) &&
                std::abs(snapshot[0] - 0.3f) < 1.0e-6f,
            "Held scene button must not retrigger while high");
    playing.params[ModularSynthMacro8::SLOT_A_PARAM].setValue(0.0f);
    playing.process(args);
    playing.params[ModularSynthMacro8::SLOT_A_PARAM].setValue(1.0f);
    playing.process(args);
    require(playing.snapshots.load(0, snapshot) && snapshot[0] == 0.0f,
            "New press after reload must still capture the current live knob");

    const std::size_t allocationsBefore = heapAllocations.load(std::memory_order_relaxed);
    for (int n = 0; n < 10000; ++n)
        playing.process(args);
    const std::size_t allocationsAfter = heapAllocations.load(std::memory_order_relaxed);
    require(allocationsBefore == allocationsAfter,
            "Macro8 steady-state process() must never allocate");

    // Reset and state restore may arrive from a non-audio thread. Exercise
    // that schedule while one thread exclusively owns the DSP/trigger state.
    // This checks bounded output under contention; it does not substitute
    // for a data-race sanitizer or a real Rack host test.
    ModularSynthMacro8 concurrent;
    concurrent.params[knob].setValue(0.8f);
    concurrent.params[ModularSynthMacro8::MORPH_TIME_PARAM].setValue(5.0f);
    std::atomic<bool> finiteAndBounded{true};
    std::thread audio([&] {
        for (int n = 0; n < 50000; ++n) {
            concurrent.process(args);
            const float v = concurrent.outputs[out].getVoltage();
            if (!(v >= 0.0f && v <= 10.0f))
                finiteAndBounded.store(false, std::memory_order_relaxed);
        }
    });
    std::thread editor([&] {
        for (int n = 0; n < 3000; ++n) {
            if (n & 1)
                concurrent.onReset(rack::ResetEvent{});
            else
                concurrent.dataFromJson(saved.get());
        }
    });
    audio.join();
    editor.join();
    require(finiteAndBounded.load(std::memory_order_relaxed),
            "Macro8 threaded reset/restore stress must keep audio CV finite and bounded");
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

void smokeFM(const rack::ProcessArgs& args) {
    ModularSynthFMVoice module;
    require(module.params.size() == ModularSynthFMVoice::NUM_PARAMS, "FM params");
    require(module.inputs.size() == ModularSynthFMVoice::NUM_INPUTS, "FM inputs");
    module.inputs[ModularSynthFMVoice::PITCH_INPUT].setChannels(8);
    module.params[ModularSynthFMVoice::RATIO_PARAM].setValue(2.0f);
    module.params[ModularSynthFMVoice::INDEX_PARAM].setValue(2.5f);
    module.params[ModularSynthFMVoice::FEEDBACK_PARAM].setValue(0.2f);
    for (int c = 0; c < 8; ++c)
        module.inputs[ModularSynthFMVoice::PITCH_INPUT].setVoltage(0.25f * c, c);
    module.process(args);  // Initialize stub-port channel storage before allocation check.
    const std::size_t before = heapAllocations.load(std::memory_order_relaxed);
    for (int n = 0; n < 1024; ++n)
        module.process(args);
    const std::size_t after = heapAllocations.load(std::memory_order_relaxed);
    require(before == after, "FM audio callback must not allocate");
    outputsFinite(module, ModularSynthFMVoice::NUM_OUTPUTS, 8, "FMVoice");
    module.inputs[ModularSynthFMVoice::PITCH_INPUT].setChannels(1);
    module.process(args);
    outputsFinite(module, ModularSynthFMVoice::NUM_OUTPUTS, 1, "FM retired lanes");
    module.onReset();
    module.process(args);
    outputsFinite(module, ModularSynthFMVoice::NUM_OUTPUTS, 1, "FM reset");
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


void smokeChance(const rack::ProcessArgs& args) {
    ModularSynthChanceHold module;
    require(module.params.size() == ModularSynthChanceHold::NUM_PARAMS,
            "ChanceHold params");
    require(module.inputs.size() == ModularSynthChanceHold::NUM_INPUTS,
            "ChanceHold inputs");
    module.inputs[ModularSynthChanceHold::RATE_CV_INPUT].setChannels(16);
    module.params[ModularSynthChanceHold::CHANCE_PARAM].setValue(1.0f);
    module.params[ModularSynthChanceHold::GLIDE_PARAM].setValue(0.2f);
    module.process(args);
    const auto before = heapAllocations.load(std::memory_order_relaxed);
    for (int n = 0; n < 1024; ++n)
        module.process(args);
    const auto after = heapAllocations.load(std::memory_order_relaxed);
    require(before == after, "ChanceHold process must never allocate");
    outputsFinite(module, ModularSynthChanceHold::NUM_OUTPUTS, 16, "ChanceHold");
    module.inputs[ModularSynthChanceHold::RATE_CV_INPUT].setChannels(1);
    module.process(args);
    outputsFinite(module, ModularSynthChanceHold::NUM_OUTPUTS, 1, "Chance retired lanes");
    module.onReset();
    module.process(args);
    outputsFinite(module, ModularSynthChanceHold::NUM_OUTPUTS, 1, "Chance reset");
}

template <typename ModuleT>
void verifyDeferredHostReset(const rack::ProcessArgs& args, int inputId,
                             int outputCount, const char* label) {
    // Rack may dispatch reset on the editor thread while an engine callback
    // owns oscillator/filter/delay state. The callbacks must only publish an
    // atomic request; process() performs the first actual DSP reset.
    auto playing = std::make_unique<ModuleT>();
    auto pristine = std::make_unique<ModuleT>();
    for (ModuleT* module : {playing.get(), pristine.get()}) {
        module->inputs[static_cast<std::size_t>(inputId)].setChannels(4);
        for (int lane = 0; lane < 4; ++lane)
            module->inputs[static_cast<std::size_t>(inputId)].setVoltage(
                static_cast<float>(lane) * 0.125f, lane);
    }

    for (int n = 0; n < 512; ++n)
        playing->process(args);
    require(playing->previousChannels == 4,
            std::string(label) + " polyphonic setup did not activate 4 lanes");

    // Test both the legacy Rack reset callback and the modern event dispatch.
    // Either may be invoked on the host/UI thread. Neither may directly write
    // process-owned channel history or mutate DSP state.
    playing->onReset();
    require(playing->pendingReset.load(std::memory_order_acquire),
            std::string(label) + " legacy onReset did not publish a request");
    require(playing->previousChannels == 4,
            std::string(label) + " legacy onReset raced with channel history");
    playing->onReset(rack::ResetEvent{});
    require(playing->pendingReset.load(std::memory_order_acquire),
            std::string(label) + " event onReset did not publish a request");
    require(playing->previousChannels == 4,
            std::string(label) + " event onReset raced with channel history");

    const std::size_t before = heapAllocations.load(std::memory_order_relaxed);
    playing->process(args);
    const std::size_t after = heapAllocations.load(std::memory_order_relaxed);
    require(before == after,
            std::string(label) + " deferred reset audio tick allocated");
    pristine->process(args);
    require(!playing->pendingReset.load(std::memory_order_acquire),
            std::string(label) + " deferred reset request not consumed");
    require(playing->previousChannels == 4,
            std::string(label) + " reset did not restore active channel count");
    outputsFinite(*playing, outputCount, 4, label);

    // After a reset the very next audio sample must agree with an otherwise
    // identical fresh module; no old phase, envelope, PRNG or delay tail.
    for (int port = 0; port < outputCount; ++port) {
        for (int lane = 0; lane < 4; ++lane) {
            const float got = playing->outputs[static_cast<std::size_t>(port)].getVoltage(lane);
            const float expected = pristine->outputs[static_cast<std::size_t>(port)].getVoltage(lane);
            require(std::abs(got - expected) < 5.0e-5f,
                    std::string(label) + " reset did not replay first sample");
        }
    }

    std::atomic<bool> finite{true};
    std::thread engine([&] {
        for (int n = 0; n < 9000; ++n) {
            playing->process(args);
            for (int port = 0; port < outputCount; ++port)
                for (int lane = 0; lane < 4; ++lane)
                    if (!std::isfinite(playing->outputs[static_cast<std::size_t>(port)].getVoltage(lane)))
                        finite.store(false, std::memory_order_relaxed);
        }
    });
    std::thread host([&] {
        for (int n = 0; n < 1800; ++n) {
            if (n & 1)
                playing->onReset();
            else
                playing->onReset(rack::ResetEvent{});
        }
    });
    engine.join();
    host.join();
    require(finite.load(std::memory_order_relaxed),
            std::string(label) + " threaded reset emitted nonfinite audio/CV");
}

void regressionDeferredHostResets(const rack::ProcessArgs& args) {
    verifyDeferredHostReset<ModularSynthMorphVCO>(
        args, ModularSynthMorphVCO::PITCH_INPUT,
        ModularSynthMorphVCO::NUM_OUTPUTS, "MorphVCO host reset");
    verifyDeferredHostReset<ModularSynthStateFilter>(
        args, ModularSynthStateFilter::AUDIO_INPUT,
        ModularSynthStateFilter::NUM_OUTPUTS, "StateFilter host reset");
    verifyDeferredHostReset<ModularSynthStereoEcho>(
        args, ModularSynthStereoEcho::LEFT_INPUT,
        ModularSynthStereoEcho::NUM_OUTPUTS, "StereoEcho host reset");
    verifyDeferredHostReset<ModularSynthClockedLFO>(
        args, ModularSynthClockedLFO::RATE_CV_INPUT,
        ModularSynthClockedLFO::NUM_OUTPUTS, "ClockedLFO host reset");
    verifyDeferredHostReset<ModularSynthFMVoice>(
        args, ModularSynthFMVoice::PITCH_INPUT,
        ModularSynthFMVoice::NUM_OUTPUTS, "FMVoice host reset");
    verifyDeferredHostReset<ModularSynthChanceHold>(
        args, ModularSynthChanceHold::RATE_CV_INPUT,
        ModularSynthChanceHold::NUM_OUTPUTS, "ChanceHold host reset");
}

} // namespace

int main() {
    try {
        require(modelMorphVCO && modelStateFilter && modelMacro8 && modelStereoEcho &&
                    modelClockedLFO && modelFMVoice && modelChanceHold,
                "Seven shim-tested first-party models must instantiate");
        const rack::ProcessArgs args{};
        smokeMorph(args);
        smokeFilter(args);
        smokeMacro(args);
        regressionMacroResetAndReload(args);
        smokeEcho(args);
        smokeClock(args);
        smokeFM(args);
        smokeChance(args);
        regressionDeferredHostResets(args);
        std::cout << "PASS: 7 HEADLESS wrapper compile/process/port/reset smokes "
                     "and Macro8/six-wrapper deferred host reset regressions (test shim)\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
