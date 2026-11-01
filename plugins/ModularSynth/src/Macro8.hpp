/*
 * MODULAR-SYNTH Macro8 pure DSP/snapshot core
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Rack-independent. The audio callback never allocates, locks, or waits.
 */
#pragma once

#include <array>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

namespace modular_synth {
namespace dsp {

constexpr int kMacro8Count = 8;
constexpr int kMacro8Slots = 4;

// The project may build with -ffast-math, which allows compilers to remove
// std::isfinite checks. Inspect IEEE-754 exponent bits instead so host NaNs
// and infinities cannot escape from control/CV sanitation.
static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559,
              "Macro8 requires IEEE-754 single-precision floats");
static_assert(sizeof(double) == 8 && std::numeric_limits<double>::is_iec559,
              "Macro8 requires IEEE-754 double-precision floats");

inline bool macro8Finite(float value) noexcept {
    std::uint32_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    return (bits & 0x7f800000u) != 0x7f800000u;
}

inline bool macro8Finite(double value) noexcept {
    std::uint64_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    return (bits & 0x7ff0000000000000ull) != 0x7ff0000000000000ull;
}

inline float macro8Unit(float value) noexcept {
    if (!macro8Finite(value))
        return 0.0f;
    return value < 0.0f ? 0.0f : (value > 1.0f ? 1.0f : value);
}

inline double macro8Unit(double value) noexcept {
    if (!macro8Finite(value))
        return 0.0;
    return value < 0.0 ? 0.0 : (value > 1.0 ? 1.0 : value);
}

// Independent double-precision one-poles. The knob's "morph time" is the
// time to settle to within 0.1%. Float accumulation stalls below this
// threshold at high sample rates; double avoids the rounding dead zone.
struct Macro8Smoother {
    std::array<double, kMacro8Count> current{};
    bool initialized = false;
    float previousSampleTime = -1.0f;
    float previousSettleSeconds = -1.0f;
    double smoothingAmount = 1.0;

    void reset() noexcept {
        current.fill(0.0);
        initialized = false;
        previousSampleTime = -1.0f;
        previousSettleSeconds = -1.0f;
        smoothingAmount = 1.0;
    }

    void process(float sampleTime, float settleSeconds,
                 const float (&targets)[kMacro8Count]) noexcept {
        if (!initialized) {
            for (int i = 0; i < kMacro8Count; ++i)
                current[i] = static_cast<double>(macro8Unit(targets[i]));
            initialized = true;
            return;
        }

        const float dt = macro8Finite(sampleTime) ? sampleTime : 0.0f;
        const float seconds = macro8Finite(settleSeconds) ? settleSeconds : 0.0f;
        // Host sample time and manual morph time are usually constant for
        // many thousands of samples. Avoid evaluating exp() on every tick.
        if (dt != previousSampleTime || seconds != previousSettleSeconds) {
            previousSampleTime = dt;
            previousSettleSeconds = seconds;
            if (seconds <= 0.0f) {
                smoothingAmount = 1.0;
            } else if (dt <= 0.0f) {
                smoothingAmount = 0.0;
            } else {
                const double boundedSeconds = seconds > 30.0f ? 30.0 : seconds;
                const double boundedDt = dt > 1.0f ? 1.0 : dt;
                smoothingAmount = 1.0 - std::exp(-6.907755278982137 * boundedDt / boundedSeconds);
            }
        }

        for (int i = 0; i < kMacro8Count; ++i) {
            const double target = static_cast<double>(macro8Unit(targets[i]));
            current[i] += smoothingAmount * (target - current[i]);
        }
    }

    static float voltage(double normalized, bool bipolar) noexcept {
        const double value = macro8Unit(normalized);
        return static_cast<float>(bipolar ? value * 10.0 - 5.0 : value * 10.0);
    }
};

// Four lock-free snapshots. Slot values and the generation counter are
// atomic because the host may save Rack module state on a non-audio thread.
// The reader makes one bounded attempt; it never spins in the audio callback.
// Sequentially consistent atomic ordering keeps the generation check valid
// on weakly ordered ARM/RISC-V as well as x86. Two concurrent writers to one
// slot are rejected rather than serialized.
struct Macro8SnapshotBank {
    struct Slot {
        std::array<std::atomic<float>, kMacro8Count> values{};
        std::atomic<std::uint32_t> generation{0};
        std::atomic<bool> valid{false};
    };
    std::array<Slot, kMacro8Slots> slots{};

    void clear() noexcept {
        for (Slot& slot : slots)
            slot.valid.store(false, std::memory_order_seq_cst);
    }

    bool store(int index, const float (&values)[kMacro8Count]) noexcept {
        if (index < 0 || index >= kMacro8Slots)
            return false;

        Slot& slot = slots[static_cast<std::size_t>(index)];
        std::uint32_t version = slot.generation.load(std::memory_order_seq_cst);
        if ((version & 1u) != 0u ||
            !slot.generation.compare_exchange_strong(version, version + 1u,
                                                     std::memory_order_seq_cst,
                                                     std::memory_order_seq_cst))
            return false;

        for (int i = 0; i < kMacro8Count; ++i)
            slot.values[static_cast<std::size_t>(i)].store(macro8Unit(values[i]),
                                                           std::memory_order_seq_cst);

        slot.valid.store(true, std::memory_order_seq_cst);
        slot.generation.store(version + 2u, std::memory_order_seq_cst);
        return true;
    }

    bool load(int index, float (&values)[kMacro8Count]) const noexcept {
        if (index < 0 || index >= kMacro8Slots)
            return false;

        const Slot& slot = slots[static_cast<std::size_t>(index)];
        const std::uint32_t before = slot.generation.load(std::memory_order_seq_cst);
        if ((before & 1u) != 0u || !slot.valid.load(std::memory_order_seq_cst))
            return false;

        for (int i = 0; i < kMacro8Count; ++i)
            values[i] = slot.values[static_cast<std::size_t>(i)].load(std::memory_order_seq_cst);

        const std::uint32_t after = slot.generation.load(std::memory_order_seq_cst);
        return before == after && (after & 1u) == 0u;
    }

    // Used only to distinguish an intentionally empty slot from a short-lived
    // odd-generation collision. It does not make a snapshot read stable.
    bool mayExist(int index) const noexcept {
        if (index < 0 || index >= kMacro8Slots)
            return false;
        return slots[static_cast<std::size_t>(index)].valid.load(std::memory_order_seq_cst);
    }

    bool has(int index) const noexcept {
        if (index < 0 || index >= kMacro8Slots)
            return false;
        const Slot& slot = slots[static_cast<std::size_t>(index)];
        const auto version = slot.generation.load(std::memory_order_seq_cst);
        return (version & 1u) == 0u && slot.valid.load(std::memory_order_seq_cst);
    }
};

} // namespace dsp
} // namespace modular_synth
