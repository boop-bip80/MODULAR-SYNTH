#!/usr/bin/env python3
"""Regression fixtures for source-backed NanoVG label/outlined port lane QA."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / 'tools' / 'ui-check' / 'label_footprint_audit.py'
MODULES = ('MorphVCO', 'StateFilter', 'FoldDrive', 'Macro8', 'StereoEcho',
           'ClockedLFO', 'FMVoice', 'ChanceHold', 'DualVCA', 'SlewGlide',
           'ScaleQuantizer')


class LabelFootprintTests(unittest.TestCase):
    def fixture(self) -> Path:
        tmp = tempfile.TemporaryDirectory(prefix='modular-label-footprint-')
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for model in MODULES:
            for folder, suffix in (('src', '.cpp'), ('res', '.svg')):
                path = Path('plugins/ModularSynth') / folder / (model + suffix)
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / path, target)
        return root

    def mutate(self, root: Path, model: str, folder: str, before: str, after: str) -> None:
        path = root / 'plugins/ModularSynth' / folder / (model + ('.cpp' if folder == 'src' else '.svg'))
        source = path.read_text(encoding='utf-8')
        self.assertIn(before, source)
        path.write_text(source.replace(before, after, 1), encoding='utf-8')

    def cli(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, '-B', str(SCRIPT), '--root', str(root)],
                              check=False, capture_output=True, text=True)

    def assert_fails(self, root: Path, signal: str) -> None:
        outcome = self.cli(root)
        self.assertNotEqual(outcome.returncode, 0, outcome.stdout)
        self.assertIn(signal, outcome.stderr)

    def test_all_eleven_originals_pass(self) -> None:
        outcome = self.cli(REPO)
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertIn('11 original panels, 131 static labels, 67 ID-linked jack captions', outcome.stdout)
        self.assertIn('font-host/physical pixels unverified', outcome.stdout)

    def test_tiny_runtime_label_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, 'SlewGlide', 'src',
                    'nvgFontSize(args.vg, 10.0f);', 'nvgFontSize(args.vg, 7.0f);')
        self.assert_fails(root, 'tiny/unknown font size')

    def test_label_clipped_outside_panel_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, 'ClockedLFO', 'src',
                    'nvgText(args.vg, 26.0f, 235.0f, "RATE", nullptr);',
                    'nvgText(args.vg, 4.0f, 235.0f, "RATE", nullptr);')
        self.assert_fails(root, 'estimated text clipped at panel edge')

    def test_neighbouring_label_collision_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, 'ChanceHold', 'src',
                    'nvgText(args.vg, 73.0f, 235.0f, "CLK", nullptr);',
                    'nvgText(args.vg, 26.0f, 235.0f, "CLK", nullptr);')
        self.assert_fails(root, 'probable label overlap')

    def test_missing_jack_caption_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, 'SlewGlide', 'src',
                    'nvgText(args.vg, 30.0f, 218.0f, "CV IN", nullptr);',
                    'nvgText(args.vg, 30.0f, 218.0f, "INPUT", nullptr);')
        self.assert_fails(root, 'missing/offset/ambiguous jack caption')

    def test_scale_quantizer_caption_outside_rail_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, 'ScaleQuantizer', 'src',
                    'nvgText(args.vg, 32.0f, 240.0f, "PITCH", nullptr);',
                    'nvgText(args.vg, 30.0f, 236.0f, "PITCH", nullptr);')
        self.assert_fails(root, 'label/jack escapes its outlined lane')

    def test_narrow_rail_does_not_hide_caption_clipping(self) -> None:
        root = self.fixture()
        self.mutate(root, 'ClockedLFO', 'res',
                    'x="8" y="225" width="224" height="70"',
                    'x="13" y="225" width="214" height="70"')
        self.assert_fails(root, 'label/jack escapes its outlined lane')

    def test_missing_plugin_local_font_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, 'DualVCA', 'src',
                    'asset::system("res/fonts/ShareTechMono-Regular.ttf")',
                    'asset::plugin(pluginInstance, "res/fonts/Unbundled.ttf")')
        self.assert_fails(root, 'missing/nonlocal plugin font asset')

    def test_missing_system_font_reference_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, 'DualVCA', 'src',
                    'res/fonts/ShareTechMono-Regular.ttf', 'res/fonts/TypoName.ttf')
        self.assert_fails(root, 'unknown Rack system font dependency')

    def test_noncentered_alignment_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, 'FMVoice', 'src',
                    'NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE',
                    'NVG_ALIGN_LEFT | NVG_ALIGN_MIDDLE')
        self.assert_fails(root, 'expected centered NanoVG text')

    def test_macro_dynamic_width_guarantee_rejected_if_removed(self) -> None:
        root = self.fixture()
        self.mutate(root, 'Macro8', 'src',
                    'constexpr float maxLabelWidth = 65.0f;',
                    'constexpr float maxLabelWidth = 85.0f;')
        self.assert_fails(root, 'dynamic name fit target')

    def test_macro_dynamic_port_ring_drift_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, 'Macro8', 'res',
                    '<circle cx="187" cy="215" r="16"/><circle cx="260" cy="215" r="16"/>',
                    '<circle cx="187" cy="215" r="16"/><circle cx="261" cy="215" r="16"/>')
        self.assert_fails(root, 'output ring missing')


if __name__ == '__main__':
    unittest.main()
