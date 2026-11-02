"""Opt-in route-aware Macro8 SVG panels: golden output, safety and legacy tests."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree

from instrument_builder import (
    InstrumentError, MANIFEST_MEMBER, build_manifest, create_bundle,
    main, preview,
)
from panel_preview import (
    FOOTER_HEIGHT, HEADER_HEIGHT, ROUTE_HEADER_HEIGHT,
    ROUTE_SECTION_HEIGHT, SECTION_HEIGHT, PreviewError, render_svg,
)
from route_report import build_route_report
from test_fm_voice_mapping import (
    fm_fold_clock_patch, fm_voice_patch, historical_bundle,
)
from test_instrument_builder import custom_archive, patch_bytes
from test_panel_preview import SVG_NS, manifest_for


def route_view(manifest: dict) -> dict:
    return {
        **manifest, "formatVersion": 1,
        "performance": {"macro8": manifest["performance"]["macro8"]},
    }


class RouteAwarePanelTests(unittest.TestCase):
    def test_default_svg_golden_is_unchanged(self) -> None:
        # The older v1 concept preview must remain exactly byte-for-byte stable.
        svg = render_svg(manifest_for())
        self.assertEqual(hashlib.sha256(svg).hexdigest(),
                         "a4b8847b1831fb6644812d70d04dd9d3b1589f7cab2b9fe5e014f9f1ca343529")
        self.assertNotIn(b"saved-route-map", svg)

    def test_fm_fold_clock_v2_has_golden_route_aware_svg(self) -> None:
        manifest = build_manifest(
            patch_bytes(fm_fold_clock_patch()), "FM & Fold", format_version=2)
        data = render_svg(route_view(manifest),
                          route_map=build_route_report(manifest))
        self.assertEqual(data, render_svg(
            route_view(manifest), route_map=build_route_report(manifest)))
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         "40ace5994482fc7db860f4c6055538bd1dae787a7dea44ae2f8f47b15e9e93e4")
        root = ElementTree.fromstring(data)
        self.assertEqual(root.attrib["height"], str(
            HEADER_HEIGHT + SECTION_HEIGHT + ROUTE_HEADER_HEIGHT
            + ROUTE_SECTION_HEIGHT + FOOTER_HEIGHT))
        self.assertEqual(len(root.findall(
            ".//s:g[@class='saved-route-controller']", SVG_NS)), 1)
        rows = root.findall(".//s:g[@class='saved-route-row']", SVG_NS)
        self.assertEqual(len(rows), 8)
        self.assertEqual([int(r.attrib["data-route-count"]) for r in rows],
                         [1, 1, 1, 1, 1, 1, 0, 0])
        self.assertTrue(all(r.attrib["data-unverified-count"] == "0"
                            for r in rows))
        accessible = " ".join((title.text or "") for title in root.findall(
            ".//s:g[@class='saved-route-row']/s:title", SVG_NS))
        self.assertIn("Ratio CV (1 V doubles ratio)", accessible)
        self.assertIn("Index CV (1 V adds 0.8 rad)", accessible)
        self.assertIn("Feedback CV (10 V adds 95%)", accessible)
        self.assertIn("FoldDrive", accessible)
        self.assertIn("ClockedLFO", accessible)
        self.assertEqual(root.findall(".//s:script", SVG_NS), [])
        self.assertEqual(root.findall(".//s:foreignObject", SVG_NS), [])

    def test_unverified_third_party_destination_is_visible_and_xml_escaped(self) -> None:
        patch = fm_fold_clock_patch()
        patch["modules"].append({
            "id": 200, "plugin": "Other&Co", "model": "<script>",
        })
        patch["cables"].append({
            "id": 180, "outputModuleId": 70, "outputId": 0,
            "inputModuleId": 200, "inputId": 1,
        })
        manifest = build_manifest(patch_bytes(patch), "Unknown", format_version=2)
        svg = render_svg(route_view(manifest), route_map=build_route_report(manifest))
        root = ElementTree.fromstring(svg)
        rows = root.findall(".//s:g[@class='saved-route-row']", SVG_NS)
        self.assertEqual(rows[0].attrib["data-route-count"], "2")
        self.assertEqual(rows[0].attrib["data-unverified-count"], "1")
        titles = [(element.text or "") for element in root.findall(
            ".//s:g[@class='saved-route-row']/s:title", SVG_NS)]
        self.assertIn("Other&Co/<script> input 1 · UNVERIFIED INPUT", titles[0])
        self.assertIn(b"Other&amp;Co/&lt;script&gt;", svg)
        self.assertNotIn(b"<script>", svg)
        self.assertEqual(root.findall(".//s:script", SVG_NS), [])
        self.assertIn(b"1 unverified", svg)

    def test_historical_v2_fm_routes_stay_unverified_in_svg(self) -> None:
        blob = historical_bundle(fm_voice_patch(), "Historical", None)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            bundle = folder / "old.msinstrument"
            panel = folder / "old.svg"
            bundle.write_bytes(blob)
            preview(bundle, panel, show_routes=True)
            svg = panel.read_bytes()
            self.assertEqual(bundle.read_bytes(), blob)
            self.assertIn(b"UNVERIFIED INPUT", svg)
            self.assertNotIn(b"Ratio CV (1 V doubles ratio)", svg)
            root = ElementTree.fromstring(svg)
            rows = root.findall(".//s:g[@class='saved-route-row']", SVG_NS)
            self.assertEqual(
                [row.attrib["data-unverified-count"] for row in rows[:4]],
                ["1", "1", "1", "1"])

    def test_multiple_controllers_stay_sorted_in_one_visual_map(self) -> None:
        patch = fm_voice_patch()
        earlier = deepcopy(patch["modules"][0])
        earlier["id"] = 12
        earlier["data"]["names"][0] = "Lead"
        patch["modules"].append(earlier)
        manifest = build_manifest(
            patch_bytes(patch), "Dual", format_version=2)
        svg = render_svg(route_view(manifest), route_map=build_route_report(manifest))
        root = ElementTree.fromstring(svg)
        sections = root.findall(
            ".//s:g[@class='saved-route-controller']", SVG_NS)
        self.assertEqual([row.attrib["data-module-id"] for row in sections],
                         ["12", "70"])
        self.assertEqual(len(root.findall(
            ".//s:g[@class='saved-route-row']", SVG_NS)), 16)
        self.assertEqual(root.attrib["height"], str(
            HEADER_HEIGHT + 2 * SECTION_HEIGHT + ROUTE_HEADER_HEIGHT
            + 2 * ROUTE_SECTION_HEIGHT + FOOTER_HEIGHT))
        self.assertEqual(sections[0].find(
            ".//s:g[@class='saved-route-row']", SVG_NS
        ).attrib["data-route-count"], "0")

    def test_opt_in_cli_writes_only_static_svg_and_preserves_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            raw = patch_bytes(fm_fold_clock_patch())
            bundle = folder / "source.msinstrument"
            blob = create_bundle(raw, "FM & Fold", format_version=2)
            bundle.write_bytes(blob)
            target = folder / "routes.svg"
            with redirect_stdout(StringIO()) as output:
                code = main([
                    "preview", str(bundle), "--show-routes",
                    "--out", str(target)])
            self.assertEqual(code, 0)
            self.assertIn("route-aware SVG preview", output.getvalue())
            self.assertEqual(bundle.read_bytes(), blob)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),
                             "40ace5994482fc7db860f4c6055538bd1dae787a7dea44ae2f8f47b15e9e93e4")
            with self.assertRaises(FileExistsError):
                preview(bundle, target, show_routes=True)
            self.assertEqual(bundle.read_bytes(), blob)

    def test_v1_requires_v2_and_invalid_bundle_creates_no_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            bundle = folder / "v1.msinstrument"
            bundle.write_bytes(create_bundle(
                patch_bytes(fm_voice_patch()), "Old", format_version=1))
            result = folder / "should-not-exist.svg"
            with self.assertRaisesRegex(
                    InstrumentError, "requires v2 source mapping metadata"):
                preview(bundle, result, show_routes=True)
            self.assertFalse(result.exists())
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(main([
                    "preview", str(bundle), "--out", str(result)]), 0)
            self.assertIn("static SVG preview", output.getvalue())
            self.assertTrue(result.is_file())

            bad = folder / "bad.msinstrument"
            bad.write_bytes(b"not a ZIP")
            with self.assertRaises(InstrumentError):
                preview(bad, folder / "bad.svg", show_routes=True)
            self.assertFalse((folder / "bad.svg").exists())

    def test_forged_marker_or_mapping_fails_before_svg_output(self) -> None:
        blob = create_bundle(
            patch_bytes(fm_voice_patch()), "FM", format_version=2)
        from test_control_mapping import manifest_entries
        entries = manifest_entries(blob)
        for mutation in (
            lambda m: m["performance"].pop("controlMappingContract"),
            lambda m: m["performance"]["controlMappings"][0]
            ["destination"].update(inputLabel="DAW certified"),
        ):
            with self.subTest(mutation=mutation):
                manifest = json.loads(dict(entries)[MANIFEST_MEMBER])
                mutation(manifest)
                forged = custom_archive([
                    (name, json.dumps(manifest).encode("utf-8")
                     if name == MANIFEST_MEMBER else content)
                    for name, content in entries
                ])
                with tempfile.TemporaryDirectory() as temporary:
                    folder = Path(temporary)
                    source = folder / "forged.msinstrument"
                    target = folder / "never.svg"
                    source.write_bytes(forged)
                    with self.assertRaisesRegex(
                            InstrumentError, "manifest does not match its patch"):
                        preview(source, target, show_routes=True)
                    self.assertFalse(target.exists())

    def test_direct_renderer_rejects_inconsistent_route_report(self) -> None:
        manifest = build_manifest(
            patch_bytes(fm_voice_patch()), "FM", format_version=2)
        view = route_view(manifest)
        baseline = build_route_report(manifest)
        for mutation in (
            lambda m: m.update(bundleFormatVersion=1),
            lambda m: m["routes"][0]["macro"].update(moduleId=9999),
            lambda m: m["routes"][0]["macro"].update(name="Forged"),
            lambda m: m["routes"][0]["destination"].update(kind="unverified"),
            lambda m: m["routes"][0]["destination"].update(inputId=True),
            lambda m: m["routes"][0]["destination"].update(label="<invalid>\ud800"),
        ):
            with self.subTest(mutation=mutation):
                tampered = deepcopy(baseline)
                mutation(tampered)
                with self.assertRaises(PreviewError):
                    render_svg(view, route_map=tampered)


if __name__ == "__main__":
    unittest.main()
