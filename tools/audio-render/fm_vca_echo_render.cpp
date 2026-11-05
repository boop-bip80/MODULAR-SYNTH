/*
 * MODULAR-SYNTH original offline FM / DualVCA / StereoEcho demonstration.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Directly exercises three first-party DSP cores without Rack, a DAW, MIDI,
 * a real-time audio callback or any third-party audio dependencies.
 */
#include "plugins/ModularSynth/src/DualVCA.hpp"
#include "plugins/ModularSynth/src/FMVoice.hpp"
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

using modular_synth::dsp::DualVCA;
using modular_synth::dsp::FMVoice;
using modular_synth::dsp::StereoEchoDSP;

constexpr int kMusicSeconds = 4;
constexpr int kChannels = 2;
constexpr int kBitsPerSample = 16;
constexpr double kPi = 3.1415926535897932384626433832795;
constexpr double kHeadroom = 0.75;
constexpr double kFinalGain = 0.70;
constexpr double kEchoDelayMs = 187.5;
constexpr double kEchoFeedback = 0.34;
constexpr double kEchoWet = 0.35;
constexpr double kEchoCrossfeed = 0.72;
constexpr std::uint64_t kFnvOffset = UINT64_C(14695981039346656037);
constexpr std::uint64_t kFnvPrime = UINT64_C(1099511628211);

// An original C-minor bell phrase, with a higher answering motif in bar 4.
constexpr std::array<int, 16> kMotif{{
    0, 3, 7, 12, 10, 7, 5, 3,
    0, 7, 10, 15, 14, 10, 7, 0
}};
constexpr std::array<double, 4> kRatios{{1.5, 2.0, 2.5, 3.0}};

struct PcmStats {
    std::uint64_t hash = kFnvOffset;
    double squares = 0.0;
    double peak = 0.0;
    std::uint64_t sampleCount = 0;

    bool write(std::ostream& out, double normalized) noexcept {
        if (!FMVoice::finite(normalized))
            return false;
        const double bounded = std::min(kHeadroom, std::max(-kHeadroom, normalized));
        const auto signedValue = static_cast<std::int32_t>(std::lround(bounded * 32767.0));
        const auto bits = static_cast<std::uint16_t>(signedValue);
        const auto lo = static_cast<std::uint8_t>(bits & 0xffu);
        const auto hi = static_cast<std::uint8_t>((bits >> 8) & 0xffu);
        out.put(static_cast<char>(lo));
        out.put(static_cast<char>(hi));
        hash = (hash ^ lo) * kFnvPrime;
        hash = (hash ^ hi) * kFnvPrime;
        peak = std::max(peak, std::abs(bounded));
        squares += bounded * bounded;
        ++sampleCount;
        return static_cast<bool>(out);
    }
};

void putU16(std::ostream& out, std::uint16_t value) {
    out.put(static_cast<char>(value & 0xffu));
    out.put(static_cast<char>((value >> 8) & 0xffu));
}

void putU32(std::ostream& out, std::uint32_t value) {
    for (int shift = 0; shift < 32; shift += 8)
        out.put(static_cast<char>((value >> shift) & 0xffu));
}

void writeWavHeader(std::ostream& out, int sampleRate, std::uint32_t frames) {
    const auto dataBytes = frames * kChannels * (kBitsPerSample / 8);
    out.write("RIFF", 4);
    putU32(out, dataBytes + 36u);
    out.write("WAVEfmt ", 8);
    putU32(out, 16u);
    putU16(out, 1u);
    putU16(out, kChannels);
    putU32(out, static_cast<std::uint32_t>(sampleRate));
    putU32(out, static_cast<std::uint32_t>(sampleRate * kChannels * (kBitsPerSample / 8)));
    putU16(out, kChannels * (kBitsPerSample / 8));
    putU16(out, kBitsPerSample);
    out.write("data", 4);
    putU32(out, dataBytes);
}

