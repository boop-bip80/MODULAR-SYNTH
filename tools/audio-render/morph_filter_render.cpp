/*
 * MODULAR-SYNTH deterministic offline audio render.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Exercises first-party MorphVCO -> StateFilter DSP, optionally StereoEcho.
 * No Rack, host, audio hardware or third-party dependencies.
 */
#include "plugins/ModularSynth/src/MorphVCO.hpp"
#include "plugins/ModularSynth/src/StateFilter.hpp"
#include "plugins/ModularSynth/src/StereoEcho.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <string>
#include <system_error>

namespace {

using modular_synth::dsp::MorphOscillator;
using modular_synth::dsp::StateFilter;
using modular_synth::dsp::StereoEchoDSP;

constexpr int kSeconds = 4;
constexpr int kChannels = 2;
constexpr int kBitsPerSample = 16;
constexpr double kPi = 3.1415926535897932384626433832795;
constexpr double kHeadroom = 0.75;
// Fixed, bounded audition settings; the four-second render truncates the tail.
constexpr double kEchoDelayMs = 187.5;
constexpr double kEchoFeedback = 0.32;
constexpr double kEchoWet = 0.35;
constexpr double kEchoCrossfeed = 0.70;
constexpr std::uint64_t kFnvOffset = UINT64_C(14695981039346656037);
constexpr std::uint64_t kFnvPrime = UINT64_C(1099511628211);

// Original sixteen-step motif; semitone offsets above C3.
constexpr std::array<int, 16> kMotif{{
    0, 7, 12, 3, 10, 5, 14, 7,
    12, 5, 9, 2, 7, 3, 10, 0
}};

struct Statistics {
    std::uint64_t hash = kFnvOffset;
    double squares = 0.0;
    double peak = 0.0;
    std::uint64_t samples = 0;

    void addByte(std::uint8_t value) noexcept {
        hash = (hash ^ static_cast<std::uint64_t>(value)) * kFnvPrime;
    }

