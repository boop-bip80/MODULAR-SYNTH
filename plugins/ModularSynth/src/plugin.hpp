/*
 * MODULAR-SYNTH first-party module registry
 * Copyright (C) 2026 boop-bip80 contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#pragma once

#include "rack.hpp"

using namespace rack;

extern Plugin* pluginInstance;
extern Model* modelMorphVCO;
extern Model* modelStateFilter;
extern Model* modelFoldDrive;
extern Model* modelMacro8;
extern Model* modelStereoEcho;
extern Model* modelClockedLFO;
extern Model* modelFMVoice;
extern Model* modelChanceHold;
extern Model* modelDualVCA;
extern Model* modelSlewGlide;
// Globally unique: the inherited AmalgamatedHarmonics collection also exports
// modelScaleQuantizer. Keep this C++ symbol distinct while preserving the
// public Rack model slug "ScaleQuantizer" in saved patches.
extern Model* modelModularSynthScaleQuantizer;
