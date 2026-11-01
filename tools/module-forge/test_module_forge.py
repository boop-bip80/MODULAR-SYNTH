"""Standard-library tests for the Module Forge generator."""
import json
import tempfile
import unittest
from pathlib import Path

from module_forge import check_module, generate, render_files, validate_slug


class ModuleForgeTests(unittest.TestCase):
    def test_generate_and_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = generate("OrbitSine", "Orbit Sine", Path(tmp))
            self.assertEqual(check_module(destination), [])
            manifest = json.loads((destination / "OrbitSine.module.json").read_text())
            self.assertEqual(manifest["slug"], "MFOrbitSine")
            self.assertIn("Oscillator", manifest["tags"])
            source = (destination / "OrbitSine.cpp").read_text()
            self.assertIn("std::clamp(pitch", source)
            self.assertIn("setChannels(voices)", source)
            self.assertIn("phase[voice]", source)

    def test_reject_invalid_identifiers(self):
        for slug in ("../outside", "bad-name", "1bad", "S", "aBad", "Name/Other"):
            with self.subTest(slug=slug):
                with self.assertRaises(ValueError):
                    validate_slug(slug)

    def test_reject_unsafe_display_name(self):
        with self.assertRaises(ValueError):
            render_files("SafeSlug", '<script>alert("x")</script>')
        with self.assertRaises(ValueError):
            render_files("SafeSlug", "contains\nnewline")

    def test_refuse_to_overwrite_existing_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = generate("MyModule", "My Module", Path(tmp))
            source = destination / "MyModule.cpp"
            source.write_text("user edits", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                generate("MyModule", "My Module", Path(tmp))
            self.assertEqual(source.read_text(), "user edits")

    def test_detect_manifest_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = generate("SafeModule", "Safe Module", Path(tmp))
            path = destination / "SafeModule.module.json"
            manifest = json.loads(path.read_text())
            manifest["slug"] = "Wrong"
            path.write_text(json.dumps(manifest))
            self.assertTrue(any("manifest slug" in error
                                for error in check_module(destination)))

    def test_detect_missing_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = generate("SafeModule", "Safe Module", Path(tmp))
            (destination / "SafeModule.svg").unlink()
            self.assertTrue(any("missing SafeModule.svg" in error
                                for error in check_module(destination)))

    def test_detect_changed_model_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = generate("SafeModule", "Safe Module", Path(tmp))
            source_path = destination / "SafeModule.cpp"
            source = source_path.read_text().replace(
                '"MFSafeModule")', '"NotTheModel")'
            )
            source_path.write_text(source)
            self.assertTrue(any("registration" in error
                                for error in check_module(destination)))


if __name__ == "__main__":
    unittest.main()
