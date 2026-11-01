"""Source-level gate for first-party Rack polyphony lane retirement.

The production wrappers cannot be compiled by this test: the full Cardinal
submodule/header tree is not present in a source-only checkout. These checks
verify the local reset wiring, while standalone C++ DSP tests exercise each
core's reset semantics independently; they are not host integration evidence.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


SOURCES = Path(__file__).resolve().parents[1] / "plugins" / "ModularSynth" / "src"
RETIRING_MODULES = ("MorphVCO", "StateFilter")


def method_body(source: str, signature: str) -> str:
    """Return one concrete wrapper method's brace-delimited body."""
    found = re.search(signature, source)
    if not found:
        raise AssertionError(f"wrapper method absent: {signature}")
    brace = source.find("{", found.end())
    if brace < 0:
        raise AssertionError("wrapper method has no body")
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1:index]
    raise AssertionError("unbalanced wrapper method body")


class PolyphonyRetirementTests(unittest.TestCase):
    def test_expired_oscillator_and_filter_lanes_reset_before_output(self):
        retirement = re.compile(
            r"for\s*\(\s*int\s+c\s*=\s*channels\s*;\s*"
            r"c\s*<\s*previousChannels\s*;\s*\+\+c\s*\)\s*"
            r"voices\s*\[\s*c\s*\]\.reset\s*\(\s*\)\s*;\s*"
            r"previousChannels\s*=\s*channels\s*;"
        )
        for module in RETIRING_MODULES:
            with self.subTest(module=module):
                source = (SOURCES / f"{module}.cpp").read_text(encoding="utf-8")
                self.assertRegex(source, r"\bint\s+previousChannels\s*=\s*0\s*;")
                reset = method_body(source, r"\bvoid\s+onReset\s*\(\s*\)\s*override")
                self.assertRegex(reset, r"\bpreviousChannels\s*=\s*0\s*;")

                process = method_body(source, r"\bvoid\s+process\s*\(\s*const\s+ProcessArgs&\s+args\s*\)\s*override")
                match = retirement.search(process)
                self.assertIsNotNone(match, "retired lanes must reset and update the previous count")
                self.assertLess(
                    process.index("channels = std::min(channels, 16);"),
                    match.start(),
                    "retirement must happen after the Rack channel cap",
                )
                first_output = process.index("].setChannels(channels);")
                self.assertLess(
                    match.end(), first_output,
                    "retired lanes must reset before the wrapper publishes output channels",
                )


if __name__ == "__main__":
    unittest.main()
