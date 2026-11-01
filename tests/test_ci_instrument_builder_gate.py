"""Keep Instrument Builder's independent unittest suite in the fast CI gate."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "quality-baseline.yml"
COMMAND = (
    "run: python3 -B -m unittest discover -s tools/instrument-builder "
    "-p 'test_*.py' -v"
)


class InstrumentBuilderQualityGateTests(unittest.TestCase):
    def test_source_quality_runs_discovered_builder_tests_once(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: Test Instrument Builder bundles and control mappings", workflow)
        self.assertEqual(workflow.count(COMMAND), 1)


if __name__ == "__main__":
    unittest.main()
