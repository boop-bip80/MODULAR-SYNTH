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
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
CHECKER = REPO / "tools" / "ui-check" / "contrast_audit.py"
MODULES = {"MorphVCO": 12, "StateFilter": 14, "FoldDrive": 12,
           "Macro8": 20, "StereoEcho": 16, "ClockedLFO": 16, "FMVoice": 12,
           "ChanceHold": 16, "DualVCA": 12, "SlewGlide": 12}


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

    def test_rgb_envelope_bound_is_conservative_not_stop_only(self) -> None:
        module = runpy.run_path(str(CHECKER))
        lower_bound = module["gradient_rgb_contrast_lower_bound"]
        contrast = module["contrast_ratio"]
        stops = [(255, 0, 0), (0, 255, 0)]
        bound = lower_bound((255, 255, 255), stops)
        self.assertIsNotNone(bound)
        # Component-wise max is yellow, a stricter bound than either
        # individual red/green stop because the gradient's middle is mixed.
        self.assertAlmostEqual(
            bound, contrast((255, 255, 255), (255, 255, 0)), places=10
        )
        for percent in range(101):
            t = percent / 100.0
            pixel = (round(255 * (1 - t)), round(255 * t), 0)
            self.assertLessEqual(bound, contrast((255, 255, 255), pixel) + 1e-10)
        self.assertEqual(lower_bound((127, 127, 127),
                                     [(0, 0, 0), (255, 255, 255)]), 1.0)
        self.assertAlmostEqual(
            lower_bound((0, 0, 0), [(100, 100, 100), (200, 200, 200)]),
            contrast((0, 0, 0), (100, 100, 100)),
        )
        self.assertIsNone(lower_bound((255, 255, 255), []))

    def test_original_gradients_have_base_only_bounds_but_no_local_pass(self) -> None:
        result = self.run_cli(REPO, "--fail-on-low-contrast")
        self.assertEqual(result.returncode, 0, result.stderr)
        for panel in ("MorphVCO", "StateFilter", "FoldDrive", "Macro8", "StereoEcho", "FMVoice"):
            with self.subTest(panel=panel):
                section = result.stdout.split(f"[{panel}] label underlay:", 1)[1]
                section = section.split("\n[", 1)[0]
                self.assertIn("UNKNOWN TEXT", section)
                self.assertIn("opaque base-gradient lower bound ≥", section)
                self.assertIn("base layer only; local contrast UNKNOWN", section)
        self.assertIn("source-only gradient-base bounds", result.stdout)
        self.assertIn("no rendered contrast", result.stdout)
        self.assertNotIn("MEASURED TEXT", result.stdout)

    def test_translucent_gradient_stop_withholds_base_bound(self) -> None:
        root = self.fixture()
        svg = root / "plugins/ModularSynth/res/Macro8.svg"
        self.replace_once(
            svg, '<stop offset="0" stop-color="#11182A"/>',
            '<stop offset="0" stop-color="#11182A" stop-opacity=".5"/>'
        )
        result = self.run_cli(root, "--fail-on-low-contrast")
        self.assertEqual(result.returncode, 0, result.stderr)
        section = result.stdout.split("[Macro8] label underlay:", 1)[1]
        section = section.split("\n[", 1)[0]
        self.assertIn("UNKNOWN TEXT MACRO 8", section)
        self.assertNotIn("opaque base-gradient lower bound", section)

    def test_unresolved_stop_color_withholds_base_bound(self) -> None:
        root = self.fixture()
        svg = root / "plugins/ModularSynth/res/MorphVCO.svg"
        self.replace_once(svg, 'stop-color="#111726"',
                          'stop-color="currentColor"')
        result = self.run_cli(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        section = result.stdout.split("[MorphVCO] label underlay:", 1)[1]
        section = section.split("\n[", 1)[0]
        self.assertIn("UNKNOWN TEXT MORPH VCO", section)
        self.assertNotIn("opaque base-gradient lower bound", section)

    def test_weak_base_bound_is_inconclusive_not_strict_failure(self) -> None:
        root = self.fixture()
        svg = root / "plugins/ModularSynth/res/MorphVCO.svg"
        self.replace_once(svg, 'stop-color="#111726"',
                          'stop-color="#F3F1FF"')
        result = self.run_cli(root, "--fail-on-low-contrast")
        self.assertEqual(result.returncode, 0, result.stderr)
        section = result.stdout.split("[MorphVCO] label underlay:", 1)[1]
        section = section.split("\n[", 1)[0]
        self.assertIn("UNKNOWN TEXT MORPH VCO", section)
        self.assertIn("opaque base-gradient lower bound ≥1.00:1", section)
        self.assertNotIn("MEASURED TEXT MORPH VCO", section)
        self.assertIn("inconclusive under 4.5:1", result.stdout)

    def test_real_panels_are_explicitly_unknown_under_gradients(self) -> None:
        result = self.run_cli(REPO)
        self.assertEqual(result.returncode, 0, result.stderr)
        for panel in ("MorphVCO", "StateFilter", "FoldDrive", "Macro8", "StereoEcho", "FMVoice"):
            self.assertIn(f"[{panel}] label underlay: gradient", result.stdout)
        self.assertIn("[ClockedLFO] label underlay: layered SVG artwork over solid base",
                      result.stdout)
        self.assertIn("UNKNOWN TEXT MORPH VCO #F3F1FF", result.stdout)
        self.assertIn("UNKNOWN TEXT STATE FILTER #F3F1FF", result.stdout)
        self.assertIn("UNKNOWN TEXT FOLD DRIVE #F3F1FF", result.stdout)
        self.assertIn("UNKNOWN TEXT MACRO 8 #F6F2FF", result.stdout)
        self.assertIn("UNKNOWN TEXT STEREO ECHO #ECF4FF", result.stdout)
        self.assertIn("UNKNOWN TEXT CLOCKED LFO #E8FFF8", result.stdout)
        self.assertIn("UNKNOWN TEXT FM VOICE #F4F3FE", result.stdout)
        self.assertIn("UNKNOWN TEXT CHANCE HOLD #E8F6FF", result.stdout)
        self.assertIn("122 nvgText sites", result.stdout)
        self.assertIn("measured SVG outline shapes", result.stdout)
        self.assertIn("UNKNOWN SVG outline shapes", result.stdout)
        self.assertIn("UNKNOWN SVG OUTLINE #63b7cc vs fill url(#dial)", result.stdout)
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
        self.assertIn("MEASURED TEXT FOLD DRIVE", result.stdout)
        self.assertIn("MEASURED TEXT MACRO 8", result.stdout)
        self.assertIn("MEASURED TEXT STEREO ECHO", result.stdout)
        self.assertIn("MEASURED TEXT CLOCKED LFO", result.stdout)
        self.assertIn("MEASURED TEXT FM VOICE", result.stdout)
        self.assertIn("dynamic label coordinates", result.stdout)
        self.assertNotIn("WARN TEXT", result.stdout)

    def test_translucent_flat_base_cannot_be_reported_as_measured(self) -> None:
        root = self.fixture()
        self.use_flat_panels(root, "#101724")
        svg = root / "plugins/ModularSynth/res/MorphVCO.svg"
        self.replace_once(svg, 'fill="#101724"',
                          'fill="#101724" fill-opacity="0.5"')
        result = self.run_cli(root, "--fail-on-low-contrast")
        self.assertEqual(result.returncode, 0, result.stderr)
        section = result.stdout.split("[MorphVCO] label underlay:", 1)[1]
        section = section.split("\n[", 1)[0]
        self.assertIn("UNKNOWN TEXT MORPH VCO", section)
        self.assertNotIn("MEASURED TEXT MORPH VCO", section)
        self.assertIn("styled/nonopaque", section)

    def test_css_styled_flat_base_cannot_be_reported_as_measured(self) -> None:
        root = self.fixture()
        self.use_flat_panels(root, "#101724")
        svg = root / "plugins/ModularSynth/res/StateFilter.svg"
        self.replace_once(svg, '<rect width="210"',
                          '<rect class="panel-theme" width="210"')
        result = self.run_cli(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        section = result.stdout.split("[StateFilter] label underlay:", 1)[1]
        section = section.split("\n[", 1)[0]
        self.assertIn("UNKNOWN TEXT STATE FILTER", section)
        self.assertNotIn("MEASURED TEXT STATE FILTER", section)

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
        self.assertIn("SVG OUTLINE #9AACCC vs fill #20243B: 6.64:1 (x3", result.stdout)
        self.assertIn("SVG OUTLINE #BB96F0 vs fill #261F41: 6.45:1 (x2", result.stdout)
        self.assertIn("SVG OUTLINE #9AACCC vs fill #232A42: 6.17:1 (x9", result.stdout)
        self.assertIn("SVG OUTLINE #65AEC3 vs fill #172738: 6.07:1 (x8", result.stdout)
        self.assertIn("SVG OUTLINE #BB96F0 vs fill #27213F: 6.35:1 (x5", result.stdout)
        self.assertIn("SVG OUTLINE #BB96F0 vs fill #29233C: 6.24:1 (x1", result.stdout)
        self.assertIn("SVG OUTLINE #9AACCC vs fill #20243B: 6.64:1 (x3", result.stdout)
        self.assertIn("0 low outline swatches", result.stdout)
        strict = self.run_cli(REPO, "--fail-on-low-contrast")
        self.assertEqual(strict.returncode, 0, strict.stdout + strict.stderr)

    def test_clocked_modules_have_distinct_readable_input_output_rails(self) -> None:
        color = runpy.run_path(str(CHECKER))
        rgb = color["rgb"]
        ratio = color["contrast_ratio"]
        backgrounds = {"ClockedLFO": ("#1C2D3C",),
                       "ChanceHold": ("#1A2239", "#1A3442")}
        for model, base_stops in backgrounds.items():
            with self.subTest(model=model):
                svg = ET.parse(REPO / "plugins/ModularSynth/res" / f"{model}.svg")
                rails = {}
                for node in svg.getroot().iter():
                    if (node.tag.endswith("}rect") and node.get("x") == "13"
                            and node.get("y") in ("230", "307")):
                        rails[node.get("y")] = node
                self.assertEqual(set(rails), {"230", "307"})
                self.assertEqual(rails["230"].get("fill"), "none")
                self.assertEqual(rails["307"].get("fill"), "none")
                first = rgb(rails["230"].get("stroke"))
                second = rgb(rails["307"].get("stroke"))
                self.assertIsNotNone(first)
                self.assertIsNotNone(second)
                self.assertNotEqual(first, second)
                # These are source-palette comparisons only, not actual
                # rendered contrast of Rack labels or controls.
                for foreground in (first, second):
                    for underlay in base_stops:
                        self.assertGreaterEqual(ratio(foreground, rgb(underlay)), 4.5)

    def test_degraded_snapshot_ring_still_triggers_strict_warning(self) -> None:
        root = self.fixture()
        source = root / "plugins/ModularSynth/res/Macro8.svg"
        self.replace_once(
            source,
            '<g stroke="#BB96F0" stroke-width="1.1" fill="#27213F">',
            '<g stroke="#755D9E" stroke-width="1.1" fill="#27213F">',
        )
        strict = self.run_cli(root, "--fail-on-low-contrast")
        self.assertEqual(strict.returncode, 2, strict.stdout + strict.stderr)
        self.assertIn("WARN SVG OUTLINE #755D9E vs fill #27213F: 2.77:1 (x5",
                      strict.stdout)

    def test_stereo_gradient_dial_stays_unknown_not_a_false_pass(self) -> None:
        result = self.run_cli(REPO, "--fail-on-low-contrast")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("[StereoEcho] label underlay: gradient url(#bg)", result.stdout)
        self.assertIn("UNKNOWN SVG OUTLINE #63b7cc vs fill url(#dial)", result.stdout)
        self.assertIn("UNKNOWN SVG outline shapes", result.stdout)
        self.assertNotIn("WARN SVG OUTLINE", result.stdout)

    def test_stereo_degraded_input_ring_triggers_strict_warning(self) -> None:
        root = self.fixture()
        source = root / "plugins/ModularSynth/res/StereoEcho.svg"
        self.replace_once(source, 'stroke="#57acb5"', 'stroke="#162f42"')
        strict = self.run_cli(root, "--fail-on-low-contrast")
        self.assertEqual(strict.returncode, 2, strict.stdout + strict.stderr)
        self.assertIn("WARN SVG OUTLINE #162F42 vs fill #162F42: 1.00:1",
                      strict.stdout)

    def test_clocked_lfo_degraded_outer_frame_triggers_strict_warning(self) -> None:
        root = self.fixture()
        panel = root / "plugins/ModularSynth/res/ClockedLFO.svg"
        self.replace_once(panel, 'stroke="#60adad"', 'stroke="#1c2d3c"')
        result = self.run_cli(root, "--fail-on-low-contrast")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("WARN SVG OUTLINE #1C2D3C vs fill #1C2D3C: 1.00:1",
                      result.stdout)

    def test_stereo_text_color_is_read_from_actual_source(self) -> None:
        root = self.fixture()
        source = root / "plugins/ModularSynth/src/StereoEcho.cpp"
        self.replace_once(source, "nvgRGB(0xEC, 0xF4, 0xFF)",
                          "nvgRGB(0xFF, 0x00, 0x00)")
        result = self.run_cli(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UNKNOWN TEXT STEREO ECHO #FF0000", result.stdout)

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
