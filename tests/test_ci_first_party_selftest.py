"""Adversarial tests for the actual Cardinal first-party runtime inventory gate."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools/ci/verify_first_party_selftest.py"
MANIFEST = REPO / "plugins/ModularSynth/plugin.json"


class FirstPartySelftestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / "selftest.log"
        self.manifest = self.root / "plugin.json"
        self.data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.slugs = [entry["slug"] for entry in self.data["modules"]]
        self.write_manifest()

    def write_manifest(self) -> None:
        self.manifest.write_text(json.dumps(self.data), encoding="utf-8")

    @staticmethod
    def load(slug: str) -> str:
        return f">>>>>>>>>>>>>>>>> LOADING module ModularSynth : {slug}"

    @staticmethod
    def add(slug: str) -> str:
        return f">>>>>>>>>>>>>>>>> ADDING TO ENGINE ModularSynth : {slug}"

    def write_log(self, lines: list[str] | None = None) -> None:
        if lines is None:
            lines = []
            for slug in self.slugs:
                lines.extend((self.load(slug), self.add(slug)))
        self.log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run_gate(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--selftest-log", str(self.log),
             "--manifest", str(self.manifest)],
            text=True, capture_output=True, check=False,
        )

    def assert_failed(self, needle: str) -> None:
        result = self.run_gate()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(needle, result.stderr)

    def test_accepts_full_distinct_runtime_load_and_engine_records(self) -> None:
        records = ["==37== ERROR SUMMARY: 0 errors from 0 contexts (suppressed: 0)"]
        records.extend((">>>>>>>>>>>>>>>>> LOADING module OtherPlugin : External",
                        ">>>>>>>>>>>>>>>>> ADDING TO ENGINE OtherPlugin : External"))
        for slug in self.slugs:
            records.extend((self.load(slug),
                            f">>>>>>>>>>>>>>>>> LOADING moduleWidget ModularSynth : {slug}",
                            self.add(slug)))
        self.write_log(records)
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"all {len(self.slugs)}", result.stdout)

    def test_rejects_missing_unreadable_or_empty_log(self) -> None:
        self.assert_failed("cannot read Cardinal selftest log")
        self.write_log([])
        self.assert_failed("missing module loads")
        self.log.write_bytes(b"\xff\xfe")
        self.assert_failed("cannot read Cardinal selftest log")

    def test_rejects_missing_load_even_when_engine_record_is_present(self) -> None:
        self.write_log()
        self.write_log([line for line in self.log.read_text().splitlines()
                        if line != self.load(self.slugs[0])])
        self.assert_failed("engine insertion before module load")

    def test_rejects_missing_engine_record(self) -> None:
        self.write_log()
        self.write_log([line for line in self.log.read_text().splitlines()
                        if line != self.add(self.slugs[0])])
        self.assert_failed("missing engine insertions")

    def test_rejects_duplicate_load_and_duplicate_engine_record(self) -> None:
        self.write_log()
        self.write_log([*self.log.read_text().splitlines(), self.load(self.slugs[0])])
        self.assert_failed("duplicate module load")
        self.write_log()
        self.write_log([*self.log.read_text().splitlines(), self.add(self.slugs[0])])
        self.assert_failed("duplicate engine insertion")

    def test_rejects_engine_insertion_before_load(self) -> None:
        self.write_log([self.add(self.slugs[0]), self.load(self.slugs[0]),
                        *(line for slug in self.slugs[1:]
                          for line in (self.load(slug), self.add(slug)))])
        self.assert_failed("engine insertion before module load")

    def test_rejects_unexpected_or_misspelled_registered_model(self) -> None:
        self.write_log([self.load("Surprise"), *(
            line for slug in self.slugs for line in (self.load(slug), self.add(slug))
        )])
        self.assert_failed("unexpected ModularSynth runtime slug 'Surprise'")

    def test_rejects_logs_that_only_quote_or_mention_slugs(self) -> None:
        self.write_log([f"LOADING module ModularSynth : {slug}"
                        for slug in self.slugs] +
                       [f">>>>>>>>>> LOADING moduleWidget ModularSynth : {slug}"
                        for slug in self.slugs])
        self.assert_failed("missing module loads")

    def test_rejects_nonzero_valgrind_error_summary_or_assertion_failure(self) -> None:
        self.write_log()
        self.write_log([*self.log.read_text().splitlines(),
                        "==67== ERROR SUMMARY: 1 errors from 1 contexts"])
        self.assert_failed("Valgrind errors")
        self.write_log()
        self.write_log(["FATAL ERROR: assertion failed",
                        *self.log.read_text().splitlines()])
        self.assert_failed("selftest reports a failure")

    def test_requires_current_manifest_and_future_modules(self) -> None:
        self.write_log()
        self.data["modules"].append({"slug": "NewFutureModule"})
        self.write_manifest()
        self.assert_failed("NewFutureModule")
        self.data["modules"].append({"slug": "MorphVCO"})
        self.write_manifest()
        self.assert_failed("duplicate module slugs")


if __name__ == "__main__":
    unittest.main()
