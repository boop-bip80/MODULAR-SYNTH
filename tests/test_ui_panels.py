#!/usr/bin/env python3
"""CLI regressions for the original first-party panel geometry preflight."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
CHECKER = REPO / "tools" / "ui-check" / "validate_panels.py"
MODULES = ("MorphVCO", "StateFilter", "FoldDrive", "Macro8", "StereoEcho", "ClockedLFO")


class PanelGeometryTests(unittest.TestCase):
    def fixture(self) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="modular-ui-panels-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for name in MODULES:
            for ext, folder in ((".cpp", "src"), (".svg", "res")):
                source = REPO / "plugins" / "ModularSynth" / folder / (name + ext)
                target = root / "plugins" / "ModularSynth" / folder / (name + ext)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        return root

    def run_checker(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root)],
            capture_output=True, text=True, check=False
        )

    def replace_one(self, path: Path, before: str, after: str) -> None:
        source = path.read_text(encoding="utf-8")
        self.assertIn(before, source, f"fixture changed unexpectedly: {path}")
        path.write_text(source.replace(before, after, 1), encoding="utf-8")

    def test_current_repository_panels_pass(self) -> None:
        result = self.run_checker(REPO)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("PASS: 6 SVG panels", result.stdout)
        self.assertIn("86 conservative candidate widget centers", result.stdout)
        self.assertIn("visual rendering/overlap not verified", result.stdout)

    def test_stereo_echo_bad_16hp_width_rejected(self) -> None:
        root = self.fixture()
        panel = root / "plugins/ModularSynth/res/StereoEcho.svg"
        self.replace_one(panel, 'width="81.28mm"', 'width="101.6mm"')
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("width", result.stderr)
        self.assertIn("16HP", result.stderr)

    def test_stereo_echo_missing_svg_rejected(self) -> None:
        root = self.fixture()
        (root / "plugins/ModularSynth/res/StereoEcho.svg").unlink()
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing panel SVG", result.stderr)

    def test_stereo_echo_outside_center_rejected(self) -> None:
        root = self.fixture()
        source = root / "plugins/ModularSynth/src/StereoEcho.cpp"
        self.replace_one(source, "Vec(207.0f, 273.0f)", "Vec(241.0f, 273.0f)")
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("center (241, 273) outside 240x380 panel", result.stderr)

    def test_stereo_echo_input_output_cardinality_rejected(self) -> None:
        root = self.fixture()
        source = root / "plugins/ModularSynth/src/StereoEcho.cpp"
        self.replace_one(
            source,
            "createInputCentered<PJ301MPort>(Vec(207.0f, 273.0f)",
            "createOutputCentered<PJ301MPort>(Vec(207.0f, 273.0f)"
        )
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected 5 Input centered callsites, found 4", result.stderr)
        self.assertIn("expected 2 Output centered callsites, found 3", result.stderr)

    def test_clocked_lfo_rejects_bad_16hp_width(self) -> None:
        root = self.fixture()
        panel = root / "plugins/ModularSynth/res/ClockedLFO.svg"
        self.replace_one(panel, 'width="240"', 'width="225"')
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("16HP", result.stderr)

    def test_clocked_lfo_center_and_jack_cardinality_are_checked(self) -> None:
        root = self.fixture()
        source = root / "plugins/ModularSynth/src/ClockedLFO.cpp"
        self.replace_one(
            source,
            "createOutputCentered<PJ301MPort>(Vec(214.0f, 344.0f)",
            "createInputCentered<PJ301MPort>(Vec(255.0f, 344.0f)"
        )
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected 5 Output centered callsites, found 4", result.stderr)
        self.assertIn("expected 5 Input centered callsites, found 6", result.stderr)
        self.assertIn("center (255, 344) outside 240x380 panel", result.stderr)

    def test_missing_svg_rejected(self) -> None:
        root = self.fixture()
        (root / "plugins/ModularSynth/res/Macro8.svg").unlink()
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing panel SVG", result.stderr)

    def test_malformed_svg_xml_rejected(self) -> None:
        root = self.fixture()
        (root / "plugins/ModularSynth/res/StateFilter.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><broken>',
            encoding="utf-8"
        )
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid SVG/XML", result.stderr)

    def test_wrong_xml_root_rejected(self) -> None:
        root = self.fixture()
        panel = root / "plugins/ModularSynth/res/MorphVCO.svg"
        self.replace_one(
            panel,
            'xmlns="http://www.w3.org/2000/svg"',
            'xmlns="http://www.example.org/not-svg"'
        )
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("root must be namespaced SVG", result.stderr)

    def test_bad_physical_height_rejected(self) -> None:
        root = self.fixture()
        panel = root / "plugins/ModularSynth/res/Macro8.svg"
        self.replace_one(panel, 'height="128.5mm"', 'height="80mm"')
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("height", result.stderr)

    def test_bad_viewbox_rejected(self) -> None:
        root = self.fixture()
        panel = root / "plugins/ModularSynth/res/StateFilter.svg"
        self.replace_one(panel, 'viewBox="0 0 210 380"', 'viewBox="0 0 999 380"')
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("viewBox", result.stderr)

    def test_wrong_panel_asset_reference_rejected(self) -> None:
        root = self.fixture()
        source = root / "plugins/ModularSynth/src/Macro8.cpp"
        self.replace_one(source, '"res/Macro8.svg"', '"res/OtherPanel.svg"')
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected exactly one setPanel()", result.stderr)

    def test_missing_widget_source_rejected(self) -> None:
        root = self.fixture()
        (root / "plugins/ModularSynth/src/StateFilter.cpp").unlink()
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing widget source", result.stderr)

    def test_literal_control_center_out_of_bounds_rejected(self) -> None:
        root = self.fixture()
        source = root / "plugins/ModularSynth/src/StateFilter.cpp"
        self.replace_one(source, "Vec(59.0f, 99.0f)", "Vec(999.0f, 99.0f)")
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("center (999, 99) outside", result.stderr)

    def test_constant_array_control_center_out_of_bounds_rejected(self) -> None:
        root = self.fixture()
        source = root / "plugins/ModularSynth/src/Macro8.cpp"
        self.replace_one(
            source, "187.0f, 260.0f", "187.0f, 400.0f"
        )
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("center (400,", result.stderr)


if __name__ == "__main__":
    unittest.main()
