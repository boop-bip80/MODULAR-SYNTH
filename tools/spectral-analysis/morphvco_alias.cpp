/*
 * MODULAR-SYNTH MorphVCO spectral alias-energy report CLI.
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "tools/spectral-analysis/alias_metrics.hpp"

#include <array>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <string>

namespace {

struct Pitch {
    const char* label;
    double frequency;
    bool relativeToSampleRate;
};

constexpr std::array<Pitch, 7> kPitches{{
    {"A3", 220.0, false},
    {"A4", 440.0, false},
    {"A5", 880.0, false},
    {"A6", 1760.0, false},
    {"A7", 3520.0, false},
    {"A8", 7040.0, false},
    {"0.42fs", 0.42, true}
}};

void usage(std::ostream& output) {
    output << "Usage: morphvco_alias [--sample-rate 48000|96000|both] "
              "[--waveform saw|pulse|both]\n"
              "Prints CSV: alias-band RMS outside legitimate coherent FFT "
              "harmonic bins (Hann window).\n";
}

} // namespace

int main(int argc, char** argv) {
    std::string rates = "both";
    std::string shapes = "both";
    for (int i = 1; i < argc; ++i) {
        const std::string argument(argv[i]);
        if (argument == "--help" || argument == "-h") {
            usage(std::cout);
            return 0;
        }
        if ((argument == "--sample-rate" || argument == "--waveform") && i + 1 < argc) {
            const std::string choice(argv[++i]);
            if (argument == "--sample-rate") {
                if (choice != "48000" && choice != "96000" && choice != "both") {
                    std::cerr << "Invalid sample rate: " << choice << '\n';
                    return 2;
                }
                rates = choice;
            } else {
                if (choice != "saw" && choice != "pulse" && choice != "both") {
                    std::cerr << "Invalid waveform: " << choice << '\n';
                    return 2;
                }
                shapes = choice;
            }
        } else {
            std::cerr << "Unknown/missing option: " << argument << '\n';
            usage(std::cerr);
            return 2;
        }
    }

    std::cout << "sample_rate,note,nominal_hz,coherent_hz,fft_bin,waveform,"
                 "naive_alias_rms,polyblep_alias_rms,reduction_db,"
                 "naive_alias_percent,polyblep_alias_percent,"
                 "naive_total_rms,polyblep_total_rms\n";
    std::cout << std::fixed << std::setprecision(8);

    for (int rate : {48000, 96000}) {
        if (rates != "both" && rates != std::to_string(rate))
            continue;
        for (const auto& note : kPitches) {
            const double nominalHz = note.relativeToSampleRate
                ? note.frequency * rate : note.frequency;
            for (const auto mode : {modular_synth::spectral::Waveform::Saw,
                                    modular_synth::spectral::Waveform::Pulse}) {
                if (shapes != "both" && shapes != modular_synth::spectral::waveformName(mode))
                    continue;
                const auto x = modular_synth::spectral::compare(rate, nominalHz, mode);
                std::cout << rate << ',' << note.label << ',' << x.nominalHz << ','
                          << x.coherentHz << ',' << x.fundamentalBin << ','
                          << modular_synth::spectral::waveformName(mode) << ','
                          << x.naive.aliasRms() << ',' << x.polyblep.aliasRms()
                          << ',' << x.improvementDb() << ','
                          << x.naive.aliasFraction() * 100.0 << ','
                          << x.polyblep.aliasFraction() * 100.0 << ','
                          << std::sqrt(x.naive.totalPower) << ','
                          << std::sqrt(x.polyblep.totalPower) << '\n';
            }
        }
    }
    return 0;
}
