#!/usr/bin/env python3
"""Guard legibility and fixed control geometry of first-party performance panels.

SVG source colors are checked, not the host renderer or the actual widget faces.
"""
from __future__ import annotations

from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PANEL_ROOT = ROOT / "plugins" / "ModularSynth" / "res"
SVG = "{http://www.w3.org/2000/svg}"


def luminance(color: str) -> float:
    values = [int(color[pos:pos + 2], 16) / 255.0 for pos in (1, 3, 5)]
    corrected = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
                 for v in values]
    return sum(c * weight for c, weight in zip(corrected, (.2126, .7152, .0722)))


def contrast_ratio(first: str, second: str) -> float:
    hi, lo = sorted((luminance(first), luminance(second)), reverse=True)
    return (hi + .05) / (lo + .05)


class PerformancePanelContrastTests(unittest.TestCase):
    def svg(self, panel: str) -> ET.Element:
        return ET.parse(PANEL_ROOT / (panel + ".svg")).getroot()

    def assert_legible_group(self, panel: str, tag: str, fill: str, outline: str,
                             centers: list[tuple[int, int, int]],
                             stroke_width: str) -> None:
        root = self.svg(panel)
        matching_groups = [g for g in root.iter(SVG + "g")
                           if g.get("stroke") == outline and g.get("fill") == fill]
        self.assertEqual(len(matching_groups), 1, panel)
        group = matching_groups[0]
        self.assertEqual(group.get("stroke-width"), stroke_width)
        circles = list(group.findall(SVG + tag))
        self.assertEqual(
            [(int(circle.get("cx")), int(circle.get("cy")), int(circle.get("r")))
             for circle in circles], centers,
        )
        self.assertGreaterEqual(contrast_ratio(fill, outline), 6.0)

    def test_macro_knob_and_output_boundaries_retain_geometry_and_contrast(self) -> None:
        self.assert_legible_group(
            "Macro8", "circle", "#232A42", "#9AACCC",
            [(x, y, 24) for y in (82, 172) for x in (40, 113, 187, 260)]
            + [(78, 266, 26)], "1.1",
        )
        self.assert_legible_group(
            "Macro8", "circle", "#172738", "#65AEC3",
            [(x, y, 16) for y in (125, 215) for x in (40, 113, 187, 260)],
            "1.3",
        )

    def test_macro_snapshot_and_store_controls_remain_visible(self) -> None:
        self.assert_legible_group(
            "Macro8", "circle", "#27213F", "#BB96F0",
            [(x, 329, 17) for x in (34, 91, 148, 205, 262)], "1.1",
        )
        root = self.svg("Macro8")
        store = [rect for rect in root.findall(SVG + "rect")
                 if rect.get("x") == "177" and rect.get("y") == "246"]
        self.assertEqual(len(store), 1)
        self.assertEqual(
            {name: store[0].get(name) for name in ("width", "height", "rx", "fill", "stroke")},
            {"width": "83", "height": "41", "rx": "9", "fill": "#29233C", "stroke": "#BB96F0"},
        )
        self.assertGreaterEqual(contrast_ratio("#29233C", "#BB96F0"), 6.0)

    def test_fm_voice_control_rings_retain_original_centers(self) -> None:
        root = self.svg("FMVoice")
        circles = root.findall(SVG + "circle")
        actual = [(int(c.get("cx")), int(c.get("cy")), int(c.get("r")),
                   c.get("fill"), c.get("stroke"), c.get("stroke-width"))
                  for c in circles]
        self.assertEqual(actual, [
            (50, 83, 28, "#20243B", "#9AACCC", "1.5"),
            (130, 83, 28, "#20243B", "#9AACCC", "1.5"),
            (50, 164, 28, "#27213F", "#BB96F0", "1.5"),
            (130, 164, 28, "#27213F", "#BB96F0", "1.5"),
            (90, 228, 24, "#20243B", "#9AACCC", "1.5"),
        ])
        for circle in circles:
            with self.subTest(center=(circle.get("cx"), circle.get("cy"))):
                self.assertGreaterEqual(
                    contrast_ratio(circle.get("fill"), circle.get("stroke")), 6.0,
                )

    def test_original_low_contrast_snapshot_outline_would_fail(self) -> None:
        self.assertLess(contrast_ratio("#27213F", "#8169AA"), 6.0)
        self.assertGreaterEqual(contrast_ratio("#27213F", "#BB96F0"), 6.0)


if __name__ == "__main__":
    unittest.main()
