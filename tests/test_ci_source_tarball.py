"""Offline regression coverage for the source-tarball release gate.

These checks validate archive completeness and workflow wiring; they are not
evidence of any completed hosted build or downloadable release.
"""

from pathlib import Path
import io
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/workflows/scripts/verify-source-tarballs.sh"
WORKFLOW = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")
VERSION = re.search(r"(?m)^VERSION = (\S+)$", MAKEFILE).group(1)
ARCHIVES = (f"cardinal-{VERSION}.tar.xz", f"cardinal+deps-{VERSION}.tar.xz")
MANIFEST = json.loads(
    (ROOT / "plugins/ModularSynth/plugin.json").read_text(encoding="utf-8")
)
# Exercise the just-added tenth first-party model even when this isolated CI
# hardening worktree still has the preceding nine-module source manifest.
if not any(module["slug"] == "SlewGlide" for module in MANIFEST["modules"]):
    MANIFEST["modules"].append({"slug": "SlewGlide"})
MODULE_SLUGS = tuple(module["slug"] for module in MANIFEST["modules"])
REQUIRED_FILES = (
    "LICENSE",
    "README.md",
    "Makefile",
    "plugins/ModularSynth/plugin.json",
    "plugins/ModularSynth/src/plugin.hpp",
) + tuple(
    f"plugins/ModularSynth/{directory}/{slug}.{extension}"
    for slug in MODULE_SLUGS
    for directory, extension in (("src", "cpp"), ("src", "hpp"), ("res", "svg"))
)


def source_job() -> str:
    match = re.search(
        r"(?ms)^  source-tarball:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)",
        WORKFLOW,
    )
    if match is None:
        raise AssertionError("Missing source-tarball job")
    return match.group(1)


