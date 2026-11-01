/*
 * Headless filter-response regression test, auto-discovered by CI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "../tools/filter-analysis/response.hpp"

#include <cmath>
#include <cstdio>

int main() {
    const auto matrix = modular_synth::analysis::evaluateMatrix();
    for (const auto& row : matrix.rows) {
        if (row.passed)
            continue;
        std::fprintf(stderr,
            "FAIL Fs=%.0f cutoff=%.0f Qcontrol=%.4f probe=%.1f %s "
            "expected=%.6f measured=%.6f error=%.2f dB\n",
            row.sampleRate, row.cutoffHz, row.resonance, row.probeHz,
            modular_synth::analysis::outputName(row.output),
            row.predictedGain, row.measuredGain, row.errorDb);
    }

    if (matrix.rows.size() != 162 || matrix.failed != 0) {
        std::fprintf(stderr, "StateFilter response: %zu of %zu failed; worst dB=%.4f\n",
                     matrix.failed, matrix.rows.size(), matrix.worstDb);
        return 1;
    }

    std::printf("PASS: StateFilter LP/BP/HP digital response %zu cases "
                "(44.1/48/96 kHz, 3 cutoffs, 2 Q settings, 3 probes); "
                "max error %.4f dB\n",
                matrix.rows.size(), matrix.worstDb);
    return 0;
}
