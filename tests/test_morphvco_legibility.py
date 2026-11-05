#!/usr/bin/env python3
"""Regression guards for MorphVCO dial-ring contrast and physical layout."""
from __future__ import annotations

from pathlib import Path
import unittest
from xml.etree import ElementTree

PANEL = Path(__file__).resolve().parents[1] / "plugins/ModularSynth/res/MorphVCO.svg"
NS = {"svg": "http://www.w3.org/2000/svg"}


def luminance(hex_rgb: str) -> float:
    values = [int(hex_rgb[index:index + 2], 16) / 255.0 for index in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
              for v in values]
    return sum(weight * channel for weight, channel in
               zip((0.2126, 0.7152, 0.0722), linear))


def ratio(a: str, b: str) -> float:
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


class MorphVCOLegibility(unittest.TestCase):
    def test_dial_rings_keep_geometry_and_clear_contrast(self) -> None:
        root = ElementTree.parse(PANEL).getroot()
        self.assertEqual(
            (root.attrib["width"], root.attrib["height"], root.attrib["viewBox"]),
            ("60.96mm", "128.5mm", "0 0 180 380"),
        )
        circles = root.findall("svg:circle", NS)
        expected = [
            ("50", "82", "28", "#20243b", "#9aaccc", "1.5"),
            ("130", "82", "28", "#20243b", "#9aaccc", "1.5"),
            ("52", "164", "28", "#261f41", "#bb96f0", "1.5"),
            ("128", "164", "28", "#261f41", "#bb96f0", "1.5"),
            ("90", "229", "24", "#20243b", "#9aaccc", "1.5"),
        ]
        actual = [tuple(circle.attrib[attr] for attr in
                        ("cx", "cy", "r", "fill", "stroke", "stroke-width"))
                  for circle in circles]
        self.assertEqual(actual, expected)
        for _, _, _, fill, outline, _ in actual:
            with self.subTest(fill=fill, outline=outline):
                self.assertGreaterEqual(ratio(fill, outline), 6.0)


if __name__ == "__main__":
    unittest.main()
