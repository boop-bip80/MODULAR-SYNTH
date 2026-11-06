/*
 * MODULAR-SYNTH standalone DSP microbenchmark (not a Cardinal/DAW benchmark).
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Eight source DSP cores, deterministic control/audio stimuli, no host/Rack.
 * Time is informational; functional and allocation checks are acceptance gates.
 */

#include "../../plugins/ModularSynth/src/MorphVCO.hpp"
#include "../../plugins/ModularSynth/src/StateFilter.hpp"
#include "../../plugins/ModularSynth/src/FMVoice.hpp"
#include "../../plugins/ModularSynth/src/StereoEcho.hpp"
#include "../../plugins/ModularSynth/src/FoldDrive.hpp"
#include "../../plugins/ModularSynth/src/ClockedLFO.hpp"
#include "../../plugins/ModularSynth/src/ChanceHold.hpp"
#include "../../plugins/ModularSynth/src/SlewGlide.hpp"

#include <array>
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <new>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
std::atomic<bool> gTrackNew(false);
std::atomic<std::uint64_t> gNewCalls(0);
std::atomic<bool> gTrackPreparation(false);
std::atomic<std::uint64_t> gPreparedCppNewBytes(0);
}

// The measurement counts C++ new/new[] calls in the sample loop. It does not
// intercept malloc, aligned allocators, or allocations in a real audio host.
void* operator new(std::size_t bytes) {
    if (gTrackNew.load(std::memory_order_relaxed))
        gNewCalls.fetch_add(1u, std::memory_order_relaxed);
    if (gTrackPreparation.load(std::memory_order_relaxed))
        gPreparedCppNewBytes.fetch_add(static_cast<std::uint64_t>(bytes),
                                      std::memory_order_relaxed);
    if (void* memory = std::malloc(bytes == 0 ? 1u : bytes))
        return memory;
    throw std::bad_alloc();
}

void* operator new[](std::size_t bytes) {
    return ::operator new(bytes);
}

// GCC 13's aggressive interprocedural mismatched-new-delete heuristic treats
// the intentional malloc/free-backed global new override as foreign to STL
// allocator new expressions if it inlines these shims into vector teardown.
// Keep the delete shims opaque without suppressing the project's -Werror.
#if defined(__GNUC__) || defined(__clang__)
__attribute__((noinline))
#endif
void operator delete(void* memory) noexcept { std::free(memory); }
#if defined(__GNUC__) || defined(__clang__)
__attribute__((noinline))
#endif
void operator delete[](void* memory) noexcept { ::operator delete(memory); }
#if __cplusplus >= 201402L
#if defined(__GNUC__) || defined(__clang__)
__attribute__((noinline))
#endif
void operator delete(void* memory, std::size_t) noexcept { std::free(memory); }
#if defined(__GNUC__) || defined(__clang__)
__attribute__((noinline))
#endif
void operator delete[](void* memory, std::size_t) noexcept { ::operator delete(memory); }
#endif

