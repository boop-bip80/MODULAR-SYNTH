/*
 * Headless filter response analyzer/benchmark.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "response.hpp"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>

namespace {

void bench() {
    constexpr std::size_t iterations = 1000000;
    modular_synth::dsp::StateFilter filter;
    const auto begin = std::chrono::steady_clock::now();
    double checksum = 0.0;
    for (std::size_t i = 0; i < iterations; ++i) {
        const double input = 0.2 * std::sin(i * 0.017);
        const auto s = filter.process(input, 48000.0, 1250.0, 0.35, 0.0);
        checksum += s.low;
    }
    const auto end = std::chrono::steady_clock::now();
    const double seconds = std::chrono::duration<double>(end - begin).count();
    std::printf("Filter core: %zu samples in %.6f s (%.2f Msample/s), "
                "checksum %.6f\n",
                iterations, seconds, iterations / seconds / 1.0e6, checksum);
    std::puts("Hardware-dependent throughput is informational only, not a CI gate.");
}

} // namespace

int main(int argc, char** argv) {
    const bool csv = argc == 2 && std::strcmp(argv[1], "--csv") == 0;
    const bool check = argc == 2 && std::strcmp(argv[1], "--check") == 0;
    const bool benchmark = argc == 2 && std::strcmp(argv[1], "--bench") == 0;
    const bool help = argc == 2 && (std::strcmp(argv[1], "--help") == 0
                                  || std::strcmp(argv[1], "-h") == 0);
    if (argc > 2 || (argc == 2 && !check && !csv && !benchmark && !help)) {
        std::fputs("Usage: filter-analysis [--check | --csv | --bench | --help]\n", stderr);
        return 2;
    }
    if (help) {
        std::puts("StateFilter analysis: default/--check validates 162 transfer "
                  "magnitudes; --csv prints the response matrix; "
                  "--bench times 1M real DSP samples.");
        return 0;
    }
    if (benchmark) {
        bench();
        return 0;
    }

    const auto matrix = modular_synth::analysis::evaluateMatrix();
    if (csv) {
        std::puts("sample_rate_hz,cutoff_hz,resonance_knob,probe_hz,"
                  "output,predicted_gain,measured_gain,error_db,pass");
        for (const auto& row : matrix.rows)
            std::printf("%.0f,%.0f,%.4f,%.2f,%s,%.8f,%.8f,%.5f,%s\n",
                row.sampleRate, row.cutoffHz, row.resonance, row.probeHz,
                modular_synth::analysis::outputName(row.output),
                row.predictedGain, row.measuredGain, row.errorDb,
                row.passed ? "true" : "false");
    } else {
        for (const auto& row : matrix.rows) {
            if (row.passed)
                continue;
            std::fprintf(stderr,
                "FAIL Fs=%.0f cutoff=%.0f res=%.4f probe=%.1f %s "
                "pred=%.5f got=%.5f err=%.3f dB\n",
                row.sampleRate, row.cutoffHz, row.resonance, row.probeHz,
                modular_synth::analysis::outputName(row.output),
                row.predictedGain, row.measuredGain, row.errorDb);
        }
        std::printf("%zu response rows, %zu failed; maximum |dB error| %.5f\n",
                    matrix.rows.size(), matrix.failed, matrix.worstDb);
    }
    return matrix.failed == 0 ? 0 : 1;
}