class SourceReleaseWorkflowTests(unittest.TestCase):
    def test_makefile_contract_and_explicit_archive_gate(self) -> None:
        self.assertIn("tar -c --xz", MAKEFILE)
        self.assertNotIn("tar -c --lzma", MAKEFILE)
        self.assertIn("../cardinal-$(VERSION).tar.xz", MAKEFILE)
        self.assertIn("../cardinal+deps-$(VERSION).tar.xz", MAKEFILE)

        job = source_job()
        create = job.index("- name: Create source tarball")
        verify = job.index("- name: Verify source release archives")
        upload = job.index("- uses: actions/upload-artifact@v4")
        self.assertLess(create, verify)
        self.assertLess(verify, upload)
        self.assertIn(
            "source_version=\"$(awk '$1 == \"VERSION\" && $2 == \"=\" { print $3; exit }' Makefile)\"",
            job,
        )
        self.assertIn(
            'bash .github/workflows/scripts/verify-source-tarballs.sh "$source_version"',
            job,
        )
        self.assertNotIn("make -s version", job)
        checker = SCRIPT.read_text(encoding="utf-8")
        for suffix in ("cardinal-${version}.tar.xz", "cardinal+deps-${version}.tar.xz"):
            self.assertIn(suffix, checker)
        self.assertIn('[[ ! -s "$archive" ]]', checker)
        self.assertIn("fd377a585a00", checker)
        self.assertIn("Source release archive is not an XZ container", checker)
        self.assertIn('tar --xz -tf "$archive"', checker)
        self.assertNotIn("tar --lzma", checker)
        self.assertIn('root="cardinal-${version}"', checker)
        self.assertIn('required["plugins/ModularSynth/src/plugin.hpp"]', checker)
        self.assertGreaterEqual(len(MODULE_SLUGS), 11)
        self.assertIn('module_count = split(module_names, slugs, " ")', checker)
        self.assertIn('-v module_names="$module_slugs"', checker)
        self.assertIn('Path("plugins/ModularSynth/plugin.json")', checker)
        self.assertIn('cmp -s "plugins/ModularSynth/plugin.json"', checker)
        for directory, extension in (("src", "cpp"), ("src", "hpp"), ("res", "svg")):
            with self.subTest(extension=extension):
                self.assertIn(
                    f'required["plugins/ModularSynth/{directory}/" slugs[i] ".{extension}"]',
                    checker,
                )
        self.assertIn("Archive member escapes versioned root", checker)

    def test_tagged_upload_and_release_fail_on_unmatched_files(self) -> None:
        job = source_job()
        upload = job.split("      - uses: actions/upload-artifact@v4\n", 1)[1]
        upload = upload.split("      - uses:", 1)[0]
        release = job.split("      - uses: softprops/action-gh-release@v1\n", 1)[1]
        self.assertIn(
            "if-no-files-found: ${{ startsWith(github.ref, 'refs/tags/') "
            "&& 'error' || 'warn' }}",
            upload,
        )
        self.assertIn("fail_on_unmatched_files: true", release)
        # action-gh-release checks each pattern separately. Three alternative
        # /home/runner glob depths would make a successful release fail.
        patterns = release.split("files: |", 1)[1].splitlines()
        self.assertEqual([p.strip() for p in patterns if p.strip()], [
            "../cardinal*.tar.xz",
        ])

    @unittest.skipUnless(
        shutil.which("tar") and shutil.which("xz") and shutil.which("bash"),
        "GNU tar/XZ/Bash unavailable for archive smoke test",
    )
    def test_validator_accepts_both_valid_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "checkout"
            project.mkdir()
            self._stage_source_members(project)
            self._create_archives(project)
            result = self._run(project, VERSION)
            self.assertEqual(result.returncode, 0, result.stderr)

            for archive in ARCHIVES:
                path = project.parent / archive
                with self.subTest(archive=archive):
                    self.assertEqual(path.read_bytes()[:6], b"\xfd7zXZ\x00")
                    self.assertEqual(
                        subprocess.run(["xz", "-t", str(path)], capture_output=True).returncode,
                        0,
                    )
                    self.assertEqual(
                        subprocess.run(["tar", "-tJf", str(path)], capture_output=True).returncode,
                        0,
                    )

    @unittest.skipUnless(
        shutil.which("tar") and shutil.which("xz") and shutil.which("bash"),
        "GNU tar/XZ/Bash unavailable for codec-compatibility test",
    )
    def test_validator_rejects_legacy_lzma_stream_with_xz_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "checkout"
            project.mkdir()
            self._stage_source_members(project)
            self._create_archives(project)
            wrong_codec = project.parent / ARCHIVES[1]
            # GNU tar's --lzma invocation may still select XZ on modern
            # hosts. Build the legacy LZMA-alone stream explicitly with xz.
            plain_tar = subprocess.run(
                ["tar", f"--transform=s,^\\.,cardinal-{VERSION},",
                 "-cf", "-", "-C", str(project), "."],
                check=True, capture_output=True,
            ).stdout
            legacy_lzma = subprocess.run(
                ["xz", "--format=lzma", "-c"],
                input=plain_tar, check=True, capture_output=True,
            ).stdout
            wrong_codec.write_bytes(legacy_lzma)
            self.assertNotEqual(wrong_codec.read_bytes()[:6], b"\xfd7zXZ\x00")
            self.assertNotEqual(
                subprocess.run(["xz", "-t", "--format=xz", str(wrong_codec)], capture_output=True).returncode,
                0,
            )
            result = self._run(project, VERSION)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not an XZ container", result.stderr)

    @unittest.skipUnless(
        shutil.which("tar") and shutil.which("xz") and shutil.which("bash"),
        "GNU tar/XZ/Bash unavailable for archive smoke test",
    )
    def test_validator_rejects_missing_empty_and_corrupt_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "checkout"
            project.mkdir()
            self._stage_source_members(project)
            self._create_archives(project)
            with_deps = project.parent / ARCHIVES[1]
            with_deps.unlink()
            self.assertNotEqual(self._run(project, VERSION).returncode, 0)

            with_deps.touch()
            self.assertNotEqual(self._run(project, VERSION).returncode, 0)

            with_deps.write_bytes(b"not a compressed tar archive")
            self.assertNotEqual(self._run(project, VERSION).returncode, 0)

    @unittest.skipUnless(
        shutil.which("tar") and shutil.which("xz") and shutil.which("bash"),
        "GNU tar/XZ/Bash unavailable for archive smoke test",
    )
    def test_validator_rejects_missing_first_party_source(self) -> None:
        missing_cases = (
            "plugins/ModularSynth/src/FMVoice.cpp",
            "plugins/ModularSynth/src/StateFilter.hpp",
            "plugins/ModularSynth/res/FMVoice.svg",
            "plugins/ModularSynth/src/SlewGlide.cpp",
            "plugins/ModularSynth/src/DualVCA.hpp",
        )
        for missing in missing_cases:
            with self.subTest(missing=missing):
                with tempfile.TemporaryDirectory() as temp:
                    project = Path(temp) / "checkout"
                    project.mkdir()
                    self._stage_source_members(project)
                    (project / missing).unlink()
                    self._create_archives(project)
                    result = self._run(project, VERSION)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("missing required member", result.stderr)
                    self.assertIn(missing, result.stderr)

    @unittest.skipUnless(
        shutil.which("tar") and shutil.which("xz") and shutil.which("bash"),
        "GNU tar/XZ/Bash unavailable for archive smoke test",
    )
    def test_validator_requires_new_manifest_module_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "checkout"
            project.mkdir()
            self._stage_source_members(project)
            manifest_file = project / "plugins/ModularSynth/plugin.json"
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest["modules"].append({"slug": "FutureUtility"})
            manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
            # New module was declared but none of its three source files exist.
            self._create_archives(project)
            result = self._run(project, VERSION)
            self.assertNotEqual(result.returncode, 0)
            for name in ("src/FutureUtility.cpp", "src/FutureUtility.hpp",
                         "res/FutureUtility.svg"):
                self.assertIn(name, result.stderr)

    @unittest.skipUnless(
        shutil.which("tar") and shutil.which("xz") and shutil.which("bash"),
        "GNU tar/XZ/Bash unavailable for archive smoke test",
    )
    def test_validator_rejects_stale_archive_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "checkout"
            project.mkdir()
            self._stage_source_members(project)
            self._create_archives(project)
            # The archived manifest is now stale even though filenames match.
            changed = (project / "plugins/ModularSynth/plugin.json")
            manifest = json.loads(changed.read_text(encoding="utf-8"))
            manifest["version"] = "stale-source-checkout"
            changed.write_text(json.dumps(manifest), encoding="utf-8")
            result = self._run(project, VERSION)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("manifest differs", result.stderr)

    @unittest.skipUnless(
        shutil.which("tar") and shutil.which("xz") and shutil.which("bash"),
        "GNU tar/XZ/Bash unavailable for archive smoke test",
    )
    def test_validator_rejects_wrong_archive_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "checkout"
            project.mkdir()
            self._stage_source_members(project)
            self._create_archives(project, archive_root="cardinal-old")
            result = self._run(project, VERSION)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("escapes versioned root", result.stderr)

    @unittest.skipUnless(
        shutil.which("tar") and shutil.which("xz") and shutil.which("bash"),
        "GNU tar/XZ/Bash unavailable for archive smoke test",
    )
    def test_validator_rejects_duplicate_archive_member(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "checkout"
            project.mkdir()
            self._stage_source_members(project)
            self._create_archives(project)
            duplicate = tarfile.TarInfo(f"cardinal-{VERSION}/README.md")
            self._append_archive_member(project.parent / ARCHIVES[0], duplicate)
            result = self._run(project, VERSION)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Duplicate archive member path", result.stderr)

    @unittest.skipUnless(
        shutil.which("tar") and shutil.which("xz") and shutil.which("bash"),
        "GNU tar/XZ/Bash unavailable for archive smoke test",
    )
    def test_validator_rejects_escaping_archive_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "checkout"
            project.mkdir()
            self._stage_source_members(project)
            self._create_archives(project)
            link = tarfile.TarInfo(f"cardinal-{VERSION}/plugins/ModularSynth/escape")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../../outside-release"
            self._append_archive_member(project.parent / ARCHIVES[1], link)
            result = self._run(project, VERSION)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Archive symlink escapes versioned root", result.stderr)

    def test_validator_rejects_path_like_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            result = self._run(project, "../untrusted")
            self.assertEqual(result.returncode, 2)

    @staticmethod
    def _run(project: Path, version: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), version],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def _stage_source_members(project: Path) -> None:
        for name in REQUIRED_FILES:
            destination = project / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if name == "plugins/ModularSynth/plugin.json":
                destination.write_text(json.dumps(MANIFEST), encoding="utf-8")
            else:
                destination.write_text(f"source placeholder: {name}", encoding="utf-8")

    @staticmethod
    def _append_archive_member(archive: Path, extra: tarfile.TarInfo) -> None:
        # Repack a synthetic fixture while preserving each original tar header.
        with tarfile.open(archive, "r:xz") as source:
            members = [
                (member, source.extractfile(member).read() if member.isfile() else None)
                for member in source
            ]
        with tarfile.open(archive, "w:xz") as output:
            for member, content in members:
                output.addfile(member, io.BytesIO(content) if content is not None else None)
            if extra.isfile():
                payload = b"duplicate fixture"
                extra.size = len(payload)
                output.addfile(extra, io.BytesIO(payload))
            else:
                output.addfile(extra)

    @staticmethod
    def _create_archives(project: Path, archive_root: str | None = None) -> None:
        prefix = archive_root or f"cardinal-{VERSION}"
        for archive in ARCHIVES:
            subprocess.run(
                [
                    "tar", "--xz", f"--transform=s,^\\.,{prefix},",
                    "-cf", str(project.parent / archive),
                    "-C", str(project), ".",
                ],
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()
