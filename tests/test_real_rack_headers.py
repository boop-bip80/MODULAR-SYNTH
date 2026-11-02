"""Offline contract checks for the optional pinned real-Rack compiler gate.

These tests deliberately require no downloaded Rack/DPF SDK. The real SDK
compilation itself runs separately in check_real_rack_headers.py.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from tools.ci import check_real_rack_headers as real_rack


class RealRackHeaderCheckTests(unittest.TestCase):
    def test_exact_gitlink_parser_rejects_non_github_revisions(self) -> None:
        sha = "8c6f41b778b4bf8860b89b36d5503fd37924077f"
        self.assertEqual(real_rack.parse_gitlink(f"160000 commit {sha}\tsrc/Rack", "src/Rack"), sha)
        with self.assertRaises(real_rack.PreflightError):
            real_rack.parse_gitlink(f"100644 blob {sha}\tsrc/Rack", "src/Rack")
        with self.assertRaises(real_rack.PreflightError):
            real_rack.parse_gitlink(f"160000 commit {sha}\tdpf", "src/Rack")

    def test_speex_type_config_uses_original_template_platform_substitutions(self) -> None:
        template = " ".join((
            "@INCLUDE_STDINT@", "@SIZE16@", "@USIZE16@", "@SIZE32@", "@USIZE32@",
        ))
        rendered = real_rack.render_linux_speex_types(template)
        self.assertEqual(
            rendered, "#include <stdint.h> int16_t uint16_t int32_t uint32_t",
        )

    def test_speex_type_config_refuses_changed_or_incomplete_template(self) -> None:
        with self.assertRaises(real_rack.PreflightError):
            real_rack.render_linux_speex_types("@INCLUDE_STDINT@ @SIZE16@ @SIZE32@")
        with self.assertRaises(real_rack.PreflightError):
            real_rack.render_linux_speex_types(
                "@INCLUDE_STDINT@ @SIZE16@ @USIZE16@ @SIZE32@ @USIZE32@ @NEW_MARKER@",
            )

    def test_compiler_flags_use_real_rack_and_production_plugin_alias(self) -> None:
        flags = real_rack.compiler_flags(
            Path("/sdk/rack"), Path("/sdk/dpf"), Path("/sdk/jansson"),
            Path("/temporary/speex-types"),
        )
        self.assertIn("-DpluginInstance=pluginInstance__ModularSynth", flags)
        self.assertIn("-DHEADLESS", flags)
        self.assertIn("/sdk/rack/include", flags)
        self.assertIn("/sdk/dpf/distrho", flags)
        self.assertNotIn(str(real_rack.ROOT / "tests" / "rack_stub"), flags)
        self.assertEqual(len(real_rack.MODULES), 6)
        self.assertIn("FoldDrive", real_rack.MODULES)

    def test_unavailable_sdk_fails_clearly_without_network_or_auto_install(self) -> None:
        missing = real_rack.ROOT / "__no_rack_sdk_at_this_path__"
        result = subprocess.run(
            [
                sys.executable, "-B", str(real_rack.ROOT / "tools/ci/check_real_rack_headers.py"),
                "--rack-root", str(missing), "--preflight-only",
            ], cwd=real_rack.ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Real Rack header preflight unavailable", result.stderr)
        self.assertIn("git submodule update --init --depth 1", result.stderr)
        self.assertNotIn("PASS: 6/6", result.stdout)


if __name__ == "__main__":
    unittest.main()
