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

namespace modular_synth {
namespace dsp {

constexpr int kMacro8Count = 8;
constexpr int kMacro8Slots = 4;

inline float macro8Unit(float value) noexcept {
    if (!std::isfinite(value))
        return 0.0f;
    return value < 0.0f ? 0.0f : (value > 1.0f ? 1.0f : value);
}

// Independent one-pole smoothers; the knob's "morph time" is the time to
// settle to within approximately 0.1% of the next target.
struct Macro8Smoother {
    std::array<float, kMacro8Count> current{};
    bool initialized = false;

    void reset() noexcept {
        current.fill(0.0f);
        initialized = false;
    }

    void process(float sampleTime, float settleSeconds,
                 const float (&targets)[kMacro8Count]) noexcept {
        if (!initialized) {
            for (int i = 0; i < kMacro8Count; ++i)
                current[i] = macro8Unit(targets[i]);
            initialized = true;
            return;
        }

        float amount = 1.0f;
        if (std::isfinite(settleSeconds) && settleSeconds > 0.0f) {
            if (!std::isfinite(sampleTime) || sampleTime <= 0.0f) {
                amount = 0.0f;
            } else {
                const float seconds = settleSeconds > 30.0f ? 30.0f : settleSeconds;
                const float dt = sampleTime > 1.0f ? 1.0f : sampleTime;
                amount = 1.0f - std::exp(-6.907755278982137f * dt / seconds);
            }
        }
        for (int i = 0; i < kMacro8Count; ++i) {
            const float target = macro8Unit(targets[i]);
            current[i] = macro8Unit(current[i] + amount * (target - current[i]));
        }
    }

    static float voltage(float normalized, bool bipolar) noexcept {
        const float value = macro8Unit(normalized);
        return bipolar ? value * 10.0f - 5.0f : value * 10.0f;
    }
};

// Four lock-free snapshots. Slot values and the generation counter are
// atomic because the host may save Rack module state on a non-audio thread.
// The reader makes one bounded attempt; it never spins in the audio callback.
// Two concurrent writers to one slot are rejected rather than serialized.
struct Macro8SnapshotBank {
    struct Slot {
        std::array<std::atomic<float>, kMacro8Count> values{};
        std::atomic<std::uint32_t> generation{0};
        std::atomic<bool> valid{false};
    };
    std::array<Slot, kMacro8Slots> slots{};

    void clear() noexcept {
        for (Slot& slot : slots)
            slot.valid.store(false, std::memory_order_release);
    }

    bool store(int index, const float (&values)[kMacro8Count]) noexcept {
        if (index < 0 || index >= kMacro8Slots)
            return false;

        Slot& slot = slots[static_cast<std::size_t>(index)];
        std::uint32_t version = slot.generation.load(std::memory_order_relaxed);
        if ((version & 1u) != 0u ||
            !slot.generation.compare_exchange_strong(version, version + 1u,
                                                     std::memory_order_acq_rel,
                                                     std::memory_order_relaxed))
            return false;

        for (int i = 0; i < kMacro8Count; ++i)
            slot.values[static_cast<std::size_t>(i)].store(macro8Unit(values[i]),
                                                           std::memory_order_relaxed);

        slot.valid.store(true, std::memory_order_relaxed);
        slot.generation.store(version + 2u, std::memory_order_release);
        return true;
    }

    bool load(int index, float (&values)[kMacro8Count]) const noexcept {
        if (index < 0 || index >= kMacro8Slots)
            return false;

        const Slot& slot = slots[static_cast<std::size_t>(index)];
        const std::uint32_t before = slot.generation.load(std::memory_order_acquire);
        if ((before & 1u) != 0u || !slot.valid.load(std::memory_order_relaxed))
            return false;

        for (int i = 0; i < kMacro8Count; ++i)
            values[i] = slot.values[static_cast<std::size_t>(i)].load(std::memory_order_relaxed);

        const std::uint32_t after = slot.generation.load(std::memory_order_acquire);
        return before == after && (after & 1u) == 0u;
    }

    bool has(int index) const noexcept {
        if (index < 0 || index >= kMacro8Slots)
            return false;
        const Slot& slot = slots[static_cast<std::size_t>(index)];
        const auto version = slot.generation.load(std::memory_order_acquire);
        return (version & 1u) == 0u && slot.valid.load(std::memory_order_relaxed);
    }
};

} // namespace dsp
} // namespace modular_synth