namespace {
namespace dsp = modular_synth::dsp;

static constexpr double kTwoPi = 6.283185307179586476925286766559;
static constexpr std::size_t kSignalPeriod = 1024;

bool finiteBits(double value) noexcept {
    std::uint64_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return (bits & UINT64_C(0x7ff0000000000000)) != UINT64_C(0x7ff0000000000000);
}

const std::array<float, kSignalPeriod>& inputTable() {
    static const std::array<float, kSignalPeriod> table = [] {
        std::array<float, kSignalPeriod> values = {};
        for (std::size_t n = 0; n < values.size(); ++n) {
            const double phase = kTwoPi * static_cast<double>(n) / values.size();
            values[n] = static_cast<float>(0.5 * std::sin(phase)
                                         + 0.16 * std::sin(3.0 * phase));
        }
        return values;
    }();
    return table;
}

struct MorphStep {
    double operator()(dsp::MorphOscillator& engine, int frame, int voice,
                      double rate, float) const noexcept {
        const float morph = (frame & 2047) < 1024 ? 0.23f : 0.76f;
        const dsp::MorphOscillator::Sample sample = engine.process(
            110.0 + 19.0 * voice, rate, morph, 0.32f + voice * 0.006f);
        return static_cast<double>(sample.sine) * sample.sine
             + static_cast<double>(sample.morph) * sample.morph;
    }
};

struct FilterStep {
    double operator()(dsp::StateFilter& engine, int frame, int voice,
                      double rate, float signal) const noexcept {
        const double cutoff = 400.0 + voice * 100.0
                            + ((frame & 4095) < 2048 ? 900.0 : 1800.0);
        const dsp::StateFilter::Sample sample = engine.process(
            5.0 * signal, rate, cutoff, 0.48, 0.35);
        return static_cast<double>(sample.low) * sample.low
             + static_cast<double>(sample.band) * sample.band
             + static_cast<double>(sample.high) * sample.high;
    }
};

struct FMStep {
    double operator()(dsp::FMVoice& engine, int frame, int voice,
                      double rate, float) const noexcept {
        const double index = (frame & 4095) < 2048 ? 2.5 : 3.75;
        const dsp::FMVoice::Input input(
            140.0 + voice * 17.0, rate, 2.0, index, -0.24);
        const dsp::FMVoice::Output sample = engine.process(input);
        return static_cast<double>(sample.carrier) * sample.carrier
             + static_cast<double>(sample.modulator) * sample.modulator;
    }
};

struct EchoStep {
    double operator()(dsp::StereoEchoDSP& engine, int frame, int voice,
                      double rate, float signal) const noexcept {
        const double left = static_cast<double>(signal) * 5.0;
        const double right = static_cast<double>(inputTable()[
            (static_cast<std::size_t>(frame) + 139u) % kSignalPeriod]) * 5.0;
        const double delayMs = 55.0 + voice * 1.2;
        const dsp::StereoEchoDSP::Sample sample = engine.process(
            left, right, rate, delayMs, 0.4, 0.65, 0.2);
        return static_cast<double>(sample.left) * sample.left
             + static_cast<double>(sample.right) * sample.right;
    }
};

struct FoldStep {
    double operator()(dsp::FoldDrive& engine, int frame, int voice,
                      double rate, float signal) const noexcept {
        const double drive = (frame & 4095) < 2048 ? 0.63 : 0.81;
        const double bias = (voice % 3 - 1) * 0.19;
        const double output = engine.process(
            5.0 * signal, rate, drive, bias, 0.8);
        return output * output;
    }
};

struct ClockStep {
    double operator()(dsp::ClockedLFO& engine, int frame, int voice,
                      double rate, float) const noexcept {
        dsp::ClockedLFO::Input input;
        input.sampleRateHz = rate;
        input.log2RateHz = -1.0 + 0.08 * voice;
        input.rateCvVolts = (frame & 8191) < 4096 ? 0.0 : 0.32;
        input.ratioIndex = static_cast<double>(1 + voice % 3);
        input.phaseOffset = voice * 0.02;
        input.pulseWidth = 0.38 + voice * 0.01;
        // Both free and externally clocked lanes are exercised. Clock periods
        // are exact frame-count multiples at each rate, independent of CPU.
        input.clockConnected = (voice & 1) != 0;
        const int clockPeriodFrames = static_cast<int>(rate / 8.0);
        input.clockVoltage = input.clockConnected &&
            frame % clockPeriodFrames < 8 ? 10.0 : 0.0;
        const dsp::ClockedLFO::Output output = engine.process(input);
        return static_cast<double>(output.sine) * output.sine
             + static_cast<double>(output.triangle) * output.triangle
             + static_cast<double>(output.pulse) * output.pulse;
    }
};

struct ChanceStep {
    double operator()(dsp::ChanceHold& engine, int frame, int voice,
                      double rate, float) const noexcept {
        dsp::ChanceHold::Input input;
        input.sampleRateHz = rate;
        input.log2RateHz = 4.0;
        input.rateCvVolts = voice * 0.03;
        input.probability = 1.0;
        input.glideSeconds = (frame & 8191) < 4096 ? 0.05 : 0.2;
        input.semitoneQuantize = (voice & 1) != 0;
        const dsp::ChanceHold::Output output = engine.process(input);
        return static_cast<double>(output.held) * output.held
             + static_cast<double>(output.glide) * output.glide
             + static_cast<double>(output.trigger) * output.trigger;
    }
};

struct SlewStep {
    double operator()(dsp::SlewGlide& engine, int frame, int voice,
                      double rate, float signal) const noexcept {
        dsp::SlewGlide::Input input;
        input.sampleRateHz = rate;
        // Alternating bipolar targets drive both rise and fall paths, even
        // during short 1024-frame smoke runs. Audio-rate ripple and a small
        // per-voice offset keep simultaneous lanes distinct and nonconstant.
        const bool risingTarget = ((frame / 768 + voice) & 1) != 0;
        input.voltage = (risingTarget ? 4.25 : -3.75)
                      + 0.65 * static_cast<double>(signal) + 0.07 * voice;
        input.riseSeconds = 0.028 + 0.003 * (voice % 5);
        input.fallSeconds = 0.049 + 0.004 * (voice % 5);
        // Finite, changing control CV updates the real core's cached
        // directional coefficients during the measured processing workload.
        input.riseCvVolts = ((frame / 512 + voice) & 1) != 0 ? 0.07 : -0.018;
        input.fallCvVolts = ((frame / 384 + voice) & 1) != 0 ? 0.05 : -0.028;
        const dsp::SlewGlide::Output output = engine.process(input);
        return static_cast<double>(output.linear) * output.linear
             + static_cast<double>(output.exponential) * output.exponential
             + 0.01 * static_cast<double>(output.movingGate) * output.movingGate;
    }
};

struct Measurement {
    const char* engine;
    int voices;
    int sampleRate;
    int frames;
    int warmupFrames;
    std::uint64_t timedVoiceSamples;
    double elapsedMs;
    double nsPerVoiceSample;
    double realtimeFactor;
    double meanEnergy;
    std::uint64_t newCalls;
    std::size_t preparedBytesHint;
    std::uint64_t preparedCppNewBytes;
    int repetitions;
    double minElapsedMs;
    double p90ElapsedMs;
    double maxElapsedMs;
};

template <typename Engine, typename Step>
Measurement measureOnce(const char* name, int voices, int sampleRate, int frames,
                        std::size_t extraBytesPerVoice = 0u) {
    // Important: 16 StereoEcho voices allocate ~23.4 MiB, but all constructors,
    // table initialization and warmup execute before timing/heap tracking.
    gPreparedCppNewBytes.store(0u, std::memory_order_relaxed);
    gTrackPreparation.store(true, std::memory_order_relaxed);
    std::vector<Engine> state(static_cast<std::size_t>(voices));
    gTrackPreparation.store(false, std::memory_order_relaxed);
    const std::uint64_t preparedNewBytes =
        gPreparedCppNewBytes.load(std::memory_order_relaxed);
    const std::array<float, kSignalPeriod>& signal = inputTable();
    const Step step;
    const int warmupFrames = sampleRate / 12; // 83 ms: primes the 55-73 ms delay.
    for (int frame = 0; frame < warmupFrames; ++frame)
        for (int voice = 0; voice < voices; ++voice)
            step(state[static_cast<std::size_t>(voice)], frame, voice,
                 static_cast<double>(sampleRate),
                 signal[static_cast<std::size_t>(frame) % kSignalPeriod]);

    double energy = 0.0;
    bool finite = true;
    gNewCalls.store(0u, std::memory_order_relaxed);
    const std::chrono::steady_clock::time_point start = std::chrono::steady_clock::now();
    gTrackNew.store(true, std::memory_order_relaxed);
    for (int frame = 0; frame < frames; ++frame) {
        // Continue the input/control timeline after warmup. Restarting it at
        // frame zero would introduce an artificial discontinuity at timing.
        const int absoluteFrame = frame + warmupFrames;
        const float signalValue = signal[static_cast<std::size_t>(absoluteFrame)
                                         % kSignalPeriod];
        for (int voice = 0; voice < voices; ++voice) {
            const double sampleEnergy = step(state[static_cast<std::size_t>(voice)],
                                             absoluteFrame, voice,
                                             static_cast<double>(sampleRate),
                                             signalValue);
            if (!finiteBits(sampleEnergy) || sampleEnergy < 0.0)
                finite = false;
            energy += sampleEnergy;
        }
    }
    gTrackNew.store(false, std::memory_order_relaxed);
    const std::chrono::steady_clock::time_point end = std::chrono::steady_clock::now();
    const std::uint64_t allocations = gNewCalls.load(std::memory_order_relaxed);
    const double elapsedNs = std::chrono::duration<double, std::nano>(end - start).count();
    const double voiceSamples = static_cast<double>(voices) * frames;
    const double averageEnergy = energy / voiceSamples;
    if (!finite || !finiteBits(averageEnergy) || averageEnergy <= 0.0 || allocations != 0u
        || !finiteBits(elapsedNs) || elapsedNs <= 0.0)
        throw std::runtime_error(std::string(name)
            + ": invalid output energy/timing or C++ allocation inside sample loop");

    Measurement result = {};
    result.engine = name;
    result.voices = voices;
    result.sampleRate = sampleRate;
    result.frames = frames;
    result.warmupFrames = warmupFrames;
    result.timedVoiceSamples = static_cast<std::uint64_t>(voices) * frames;
    result.elapsedMs = elapsedNs / 1.0e6;
    result.nsPerVoiceSample = elapsedNs / voiceSamples;
    result.realtimeFactor = (elapsedNs / 1.0e9) / (frames / static_cast<double>(sampleRate));
    result.meanEnergy = averageEnergy;
    result.newCalls = allocations;
    result.preparedBytesHint = static_cast<std::size_t>(voices)
                             * (sizeof(Engine) + extraBytesPerVoice);
    result.preparedCppNewBytes = preparedNewBytes;
    result.repetitions = 1;
    result.minElapsedMs = result.elapsedMs;
    result.p90ElapsedMs = result.elapsedMs;
    result.maxElapsedMs = result.elapsedMs;
    return result;
}

template <typename Engine, typename Step>
Measurement measure(const char* name, int voices, int sampleRate, int frames,
                    int repetitions, std::size_t extraBytesPerVoice = 0u) {
    // Reconstruct and warm fresh engine states before every timed repetition.
    // Median elapsed time is more useful than a single scheduling outlier,
    // but deliberately remains observational rather than a CI pass threshold.
    std::vector<double> times;
    times.reserve(static_cast<std::size_t>(repetitions));
    Measurement aggregate = {};
    for (int trial = 0; trial < repetitions; ++trial) {
        const Measurement next = measureOnce<Engine, Step>(
            name, voices, sampleRate, frames, extraBytesPerVoice);
        if (trial == 0)
            aggregate = next;
        else if (aggregate.meanEnergy != next.meanEnergy
                 || aggregate.preparedBytesHint != next.preparedBytesHint
                 || aggregate.preparedCppNewBytes != next.preparedCppNewBytes)
            throw std::runtime_error(std::string(name)
                + ": repeated source DSP output/preparation was not deterministic");
        times.push_back(next.elapsedMs);
    }
    std::sort(times.begin(), times.end());
    const std::size_t middle = times.size() / 2u;
    const double medianMs = times.size() % 2u
        ? times[middle]
        : (times[middle - 1u] + times[middle]) * 0.5;
    const std::size_t p90Index = (times.size() * 9u + 9u) / 10u - 1u;
    aggregate.elapsedMs = medianMs;
    aggregate.nsPerVoiceSample = medianMs * 1.0e6
        / (static_cast<double>(frames) * voices);
    aggregate.realtimeFactor = (medianMs / 1000.0)
        / (frames / static_cast<double>(sampleRate));
    aggregate.repetitions = repetitions;
    aggregate.minElapsedMs = times.front();
    aggregate.p90ElapsedMs = times[p90Index];
    aggregate.maxElapsedMs = times.back();
    return aggregate;
}

void printCsv(const std::vector<Measurement>& rows) {
    std::cout << "engine,voices,sample_rate_hz,frames,warmup_frames,timed_voice_samples,elapsed_ms,ns_per_voice_sample,"
                 "realtime_factor,mean_output_energy,cpp_new_calls,prepared_bytes_hint,"
                 "prepared_cpp_new_bytes,repetitions,min_elapsed_ms,p90_elapsed_ms,max_elapsed_ms\n";
    std::cout << std::setprecision(9);
    for (std::size_t n = 0; n < rows.size(); ++n) {
        const Measurement& r = rows[n];
        std::cout << r.engine << ',' << r.voices << ',' << r.sampleRate << ','
                  << r.frames << ',' << r.warmupFrames << ',' << r.timedVoiceSamples
                  << ',' << r.elapsedMs << ',' << r.nsPerVoiceSample
                  << ',' << r.realtimeFactor << ',' << r.meanEnergy << ','
                  << r.newCalls << ',' << r.preparedBytesHint << ','
                  << r.preparedCppNewBytes << ',' << r.repetitions << ','
                  << r.minElapsedMs << ',' << r.p90ElapsedMs << ','
                  << r.maxElapsedMs << '\n';
    }
}

void printJson(const std::vector<Measurement>& rows) {
    std::cout << "[\n" << std::setprecision(9);
    for (std::size_t n = 0; n < rows.size(); ++n) {
        const Measurement& r = rows[n];
        std::cout << "  {\"engine\":\"" << r.engine << "\",\"voices\":" << r.voices
                  << ",\"sample_rate_hz\":" << r.sampleRate
                  << ",\"frames\":" << r.frames
                  << ",\"warmup_frames\":" << r.warmupFrames
                  << ",\"timed_voice_samples\":" << r.timedVoiceSamples
                  << ",\"elapsed_ms\":" << r.elapsedMs
                  << ",\"ns_per_voice_sample\":" << r.nsPerVoiceSample
                  << ",\"realtime_factor\":" << r.realtimeFactor
                  << ",\"mean_output_energy\":" << r.meanEnergy
                  << ",\"cpp_new_calls\":" << r.newCalls
                  << ",\"prepared_bytes_hint\":" << r.preparedBytesHint
                  << ",\"prepared_cpp_new_bytes\":" << r.preparedCppNewBytes
                  << ",\"repetitions\":" << r.repetitions
                  << ",\"min_elapsed_ms\":" << r.minElapsedMs
                  << ",\"p90_elapsed_ms\":" << r.p90ElapsedMs
                  << ",\"max_elapsed_ms\":" << r.maxElapsedMs << '}';
        if (n + 1u != rows.size())
            std::cout << ',';
        std::cout << '\n';
    }
    std::cout << "]\n";
}

int parseFrames(const char* text) {
    errno = 0;
    char* end = NULL;
    const long value = std::strtol(text, &end, 10);
    if (errno != 0 || text == end || *end != '\0' || value < 256L || value > 1000000L)
        throw std::invalid_argument("--frames must be an integer 256..1000000");
    return static_cast<int>(value);
}

int parseRepetitions(const char* text) {
    errno = 0;
    char* end = NULL;
    const long value = std::strtol(text, &end, 10);
    if (errno != 0 || text == end || *end != '\0' || value < 1L || value > 9L)
        throw std::invalid_argument("--repeats must be an integer 1..9");
    return static_cast<int>(value);
}

void usage(const char* command) {
    std::cout << "Usage: " << command << " [--frames 32768] [--repeats 1] [--json]\n"
              << "Runs MorphVCO, StateFilter, FMVoice, StereoEcho, FoldDrive, "
                 "ClockedLFO, ChanceHold and SlewGlide at 48/96 kHz, "
                 "1/8/16 voices.\n"
              << "Source DSP timing only: no Cardinal, UI, drivers, host, or audio I/O.\n"
              << "Warmup frames are excluded; ns_per_voice_sample is wall-clock time per\n"
              << "source DSP voice-sample, not host CPU usage or DAW performance.\n";
}
} // namespace

