#!/usr/bin/env python3
"""Compare measured source-DSP microbenchmarks without inventing host CPU claims.

No timing thresholds are applied: VM scheduling, thermal state and affinity can
dominate the small differences in a standalone DSP loop. The report contains
an observational speed ratio and a deliberately weak interval heuristic.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


LEGACY_ENGINES = ("MorphVCO", "StateFilter", "FMVoice", "StereoEcho")
PREVIOUS_ENGINES = LEGACY_ENGINES + ("FoldDrive", "ClockedLFO", "ChanceHold")
ENGINES = PREVIOUS_ENGINES + ("SlewGlide",)
VOICES = (1, 8, 16)
RATES = (48000, 96000)
MAX_BYTES = 8 * 1024 * 1024
SCENARIO_SETS = {
    frozenset((engine, voice, rate)
              for engine in engines for voice in VOICES for rate in RATES): label
    for engines, label in ((LEGACY_ENGINES, "legacy-24"),
                           (PREVIOUS_ENGINES, "extended-42"),
                           (ENGINES, "extended-48"))
}


class CompareError(ValueError):
    """Invalid or non-comparable performance evidence."""


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CompareError(f"duplicate JSON property: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise CompareError(f"invalid JSON nonfinite value: {value}")


def _number(row: dict, key: str, *, positive: bool = True) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CompareError(f"{key}: finite numeric value required")
    try:
        number = float(value)
    except OverflowError as exc:
        raise CompareError(f"{key}: numeric overflow") from exc
    if not math.isfinite(number) or (positive and number <= 0.0):
        raise CompareError(f"{key}: finite {'positive' if positive else 'nonnegative'} value required")
    if not positive and number < 0.0:
        raise CompareError(f"{key}: negative value")
    return number


def _integer(row: dict, key: str, *, allow_zero: bool = False) -> int:
    value = row.get(key)
    if (type(value) is not int or (value < 0 if allow_zero else value <= 0)
            or value > (1 << 64) - 1):
        raise CompareError(f"{key}: nonnegative integer required" if allow_zero else
                           f"{key}: positive integer required")
    return value


def load_rows(path: Path) -> dict[tuple[str, int, int], dict]:
    try:
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise CompareError(f"{path}: missing or oversized benchmark input")
        rows = json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=_unique_pairs,
                          parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompareError(f"{path}: invalid JSON benchmark: {exc}") from exc
    if not isinstance(rows, list) or len(rows) not in (24, 42, 48):
        raise CompareError("expected exactly 24, 42 or 48 benchmark scenarios")
    indexed: dict[tuple[str, int, int], dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise CompareError("benchmark row must be an object")
        engine = row.get("engine")
        voices = _integer(row, "voices")
        rate = _integer(row, "sample_rate_hz")
        frames = _integer(row, "frames")
        if (engine not in ENGINES or voices not in VOICES
                or rate not in RATES or not 256 <= frames <= 1_000_000):
            raise CompareError(f"invalid scenario {engine!r}/{voices}/{rate}")
        key = (engine, voices, rate)
        if key in indexed:
            raise CompareError(f"duplicate scenario: {key}")
        elapsed = _number(row, "elapsed_ms")
        ns_per_sample = _number(row, "ns_per_voice_sample")
        realtime = _number(row, "realtime_factor")
        expected_ns = elapsed * 1e6 / (frames * voices)
        expected_realtime = elapsed * rate / (1000.0 * frames)
        if (not math.isclose(ns_per_sample, expected_ns, rel_tol=2e-6)
                or not math.isclose(realtime, expected_realtime, rel_tol=2e-6)):
            raise CompareError(f"reported timing fields inconsistent in {key}")
        _number(row, "mean_output_energy")
        _integer(row, "prepared_bytes_hint")
        if _integer(row, "cpp_new_calls", allow_zero=True) != 0:
            raise CompareError(f"audio-loop C++ allocation in {key}")

        # Older benchmark JSON is supported as a one-timing observational
        # capture. New schema adds repetitions and setup heap byte evidence.
        repeats = row.get("repetitions", 1)
        if type(repeats) is not int or not 1 <= repeats <= 9:
            raise CompareError(f"invalid repetitions in {key}")
        prepared = row.get("prepared_cpp_new_bytes")
        if prepared is not None:
            _integer(row, "prepared_cpp_new_bytes", allow_zero=True)
        low = _number({"v": row.get("min_elapsed_ms", row["elapsed_ms"])}, "v")
        high = _number({"v": row.get("max_elapsed_ms", row["elapsed_ms"])}, "v")
        p90 = _number({"v": row.get("p90_elapsed_ms", row["elapsed_ms"])}, "v")
        median = float(row["elapsed_ms"])
        if not low <= median <= p90 <= high:
            raise CompareError(f"elapsed time quantiles inconsistent in {key}")
        if repeats == 1 and (low != median or high != median or p90 != median):
            raise CompareError(f"single repeat cannot have dispersion in {key}")
        indexed[key] = dict(row, repetitions=repeats, min_elapsed_ms=low,
                            max_elapsed_ms=high, p90_elapsed_ms=p90)
    if frozenset(indexed) not in SCENARIO_SETS:
        raise CompareError("missing expected benchmark scenarios for a complete 24/42/48 profile")
    return indexed


def compare(baseline: dict, candidate: dict) -> dict:
    if set(baseline) != set(candidate):
        raise CompareError("benchmark scenario sets differ")
    rows = []
    logarithms = []
    for key in sorted(baseline):
        old, new = baseline[key], candidate[key]
        if old["frames"] != new["frames"]:
            raise CompareError(f"frames differ for {key}")
        old_time, new_time = old["ns_per_voice_sample"], new["ns_per_voice_sample"]
        speedup = old_time / new_time
        if not math.isfinite(speedup) or speedup <= 0:
            raise CompareError(f"invalid timing ratio for {key}")
        logarithms.append(math.log(speedup))
        # These labels describe only the observed range of wall-clock trials;
        # they are not statistical confidence or realtime deadline tests.
        if new["max_elapsed_ms"] < old["min_elapsed_ms"]:
            observation = "nonoverlap-faster"
        elif new["min_elapsed_ms"] > old["max_elapsed_ms"]:
            observation = "nonoverlap-slower"
        else:
            observation = "overlapping-ranges"
        energy_ratio = new["mean_output_energy"] / old["mean_output_energy"]
        if not math.isfinite(energy_ratio):
            raise CompareError(f"invalid output energy ratio for {key}")
        rows.append({
            "engine": key[0], "voices": key[1], "sample_rate_hz": key[2],
            "frames": old["frames"],
            "baseline_ns_per_voice_sample": old_time,
            "candidate_ns_per_voice_sample": new_time,
            "speedup_ratio": speedup,
            "candidate_time_delta_pct": 100.0 * (new_time / old_time - 1.0),
            "baseline_repetitions": old["repetitions"],
            "candidate_repetitions": new["repetitions"],
            "observed_range": observation,
            "energy_ratio": energy_ratio,
            "prepared_heap_bytes_delta": (
                new["prepared_cpp_new_bytes"] - old["prepared_cpp_new_bytes"]
                if old.get("prepared_cpp_new_bytes") is not None
                and new.get("prepared_cpp_new_bytes") is not None else None
            ),
        })
    return {
        "scope": "standalone source-DSP only, not DAW/host CPU or deadline evidence",
        "confidence": "observed trial ranges only; no statistical significance or CI timing gate",
        "scenario_profile": SCENARIO_SETS[frozenset(baseline)],
        "equal_weight_geometric_speedup": math.exp(sum(logarithms) / len(logarithms)),
        "scenarios": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--json", action="store_true", help="strict structured report")
    args = parser.parse_args(argv)
    try:
        report = compare(load_rows(args.baseline), load_rows(args.candidate))
    except CompareError as exc:
        print(f"DSP benchmark comparison: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        print("Source DSP only: timing trends are not host CPU, audio deadlines, or DAW quality.")
        print("Equal-weight geometric speedup: "
              f"{report['equal_weight_geometric_speedup']:.3f}x")
        print("engine       voices rate   baseline ns  candidate ns  speedup   range")
        for row in report["scenarios"]:
            print(f"{row['engine']:<12} {row['voices']:>2} {row['sample_rate_hz']:>6} "
                  f"{row['baseline_ns_per_voice_sample']:>12.1f} "
                  f"{row['candidate_ns_per_voice_sample']:>13.1f} "
                  f"{row['speedup_ratio']:>8.3f}x  {row['observed_range']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
