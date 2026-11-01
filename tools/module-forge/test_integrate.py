"""Integration transaction and collision tests using isolated temporary fixtures."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from integrate import IntegrationError, apply_plan, integration_plan, plan_diff
from module_forge import generate


MAKEFILE = """# MODULAR-SYNTH first-party collection (full variants)
PLUGIN_FILES += ModularSynth/src/MorphVCO.cpp

$(BUILD_DIR)/ModularSynth/%.cpp.o: ModularSynth/%.cpp
\t$(CXX) $< -DpluginInstance=pluginInstance__ModularSynth
"""

LOADER_SINGLE = """static void initStatic__ModularSynth()
{
    Plugin* const p = new Plugin;
    pluginInstance__ModularSynth = p;

    const StaticPluginLoader spl(p, "ModularSynth");
    if (spl.ok())
        p->addModel(modelMorphVCO);
}

static void initStatic__Fundamental()
{
}
"""

LOADER_BRACED = """static void initStatic__ModularSynth()
{
    Plugin* const p = new Plugin;
    pluginInstance__ModularSynth = p;

    const StaticPluginLoader spl(p, "ModularSynth");
    if (spl.ok())
    {
        p->addModel(modelMorphVCO);
    }
}

static void initStatic__Fundamental()
{
}
"""


def fixture_root(root: Path, loader: str = LOADER_SINGLE) -> tuple[Path, Path]:
    (root / "plugins/ModularSynth/src").mkdir(parents=True)
    (root / "plugins/ModularSynth/res").mkdir()
    (root / "plugins/Makefile").write_text(MAKEFILE, encoding="utf-8")
    (root / "plugins/plugins.cpp").write_text(loader, encoding="utf-8")
    (root / "plugins/ModularSynth/src/plugin.hpp").write_text(
        '#include "rack.hpp"\nusing namespace rack;\n'
        'extern Model* modelMorphVCO;\n', encoding="utf-8")
    manifest = {
        "slug": "ModularSynth",
        "name": "MODULAR-SYNTH Originals",
        "version": "0.1.0",
        "modules": [{"slug": "MorphVCO", "name": "Morph VCO"}],
    }
    (root / "plugins/ModularSynth/plugin.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    generated = generate("OrbitSine", "Orbit Sine", root / "generated")
    return root, generated


def registered_files(root: Path) -> dict[Path, bytes]:
    paths = (
        root / "plugins/Makefile",
        root / "plugins/plugins.cpp",
        root / "plugins/ModularSynth/src/plugin.hpp",
        root / "plugins/ModularSynth/plugin.json",
    )
    return {path: path.read_bytes() for path in paths}


class IntegrationTests(unittest.TestCase):
    def test_dry_run_is_deterministic_and_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, module = fixture_root(Path(temporary))
            before = registered_files(root)
            a = integration_plan(module, root)
            b = integration_plan(module, root)
            self.assertEqual(plan_diff(a, root), plan_diff(b, root))
            self.assertIn("p->addModel(modelMSOrbitSine)", plan_diff(a, root))
            self.assertEqual(len(a), 6)
            self.assertEqual(registered_files(root), before)
            self.assertFalse((root / "plugins/ModularSynth/src/OrbitSine.cpp").exists())

    def test_apply_updates_all_registries_and_rejects_repeat(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, module = fixture_root(Path(temporary))
            apply_plan(integration_plan(module, root), root)
            self.assertTrue((root / "plugins/ModularSynth/src/OrbitSine.cpp").is_file())
            self.assertTrue((root / "plugins/ModularSynth/res/OrbitSine.svg").is_file())
            self.assertIn("PLUGIN_FILES += ModularSynth/src/OrbitSine.cpp",
                          (root / "plugins/Makefile").read_text())
            self.assertIn("extern Model* modelMSOrbitSine;",
                          (root / "plugins/ModularSynth/src/plugin.hpp").read_text())
            self.assertIn("p->addModel(modelMSOrbitSine);",
                          (root / "plugins/plugins.cpp").read_text())
            manifest = json.loads((root / "plugins/ModularSynth/plugin.json").read_text())
            self.assertEqual([m["slug"] for m in manifest["modules"]],
                             ["MorphVCO", "OrbitSine"])
            with self.assertRaises(IntegrationError):
                integration_plan(module, root)

    def test_braced_loader_supports_additional_models(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, module = fixture_root(Path(temporary), LOADER_BRACED)
            apply_plan(integration_plan(module, root), root)
            content = (root / "plugins/plugins.cpp").read_text()
            self.assertIn("p->addModel(modelMorphVCO);", content)
            self.assertIn("p->addModel(modelMSOrbitSine);", content)
            self.assertLess(content.index("modelMorphVCO"), content.index("modelMSOrbitSine"))

    def test_collision_never_overwrites_existing_user_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, module = fixture_root(Path(temporary))
            existing = root / "plugins/ModularSynth/src/OrbitSine.cpp"
            existing.write_text("user source", encoding="utf-8")
            before = registered_files(root)
            with self.assertRaises(IntegrationError):
                integration_plan(module, root)
            self.assertEqual(existing.read_text(), "user source")
            self.assertEqual(registered_files(root), before)

    def test_missing_compiler_rule_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, module = fixture_root(Path(temporary))
            make = root / "plugins/Makefile"
            make.write_text(make.read_text().replace(
                "-DpluginInstance=pluginInstance__ModularSynth", "-Dmissing"))
            before = registered_files(root)
            with self.assertRaises(IntegrationError):
                integration_plan(module, root)
            self.assertEqual(registered_files(root), before)

    def test_malformed_manifest_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, module = fixture_root(Path(temporary))
            manifest = root / "plugins/ModularSynth/plugin.json"
            manifest.write_text('{"slug":"not ModularSynth"}')
            before = registered_files(root)
            with self.assertRaises(IntegrationError):
                integration_plan(module, root)
            self.assertEqual(registered_files(root), before)

    def test_generated_module_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, module = fixture_root(Path(temporary))
            source = module / "OrbitSine.cpp"
            source.write_text(source.read_text().replace(
                '"OrbitSine")', '"ChangedSlug")'))
            with self.assertRaises(IntegrationError):
                integration_plan(module, root)

    def test_changes_after_planning_block_apply(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, module = fixture_root(Path(temporary))
            plan = integration_plan(module, root)
            target = root / "plugins/Makefile"
            target.write_text(target.read_text() + "# another developer changed this\n")
            before = registered_files(root)
            with self.assertRaises(IntegrationError):
                apply_plan(plan, root)
            self.assertEqual(registered_files(root), before)

    def test_failure_during_apply_rolls_back_completed_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, module = fixture_root(Path(temporary))
            before = registered_files(root)
            plan = integration_plan(module, root)
            original_replace = os.replace
            count = [0]

            def fail_on_second_replace(source, target):
                count[0] += 1
                if count[0] == 2:
                    raise OSError("injected interruption")
                return original_replace(source, target)

            with mock.patch("integrate.os.replace", side_effect=fail_on_second_replace):
                with self.assertRaises(OSError):
                    apply_plan(plan, root)
            self.assertEqual(registered_files(root), before)
            self.assertFalse((root / "plugins/ModularSynth/src/OrbitSine.cpp").exists())
            self.assertFalse((root / "plugins/ModularSynth/res/OrbitSine.svg").exists())


if __name__ == "__main__":
    unittest.main()
