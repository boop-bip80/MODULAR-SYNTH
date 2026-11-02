/*
 * MODULAR-SYNTH offline FMVoice audio demonstration.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Deterministic PCM16 audition of the unmodified first-party FMVoice DSP.
 * No Rack SDK, audio host, external samples, or audio callback is involved.
 */
#include "plugins/ModularSynth/src/FMVoice.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>
#include <system_error>

namespace {

using modular_synth::dsp::FMVoice;

constexpr int kSeconds = 4;
constexpr int kChannels = 2;
constexpr int kBitsPerSample = 16;
constexpr int kMaxUnisonVoices = 4;
constexpr double kHeadroom = 0.75;
constexpr double kPi = 3.1415926535897932384626433832795;
constexpr std::uint64_t kFnvOffset = UINT64_C(14695981039346656037);
constexpr std::uint64_t kFnvPrime = UINT64_C(1099511628211);

// Original minor-flavored sixteen-step exercise, semitones above C3.
constexpr std::array<int, 16> kMotif{{
    0, 3, 7, 10, 12, 7, 5, 2,
    0, 5, 8, 12, 10, 7, 3, 0
}};
constexpr std::array<double, 4> kRatios{{1.0, 1.5, 2.0, 3.0}};

struct PcmStats {
    std::uint64_t hash = kFnvOffset;
    double sumSquares = 0.0;
    double peak = 0.0;
    std::uint64_t samples = 0;

    bool write(std::ostream& out, double value) noexcept {
        // This bitwise finite guard is reliable even with -ffast-math.
        if (!FMVoice::finite(value))
            return false;
        const double bounded = std::clamp(value, -kHeadroom, kHeadroom);
        const auto quantized = static_cast<std::int32_t>(
            std::lround(bounded * 32767.0));
        const auto raw = static_cast<std::uint16_t>(quantized);
        const auto low = static_cast<std::uint8_t>(raw & 0xffu);
        const auto high = static_cast<std::uint8_t>((raw >> 8) & 0xffu);
        out.put(static_cast<char>(low));
        out.put(static_cast<char>(high));
        hash = (hash ^ low) * kFnvPrime;
        hash = (hash ^ high) * kFnvPrime;
        peak = std::max(peak, std::abs(bounded));
        sumSquares += bounded * bounded;
        ++samples;
        return static_cast<bool>(out);
    }
};

void writeU16(std::ostream& out, std::uint16_t v) {
    out.put(static_cast<char>(v & 0xffu));
    out.put(static_cast<char>((v >> 8) & 0xffu));
}

void writeU32(std::ostream& out, std::uint32_t v) {
    for (int shift = 0; shift < 32; shift += 8)
        out.put(static_cast<char>((v >> shift) & 0xffu));
}

void writeWavHeader(std::ostream& out, int sampleRate, std::uint32_t frames) {
    const std::uint32_t dataBytes = frames * kChannels * (kBitsPerSample / 8);
    out.write("RIFF", 4);
    writeU32(out, dataBytes + 36u);
    out.write("WAVE", 4);
    out.write("fmt ", 4);
    writeU32(out, 16u);
    writeU16(out, 1u);
    writeU16(out, kChannels);
    writeU32(out, static_cast<std::uint32_t>(sampleRate));
    writeU32(out, static_cast<std::uint32_t>(
        sampleRate * kChannels * (kBitsPerSample / 8)));
    writeU16(out, kChannels * (kBitsPerSample / 8));
    writeU16(out, kBitsPerSample);
    out.write("data", 4);
    writeU32(out, dataBytes);
}

bool render(const std::string& outputPath, int sampleRate,
            bool sineReference, int unisonVoices) {
    const int framesPerNote = sampleRate / 4;
    const auto frames = static_cast<std::uint32_t>(sampleRate * kSeconds);
    std::ofstream out(outputPath, std::ios::binary | std::ios::trunc);
    if (!out) {
        std::cerr << "Cannot create output WAV: " << outputPath << '\n';
        return false;
    }

    writeWavHeader(out, sampleRate, frames);
    // Each detuned layer has independent PM phases and smoothing state.
    // Fixed-size storage keeps this renderer allocation-free per audio frame.
    std::array<FMVoice, kMaxUnisonVoices> leftVoices;
    std::array<FMVoice, kMaxUnisonVoices> rightVoices;
    PcmStats stats;
    for (std::uint32_t frame = 0; frame < frames; ++frame) {
        const auto noteIndex = static_cast<std::size_t>(frame / framesPerNote);
        const double phase = static_cast<double>(frame % framesPerNote)
                             / framesPerNote;
        const double seconds = static_cast<double>(frame) / sampleRate;
        // 15 ms onset and 40 ms release around each 250 ms note; no voice
        // reset is required at a note boundary, preserving phase continuity.
        const double attack = std::min(1.0, phase / 0.06);
        const double release = std::min(1.0, (1.0 - phase) / 0.16);
        const double envelope = attack * release;

        const double frequency = FMVoice::frequencyForPitch(
            -1.0 + kMotif[noteIndex] / 12.0);
        const double ratio = sineReference ? 1.0 : kRatios[noteIndex % 4];
        const double index = sineReference ? 0.0
            : 1.2 + 0.75 * (0.5 + 0.5 * std::sin(2.0 * kPi * 0.43 * seconds))
                  + 0.14 * (noteIndex % 4);
        const double feedback = sineReference ? 0.0
            : 0.12 + 0.08 * (0.5 + 0.5 * std::sin(2.0 * kPi * 0.23 * seconds));

        // With one layer this is the historical stereo FM reference. Two or
        // four layers add independent, symmetrically detuned FM oscillators;
        // the normalized sum prevents level from scaling with voice count.
        // Right stays four cents above left for a stable stereo center.
        double leftSum = 0.0;
        double rightSum = 0.0;
        for (int layer = 0; layer < unisonVoices; ++layer) {
            const double spread = unisonVoices == 1 ? 0.0
                : (2.0 * layer / (unisonVoices - 1) - 1.0);
            const double detuneCents = spread * (unisonVoices == 2 ? 5.0 : 8.0);
            const double ratioSpread = 1.0 + spread * 0.008;
            const FMVoice::Input lInput{
                frequency * std::exp2(detuneCents / 1200.0),
                static_cast<double>(sampleRate),
                sineReference ? 1.0 : ratio * ratioSpread,
                sineReference ? 0.0 : index * (1.0 + spread * 0.06),
                feedback
            };
            const FMVoice::Input rInput{
                frequency * std::exp2((4.0 + detuneCents) / 1200.0),
                static_cast<double>(sampleRate),
                sineReference ? 1.0 : ratio * 1.013 * ratioSpread,
                sineReference ? 0.0 : index * 0.82 * (1.0 - spread * 0.04),
                sineReference ? 0.0 : feedback * 0.70
            };
            const auto l = leftVoices[layer].process(lInput);
            const auto r = rightVoices[layer].process(rInput);
            leftSum += 0.34 * l.carrier
                + (sineReference ? 0.0 : 0.035 * l.modulator);
            rightSum += 0.34 * r.carrier
                - (sineReference ? 0.0 : 0.035 * r.modulator);
        }
        const double layerGain = 1.0 / unisonVoices;
        const double left = envelope * layerGain * leftSum;
        const double right = envelope * layerGain * rightSum;
        if (!stats.write(out, left) || !stats.write(out, right)) {
            std::cerr << "FMVoice WAV failed: non-finite sample or I/O error\n";
            return false;
        }
    }
    out.flush();
    if (!out) {
        std::cerr << "FMVoice WAV failed: flush error\n";
        return false;
    }
    const double rms = std::sqrt(stats.sumSquares / stats.samples);
    std::cout << "WAV " << outputPath
              << " mode=" << (sineReference ? "sine" : "fm")
              << " unison=" << unisonVoices
              << " rate=" << sampleRate << " frames=" << frames
              << " channels=" << kChannels
              << " peak=" << std::fixed << std::setprecision(6) << stats.peak
              << " rms=" << rms
              << " pcm_fnv1a64=" << std::hex << std::setw(16)
              << std::setfill('0') << stats.hash << std::dec << '\n';
    return true;
}

void usage(std::ostream& out) {
    out << "Usage: fm_voice_render --output FILE.wav "
           "[--sample-rate 44100|48000|96000] [--sine-reference] "
           "[--unison 1|2|4]\n";
}

} // namespace

