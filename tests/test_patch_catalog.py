"""Dynamic factory patch index tests; no DSP or audio-host invocation."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "patches"))
import patch_catalog  # noqa: E402


class PatchCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.examples = Path(self.temp.name) / "examples"
        self.examples.mkdir()
        originals = ROOT / "patches" / "examples"
        for path in originals.glob("MODULAR_-_*.vcv"):
            shutil.copyfile(path, self.examples / path.name)

    def catalog(self) -> dict:
        return patch_catalog.collect(ROOT, self.examples)

    def mutate(self, filename: str, edit) -> None:
        path = self.examples / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        edit(payload)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def test_discovery_matches_current_files_without_hardcoded_count(self) -> None:
        catalog = patch_catalog.collect(ROOT)
        files = sorted((ROOT / "patches" / "examples").glob("MODULAR_-_*.vcv"))
        self.assertTrue(catalog["ok"], catalog["errors"])
        self.assertEqual(catalog["patch_count"], len(files))
        self.assertEqual(len(catalog["patches"]), len(files))
        self.assertEqual(
            [entry["file"].split("/")[-1] for entry in catalog["patches"]],
            sorted((path.name for path in files),
                   key=lambda name: (name.casefold(), name)),
        )
        self.assertTrue(all("module_inventory" in entry
                            and "inspector_has_warnings" in entry
                            for entry in catalog["patches"]))

    def test_routed_control_flags_and_macro_scene_counts(self) -> None:
        catalog = self.catalog()
        entries = {entry["title"]: entry for entry in catalog["patches"]}
        self.assertTrue(entries["Clockwork Pulses"]["host_transport_routed"])
        self.assertFalse(entries["Clockwork Pulses"]["midi_routed"])
        self.assertTrue(entries["Pulse Bass"]["midi_routed"])
        self.assertFalse(entries["Pulse Bass"]["host_transport_routed"])
        self.assertEqual(entries["Pulse Bass"]["macro8_stored_scenes"], 0)
        self.assertEqual(entries["Morphing State Pad"]["macro8_stored_scenes"], 2)
        self.assertEqual(entries["Polyphonic Motion Pad"]["macro8_stored_scenes"], 4)
        self.assertEqual(entries["Polyphonic Motion Pad"]["midi_channels_saved"], 8)
        self.assertIn("MorphVCO",
                      entries["Polyphonic Motion Pad"]["original_modules"])
        self.assertTrue(entries["Polyphonic Motion Pad"]["inspector_has_warnings"])

    def test_json_and_markdown_are_reproducible(self) -> None:
        first, second = self.catalog(), self.catalog()
        self.assertEqual(first, second)
        rendered = patch_catalog.markdown(first)
        self.assertEqual(rendered, patch_catalog.markdown(second))
        self.assertIn("| Patch | Modules | MIDI / host transport routes |", rendered)
        self.assertIn("Polyphonic Motion Pad", rendered)
        self.assertIn("Host transport", rendered)
        self.assertIn("inspector warnings", rendered)
        self.assertNotIn(str(self.examples), rendered)
        for entry in first["patches"]:
            self.assertNotIn("genre", entry)
            self.assertNotIn("audio_verified", entry)
            self.assertNotIn("sounds_like", entry)

    def test_cli_formats(self) -> None:
        script = ROOT / "tools" / "patches" / "patch_catalog.py"
        for format_name in ("markdown", "json"):
            completed = subprocess.run(
                [sys.executable, str(script), "--format", format_name],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0,
                             completed.stdout + completed.stderr)
            if format_name == "json":
                catalog = json.loads(completed.stdout)
                self.assertEqual(catalog["patch_count"],
                                 len(list((ROOT / "patches" / "examples").glob(
                                     "MODULAR_-_*.vcv"))))
                self.assertTrue(catalog["ok"])
            else:
                self.assertIn("# MODULAR-SYNTH original patch index",
                              completed.stdout)

    def test_new_future_named_patch_is_automatically_included(self) -> None:
        future = self.examples / "MODULAR_-_Future_Module_Showcase.vcv"
        shutil.copyfile(self.examples / "MODULAR_-_Pulse_Bass.vcv", future)
        catalog = self.catalog()
        self.assertTrue(catalog["ok"], catalog["errors"])
        self.assertEqual(catalog["patch_count"],
                         len(patch_catalog.collect(ROOT)["patches"]) + 1)
        self.assertTrue(any(entry["title"] == "Future Module Showcase"
                            for entry in catalog["patches"]))

    def test_host_time_module_without_output_cable_is_not_a_clock_route(self) -> None:
        def remove_transport_links(patch: dict) -> None:
            host_time = next(m["id"] for m in patch["modules"]
                             if m["plugin"] == "Cardinal"
                             and m["model"] == "HostTime")
            patch["cables"] = [c for c in patch["cables"]
                               if c["outputModuleId"] != host_time]

        self.mutate("MODULAR_-_Clockwork_Pulses.vcv", remove_transport_links)
        clockwork = next(entry for entry in self.catalog()["patches"]
                         if entry["title"] == "Clockwork Pulses")
        self.assertTrue(clockwork["structurally_valid"], clockwork["errors"])
        self.assertFalse(clockwork["host_transport_routed"])

    def test_invalid_first_party_cable_error_is_inherited(self) -> None:
        def corrupt_patch(patch: dict) -> None:
            macro_id = next(m["id"] for m in patch["modules"]
                            if m["plugin"] == "ModularSynth"
                            and m["model"] == "Macro8")
            cable = next(c for c in patch["cables"]
                         if c["outputModuleId"] == macro_id)
            cable["outputId"] = 999

        self.mutate("MODULAR_-_Polyphonic_Motion_Pad.vcv", corrupt_patch)
        catalog = self.catalog()
        self.assertFalse(catalog["ok"])
        self.assertTrue(any("outputs index 999 exceeds known count 8" in error
                            for error in catalog["errors"]), catalog["errors"])
        pad = next(entry for entry in catalog["patches"]
                   if entry["title"] == "Polyphonic Motion Pad")
        self.assertFalse(pad["structurally_valid"])
        self.assertIsNone(pad["macro8_stored_scenes"])

    def test_unrecognized_macro8_snapshot_type_is_metadata_warning(self) -> None:
        def strange_data(patch: dict) -> None:
            macro = next(m for m in patch["modules"]
                         if m["plugin"] == "ModularSynth"
                         and m["model"] == "Macro8")
            macro["data"]["snapshots"] = {"unexpected": "object"}

        self.mutate("MODULAR_-_Polyphonic_Motion_Pad.vcv", strange_data)
        catalog = self.catalog()
        self.assertTrue(catalog["ok"], catalog["errors"])
        pad = next(entry for entry in catalog["patches"]
                   if entry["title"] == "Polyphonic Motion Pad")
        self.assertTrue(pad["structurally_valid"])
        self.assertIsNone(pad["macro8_stored_scenes"])
        self.assertEqual(len(pad["catalog_warnings"]), 1)

    def test_catalog_counts_slots_without_rechecking_coverage(self) -> None:
        def empty_fourth(patch: dict) -> None:
            macro = next(m for m in patch["modules"]
                         if m["plugin"] == "ModularSynth"
                         and m["model"] == "Macro8")
            macro["data"]["snapshots"][3] = None

        self.mutate("MODULAR_-_Polyphonic_Motion_Pad.vcv", empty_fourth)
        catalog = self.catalog()
        self.assertTrue(catalog["ok"], catalog["errors"])
        pad = next(entry for entry in catalog["patches"]
                   if entry["title"] == "Polyphonic Motion Pad")
        self.assertEqual(pad["macro8_stored_scenes"], 3)

    def test_empty_directory_fails_with_useful_error(self) -> None:
        empty = Path(self.temp.name) / "empty"
        empty.mkdir()
        catalog = patch_catalog.collect(ROOT, empty)
        self.assertFalse(catalog["ok"])
        self.assertEqual(catalog["patch_count"], 0)
        self.assertTrue(any("No MODULAR_-_*.vcv" in error
                            for error in catalog["errors"]))


if __name__ == "__main__":
    unittest.main()
