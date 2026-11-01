"""Offline SVG concept panel: deterministic, readable, non-executable tests."""
from copy import deepcopy
from io import StringIO
from contextlib import redirect_stdout
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree

from instrument_builder import (
    InstrumentError, build_manifest, create_bundle, main, preview,
)
from panel_preview import (
    CARD_WIDTH, COLORS, FOOTER_HEIGHT, HEADER_HEIGHT, PreviewError,
    SECTION_HEIGHT, render_svg,
)


SVG_NS = {"s": "http://www.w3.org/2000/svg"}


def patch_data() -> dict:
    return {
        "version": "2.4.1",
        "modules": [{
            "id": 700, "plugin": "ModularSynth", "model": "Macro8",
            "params": [{"id": i, "value": 0.5 if i < 8 else
                        (0.75 if i == 8 else 0.0)}
                       for i in range(23)],
            "data": {
                "macro8Version": 1,
                "names": ["Shape", "Color", "Drive", "Motion",
                          "Space", "Gain", "Width", "Texture"],
                "snapshots": [[0.2] * 8, [0.75] * 8, None, None],
                "selectedSlot": 0,
            },
        }],
        "cables": [],
    }


def source_bytes(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, ensure_ascii=True) + "\n").encode()


def manifest_for(data: dict | None = None, name: str = "Demo Instrument") -> dict:
    return build_manifest(source_bytes(data or patch_data()), name)


def _luminance(color: str) -> float:
    digits = color.lstrip("#")
    channels = [int(digits[i:i+2], 16) / 255 for i in (0, 2, 4)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
              for v in channels]
    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722


def contrast_ratio(first: str, second: str) -> float:
    a, b = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (a + 0.05) / (b + 0.05)


