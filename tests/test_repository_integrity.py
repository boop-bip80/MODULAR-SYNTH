"""Fast, dependency-free integrity checks for MODULAR-SYNTH.

Run from the repository root:
    python3 -m unittest discover -s tests -p 'test_*.py' -v

These checks complement (not replace) the existing Cardinal plugin/self-test CI.
"""
from __future__ import annotations

import configparser
import json
import subprocess
import unittest
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


class RepositoryIntegrityTests(unittest.TestCase):
    def test_first_party_module_manifest(self) -> None:
        path = ROOT / "plugins" / "Cardinal" / "plugin.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(manifest.get("slug"), "Cardinal")
        self.assertIsInstance(manifest.get("license"), str)
        modules = manifest.get("modules")
        self.assertIsInstance(modules, list)
        self.assertGreater(len(modules), 0, "First-party module list is empty")

        seen_slugs: set[str] = set()
        for module in modules:
            with self.subTest(module=module.get("slug")):
                slug = module.get("slug")
                self.assertIsInstance(slug, str)
                self.assertTrue(slug and slug.strip() == slug)
                self.assertNotIn(slug, seen_slugs, "Duplicate module slug")
                seen_slugs.add(slug)
                self.assertIsInstance(module.get("name"), str)
                self.assertTrue(module["name"].strip(), "Missing module name")
                self.assertIsInstance(module.get("tags", []), list)

    def test_bundled_patch_graphs(self) -> None:
        patches = sorted((ROOT / "patches").rglob("*.vcv"))
        self.assertTrue(patches, "No bundled patches were found")
        for path in patches:
            with self.subTest(patch=str(path.relative_to(ROOT))):
                # Cardinal stores its checked-in patches as plain UTF-8 JSON.
                patch = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(patch.get("version"), str)
                modules = patch.get("modules")
                cables = patch.get("cables")
                self.assertIsInstance(modules, list)
                self.assertIsInstance(cables, list)

                module_ids: set[int] = set()
                for module in modules:
                    module_id = module.get("id")
                    self.assertIsInstance(module_id, int)
                    self.assertNotIn(module_id, module_ids, "Duplicate module ID")
                    module_ids.add(module_id)
                    self.assertIsInstance(module.get("plugin"), str)
                    self.assertIsInstance(module.get("model"), str)

                cable_ids: set[int] = set()
                for cable in cables:
                    cable_id = cable.get("id")
                    self.assertIsInstance(cable_id, int)
                    self.assertNotIn(cable_id, cable_ids, "Duplicate cable ID")
                    cable_ids.add(cable_id)
                    for endpoint in ("inputModuleId", "outputModuleId"):
                        self.assertIn(
                            cable.get(endpoint),
                            module_ids,
                            "Cable references a non-existent module",
                        )
                    self.assertIsInstance(cable.get("inputId"), int)
                    self.assertIsInstance(cable.get("outputId"), int)

    def test_declared_submodules_match_gitlinks(self) -> None:
        config = configparser.ConfigParser(interpolation=None)
        config.read(ROOT / ".gitmodules", encoding="utf-8")
        self.assertTrue(config.sections(), "No submodules are declared")

        declared: set[str] = set()
        for section in config.sections():
            with self.subTest(section=section):
                self.assertTrue(section.startswith('submodule "'))
                path = config.get(section, "path")
                url = config.get(section, "url")
                posix = PurePosixPath(path)
                self.assertFalse(posix.is_absolute())
                self.assertNotIn("..", posix.parts)
                self.assertNotIn(path, declared, "Duplicate submodule path")
                declared.add(path)
                self.assertTrue(
                    url.startswith("https://"),
                    "Submodule URL must use HTTPS",
                )

        # A source archive has no Git index. Still validate .gitmodules above.
        if not (ROOT / ".git").exists():
            self.skipTest("Git index unavailable (source archive)")

        output = subprocess.check_output(
            ["git", "ls-files", "--stage", "-z"], cwd=ROOT
        )
        gitlinks: set[str] = set()
        for record in output.split(b"\0"):
            if not record:
                continue
            metadata, path = record.split(b"\t", 1)
            if metadata.split(b" ", 1)[0] == b"160000":
                gitlinks.add(path.decode("utf-8"))

        self.assertEqual(
            declared,
            gitlinks,
            "Declared .gitmodules entries differ from committed gitlinks",
        )


if __name__ == "__main__":
    unittest.main()
