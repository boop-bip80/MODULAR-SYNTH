#!/usr/bin/env python3
"""Behavioral and numeric regressions for the source-backed contrast CLI."""
from __future__ import annotations

from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
CHECKER = REPO / "tools" / "ui-check" / "contrast_audit.py"
MODULES = {"MorphVCO": 12, "StateFilter": 14, "Macro8": 20}


class PanelContrastTests(unittest.TestCase):
    def fixture(self) -> Path:
        tmp = tempfile.TemporaryDirectory(prefix="modular-contrast-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name in MODULES:
            for extension, folder in ((".cpp", "src"), (".svg", "res")):
                src = REPO / "plugins" / "ModularSynth" / folder / (name + extension)
                dst = root / "plugins" / "ModularSynth" / folder / (name + extension)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
        return root

    def run_cli(self, root: Path, *flags: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root), *flags],
            check=False, capture_output=True, text=True
        )

    def replace_once(self, path: Path, before: str, after: str) -> None:
        content = path.read_text(encoding="utf-8")
        self.assertIn(before, content)
        path.write_text(content.replace(before, after, 1), encoding="utf-8")

    def use_flat_panels(self, root: Path, fill: str) -> None:
        for name, hp in MODULES.items():
            w = hp * 15
            physical = hp * 5.08
            path = root / "plugins" / "ModularSynth" / "res" / (name + ".svg")
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{physical:g}mm" height="128.5mm" viewBox="0 0 {w} 380">'
                f'<rect width="{w}" height="380" fill="{fill}"/></svg>',
                encoding="utf-8"
            )

    def test_luminance_and_ratio_reference_values(self) -> None:
        module = runpy.run_path(str(CHECKER))
        contrast = module["contrast_ratio"]
        luminance = module["luminance"]
        self.assertAlmostEqual(luminance((0, 0, 0)), 0, places=10)
        self.assertAlmostEqual(luminance((255, 255, 255)), 1, places=10)
        self.assertAlmostEqual(contrast((0, 0, 0), (255, 255, 255)), 21, places=10)
        self.assertAlmostEqual(contrast((7, 23, 51), (7, 23, 51)), 1, places=10)
        self.assertAlmostEqual(contrast((119, 119, 119), (255, 255, 255)),
                               4.478, delta=0.01)

    def test_real_panels_are_explicitly_unknown_under_gradients(self) -> None:
        result = self.run_cli(REPO)
        self.assertEqual(result.returncode, 0, result.stderr)
        for panel in MODULES:
            self.assertIn(f"[{panel}] label underlay: gradient", result.stdout)
        self.assertIn("UNKNOWN TEXT MORPH VCO #F3F1FF", result.stdout)
        self.assertIn("UNKNOWN TEXT STATE FILTER #F3F1FF", result.stdout)
        self.assertIn("UNKNOWN TEXT MACRO 8 #F6F2FF", result.stdout)
        self.assertIn("gradient-stop swatches", result.stdout)
        self.assertIn("not local contrast", result.stdout)
        self.assertNotIn("WARN SVG OUTLINE", result.stdout)
        self.assertIn("no rendered contrast", result.stdout)
        self.assertNotIn("MEASURED TEXT", result.stdout)

    def test_flat_dark_panels_permit_measured_text(self) -> None:
        root = self.fixture()
        self.use_flat_panels(root, "#101724")
        result = self.run_cli(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MEASURED TEXT MORPH VCO", result.stdout)
        self.assertIn("MEASURED TEXT STATE FILTER", result.stdout)
        self.assertIn("MEASURED TEXT MACRO 8", result.stdout)
        self.assertIn("dynamic label coordinates", result.stdout)
        self.assertNotIn("WARN TEXT", result.stdout)

    def test_flat_low_contrast_label_warns_and_optional_strict_fails(self) -> None:
        root = self.fixture()
        self.use_flat_panels(root, "#F3F1FF")
        result = self.run_cli(root, "--fail-on-low-contrast")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("WARN TEXT MORPH VCO #F3F1FF vs #F3F1FF: 1.00:1",
                      result.stdout)
        self.assertIn("low text", result.stdout)

    def test_current_decorative_outlines_meet_advisory(self) -> None:
        result = self.run_cli(REPO)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SVG OUTLINE #61768F vs fill #20243B: 3.27:1 (x3", result.stdout)
        self.assertIn("SVG OUTLINE #8169AA vs fill #27213F: 3.30:1 (x5", result.stdout)
        self.assertIn("SVG OUTLINE #8267B5 vs fill #29233C: 3.25:1 (x1", result.stdout)
        self.assertIn("0 low outline swatches", result.stdout)
        strict = self.run_cli(REPO, "--fail-on-low-contrast")
        self.assertEqual(strict.returncode, 0, strict.stdout + strict.stderr)

    def test_degraded_snapshot_ring_still_triggers_strict_warning(self) -> None:
        root = self.fixture()
        source = root / "plugins/ModularSynth/res/Macro8.svg"
        self.replace_once(source, 'stroke="#8169AA"', 'stroke="#755D9E"')
        strict = self.run_cli(root, "--fail-on-low-contrast")
        self.assertEqual(strict.returncode, 2, strict.stdout + strict.stderr)
        self.assertIn("WARN SVG OUTLINE #755D9E vs fill #27213F: 2.77:1 (x5",
                      strict.stdout)

    def test_missing_svg_is_a_fatal_audit_error(self) -> None:
        root = self.fixture()
        (root / "plugins/ModularSynth/res/StateFilter.svg").unlink()
        result = self.run_cli(root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("unable to audit", result.stderr)

    def test_malformed_svg_is_a_fatal_audit_error(self) -> None:
        root = self.fixture()
        (root / "plugins/ModularSynth/res/Macro8.svg").write_text(
            "<svg><unclosed>", encoding="utf-8"
        )
        result = self.run_cli(root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("unable to audit", result.stderr)

    def test_missing_gradient_stops_remain_unknown_not_false_pass(self) -> None:
        root = self.fixture()
        svg = root / "plugins/ModularSynth/res/Macro8.svg"
        self.replace_once(svg, 'fill="url(#panel)"', 'fill="url(#no-such-gradient)"')
        result = self.run_cli(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("gradient url(#no-such-gradient)", result.stdout)
        self.assertIn("UNKNOWN TEXT MACRO 8", result.stdout)
        self.assertNotIn("MEASURED TEXT MACRO 8", result.stdout)

    def test_unknown_nvg_color_never_uses_previous_foreground(self) -> None:
        root = self.fixture()
        source = root / "plugins/ModularSynth/src/MorphVCO.cpp"
        self.replace_once(source, "nvgRGB(0xF3, 0xF1, 0xFF)",
                          "nvgRGBA(0xF3, 0xF1, 0xFF, 255)")
        result = self.run_cli(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UNKNOWN TEXT MORPH VCO: NanoVG foreground", result.stdout)

    def test_missing_draw_function_is_fatal(self) -> None:
        root = self.fixture()
        source = root / "plugins/ModularSynth/src/StateFilter.cpp"
        self.replace_once(source, "void draw(const DrawArgs& args) override",
                          "void render(const DrawArgs& args) override")
        result = self.run_cli(root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no ModuleWidget::draw", result.stderr)


if __name__ == "__main__":
    unittest.main()
