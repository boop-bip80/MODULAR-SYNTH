"""Regression checks for cold-cache builds and release asset integrity.

These checks use source text only; they do not execute a hosted build, sign a
package, or verify installation in a DAW.
"""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
MACOS_INSTALLER = (ROOT / "utils/create-macos-installer.sh").read_text(encoding="utf-8")


def job_block(name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)",
        WORKFLOW,
    )
    if match is None:
        raise AssertionError(f"Missing workflow job: {name}")
    return match.group(1)


def named_step(job: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^      - name: {re.escape(name)}\n(.*?)(?=^      - |\Z)",
        job_block(job),
    )
    if match is None:
        raise AssertionError(f"Missing step {name} in {job}")
    return match.group(1)


class ColdCacheBuildTests(unittest.TestCase):
    def test_production_build_and_packaging_steps_run_on_cache_misses(self) -> None:
        essential_steps = {
            "macos": (
                "Build macOS (base)", "Build macOS (packaging)", "Rename macOS bundle",
            ),
            "mod-plugin-builder": ("Build for modaudio", "Pack binaries"),
            "wasm": (
                "Build wasm cross-compiled", "Build modgui",
                "Make wasm versioned and compress", "Pack binaries",
            ),
            "windows": (
                "Build cross-compiled (base)", "Build cross-compiled (carla)",
                "Build cross-compiled (packaging)", "Pack binaries",
            ),
        }
        for job, steps in essential_steps.items():
            for name in steps:
                with self.subTest(job=job, name=name):
                    body = named_step(job, name)
                    self.assertNotRegex(
                        body,
                        r"(?m)^        if: steps\.(?:cache|mpb-cache)\.outputs\.cache-hit == 'true'$",
                    )

    def test_cold_cache_bootstraps_are_still_configured(self) -> None:
        self.assertIn(
            "if: steps.mpb-cache.outputs.cache-hit != 'true'",
            named_step("mod-plugin-builder", "Bootstrap toolchain"),
        )
        for job in ("macos", "wasm", "windows"):
            self.assertIn("bootstrap-cardinal.sh", named_step(job, "Build extra dependencies"))

    def test_macos_packager_name_matches_rename_source(self) -> None:
        self.assertIn("\n  Cardinal-macOS.pkg\n", MACOS_INSTALLER)
        rename = named_step("macos", "Rename macOS bundle")
        self.assertIn("test -s Cardinal-macOS.pkg", rename)
        self.assertIn("mv Cardinal-macOS.pkg", rename)
        self.assertIn(
            "${{ github.event.repository.name }}-macOS-universal-",
            rename,
        )
        self.assertNotIn(
            "mv ${{ github.event.repository.name }}-macOS.pkg",
            rename,
        )

    def test_linux_and_wasm_release_assets_fail_closed(self) -> None:
        for job in ("linux", "wasm"):
            with self.subTest(job=job):
                body = job_block(job)
                upload = re.search(
                    r"(?ms)^      - uses: actions/upload-artifact@v4\n(.*?)(?=^      - |\Z)",
                    body,
                )
                release = re.search(
                    r"(?ms)^      - uses: softprops/action-gh-release@v1\n(.*?)(?=^      - |\Z)",
                    body,
                )
                self.assertIsNotNone(upload)
                self.assertIsNotNone(release)
                self.assertIn(
                    "if-no-files-found: ${{ startsWith(github.ref, 'refs/tags/') && 'error' || 'warn' }}",
                    upload.group(1),
                )
                self.assertIn("fail_on_unmatched_files: true", release.group(1))


if __name__ == "__main__":
    unittest.main()