int main(int argc, char** argv) {
    try {
        int frames = 32768;
        int repeats = 1;
        bool json = false;
        for (int n = 1; n < argc; ++n) {
            if (std::strcmp(argv[n], "--frames") == 0) {
                if (n + 1 == argc)
                    throw std::invalid_argument("--frames needs a value");
                frames = parseFrames(argv[++n]);
            } else if (std::strcmp(argv[n], "--repeats") == 0) {
                if (n + 1 == argc)
                    throw std::invalid_argument("--repeats needs a value");
                repeats = parseRepetitions(argv[++n]);
            } else if (std::strcmp(argv[n], "--json") == 0) {
                json = true;
            } else if (std::strcmp(argv[n], "--help") == 0) {
                usage(argv[0]);
                return 0;
            } else {
                throw std::invalid_argument(std::string("unknown argument: ") + argv[n]);
            }
        }

        std::vector<Measurement> rows;
        const int rates[] = {48000, 96000};
        const int voices[] = {1, 8, 16};
        for (std::size_t rate = 0; rate < 2u; ++rate) {
            for (std::size_t voice = 0; voice < 3u; ++voice) {
                const int sr = rates[rate];
                const int count = voices[voice];
                rows.push_back(measure<dsp::MorphOscillator, MorphStep>(
                    "MorphVCO", count, sr, frames, repeats));
                rows.push_back(measure<dsp::StateFilter, FilterStep>(
                    "StateFilter", count, sr, frames, repeats));
                rows.push_back(measure<dsp::FMVoice, FMStep>(
                    "FMVoice", count, sr, frames, repeats));
                rows.push_back(measure<dsp::StereoEchoDSP, EchoStep>(
                    "StereoEcho", count, sr, frames, repeats,
                    dsp::StereoEchoDSP::reservedBytesPerVoice()));
                rows.push_back(measure<dsp::FoldDrive, FoldStep>(
                    "FoldDrive", count, sr, frames, repeats));
                rows.push_back(measure<dsp::ClockedLFO, ClockStep>(
                    "ClockedLFO", count, sr, frames, repeats));
                rows.push_back(measure<dsp::ChanceHold, ChanceStep>(
                    "ChanceHold", count, sr, frames, repeats));
                rows.push_back(measure<dsp::SlewGlide, SlewStep>(
                    "SlewGlide", count, sr, frames, repeats));
            }
        }
        if (json)
            printJson(rows);
        else
            printCsv(rows);
    } catch (const std::exception& problem) {
        std::fprintf(stderr, "DSP benchmark: %s\n", problem.what());
        return 1;
    }
    return 0;
}