int main(int argc, char** argv) {
    std::string output;
    int sampleRate = 48000;
    bool sineReference = false;
    int unisonVoices = 1;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--help" || arg == "-h") {
            usage(std::cout);
            return 0;
        }
        if (arg == "--sine-reference") {
            sineReference = true;
            continue;
        }
        if ((arg == "--output" || arg == "--sample-rate"
             || arg == "--unison") && i + 1 < argc) {
            const std::string value = argv[++i];
            if (arg == "--output") {
                output = value;
            } else if (arg == "--unison") {
                if (value == "1" || value == "2" || value == "4") {
                    unisonVoices = value == "1" ? 1 : (value == "2" ? 2 : 4);
                } else {
                    std::cerr << "Unsupported unison count: " << value << '\n';
                    usage(std::cerr);
                    return 2;
                }
            } else if (value == "44100" || value == "48000" || value == "96000") {
                sampleRate = value == "44100" ? 44100
                    : (value == "48000" ? 48000 : 96000);
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
    // A preflight only. No atomic O_EXCL guarantee against another writer
    // replacing this path between the status query and ofstream opening.
    std::error_code error;
    const auto status = std::filesystem::symlink_status(output, error);
    if (error && error != std::errc::no_such_file_or_directory) {
        std::cerr << "Cannot inspect output: " << error.message() << '\n';
        return 2;
    }
    if (status.type() != std::filesystem::file_type::not_found) {
        std::cerr << "Output already exists (will not overwrite): "
                  << output << '\n';
        return 2;
    }
    return render(output, sampleRate, sineReference, unisonVoices) ? 0 : 1;
}