bool render(const std::string& path, int sampleRate, int tailSeconds,
            bool dryReference) {
    const auto musicFrames = static_cast<std::uint32_t>(sampleRate * kMusicSeconds);
    const auto frames = static_cast<std::uint32_t>(
        sampleRate * (kMusicSeconds + tailSeconds));

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) {
        std::cerr << "Cannot create WAV: " << path << '\n';
        return false;
    }
    writeWavHeader(out, sampleRate, frames);

    FMVoice fmLeft;
    FMVoice fmRight;
    DualVCA vcaLeft;
    DualVCA vcaRight;
    // Ring allocation occurs once, before the sample loop. The DSP process
    // calls below do not allocate or perform disk I/O; writing the WAV itself
    // is deliberately an offline, non-real-time operation.
    std::optional<StereoEchoDSP> echo;
    if (!dryReference)
        echo.emplace();
    PcmStats stats;

    const int framesPerNote = sampleRate / 4;
    for (std::uint32_t frame = 0; frame < frames; ++frame) {
        double leftVoltage = 0.0;
        double rightVoltage = 0.0;
        if (frame < musicFrames) {
            const auto noteIndex = static_cast<std::size_t>(frame / framesPerNote);
            const double notePhase = static_cast<double>(frame % framesPerNote)
                / framesPerNote;
            const double seconds = static_cast<double>(frame) / sampleRate;
            // Attack/decay/release are continuously fed into the *actual*
            // DualVCA CV port. The VCA's own 2-ms smoothing is retained.
            const double attack = std::min(1.0, notePhase / 0.048);
            const double decay = std::exp(-2.2 * notePhase);
            const double release = std::min(1.0, (1.0 - notePhase) / 0.12);
            const double accent = 0.72 + ((noteIndex % 4 == 0) ? 0.22 : 0.0)
                + ((noteIndex % 4 == 2) ? 0.08 : 0.0);
            const double envelope = attack * decay * release * accent;

            const double frequency = FMVoice::frequencyForPitch(
                -1.0 + kMotif[noteIndex] / 12.0);
            const double ratio = kRatios[noteIndex % kRatios.size()];
            const double index = 2.05 + 0.36 * (noteIndex % 4)
                + 0.17 * std::sin(2.0 * kPi * 0.41 * seconds);
            const double feedback = 0.11 + 0.035
                * std::sin(2.0 * kPi * 0.29 * seconds);
            const auto left = fmLeft.process({
                frequency * std::exp2(-2.0 / 1200.0),
                static_cast<double>(sampleRate), ratio, index, feedback
            });
            const auto right = fmRight.process({
                frequency * std::exp2(2.5 / 1200.0),
                static_cast<double>(sampleRate), ratio * 1.008,
                index * 0.94, feedback * 0.68
            });

            leftVoltage = vcaLeft.process({
                5.0 * (0.78 * left.carrier + 0.06 * left.modulator),
                static_cast<double>(sampleRate), 0.69,
                envelope * 10.0, 0.42, true
            });
            rightVoltage = vcaRight.process({
                5.0 * (0.77 * right.carrier - 0.05 * right.modulator),
                static_cast<double>(sampleRate), 0.67,
                envelope * 10.0, 0.56, true
            });
        }

        // Tail frames pass actual silence to the existing echo rings; this
        // exercises feedback decay without generating synthetic extra notes.
        if (echo) {
            const auto delayed = echo->process(
                leftVoltage, rightVoltage, sampleRate, kEchoDelayMs,
                kEchoFeedback, kEchoWet, kEchoCrossfeed);
            leftVoltage = delayed.left;
            rightVoltage = delayed.right;
        }
        if (!stats.write(out, kFinalGain * leftVoltage / 5.0)
                || !stats.write(out, kFinalGain * rightVoltage / 5.0)) {
            std::cerr << "FM/VCA/Echo WAV failed: non-finite audio or I/O error\n";
            return false;
        }
    }

    out.flush();
    if (!out) {
        std::cerr << "FM/VCA/Echo WAV failed: flush error\n";
        return false;
    }
    const double rms = std::sqrt(stats.squares / stats.sampleCount);
    std::cout << "WAV " << path << " chain=FMVoice+DualVCA+StereoEcho"
              << " echo=" << (dryReference ? "off" : "on")
              << " rate=" << sampleRate << " frames=" << frames
              << " channels=" << kChannels
              << " tail_seconds=" << tailSeconds
              << " peak=" << std::fixed << std::setprecision(6) << stats.peak
              << " rms=" << rms
              << " pcm_fnv1a64=" << std::hex << std::setw(16)
              << std::setfill('0') << stats.hash << std::dec << '\n';
    return true;
}

void usage(std::ostream& out) {
    out << "Usage: fm_vca_echo_render --output FILE.wav "
           "[--sample-rate 48000|96000] [--tail-seconds 0|1|2] "
           "[--dry-reference]\n";
}

}  // namespace

int main(int argc, char** argv) {
    std::string output;
    int sampleRate = 48000;
    int tailSeconds = 1;
    bool dryReference = false;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--help" || arg == "-h") {
            usage(std::cout);
            return 0;
        }
        if (arg == "--dry-reference") {
            dryReference = true;
            continue;
        }
        if ((arg == "--output" || arg == "--sample-rate"
                || arg == "--tail-seconds") && i + 1 < argc) {
            const std::string value = argv[++i];
            if (arg == "--output") {
                output = value;
            } else if (arg == "--sample-rate") {
                if (value == "48000" || value == "96000")
                    sampleRate = value == "48000" ? 48000 : 96000;
                else {
                    std::cerr << "Unsupported sample rate: " << value << '\n';
                    return 2;
                }
            } else if (value == "0" || value == "1" || value == "2") {
                tailSeconds = value == "0" ? 0 : (value == "1" ? 1 : 2);
            } else {
                std::cerr << "Unsupported tail duration: " << value << '\n';
                return 2;
            }
        } else {
            std::cerr << "Unknown/missing argument: " << arg << '\n';
            usage(std::cerr);
            return 2;
        }
    }
    if (output.empty() || (dryReference && tailSeconds != 0)) {
        std::cerr << "Output is required; dry reference requires --tail-seconds 0\n";
        usage(std::cerr);
        return 2;
    }

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
    return render(output, sampleRate, tailSeconds, dryReference) ? 0 : 1;
}
