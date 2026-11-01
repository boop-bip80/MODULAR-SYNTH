#!/usr/bin/env python3
"""Source-integrity checks for docs/MODULE_QUICK_REFERENCE.md.

These checks compare checked-in Rack metadata and saved .vcv patch graphs with
the musician-facing reference. They do not exercise Cardinal's GUI or audio.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs/MODULE_QUICK_REFERENCE.md"
PLUGIN_DIR = ROOT / "plugins/ModularSynth"
PATCH_DIR = ROOT / "patches/examples"

# The quick reference covers exactly the current four first-party modules.
# A newly registered model requires an explicit catalog update.
MODULE_SLUGS = ("MorphVCO", "StateFilter", "Macro8", "StereoEcho")


def enum_ports(source: str, enum_name: str) -> list[str]:
    match = re.search(r"\benum\s+" + re.escape(enum_name) + r"\s*\{([^}]*)\}", source)
    if not match:
        raise ValueError(f"Missing {enum_name}")
    without_comments = re.sub(r"//[^\n]*|/\*.*?\*/", "", match.group(1), flags=re.S)
    return [
        part.strip().split("=")[0].strip()
        for part in without_comments.split(",")
        if part.strip() and not part.strip().startswith("NUM_")
    ]


def patch_reference_rows(document: str) -> list[tuple[str, str]]:
    """Extract precisely the factory-patch table's link and classification."""
    return re.findall(
        r"^\|\s*\[[^]]+\]\(\.\./(patches/examples/MODULAR_[^)]+\.vcv)\)"
        r"\s*\|\s*(Bundled-only|Originals)\s*\|",
        document,
        flags=re.M,
    )


class ModuleQuickReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = DOC_PATH.read_text(encoding="utf-8")
        cls.manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
        cls.modules = cls.manifest["modules"]
        cls.sources = {
            slug: (PLUGIN_DIR / "src" / f"{slug}.cpp").read_text(encoding="utf-8")
            for slug in MODULE_SLUGS
        }

    def test_manifest_and_compiled_models_appear_in_catalog(self) -> None:
        self.assertEqual("ModularSynth", self.manifest["slug"])
        slugs = tuple(module["slug"] for module in self.modules)
        self.assertEqual(MODULE_SLUGS, slugs, "Update quick reference when registered models change")
        self.assertEqual(len(set(slugs)), len(slugs))
        for module in self.modules:
            slug, name = module["slug"], module["name"]
            self.assertIn(f"**{name}** (", self.document)
            self.assertIn(f"### {name} (", self.document)
            self.assertIn(f"../plugins/ModularSynth/src/{slug}.cpp", self.document)
            self.assertRegex(
                self.sources[slug],
                r'createModel<[\s\S]*?>\(\s*"' + re.escape(slug) + r'"\s*\)',
            )

    def test_jack_counts_derived_from_rack_enum_metadata(self) -> None:
        for module in self.modules:
            slug, name = module["slug"], module["name"]
            source = self.sources[slug]
            inputs = enum_ports(source, "InputIds")
            outputs = enum_ports(source, "OutputIds")
            expected = f"**{len(inputs)} in / {len(outputs)} out**"
            row = next(
                (line for line in self.document.splitlines()
                 if line.startswith("| **" + name + "** (" + chr(96) + slug + chr(96) + ")")),
                None,
            )
            self.assertIsNotNone(row, f"Missing catalog row for {slug}")
            self.assertIn(expected, row, f"Wrong Rack port count for {slug}")

    def test_rack_metadata_tooltip_units_and_defaults(self) -> None:
        # Exact configParam/configInput descriptors are the source of truth.
        expected_sources = {
            "MorphVCO": (
                'configParam(OCTAVE_PARAM, -4.0f, 4.0f, 0.0f,',
                'configParam(FINE_PARAM, -100.0f, 100.0f, 0.0f,',
                '"Pitch CV (1 V/oct)"',
                '"Exponential FM CV (5 V/oct at 100% depth)"',
                '"Wave morph CV (10 V full span; adds to knob)"',
                '"Pulse width CV (10 V full span; adds to knob)"',
            ),
            "StateFilter": (
                'configParam(CUTOFF_PARAM, -5.643856f, 4.321928f, 0.0f,',
                'configParam(RESONANCE_PARAM, 0.0f, 1.0f, 0.0f,',
                '"Cutoff CV (1 V/oct; adds to knob)"',
                '"Resonance CV (10 V full span; adds to knob)"',
                '"Drive CV (10 V full span; adds to knob)"',
            ),
            "Macro8": (
                'configParam(MORPH_TIME_PARAM, 0.0f, 5.0f, 0.25f,',
                '"Snapshot transition time (99.9% settling)"',
                '"Unipolar: 0 to +10 V"',
                '"Bipolar: -5 to +5 V"',
                '"Snapshot button action", {"Recall", "Store"}',
            ),
            "StereoEcho": (
                'configParam(TIME_PARAM, 1.0f, 1000.0f, 250.0f,',
                'configParam(FEEDBACK_PARAM, 0.0f, 0.9f, 0.35f,',
                'configParam(MIX_PARAM, 0.0f, 1.0f, 0.4f,',
                'configParam(CROSSFEED_PARAM, 0.0f, 1.0f, 0.5f,',
                '"Right audio input (uses left when unplugged)"',
                '"Echo time CV (additive 100 ms/V; accepts negative CV)"',
                '"Feedback CV (adds 10 percentage points/V)"',
                '"Wet mix CV (adds 10 percentage points/V)"',
            ),
        }
        for slug, snippets in expected_sources.items():
            normalized = " ".join(self.sources[slug].split())
            for snippet in snippets:
                with self.subTest(slug=slug, snippet=snippet):
                    self.assertIn(snippet, normalized)
        for phrase in (
            "1 V/oct", "5 V/oct", "10 V full span",
            "0.25 s", "0…+10 V", "−5…+5 V", "100 ms per volt",
            "10 percentage points", "IN R", "normalled",
        ):
            self.assertIn(phrase, self.document)

    def test_all_factory_patches_have_unique_catalog_entries(self) -> None:
        rows = patch_reference_rows(self.document)
        actual = {p.relative_to(ROOT).as_posix() for p in PATCH_DIR.glob("MODULAR_*.vcv")}
        linked = [path for path, _ in rows]
        self.assertEqual(len(linked), len(set(linked)), "Duplicate factory-patch references")
        self.assertEqual(actual, set(linked), "Update quick reference when factory patches change")
        self.assertEqual(10, len(actual))
        for path, classification in rows:
            with self.subTest(path=path):
                patch = json.loads((ROOT / path).read_text(encoding="utf-8"))
                self.assertIsInstance(patch["modules"], list)
                self.assertIsInstance(patch["cables"], list)
                originals = [m for m in patch["modules"] if m["plugin"] == "ModularSynth"]
                self.assertEqual("Originals" if originals else "Bundled-only", classification)
                for module in originals:
                    self.assertIn(module["model"], MODULE_SLUGS)

    def test_saved_stereo_echo_showcase_routes_lp_hp_to_separate_channels(self) -> None:
        patch = json.loads(
            (PATCH_DIR / "MODULAR_-_Stereo_Echo_Showcase.vcv").read_text(encoding="utf-8")
        )
        modules = {m["id"]: (m["plugin"], m["model"]) for m in patch["modules"]}
        routes = {
            (modules[c["outputModuleId"]], c["outputId"],
             modules[c["inputModuleId"]], c["inputId"])
            for c in patch["cables"]
        }
        for route in (
            (("ModularSynth", "StateFilter"), 0, ("ModularSynth", "StereoEcho"), 0),
            (("ModularSynth", "StateFilter"), 2, ("ModularSynth", "StereoEcho"), 1),
            (("ModularSynth", "StereoEcho"), 0, ("Cardinal", "HostAudio2"), 0),
            (("ModularSynth", "StereoEcho"), 1, ("Cardinal", "HostAudio2"), 1),
        ):
            self.assertIn(route, routes)
        self.assertIn("**LP\nand HP**", self.document)

    def test_echo_motion_performance_has_four_scenes_and_exact_cv_routes(self) -> None:
        path = PATCH_DIR / "MODULAR_-_Echo_Motion_Performance.vcv"
        patch = json.loads(path.read_text(encoding="utf-8"))
        modules_by_id = {m["id"]: m for m in patch["modules"]}
        modules = {
            m["model"]: m for m in patch["modules"] if m["plugin"] == "ModularSynth"
        }
        routes = {
            ((modules_by_id[c["outputModuleId"]]["plugin"],
              modules_by_id[c["outputModuleId"]]["model"]), c["outputId"],
             (modules_by_id[c["inputModuleId"]]["plugin"],
              modules_by_id[c["inputModuleId"]]["model"]), c["inputId"])
            for c in patch["cables"]
        }
        expected = (
            (("ModularSynth", "Macro8"), 0, ("ModularSynth", "StereoEcho"), 2),
            (("ModularSynth", "Macro8"), 1, ("ModularSynth", "StereoEcho"), 3),
            (("ModularSynth", "Macro8"), 2, ("ModularSynth", "StereoEcho"), 4),
            (("ModularSynth", "Macro8"), 3, ("ModularSynth", "MorphVCO"), 2),
            (("ModularSynth", "StateFilter"), 0, ("ModularSynth", "StereoEcho"), 0),
            (("ModularSynth", "StateFilter"), 2, ("ModularSynth", "StereoEcho"), 1),
            (("ModularSynth", "StereoEcho"), 0, ("Cardinal", "HostAudio2"), 0),
            (("ModularSynth", "StereoEcho"), 1, ("Cardinal", "HostAudio2"), 1),
        )
        for route in expected:
            with self.subTest(route=route):
                self.assertIn(route, routes)
        macro = modules["Macro8"]
        params = {param["id"]: param["value"] for param in macro["params"]}
        self.assertEqual(macro["data"]["macro8Version"], 1)
        self.assertEqual(macro["data"]["selectedSlot"], -1)
        self.assertEqual(macro["data"]["names"][:4], ["Time", "Feedback", "Wet", "Wave"])
        self.assertEqual(len(macro["data"]["snapshots"]), 4)
        self.assertTrue(all(isinstance(scene, list) and len(scene) == 8
                            for scene in macro["data"]["snapshots"]))
        self.assertAlmostEqual(params[8], 1.2)
        self.assertTrue(all(params[15 + index] == 0 for index in range(4)))
        self.assertIn(
            "[Echo Motion Performance](../patches/examples/"
            "MODULAR_-_Echo_Motion_Performance.vcv)", self.document
        )
        self.assertIn("Macro8 A–D", self.document)
        self.assertIn("other nine", self.document)

    def test_documented_factory_menu_matches_actual_source_label(self) -> None:
        menu = (ROOT / "src/override/MenuBar.cpp").read_text(encoding="utf-8")
        self.assertIn('createSubmenuItem("Open demo / example project"', menu)
        self.assertIn('if (!demoPatches.empty())', menu)
        self.assertIn('DISTRHO_OS_SEP_STR "examples"', menu)
        for file in (
            DOC_PATH,
            ROOT / "docs/FACTORY_PATCHES.md",
            ROOT / "docs/GETTING_STARTED.md",
        ):
            with self.subTest(document=file.name):
                text = file.read_text(encoding="utf-8")
                self.assertIn("File → Open demo / example project", text)
                self.assertNotIn("Demo patches", text)

    def test_all_relative_markdown_links_resolve(self) -> None:
        for link in re.findall(r"\]\((?!https?://)([^)#]+)(?:#[^)]*)?\)", self.document):
            with self.subTest(link=link):
                self.assertTrue((DOC_PATH.parent / link).exists(), f"Broken doc link: {link}")

    def test_no_unverified_host_or_audio_claims(self) -> None:
        self.assertIn("not**\nmeasured audio", self.document)
        self.assertIn("Not verified by this reference", self.document)
        self.assertIn("DAW save/reopen", self.document)
        self.assertIn("not** a nested patch-to-plugin exporter", self.document)


if __name__ == "__main__":
    unittest.main()
