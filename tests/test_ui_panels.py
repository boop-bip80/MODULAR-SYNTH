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
RAIL_CHECKER = REPO / "tools" / "ui-check" / "port_rail_audit.py"
MODULES = ("MorphVCO", "StateFilter", "FoldDrive", "Macro8", "StereoEcho", "ClockedLFO", "FMVoice", "ChanceHold", "DualVCA")


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

    def run_rail_checker(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RAIL_CHECKER), "--root", str(root)],
            capture_output=True, text=True, check=False
        )

    def replace_one(self, path: Path, before: str, after: str) -> None:
        source = path.read_text(encoding="utf-8")
        self.assertIn(before, source, f"fixture changed unexpectedly: {path}")
        path.write_text(source.replace(before, after, 1), encoding="utf-8")

    def test_current_repository_panels_pass(self) -> None:
        result = self.run_checker(REPO)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("PASS: 9 SVG panels", result.stdout)
        self.assertIn("121 conservative candidate widget centers", result.stdout)
        self.assertIn("visual rendering/overlap not verified", result.stdout)

    def test_source_signal_rails_cover_real_ports_and_labels(self) -> None:
        result = self.run_rail_checker(REPO)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("5 rails, 14 jacks and 14 labels", result.stdout)
        self.assertIn("DualVCA/dualInputRail: 4 ports", result.stdout)
        self.assertIn("StereoEcho/echoMixCvRail: 1 ports", result.stdout)
        self.assertIn("StereoEcho/echoOutputRail: 2 ports", result.stdout)
        self.assertIn("no rendered contrast", result.stdout)

    def test_signal_rail_catches_port_relocation_inside_panel(self) -> None:
        root = self.fixture()
        cpp = root / "plugins/ModularSynth/src/DualVCA.cpp"
        self.replace_one(cpp, "Vec(156.0f, 268.0f)", "Vec(174.0f, 268.0f)")
        # 174 is inside the 180-px physical panel but outside the input rail.
        self.assertEqual(self.run_checker(root).returncode, 0)
        result = self.run_rail_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CV_B_INPUT center (174, 268) outside", result.stderr)

    def test_signal_rail_catches_removed_input_zone(self) -> None:
        root = self.fixture()
        svg = root / "plugins/ModularSynth/res/StereoEcho.svg"
        self.replace_one(svg, 'id="echoMixCvRail"', 'id="oldMixCvRail"')
        result = self.run_rail_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("echoMixCvRail: expected exactly one", result.stderr)

    def test_signal_rail_catches_input_retyped_as_output(self) -> None:
        root = self.fixture()
        cpp = root / "plugins/ModularSynth/src/StereoEcho.cpp"
        self.replace_one(
            cpp,
            "addInput(createInputCentered<PJ301MPort>(Vec(35.0f, 340.0f)",
            "addOutput(createOutputCentered<PJ301MPort>(Vec(35.0f, 340.0f)"
        )
        result = self.run_rail_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing=['Input:MIX_CV_INPUT']", result.stderr)
        self.assertIn("unexpected=['Output:MIX_CV_INPUT']", result.stderr)

    def test_signal_rail_catches_moved_label(self) -> None:
        root = self.fixture()
        cpp = root / "plugins/ModularSynth/src/StereoEcho.cpp"
        self.replace_one(
            cpp,
            'nvgText(args.vg, 35.0f, 306.0f, "MIX CV", nullptr);',
            'nvgText(args.vg, 35.0f, 291.0f, "MIX CV", nullptr);'
        )
        result = self.run_rail_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("label 'MIX CV' outside solid rail", result.stderr)

    def test_signal_rail_catches_low_contrast_label_and_border(self) -> None:
        root = self.fixture()
        svg = root / "plugins/ModularSynth/res/DualVCA.svg"
        self.replace_one(svg, 'stroke="#78D5DB"', 'stroke="#182D3B"')
        result = self.run_rail_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("border/fill", result.stderr)

        root = self.fixture()
        cpp = root / "plugins/ModularSynth/src/DualVCA.cpp"
        self.replace_one(cpp, "nvgRGB(0x9F, 0xE9, 0xF8)",
                         "nvgRGB(0x16, 0x2D, 0x3C)")
        result = self.run_rail_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("label 'A IN' palette", result.stderr)

    def test_signal_rail_catches_port_decoration_clipping(self) -> None:
        root = self.fixture()
        svg = root / "plugins/ModularSynth/res/DualVCA.svg"
        self.replace_one(svg, 'cx="24" cy="268" r="13.5"',
                         'cx="24" cy="268" r="19"')
        result = self.run_rail_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AUDIO_A_INPUT jack ring protrudes", result.stderr)

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

    def test_all_nine_modules_have_exact_control_callsite_cardinality(self) -> None:
        changes = (
            ("MorphVCO", "createInputCentered<PJ301MPort>",
             "createOutputCentered<PJ301MPort>", "expected 4 Input centered callsites, found 3"),
            ("StateFilter", "createParamCentered<RoundBlackKnob>",
             "createOutputCentered<RoundBlackKnob>", "expected 3 Param centered callsites, found 2"),
            ("Macro8", "createLightCentered<SmallLight<GreenLight>>",
             "createInputCentered<SmallLight<GreenLight>>", "expected 3 Light centered callsites, found 2"),
        )
        for model, before, after, message in changes:
            with self.subTest(model=model):
                model_root = self.fixture()
                source = model_root / "plugins/ModularSynth/src" / (model + ".cpp")
                self.replace_one(source, before, after)
                result = self.run_checker(model_root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_unknown_control_type_is_not_silently_accepted(self) -> None:
        root = self.fixture()
        source = root / "plugins/ModularSynth/src/MorphVCO.cpp"
        self.replace_one(source, "createOutputCentered<PJ301MPort>",
                         "createLightCentered<PJ301MPort>")
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected 1 Light centered callsite(s)", result.stderr)

    def test_svg_missing_gradient_target_rejected(self) -> None:
        root = self.fixture()
        panel = root / "plugins/ModularSynth/res/Macro8.svg"
        self.replace_one(panel, 'fill="url(#panel)"', 'fill="url(#missing)"')
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("references missing/ambiguous SVG id #missing", result.stderr)

    def test_svg_duplicate_gradient_id_rejected(self) -> None:
        root = self.fixture()
        panel = root / "plugins/ModularSynth/res/MorphVCO.svg"
        self.replace_one(panel, '<linearGradient id="line"', '<linearGradient id="base"')
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate SVG id 'base'", result.stderr)

    def test_svg_paint_reference_must_point_to_gradient_or_pattern(self) -> None:
        root = self.fixture()
        panel = root / "plugins/ModularSynth/res/MorphVCO.svg"
        self.replace_one(panel, '<linearGradient id="base"', '<g id="base"')
        self.replace_one(panel, '</linearGradient>', '</g>')
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not a paint server", result.stderr)

    def test_svg_external_paint_url_rejected(self) -> None:
        root = self.fixture()
        panel = root / "plugins/ModularSynth/res/MorphVCO.svg"
        self.replace_one(panel, 'fill="url(#base)"',
                         'fill="url(https://example.invalid/base.svg#base)"')
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("external/invalid SVG url", result.stderr)

    def test_svg_script_external_image_and_entity_declarations_rejected(self) -> None:
        root = self.fixture()
        panel = root / "plugins/ModularSynth/res/MorphVCO.svg"
        original = panel.read_text(encoding="utf-8")
        try:
            for fragment, message in (
                ('<script xmlns="http://www.w3.org/2000/svg"/>',
                 "unsupported/external SVG element <script>"),
                ('<image xmlns="http://www.w3.org/2000/svg" '
                 'href="https://example.invalid/texture.png"/>',
                 "unsupported/external SVG element <image>"),
            ):
                panel.write_text(original.replace("</svg>", fragment + "</svg>"),
                                 encoding="utf-8")
                result = self.run_checker(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
            panel.write_text(original.replace("<svg ",
                '<!DOCTYPE svg [<!ENTITY external SYSTEM "file:///private.txt">]><svg ', 1),
                encoding="utf-8")
            result = self.run_checker(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("external/entity declarations are not allowed", result.stderr)
        finally:
            panel.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
