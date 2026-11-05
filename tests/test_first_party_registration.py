"""Consistency gates for the MODULAR-SYNTH first-party static collection.

These tests deliberately inspect only the ModularSynth collection, never the
upstream Cardinal or third-party plugin registrations. They do not compile C++.
"""
from __future__ import annotations

import collections
import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COLLECTION = REPO / "plugins" / "ModularSynth"
EXPECTED_ORIGINAL_MODULES = frozenset({"MorphVCO", "StateFilter", "Macro8", "StereoEcho", "ClockedLFO", "FMVoice", "FoldDrive", "ChanceHold", "DualVCA", "SlewGlide"})

# Strings are consumed as one token so // inside URLs does not become a comment.
CPP_TOKEN = re.compile(
    r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|'
    r"'(?:\\.|[^'\\])*'"
)


def mask_cpp_noncode(source: str, *, mask_strings: bool) -> str:
    """Preserve lengths/newlines while suppressing C++ comments, then strings.

    This is scoped to simple model registration functions; it is not a full
    C++ parser and must never be used to certify arbitrary C++ correctness.
    """
    def mask(match: re.Match[str]) -> str:
        token = match.group(0)
        is_comment = token.startswith("//") or token.startswith("/*")
        if not is_comment and not mask_strings:
            return token
        return "".join("\n" if ch == "\n" else " " for ch in token)

    return CPP_TOKEN.sub(mask, source)


def function_body(source: str, name: str) -> str:
    """Extract the single named C++ void function, balancing noncomment braces."""
    shadow = mask_cpp_noncode(source, mask_strings=True)
    signatures = list(re.finditer(
        rf'(?m)^[ \t]*(?:static[ \t]+)?void[ \t]+'
        rf'{re.escape(name)}[ \t]*\([ \t]*\)[ \t\r\n]*\{{',
        shadow))
    if len(signatures) != 1:
        raise AssertionError(
            f"expected exactly one {name}() definition, found {len(signatures)}")
    opening = signatures[0].end() - 1
    depth = 0
    for i in range(opening, len(shadow)):
        if shadow[i] == "{":
            depth += 1
        elif shadow[i] == "}":
            depth -= 1
            if depth == 0:
                return mask_cpp_noncode(
                    source[opening + 1:i], mask_strings=False)
    raise AssertionError(f"unterminated {name}() C++ function")


def model_definition_symbols(source: str, slug: str) -> list[str]:
    """Match exported Model pointer definitions wired to a particular Rack slug.

    The multiline regex is constrained to one createModel expression and an
    explicit string slug. Comments are already masked before this call.
    """
    pattern = re.compile(
        rf'(?m)^[ \t]*(?:rack::)?Model[ \t]*\*[ \t]*'
        rf'(model[A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t\r\n]*'
        rf'createModel[ \t\r\n]*<[^;>]+>[ \t\r\n]*'
        rf'\([ \t\r\n]*"{re.escape(slug)}"[ \t\r\n]*\)[ \t\r\n]*;')
    return pattern.findall(source)


def lines_matching(pattern: str, source: str) -> list[str]:
    return re.findall(pattern, mask_cpp_noncode(source, mask_strings=False),
                      flags=re.MULTILINE)


class FirstPartyRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(
            (COLLECTION / "plugin.json").read_text(encoding="utf-8"))
        cls.makefile = (REPO / "plugins" / "Makefile").read_text(encoding="utf-8")
        cls.header = (COLLECTION / "src" / "plugin.hpp").read_text(encoding="utf-8")
        cls.loader_source = (
            REPO / "plugins" / "plugins.cpp").read_text(encoding="utf-8")
        cls.mini_source = (
            REPO / "plugins" / "plugins-mini.cpp").read_text(encoding="utf-8")
        cls.loader_body = function_body(cls.loader_source, "initStatic__ModularSynth")
        cls.init_body = function_body(cls.loader_source, "initStaticPlugins")
        cls.entries = cls.manifest.get("modules")

    def test_collection_manifest_identity_and_unique_slugs(self):
        self.assertEqual(self.manifest.get("slug"), "ModularSynth")
        self.assertIsInstance(self.entries, list)
        self.assertTrue(self.entries, "first-party collection must not be empty")
        slugs = []
        for entry in self.entries:
            with self.subTest(entry=entry):
                self.assertIsInstance(entry, dict)
                slug = entry.get("slug")
                self.assertRegex(slug, r"^[A-Z][A-Za-z0-9]{1,39}$")
                self.assertIsInstance(entry.get("name"), str)
                self.assertTrue(entry["name"].strip())
                self.assertIsInstance(entry.get("tags"), list)
                slugs.append(slug)
        self.assertEqual(
            len({slug.casefold() for slug in slugs}), len(slugs),
            "duplicate or case-insensitively colliding module slugs")
        self.assertTrue(EXPECTED_ORIGINAL_MODULES.issubset(slugs),
                        "one of the original first-party modules is missing")

    def test_compiled_sources_match_manifest(self):
        compiled = lines_matching(
            r"^[ \t]*PLUGIN_FILES[ \t]*\+=[ \t]*"
            r"ModularSynth/src/([A-Za-z][A-Za-z0-9]*)\.cpp[ \t]*$",
            self.makefile)
        counts = collections.Counter(compiled)
        slugs = [entry["slug"] for entry in self.entries]
        for slug in slugs:
            with self.subTest(slug=slug):
                self.assertEqual(counts[slug], 1,
                                 f"expected exactly one compiled source for {slug}")
                self.assertTrue((COLLECTION / "src" / f"{slug}.cpp").is_file())
        self.assertIn(
            "-DpluginInstance=pluginInstance__ModularSynth", self.makefile,
            "first-party sources must resolve the first-party pluginInstance")

    def test_model_definitions_headers_and_loader_exactly_once(self):
        manifest_symbols = []
        for entry in self.entries:
            slug = entry["slug"]
            with self.subTest(slug=slug):
                source = (COLLECTION / "src" / f"{slug}.cpp").read_text(
                    encoding="utf-8")
                code = mask_cpp_noncode(source, mask_strings=False)
                self.assertIn('#include "plugin.hpp"', code)
                defined = model_definition_symbols(code, slug)
                self.assertEqual(
                    len(defined), 1,
                    f"{slug} must define exactly one Model* createModel(..., slug)")
                symbol = defined[0]
                manifest_symbols.append(symbol)
                declarations = lines_matching(
                    rf'^[ \t]*extern[ \t]+(?:rack::)?Model[ \t]*\*[ \t]*'
                    rf'({re.escape(symbol)})[ \t]*;',
                    self.header)
                self.assertEqual(
                    len(declarations), 1,
                    f"missing or duplicated header declaration for {symbol}")
                registrations = lines_matching(
                    rf'\bp[ \t]*->[ \t]*addModel[ \t]*\([ \t]*'
                    rf'({re.escape(symbol)})[ \t]*\)[ \t]*;',
                    self.loader_body)
                self.assertEqual(
                    len(registrations), 1,
                    f"missing or duplicated initStatic__ModularSynth() entry for {symbol}")
        self.assertEqual(
            len(set(manifest_symbols)), len(manifest_symbols),
            "two module slugs export the same C++ model symbol")
        all_registrations = lines_matching(
            r'\bp[ \t]*->[ \t]*addModel[ \t]*\([ \t]*'
            r'(model[A-Za-z_][A-Za-z0-9_]*)[ \t]*\)[ \t]*;',
            self.loader_body)
        self.assertEqual(
            collections.Counter(all_registrations),
            collections.Counter(manifest_symbols),
            "static loader contains a model not represented by the manifest")

    def test_module_svg_resources_exist_and_are_referenced(self):
        for entry in self.entries:
            slug = entry["slug"]
            with self.subTest(slug=slug):
                panel_path = COLLECTION / "res" / f"{slug}.svg"
                self.assertTrue(panel_path.is_file(), f"missing {panel_path}")
                ET.parse(panel_path)
                source = mask_cpp_noncode(
                    (COLLECTION / "src" / f"{slug}.cpp").read_text(
                        encoding="utf-8"),
                    mask_strings=False)
                self.assertIn(
                    f'"res/{slug}.svg"', source,
                    f"{slug} source has no exact first-party panel reference")

    def test_collection_loader_is_invoked_once_and_not_mini_only(self):
        init_calls = lines_matching(
            r'\b(initStatic__ModularSynth)[ \t]*\([ \t]*\)[ \t]*;',
            self.init_body)
        self.assertEqual(
            len(init_calls), 1,
            "ModularSynth plugin collection is not initialized exactly once")
        mini_sources = lines_matching(
            r"^[ \t]*MINIPLUGIN_FILES[ \t]*\+=[ \t]*"
            r"ModularSynth/src/([A-Za-z][A-Za-z0-9]*)\.cpp[ \t]*$",
            self.makefile)
        self.assertEqual(mini_sources, [],
                         "mini sources added without a reviewed mini loader")
        mini_code = mask_cpp_noncode(self.mini_source, mask_strings=False)
        self.assertNotIn('ModularSynth/src/plugin.hpp', mini_code)
        self.assertNotIn("initStatic__ModularSynth", mini_code)
        self.assertNotIn("pluginInstance__ModularSynth", mini_code)


class ParserSafetyTests(unittest.TestCase):
    def test_function_scope_skips_comments_and_string_braces(self):
        source = (
            '// static void initStatic__ModularSynth() { fake(); }\n'
            'static void initStatic__ModularSynth() {\n'
            '    const char* text = "a brace } in a string";\n'
            '    if (true) { p->addModel(modelReal); }\n'
            '}\n'
            'static void another() { p->addModel(modelOther); }\n'
        )
        body = function_body(source, "initStatic__ModularSynth")
        self.assertIn("p->addModel(modelReal)", body)
        self.assertNotIn("modelOther", body)

    def test_commented_model_definitions_do_not_count(self):
        source = (
            '// Model* modelFake = createModel<A, B>("OrbitSine");\n'
            'Model* modelReal =\n'
            '    createModel<OrbitModule, OrbitWidget>("OrbitSine");\n'
        )
        clean = mask_cpp_noncode(source, mask_strings=False)
        self.assertEqual(model_definition_symbols(clean, "OrbitSine"),
                         ["modelReal"])


if __name__ == "__main__":
    unittest.main()