class PanelPreviewTests(unittest.TestCase):
    def test_deterministic_valid_svg_and_control_counts(self):
        manifest = manifest_for()
        svg = render_svg(manifest)
        self.assertEqual(svg, render_svg(manifest))
        root = ElementTree.fromstring(svg)
        self.assertEqual(root.attrib["width"], "960")
        self.assertEqual(root.attrib["height"],
                         str(HEADER_HEIGHT + SECTION_HEIGHT + FOOTER_HEIGHT))
        self.assertEqual(root.attrib["role"], "img")
        self.assertIn("aria-labelledby", root.attrib)
        self.assertIsNotNone(root.find("s:title", SVG_NS))
        self.assertIsNotNone(root.find("s:desc", SVG_NS))
        self.assertEqual(
            len(root.findall(".//s:g[@class='macro-control']", SVG_NS)), 8)
        self.assertEqual(
            len(root.findall(".//s:text[@class='macro-label']", SVG_NS)), 8)
        self.assertEqual(
            len(root.findall(".//s:g[@class='snapshot-slot']", SVG_NS)), 4)
        self.assertEqual(
            len(root.findall(".//s:rect[@class='live-meter']", SVG_NS)), 8)
        for chip in ("selection", "action", "morph"):
            self.assertEqual(len(root.findall(
                f".//s:rect[@class='{chip}-chip']", SVG_NS)), 1)
        self.assertEqual(root.findall(".//s:script", SVG_NS), [])

    def test_xml_special_characters_are_escaped_without_markup_injection(self):
        patch = patch_data()
        labels = patch["modules"][0]["data"]["names"]
        labels[0] = "<script/>"
        labels[1] = "A&B <C>"
        name = '<Preview & "Safe">'
        svg = render_svg(manifest_for(patch, name))
        self.assertIn(b"&lt;script/&gt;", svg)
        self.assertIn(b"A&amp;B &lt;C&gt;", svg)
        self.assertNotIn(b"<script/>", svg)
        root = ElementTree.fromstring(svg)
        self.assertEqual(root.find("s:title", SVG_NS).text,
                         name + " \u2014 performance concept")
        parsed_labels = [element.text for element in root.findall(
            ".//s:text[@class='macro-label']", SVG_NS)]
        self.assertEqual(parsed_labels[0], "<script/>")
        self.assertEqual(parsed_labels[1], "A&B <C>")
        self.assertEqual(root.findall(".//s:script", SVG_NS), [])

    def test_title_wrap_and_long_macro_labels_fit_without_truncation(self):
        patch = patch_data()
        patch["modules"][0]["data"]["names"] = ["W" * 12] * 8
        full_name = "X" * 64
        root = ElementTree.fromstring(render_svg(manifest_for(patch, full_name)))
        title_lines = root.findall(".//s:text[@class='instrument-title']", SVG_NS)
        self.assertEqual(len(title_lines), 2)
        self.assertEqual("".join(part.text for part in title_lines), full_name)
        self.assertLessEqual(max(len(part.text) for part in title_lines), 46)
        self.assertEqual(
            [part.text for part in root.findall(
                ".//s:text[@class='macro-label']", SVG_NS)],
            ["W" * 12] * 8)
        # 12 fixed-pitch ~0.65em glyphs at 16 px leave ample card padding.
        self.assertLess(12 * 16 * 0.65, CARD_WIDTH - 32)

    def test_accessible_text_contrast_meets_wcag_aa(self):
        palette = COLORS
        for foreground, background in (
            ("text", "background"),
            ("text", "surface"),
            ("text", "card"),
            ("muted", "background"),
            ("muted", "card"),
            ("accent", "surface"),
            ("accent", "card"),
            ("on_active", "active"),
        ):
            with self.subTest(pair=(foreground, background)):
                self.assertGreaterEqual(
                    contrast_ratio(palette[foreground], palette[background]), 4.5)

    def test_snapshot_visual_state_and_polarities(self):
        patch = patch_data()
        patch["modules"][0]["params"][15]["value"] = 1
        patch["modules"][0]["params"][16]["value"] = 1
        svg = render_svg(manifest_for(patch))
        root = ElementTree.fromstring(svg)
        slots = root.findall(".//s:g[@class='snapshot-slot']", SVG_NS)
        self.assertEqual([slot.get("data-slot") for slot in slots],
                         list("ABCD"))
        snapshot_labels = [item.text for item in root.findall(
            ".//s:g[@class='snapshot-slot']/s:text", SVG_NS)]
        self.assertIn("A  /  SELECTED", snapshot_labels)
        self.assertIn("B  /  STORED", snapshot_labels)
        self.assertIn("C  /  EMPTY", snapshot_labels)
        self.assertIn("D  /  EMPTY", snapshot_labels)
        self.assertEqual(len(root.findall(
            ".//s:rect[@class='snapshot-meter']", SVG_NS)), 16)
        all_text = "\n".join(t.text or "" for t in root.iter(
            "{http://www.w3.org/2000/svg}text"))
        self.assertIn("BIPOLAR  /  -5 TO +5 V", all_text)
        self.assertIn("UNIPOLAR  /  0 TO +10 V", all_text)
        self.assertIn("SNAPSHOT A", all_text)

    def test_multiple_macro8_sections_sort_and_scale(self):
        patch = patch_data()
        earlier = deepcopy(patch["modules"][0])
        earlier["id"] = 4
        earlier["data"]["names"][0] = "Lead"
        patch["modules"].append(earlier)
        root = ElementTree.fromstring(render_svg(manifest_for(patch)))
        self.assertEqual(root.get("height"),
                         str(HEADER_HEIGHT + 2 * SECTION_HEIGHT + FOOTER_HEIGHT))
        sections = root.findall(".//s:g[@class='macro8-section']", SVG_NS)
        self.assertEqual(len(sections), 2)
        self.assertEqual(len(root.findall(
            ".//s:g[@class='macro-control']", SVG_NS)), 16)
        self.assertEqual(len(root.findall(
            ".//s:g[@class='snapshot-slot']", SVG_NS)), 8)
        header_labels = [item.text for item in root.findall(
            ".//s:g[@class='macro8-section']/s:text", SVG_NS)
            if (item.text or "").startswith("MACRO8  /  ID")]
        self.assertEqual(header_labels,
                         ["MACRO8  /  ID 4", "MACRO8  /  ID 700"])

    def test_preview_rejects_malformed_or_unsafe_manifest(self):
        cases = [
            lambda m: m.update(formatVersion=2),
            lambda m: m.update(name="BAD\nNAME"),
            lambda m: m["performance"]["macro8"][0]["names"].__setitem__(
                0, "over-twelve-chars"),
            lambda m: m["performance"]["macro8"][0]["ranges"].__setitem__(
                0, "invalid"),
            lambda m: m["performance"]["macro8"][0]["liveValues"].__setitem__(
                0, float("nan")),
            lambda m: m["performance"]["macro8"][0]["liveValues"].__setitem__(
                0, 10 ** 1000),
            lambda m: m["performance"]["macro8"][0]["snapshots"].__setitem__(
                0, None),
            lambda m: m["performance"]["macro8"][0].update(selectedSlot=5),
            lambda m: m["performance"]["macro8"][0].update(stateVersion=True),
        ]
        for index, mutation in enumerate(cases):
            with self.subTest(case=index):
                payload = deepcopy(manifest_for())
                mutation(payload)
                with self.assertRaises(PreviewError):
                    render_svg(payload)

    def test_preview_command_creates_svg_only_and_does_not_modify_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "demo.msinstrument"
            bundle.write_bytes(create_bundle(source_bytes(patch_data()), "Demo"))
            before = bundle.read_bytes()
            svg_path = root / "panel.svg"
            manifest = preview(bundle, svg_path)
            self.assertEqual(svg_path.read_bytes(), render_svg(manifest))
            ElementTree.fromstring(svg_path.read_bytes())
            self.assertEqual(bundle.read_bytes(), before)
            with self.assertRaises(FileExistsError):
                preview(bundle, svg_path)
            self.assertEqual(svg_path.read_bytes(), render_svg(manifest))

    def test_cli_preview_workflow(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "demo.msinstrument"
            bundle.write_bytes(create_bundle(source_bytes(patch_data()), "Demo"))
            output = root / "concept.svg"
            with redirect_stdout(StringIO()) as stream:
                result = main(["preview", str(bundle), "--out", str(output)])
            self.assertEqual(result, 0)
            self.assertIn("static SVG preview", stream.getvalue())
            self.assertTrue(output.is_file())

    def test_invalid_bundle_or_bad_extension_creates_no_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bad = root / "bad.msinstrument"
            bad.write_bytes(b"not a bundle")
            result = root / "panel.svg"
            with self.assertRaises(InstrumentError):
                preview(bad, result)
            self.assertFalse(result.exists())
            valid = root / "valid.msinstrument"
            valid.write_bytes(create_bundle(source_bytes(patch_data()), "Demo"))
            with self.assertRaises(InstrumentError):
                preview(valid, root / "panel.png")
            self.assertFalse((root / "panel.png").exists())

    def test_destination_parent_symlink_is_not_followed(self):
        if os.name != "posix":
            self.skipTest("POSIX no-follow directory test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            actual = root / "actual"
            actual.mkdir()
            link = root / "shortcut"
            link.symlink_to(actual, target_is_directory=True)
            bundle = root / "demo.msinstrument"
            bundle.write_bytes(create_bundle(source_bytes(patch_data()), "Demo"))
            with self.assertRaises((InstrumentError, OSError)):
                preview(bundle, link / "panel.svg")
            self.assertFalse((actual / "panel.svg").exists())

    def test_real_factory_performance_preview_when_present(self):
        factory = (Path(__file__).resolve().parents[2]
                   / "patches/examples/MODULAR_-_Morphing_State_Pad.vcv")
        if not factory.is_file():
            self.skipTest("real factory patch not included in checkout")
        manifest = build_manifest(factory.read_bytes(), "Morphing State Pad")
        root = ElementTree.fromstring(render_svg(manifest))
        names = [item.text for item in root.findall(
            ".//s:text[@class='macro-label']", SVG_NS)]
        self.assertEqual(names[:3], ["Shape", "Resonance", "Drive"])
        self.assertEqual(len(root.findall(
            ".//s:g[@class='snapshot-slot']", SVG_NS)), 4)


if __name__ == "__main__":
    unittest.main()
