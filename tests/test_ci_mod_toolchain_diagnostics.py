"""Static safety gate for MOD's uncached crosstool-NG bootstrap diagnostics.

This does not build the MOD target or verify its external source archive.
"""

import re
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")


class ModToolchainDiagnosticsTests(unittest.TestCase):
    def test_diagnostics_run_only_after_failed_uncached_bootstrap(self) -> None:
        job = re.search(
            r"(?ms)^  mod-plugin-builder:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)",
            WORKFLOW,
        )
        self.assertIsNotNone(job)
        section = job.group(1)
        bootstrap = section.index("- name: Bootstrap toolchain")
        diagnostics = section.index("- name: Diagnose failed toolchain bootstrap")
        build = section.index("- name: Build for modaudio")
        self.assertLess(bootstrap, diagnostics)
        self.assertLess(diagnostics, build)
        self.assertIn("id: mpb_bootstrap", section[bootstrap:diagnostics])
        self.assertIn("if: steps.mpb-cache.outputs.cache-hit != 'true'", section)
        self.assertIn(
            "if: ${{ failure() && steps.mpb_bootstrap.outcome == 'failure' }}",
            section[diagnostics:build],
        )
        self.assertNotIn("continue-on-error:", section)

    def test_diagnostic_script_is_bounded_and_bash_syntax_valid(self) -> None:
        step = WORKFLOW.split("      - name: Diagnose failed toolchain bootstrap\n", 1)[1]
        step = step.split("      - name: Build for modaudio\n", 1)[0]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])
        for required in (
            '"$HOME/mod-workdir"',
            '"$GITHUB_WORKSPACE/deps/mod-plugin-builder"',
            "-type f -name build.log -print0",
            "tail -n 200",
            "tail -n 40",
            "grep -Eiv 'token|password|secret|credential|authorization|api[_-]?key|https?://|@'",
            "-name 'gcc-linaro-7.5-2019.12.tar.xz'",
            'xz -t -- "$archive"',
            'tar -tJf "$archive"',
            "exit 0",
        ):
            with self.subTest(required=required):
                self.assertIn(required, script)
        self.assertNotIn("set -x", script)
        self.assertNotIn("cat \"$build_log\"", script)
        result = subprocess.run(
            ["bash", "-n"], input=script, capture_output=True, text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
