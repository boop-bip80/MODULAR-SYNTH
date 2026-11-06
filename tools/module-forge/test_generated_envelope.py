"""Generated ADSR wrapper behavior under the test Rack shim, not a DAW."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from integrate import integration_plan
from module_forge import check_module, generate, render_files, validate_waveform


ROOT = Path(__file__).resolve().parents[2]
COLLECTION = ROOT / "plugins" / "ModularSynth" / "src"
STUB = ROOT / "tests" / "rack_stub"

PROBE = r'''
#ifndef HEADLESS
#error "Source wrapper ADSR probe requires HEADLESS"
#endif
#include "ForgeADSR.cpp"
#include <cmath>
#include <cstdint>
#include <cstring>

static bool bitsFinite(float value) {
    std::uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return (bits & 0x7f800000u) != 0x7f800000u;
}
static float fromBits(std::uint32_t bits) {
    float v = 0.f;
    std::memcpy(&v, &bits, sizeof(v));
    return v;
}
static bool near(float actual, float expected, float eps = 0.035f) {
    return bitsFinite(actual) && std::fabs(actual - expected) <= eps;
}
int main() {
    if (!modelMSForgeADSR) return 1;
    static_assert(MSForgeADSRModule::NUM_PARAMS == 4, "ADSR params");
    static_assert(MSForgeADSRModule::NUM_INPUTS == 1, "Gate input");
    static_assert(MSForgeADSRModule::NUM_OUTPUTS == 1, "CV output");
    MSForgeADSRModule e;
    MSForgeADSRWidget widget(&e);
    if (widget.module != &e) return 2;
    rack::ProcessArgs args{};
    args.sampleRate = 48000.0;
    args.sampleTime = 1.0 / 48000.0;
    e.params[e.ATTACK_PARAM].setValue(0.001f);
    e.params[e.DECAY_PARAM].setValue(0.001f);
    e.params[e.SUSTAIN_PARAM].setValue(0.5f);
    e.params[e.RELEASE_PARAM].setValue(0.001f);
    e.inputs[e.GATE_INPUT].setChannels(2);
    e.inputs[e.GATE_INPUT].setVoltage(5.f, 0);
    e.inputs[e.GATE_INPUT].setVoltage(0.f, 1);
    for (int frame = 0; frame < 48; ++frame) e.process(args);
    if (e.outputs[e.ENV_OUTPUT].getChannels() != 2
        || !near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 10.f)
        || !near(e.outputs[e.ENV_OUTPUT].getVoltage(1), 0.f)) return 3;
    for (int frame = 0; frame < 52; ++frame) e.process(args);
    if (!near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 5.f)) return 4;
    // Hysteresis: intermediate voltages should not trigger a release.
    e.inputs[e.GATE_INPUT].setVoltage(0.55f, 0);
    e.process(args);
    if (!near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 5.f)) return 5;
    e.inputs[e.GATE_INPUT].setVoltage(0.f, 0);
    for (int frame = 0; frame < 24; ++frame) e.process(args);
    if (!near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 2.5f)) return 6;
    // Retrigger during release continues from the present value, then rises.
    const float interrupted = e.outputs[e.ENV_OUTPUT].getVoltage(0);
    e.inputs[e.GATE_INPUT].setVoltage(5.f, 0);
    e.process(args);
    if (!(e.outputs[e.ENV_OUTPUT].getVoltage(0) > interrupted)) return 7;

    // A host/UI reset event must not mutate audio-owned lanes directly.
    const double beforeReset = e.lanes[0].level;
    e.onReset(rack::ResetEvent{});
    if (!e.pendingReset.load() || e.lanes[0].level != beforeReset) return 8;
    e.process(args);
    if (e.pendingReset.load() || !near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 10.f/48.f))
        return 9;

    // 16-channel max and retirement on polyphony contraction/expansion.
    e.inputs[e.GATE_INPUT].setChannels(20);
    for (int i = 0; i < 16; ++i) e.inputs[e.GATE_INPUT].setVoltage(5.f, i);
    for (int i = 0; i < 48; ++i) e.process(args);
    if (e.outputs[e.ENV_OUTPUT].getChannels() != 16 || e.lanes[15].level == 0.f)
        return 10;
    e.inputs[e.GATE_INPUT].setChannels(1);
    e.process(args);
    if (e.lanes[15].level != 0.f || e.lanes[15].gate) return 11;
    e.inputs[e.GATE_INPUT].setChannels(16);
    e.inputs[e.GATE_INPUT].setVoltage(0.f, 15);
    e.process(args);
    if (!near(e.outputs[e.ENV_OUTPUT].getVoltage(15), 0.f)) return 12;

    // Host rate and CV/knob nonfinite values stay finite under -ffast-math.
    for (float bad : {fromBits(0x7fc00000u), fromBits(0x7f800000u),
                      fromBits(0xff800000u)}) {
        e.onReset();
        e.inputs[e.GATE_INPUT].setChannels(1);
        e.inputs[e.GATE_INPUT].setVoltage(bad);
        e.params[e.SUSTAIN_PARAM].setValue(bad);
        e.params[e.ATTACK_PARAM].setValue(bad);
        args.sampleRate = bad;
        for (int i = 0; i < 24; ++i) {
            e.process(args);
            if (!bitsFinite(e.outputs[e.ENV_OUTPUT].getVoltage(0))) return 13;
        }
    }
    // A finite but physically implausible host rate is also bounded.
    args.sampleRate = 1.0e30;
    e.onReset();
    e.params[e.ATTACK_PARAM].setValue(0.001f);
    e.inputs[e.GATE_INPUT].setVoltage(5.f);
    e.process(args);
    if (!near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 10.f / 48.f)) return 14;

    // A release must preserve its elapsed *seconds* when the host rate changes
    // between buffers; reusing a fixed per-sample decrement makes it finish
    // twice as fast at the doubled rate.
    args.sampleRate = 48000.0;
    e.onReset();
    e.params[e.ATTACK_PARAM].setValue(0.001f);
    e.params[e.DECAY_PARAM].setValue(0.001f);
    e.params[e.SUSTAIN_PARAM].setValue(1.f);
    e.params[e.RELEASE_PARAM].setValue(0.1f);
    e.inputs[e.GATE_INPUT].setVoltage(5.f);
    for (int i = 0; i < 120; ++i) e.process(args);
    if (!near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 10.f)) return 15;
    e.inputs[e.GATE_INPUT].setVoltage(0.f);
    for (int i = 0; i < 2400; ++i) e.process(args);
    if (!near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 5.f, 0.08f)) return 16;
    // The release control is captured at gate fall; modulation afterwards
    // must not warp an already active release.
    e.params[e.RELEASE_PARAM].setValue(0.001f);
    args.sampleRate = 96000.0;
    for (int i = 0; i < 2400; ++i) e.process(args);
    if (!near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 2.5f, 0.08f)) return 17;
    for (int i = 0; i < 2400; ++i) e.process(args);
    if (!near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 0.f, 0.08f)) return 18;

    // The longest permitted A stage at the highest supported sample rate
    // must not accumulate millions of float-ULP rounding errors.
    args.sampleRate = 384000.0;
    e.onReset();
    e.params[e.ATTACK_PARAM].setValue(20.f);
    e.params[e.SUSTAIN_PARAM].setValue(1.f);
    e.inputs[e.GATE_INPUT].setVoltage(5.f);
    for (int i = 0; i < 3840000; ++i) e.process(args);
    if (!near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 5.f, 0.20f)) return 19;
    for (int i = 0; i < 3840000; ++i) e.process(args);
    if (!near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 10.f, 0.15f)) return 20;

    // Zero sustain and minimum-time stages must reach a genuine sustained
    // zero, not generate denormals or stick in a decay loop at 384 kHz.
    e.onReset();
    e.params[e.ATTACK_PARAM].setValue(0.001f);
    e.params[e.DECAY_PARAM].setValue(0.001f);
    e.params[e.SUSTAIN_PARAM].setValue(0.f);
    e.params[e.RELEASE_PARAM].setValue(0.001f);
    e.inputs[e.GATE_INPUT].setVoltage(5.f);
    for (int i = 0; i < 800; ++i) e.process(args);
    if (!near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 0.f)
        || e.lanes[0].stage != MSForgeADSRModule::Sustain) return 21;
    for (int i = 0; i < 1000; ++i) {
        e.inputs[e.GATE_INPUT].setVoltage(i % 2 ? 0.11f : 0.99f);
        e.process(args);
        if (!e.lanes[0].gate || e.lanes[0].stage != MSForgeADSRModule::Sustain)
            return 22;
    }
    e.inputs[e.GATE_INPUT].setVoltage(0.1f);
    e.process(args);
    if (e.lanes[0].gate || e.lanes[0].stage != MSForgeADSRModule::Idle)
        return 23;
    e.inputs[e.GATE_INPUT].setVoltage(0.99f);
    e.process(args);
    if (e.lanes[0].gate || !near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 0.f))
        return 24;
    e.inputs[e.GATE_INPUT].setVoltage(1.f);
    e.process(args);
    if (!e.lanes[0].gate || e.lanes[0].stage != MSForgeADSRModule::Attack
        || !(e.outputs[e.ENV_OUTPUT].getVoltage(0) > 0.f)) return 25;

    // Release after a partially complete new attack must start from the
    // current value and end in approximately one 1 ms interval.
    const double retriggerLevel = e.lanes[0].level;
    e.inputs[e.GATE_INPUT].setVoltage(0.f);
    e.process(args);
    if (!(e.lanes[0].level < retriggerLevel)) return 26;
    for (int i = 0; i < 384; ++i) e.process(args);
    if (!near(e.outputs[e.ENV_OUTPUT].getVoltage(0), 0.f)
        || e.lanes[0].stage != MSForgeADSRModule::Idle) return 27;
    return 0;
}
'''


class GeneratedEnvelopeTests(unittest.TestCase):
    def test_envelope_source_and_manifest_are_stable(self) -> None:
        files = render_files("ForgeADSR", "Forge ADSR", kind="envelope")
        self.assertEqual(set(files), {"ForgeADSR.cpp", "ForgeADSR.svg",
                                     "ForgeADSR.module.json", "INTEGRATION.md"})
        source = files["ForgeADSR.cpp"]
        self.assertIn("GATE_INPUT, NUM_INPUTS", source)
        self.assertIn("ATTACK_PARAM, DECAY_PARAM, SUSTAIN_PARAM, RELEASE_PARAM", source)
        self.assertIn("pendingReset.exchange(false", source)
        self.assertIn("getNormalPolyVoltage(0.f, voice)", source)
        self.assertEqual(json.loads(files["ForgeADSR.module.json"])["tags"],
                         ["Envelope Generator", "Polyphonic"])
        self.assertNotEqual(source, render_files("ForgeADSR", "Forge ADSR")["ForgeADSR.cpp"])
        with self.assertRaisesRegex(ValueError, "non-sine"):
            validate_waveform("envelope", "saw")

    def test_envelope_integrator_plans_exact_static_registration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = generate("ForgeADSR", "Forge ADSR", Path(tmp), kind="envelope")
            self.assertEqual(check_module(folder), [])
            planned = integration_plan(folder, ROOT)
            self.assertEqual(len(planned), 6)
            changes = {e.path.relative_to(ROOT).as_posix(): e for e in planned}
            self.assertIn("plugins/ModularSynth/src/ForgeADSR.cpp", changes)
            self.assertIn("plugins/ModularSynth/res/ForgeADSR.svg", changes)
            self.assertIn('p->addModel(modelMSForgeADSR);',
                          changes["plugins/plugins.cpp"].after.decode())

    @unittest.skipUnless(shutil.which("c++"), "C++ compiler unavailable")
    def test_compiled_envelope_wrappers_process_true_adsr_and_reset(self) -> None:
        with tempfile.TemporaryDirectory(prefix="forge-adsr-") as tmp:
            folder = generate("ForgeADSR", "Forge ADSR", Path(tmp), kind="envelope")
            probe = Path(tmp) / "adsr_probe.cpp"
            probe.write_text(PROBE, encoding="utf-8")
            base = [shutil.which("c++"), "-O2", "-Wall", "-Wextra", "-Wpedantic",
                    "-Werror", "-DHEADLESS",
                    "-DpluginInstance=pluginInstance__ModularSynth",
                    "-I", str(STUB), "-I", str(COLLECTION), "-I", str(folder)]
            for label, flags in (
                ("cxx11", ["-std=gnu++11"]),
                ("cxx11_fast", ["-std=gnu++11", "-ffast-math"]),
                ("cxx17", ["-std=gnu++17"]),
                ("cxx17_fast", ["-std=gnu++17", "-ffast-math"]),
            ):
                with self.subTest(profile=label):
                    command = [*base, *flags, str(probe), "-o", str(Path(tmp) / label)]
                    result = subprocess.run(command, text=True, capture_output=True,
                                            check=False, timeout=90)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([str(Path(tmp) / label)], text=True,
                                            capture_output=True, check=False, timeout=30)
                    self.assertEqual(result.returncode, 0,
                                     f"{label}: exit {result.returncode}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
