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
        self.assertEqual(len(real_rack.MODULES), 8)
        self.assertIn("FoldDrive", real_rack.MODULES)
        self.assertIn("FMVoice", real_rack.MODULES)
        self.assertIn("ChanceHold", real_rack.MODULES)

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
        self.assertNotIn("PASS: 8/8", result.stdout)


    def test_module_sources_are_present_and_missing_wrapper_fails_closed(self) -> None:
        sources = real_rack.module_sources()
        self.assertEqual(len(sources), len(real_rack.MODULES))
        self.assertTrue(all(source.is_file() for source in sources))
        with self.assertRaisesRegex(real_rack.PreflightError, "Missing first-party wrapper"):
            real_rack.module_sources(Path("/nonexistent/sdk/modules"), ("FMVoice",))

    def test_registration_contract_rejects_missing_or_duplicate_wiring(self) -> None:
        modules = ("MorphVCO", "FMVoice")
        manifest = {"modules": [{"slug": name} for name in modules]}
        makefile = "\n".join(
            f"PLUGIN_FILES += ModularSynth/src/{name}.cpp" for name in modules
        )
        header = "\n".join(f"extern Model* model{name};" for name in modules)
        loader = (
            "static void initStatic__ModularSynth()\n{\n"
            "  p->addModel(modelMorphVCO);\n"
            "  p->addModel(modelFMVoice);\n}\n"
            "void initStaticPlugins()\n{\n"
            "  initStatic__ModularSynth();\n}\n"
        )
        real_rack.validate_registration_contract(
            manifest, makefile, header, loader, modules,
        )
        with self.assertRaisesRegex(real_rack.PreflightError, "manifest mismatch"):
            real_rack.validate_registration_contract(
                {"modules": [{"slug": "MorphVCO"}]}, makefile, header, loader, modules,
            )
        with self.assertRaisesRegex(real_rack.PreflightError, "compiled-source registry mismatch"):
            real_rack.validate_registration_contract(
                manifest, makefile.replace("FMVoice.cpp", "MorphVCO.cpp"),
                header, loader, modules,
            )
        with self.assertRaisesRegex(real_rack.PreflightError, "header declarations mismatch"):
            real_rack.validate_registration_contract(
                manifest, makefile, header.replace("modelFMVoice", "modelMorphVCO"),
                loader, modules,
            )
        with self.assertRaisesRegex(real_rack.PreflightError, "loader registrations mismatch"):
            real_rack.validate_registration_contract(
                manifest, makefile, header,
                loader.replace("p->addModel(modelFMVoice);", "p->addModel(modelMorphVCO);"),
                modules,
            )

    def test_real_registration_snapshot_matches_all_eight_modules(self) -> None:
        # This reads the real repository's production loader and Makefile,
        # avoiding a link-smoke that succeeds while the host never registers it.
        real_rack.check_registration_contract()

    def test_link_symbol_gate_rejects_missing_duplicate_and_undefined_models(self) -> None:
        modules = ("MorphVCO", "FMVoice")
        good = "00000000 D modelMorphVCO\n00000008 D modelFMVoice\n"
        host_import = "                 U _ZN4rack8hostCallEv\n"
        real_rack.validate_linked_model_symbols(good, host_import, modules)
        with self.assertRaisesRegex(real_rack.PreflightError, "Missing or duplicate"):
            real_rack.validate_linked_model_symbols(
                "00000000 D modelMorphVCO\n", host_import, modules,
            )
        with self.assertRaisesRegex(real_rack.PreflightError, "Missing or duplicate"):
            real_rack.validate_linked_model_symbols(
                good + "00000010 D modelFMVoice\n", host_import, modules,
            )
        with self.assertRaisesRegex(real_rack.PreflightError, "Unresolved first-party"):
            real_rack.validate_linked_model_symbols(
                good, host_import + "                 U modelFMVoice\n", modules,
            )

    def test_link_smoke_cli_fails_on_unavailable_real_sdk(self) -> None:
        missing = real_rack.ROOT / "__no_rack_sdk_at_this_path__"
        result = subprocess.run(
            [
                sys.executable, "-B", str(real_rack.ROOT / "tools/ci/check_real_rack_headers.py"),
                "--rack-root", str(missing), "--link-smoke",
            ], cwd=real_rack.ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Real Rack header preflight unavailable", result.stderr)
        self.assertNotIn("PASS:", result.stdout)


if __name__ == "__main__":
    unittest.main()
