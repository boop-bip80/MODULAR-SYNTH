"""Regression tests for truthful, deterministic first-party jack overlay SVG."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/ui-check"))

from jack_geometry_overlay import make_overlay  # noqa: E402
from port_rail_audit import PORT_CALL, SVG_NS, ZONES  # noqa: E402


class JackGeometryOverlayTests(unittest.TestCase):
    def test_overlay_matches_every_morphvco_source_jack(self) -> None:
        tree = make_overlay(ROOT, "MorphVCO")
        svg = tree.getroot()
        overlay = svg.find(SVG_NS + "g[@id='source-jack-geometry-overlay']")
        self.assertIsNotNone(overlay)
        boundary = overlay.find(SVG_NS + "rect[@id='source-panel-boundary']")
        self.assertEqual((boundary.get("x"), boundary.get("y"),
                          boundary.get("width"), boundary.get("height")),
                         ("0", "0", "180", "380"))
        source = (ROOT / "plugins/ModularSynth/src/MorphVCO.cpp").read_text()
        actual = {(m.group("role"), m.group("port")):
                  (float(m.group("x")), float(m.group("y")))
                  for m in PORT_CALL.finditer(source) if m.group("model") == "MorphVCO"}
        displayed = {(c.get("data-role"), c.get("data-port")):
                     (float(c.get("cx")), float(c.get("cy")))
                     for c in overlay.findall(SVG_NS + "circle")}
        self.assertEqual(displayed, actual)
        self.assertEqual(len(displayed), sum(len(ports) for ports in ZONES["MorphVCO"].values()))
        self.assertEqual(displayed[("Input", "PITCH_INPUT")], (28, 301))
        self.assertEqual(displayed[("Output", "MORPH_OUTPUT")], (55, 352))

    def test_overlay_is_deterministic_and_rejects_unknown_module(self) -> None:
        generated = ET.tostring(make_overlay(ROOT, "MorphVCO").getroot())
        preview = ET.tostring(ET.parse(
            ROOT / "tools/ui-check/MorphVCO-jack-geometry.svg").getroot())
        self.assertEqual(generated, preview, "committed SVG source preview is stale")
        for model in ZONES:
            with self.subTest(model=model):
                self.assertIsNotNone(make_overlay(ROOT, model))
        with self.assertRaisesRegex(ValueError, "unsupported model"):
            make_overlay(ROOT, "MissingPanel")


if __name__ == "__main__":
    unittest.main()
