"""Keep the first-party symbol collision guard in the actual WASM build job.

The workflow has several similarly named checkout/cache steps. This regression
test makes sure the guard cannot silently move to an unrelated job, where it
would fail to protect the hours-long Emscripten link.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/build.yml"
PREFLIGHT = "Preflight first-party model symbol collisions"
COMMANDS = (
    "python3 -B -m unittest discover -s tests -p 'test_first_party_registration.py' -v",
    "python3 -B -m unittest discover -s tests -p 'test_real_rack_headers.py' -v",
)


def job_text(workflow: str, name: str) -> str:
    """Extract a top-level Actions job without requiring a YAML dependency."""
    start = re.search(rf"(?m)^  {re.escape(name)}:\s*$", workflow)
    if start is None:
        raise AssertionError(f"missing job {name!r}")
    following = re.search(r"(?m)^  [a-zA-Z0-9_-]+:\s*$", workflow[start.end():])
    end = start.end() + following.start() if following else len(workflow)
    return workflow[start.start():end]


class WasmSymbolPreflightWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.wasm = job_text(cls.workflow, "wasm")

    def test_preflight_is_only_in_wasm_matrix_job(self) -> None:
        pattern = rf"(?m)^      - name: {re.escape(PREFLIGHT)}\s*$"
        self.assertEqual(len(re.findall(pattern, self.workflow)), 1)
        self.assertRegex(self.wasm, pattern)
        self.assertIn("target: [simd, nosimd]", self.wasm)
        self.assertNotIn(PREFLIGHT, job_text(self.workflow, "macos"))

    def test_preflight_is_between_recursive_checkout_and_cache(self) -> None:
        checkout = self.wasm.index("      - name: Complete pinned recursive submodule checkout (retry)")
        preflight = self.wasm.index(f"      - name: {PREFLIGHT}")
        cache = self.wasm.index("      - name: Set up cache")
        self.assertLess(checkout, preflight)
        self.assertLess(preflight, cache)
        step = self.wasm[preflight:cache]
        self.assertIn("        shell: bash", step)
        self.assertIn("        run: |", step)
        for command in COMMANDS:
            with self.subTest(command=command):
                self.assertIn(f"          {command}\n", step)


if __name__ == "__main__":
    unittest.main()