    bool writePcm16(std::ostream& out, double normalized) {
        // std::isfinite() is not reliable under strict -ffast-math.
        if (!MorphOscillator::finite(normalized))
            return false;
        const double safe = std::min(kHeadroom, std::max(-kHeadroom, normalized));
        const std::int32_t quantized = static_cast<std::int32_t>(std::lround(safe * 32767.0));
        const std::uint16_t encoded = static_cast<std::uint16_t>(quantized);
        const auto low = static_cast<std::uint8_t>(encoded & 0xffu);
        const auto high = static_cast<std::uint8_t>((encoded >> 8) & 0xffu);
        out.put(static_cast<char>(low));
        out.put(static_cast<char>(high));
        addByte(low);
        addByte(high);
        peak = std::max(peak, std::abs(safe));
        squares += safe * safe;
        ++samples;
        return static_cast<bool>(out);
    }
};

void writeU16(std::ostream& out, std::uint16_t value) {
    out.put(static_cast<char>(value & 0xffu));
    out.put(static_cast<char>((value >> 8) & 0xffu));
}

void writeU32(std::ostream& out, std::uint32_t value) {
    for (int shift = 0; shift < 32; shift += 8)
        out.put(static_cast<char>((value >> shift) & 0xffu));
}

void writeWaveHeader(std::ostream& out, int sampleRate, std::uint32_t frames) {
    const std::uint32_t bytes = frames * kChannels * (kBitsPerSample / 8);
    out.write("RIFF", 4);
    writeU32(out, bytes + 36u);
    out.write("WAVE", 4);
    out.write("fmt ", 4);
    writeU32(out, 16u);
    writeU16(out, 1u);
    writeU16(out, kChannels);
    writeU32(out, static_cast<std::uint32_t>(sampleRate));
    writeU32(out, static_cast<std::uint32_t>(sampleRate * kChannels * (kBitsPerSample / 8)));
    writeU16(out, kChannels * (kBitsPerSample / 8));
    writeU16(out, kBitsPerSample);
    out.write("data", 4);
    writeU32(out, bytes);
}

bool render(const std::string& output, int sampleRate, bool withEcho) {
    const int framesPerNote = sampleRate / 4;
    const auto frames = static_cast<std::uint32_t>(sampleRate * kSeconds);
    std::ofstream stream(output, std::ios::binary | std::ios::trunc);
    if (!stream) {
        std::cerr << "Cannot create WAV: " << output << '\n';
        return false;
    }

    writeWaveHeader(stream, sampleRate, frames);
    MorphOscillator voice;
    MorphOscillator subVoice;
    StateFilter bright;
    StateFilter warm;
    // The delay allocates its fixed rings only when explicitly requested.
    // No allocation or reset happens in the audio-sample loop.
    std::optional<StereoEchoDSP> echo;
    if (withEcho)
        echo.emplace();
    Statistics stats;

    for (std::uint32_t frame = 0; frame < frames; ++frame) {
        const auto step = static_cast<std::size_t>(frame / framesPerNote);
        const double within = static_cast<double>(frame % framesPerNote) / framesPerNote;
        const double seconds = static_cast<double>(frame) / sampleRate;
        const double attack = std::min(1.0, within / 0.035);
        const double release = std::min(1.0, (1.0 - within) / 0.20);
        const double envelope = attack * release;

        const double pitchVolts = -1.0 + kMotif[step] / 12.0;
        const double frequency = MorphOscillator::frequencyForPitch(pitchVolts);
        const double sweep = 0.5 + 0.5 * std::sin(2.0 * kPi * 0.31 * seconds);
        const float morph = static_cast<float>(0.17 + 0.66 * sweep);
        const float width = static_cast<float>(
            0.47 + 0.18 * std::sin(2.0 * kPi * 0.21 * seconds));
        const auto lead = voice.process(frequency, sampleRate, morph, width);
        const auto bass = subVoice.process(frequency * 0.5, sampleRate, 0.36f, 0.5f);

        const double cutoff = 360.0 + 2200.0 * envelope
            + 650.0 * (0.5 + 0.5 * std::sin(2.0 * kPi * 0.73 * seconds));
        const auto a = bright.process((1.8 * lead.morph + 0.32 * lead.sine) * envelope,
                                      sampleRate, cutoff, 0.25 + 0.17 * sweep, 0.13);
        const auto b = warm.process((1.1 * bass.morph + 0.33 * bass.sine) * envelope,
                                    sampleRate, cutoff * 0.57, 0.20, 0.07);

        // Stereo variation; both paths pass through the genuine filter.
        const double left = (0.62 * a.low + 0.21 * b.low + 0.09 * a.band) / 5.0;
        const double right = (0.47 * a.low + 0.31 * b.low - 0.07 * a.band) / 5.0;
        double outputL = left;
        double outputR = right;
        if (echo) {
            // The pure echo core uses Rack-style volts, while WAV amplitude
            // is normalized: convert to/from 5 V full-scale consistently.
            const auto delayed = echo->process(left * 5.0, right * 5.0,
                sampleRate, kEchoDelayMs, kEchoFeedback, kEchoWet, kEchoCrossfeed);
            outputL = delayed.left / 5.0;
            outputR = delayed.right / 5.0;
        }
        if (!stats.writePcm16(stream, outputL) || !stats.writePcm16(stream, outputR)) {
            std::cerr << "Audio render failed: non-finite sample or I/O error\n";
            return false;
        }
    }

    stream.flush();
    if (!stream) {
        std::cerr << "Audio render failed: could not flush WAV\n";
        return false;
    }
    const double rms = std::sqrt(stats.squares / static_cast<double>(stats.samples));
    std::cout << "WAV " << output << " rate=" << sampleRate
              << " frames=" << frames << " channels=" << kChannels
              << " echo=" << (withEcho ? "on" : "off") << " peak=" << std::fixed << std::setprecision(6) << stats.peak
              << " rms=" << rms << " pcm_fnv1a64=" << std::hex
              << std::setw(16) << std::setfill('0') << stats.hash << std::dec << '\n';
    return true;
}

void usage(std::ostream& output) {
    output << "Usage: morph_filter_render --output FILE.wav "
              "[--sample-rate 44100|48000|96000] [--with-stereo-echo]\n";
}

} // namespace

int main(int argc, char** argv) {
    std::string output;
    int sampleRate = 48000;
    bool withEcho = false;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--help" || arg == "-h") {
            usage(std::cout);
            return 0;
        }
        if (arg == "--with-stereo-echo") {
            withEcho = true;
            continue;
        }
        if ((arg == "--output" || arg == "--sample-rate") && i + 1 < argc) {
            const std::string value = argv[++i];
            if (arg == "--output") {
                output = value;
            } else if (value == "44100" || value == "48000" || value == "96000") {
                sampleRate = value == "44100" ? 44100 : (value == "48000" ? 48000 : 96000);
            } else {
                std::cerr << "Unsupported sample rate: " << value << '\n';
                usage(std::cerr);
                return 2;
            }
        } else {
            std::cerr << "Unknown/missing argument: " << arg << '\n';
            usage(std::cerr);
            return 2;
        }
    }
    if (output.empty()) {
        usage(std::cerr);
        return 2;
    }
    // Check *file entries* rather than opening an ifstream: a dangling
    // symlink also counts as an existing output and must not be followed.
    // This preflight is not an atomic O_EXCL guarantee against a concurrent
    // writer replacing the path between this check and the later open.
    std::error_code statusError;
    const auto status = std::filesystem::symlink_status(output, statusError);
    if (statusError && statusError != std::errc::no_such_file_or_directory) {
        std::cerr << "Cannot inspect output: " << statusError.message() << '\n';
        return 2;
    }
    if (status.type() != std::filesystem::file_type::not_found) {
        std::cerr << "Output already exists (will not overwrite): " << output << '\n';
        return 2;
    }
    return render(output, sampleRate, withEcho) ? 0 : 1;
}
