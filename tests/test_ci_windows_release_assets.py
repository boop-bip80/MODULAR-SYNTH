"""Offline regression checks for Windows tag assets and their upload/release paths."""

from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest
import warnings
import zipfile


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
VERIFIER = ROOT / ".github" / "workflows" / "scripts" / "verify-windows-release-artifacts.sh"
WINDOWS_JOB = re.compile(r"(?ms)^  windows:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)")


class WindowsReleaseAssetsTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cwd = Path(temporary.name)

    def verify(self, target: str = "win64", slug: str = "v26.02", repository: str = "MODULAR-SYNTH") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(VERIFIER), repository, target, slug],
            cwd=self.cwd,
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def pe(target: str = "win64", *, dll: bool = False) -> bytes:
        data = bytearray(0x400)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 0x3C, 0x80)
        data[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<H", data, 0x84, 0x14C if target == "win32" else 0x8664)
        struct.pack_into("<H", data, 0x86, 1)  # one section
        struct.pack_into("<H", data, 0x94, 0xE0 if target == "win32" else 0xF0)
        struct.pack_into("<H", data, 0x96, 0x0002 | (0x2000 if dll else 0))
        struct.pack_into("<H", data, 0x98, 0x10B if target == "win32" else 0x20B)
        return bytes(data)

    def stage_release(self, target: str = "win64", *, missing: str = "",
                      overrides: dict[str, bytes] | None = None,
                      additions: dict[str, bytes] | None = None) -> None:
        arch = "x86-win" if target == "win32" else "x86_64-win"
        contents = {
            "LICENSE": b"license fixture",
            "README.md": b"synthetic release fixture",
            "CardinalJACK.exe": self.pe(target),
            "CardinalNative.exe": self.pe(target),
            "Cardinal.clap/CardinalFX.clap": self.pe(target, dll=True),
            "Cardinal.clap/CardinalSynth.clap": self.pe(target, dll=True),
        }
        for module in ("Cardinal", "CardinalFX", "CardinalSynth"):
            contents[f"{module}.lv2/manifest.ttl"] = b"<http://example.invalid/plugin> a <http://lv2plug.in/ns/lv2core#Plugin> ."
            contents[f"{module}.vst3/Contents/{arch}/{module}.vst3"] = self.pe(target, dll=True)
        contents.update(overrides or {})
        contents.update(additions or {})
        contents.pop(missing, None)
        archive = self.cwd / f"MODULAR-SYNTH-{target}-v26.02.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zf:
            for path, data in contents.items():
                zf.writestr(path, data)
        (self.cwd / f"Cardinal-{target}-26.02-installer.exe").write_bytes(self.pe(target))

    def test_release_gate_requires_both_actual_valid_assets(self) -> None:
        self.assertNotEqual(0, self.verify().returncode)
        (self.cwd / "MODULAR-SYNTH-win64-v26.02.zip").write_bytes(b"zip")
        self.assertNotEqual(0, self.verify().returncode)
        (self.cwd / "Cardinal-win64-26.02-installer.exe").write_bytes(b"installer")
        self.assertNotEqual(0, self.verify().returncode)
        self.stage_release()
        self.assertEqual(0, self.verify().returncode, self.verify().stderr)

    def test_release_gate_accepts_each_matching_windows_architecture(self) -> None:
        for target in ("win32", "win64"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                self.cwd = Path(directory)
                self.stage_release(target)
                result = self.verify(target)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("not DAW loadability proof", result.stdout)

    def test_nonrelease_main_sha_slug_must_pass_same_payload_validation(self) -> None:
        """Green main packaging should not bypass tag-quality source gates."""
        for target in ("win32", "win64"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                self.cwd = Path(directory)
                self.stage_release(target)
                source = self.cwd / f"MODULAR-SYNTH-{target}-v26.02.zip"
                source.rename(self.cwd / f"MODULAR-SYNTH-{target}-3e44c84a.zip")
                result = self.verify(target=target, slug="3e44c84a")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("not DAW loadability proof", result.stdout)
                # An architecture-valid installer cannot rescue a broken ZIP.
                (self.cwd / f"MODULAR-SYNTH-{target}-3e44c84a.zip").write_bytes(b"not zip")
                self.assertNotEqual(0, self.verify(target=target, slug="3e44c84a").returncode)

    def test_release_gate_rejects_wrong_ref_target_and_empty_file(self) -> None:
        self.stage_release()
        (self.cwd / "Cardinal-win32-26.02-installer.exe").write_bytes(b"installer")
        self.assertEqual(0, self.verify().returncode)
        (self.cwd / "Cardinal-win64-26.02-installer.exe").unlink()
        self.assertNotEqual(0, self.verify().returncode)
        (self.cwd / "Cardinal-win64-26.02-installer.exe").touch()
        self.assertNotEqual(0, self.verify().returncode)
        (self.cwd / "Cardinal-win64-26.02-installer.exe").write_bytes(self.pe())
        self.assertNotEqual(0, self.verify(slug="different-tag").returncode)
        self.assertNotEqual(0, self.verify(target="win32").returncode)

    def test_release_gate_rejects_ambiguous_installer_or_invalid_arguments(self) -> None:
        self.stage_release()
        (self.cwd / "Cardinal-win64-old-installer.exe").write_bytes(self.pe())
        self.assertNotEqual(0, self.verify().returncode)
        self.assertEqual(2, self.verify(target="linux").returncode)
        self.assertEqual(2, self.verify(repository="bad/repository").returncode)

    def test_release_gate_rejects_missing_plugin_variants(self) -> None:
        for missing in (
            "CardinalJACK.exe", "CardinalNative.exe", "Cardinal.clap/CardinalFX.clap",
            "Cardinal.clap/CardinalSynth.clap", "Cardinal.lv2/manifest.ttl",
            "CardinalFX.lv2/manifest.ttl", "CardinalSynth.lv2/manifest.ttl",
            "CardinalFX.vst3/Contents/x86_64-win/CardinalFX.vst3",
        ):
            with self.subTest(missing=missing):
                self.stage_release(missing=missing)
                result = self.verify()
                self.assertEqual(result.returncode, 1)
                self.assertIn(missing, result.stderr)

    def test_release_gate_rejects_wrong_architecture_and_fake_executables(self) -> None:
        self.stage_release()
        installer = self.cwd / "Cardinal-win64-26.02-installer.exe"
        installer.write_bytes(self.pe("win32"))
        self.assertIn("does not match win64", self.verify().stderr)

        self.stage_release(overrides={"Cardinal.clap/CardinalFX.clap": self.pe("win32")})
        result = self.verify()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Cardinal.clap/CardinalFX.clap", result.stderr)
        self.assertIn("does not match win64", result.stderr)

        self.stage_release(overrides={"CardinalJACK.exe": b"not a Windows executable"})
        self.assertIn("missing DOS/PE", self.verify().stderr)

        minimal = bytearray(self.pe())
        struct.pack_into("<H", minimal, 0x94, 0)  # fake PE signature with no optional header
        self.stage_release(overrides={"CardinalNative.exe": bytes(minimal)})
        self.assertIn("invalid PE section or optional header", self.verify().stderr)

    def test_release_gate_requires_pe_application_versus_plugin_flags(self) -> None:
        self.stage_release(overrides={
            "Cardinal.clap/CardinalFX.clap": self.pe("win64", dll=False),
        })
        result = self.verify()
        self.assertEqual(1, result.returncode)
        self.assertIn("DLL/plugin", result.stderr)

        self.stage_release(overrides={"CardinalJACK.exe": self.pe("win64", dll=True)})
        self.assertIn("application/installer", self.verify().stderr)

        self.stage_release()
        (self.cwd / "Cardinal-win64-26.02-installer.exe").write_bytes(
            self.pe("win64", dll=True))
        self.assertIn("application/installer", self.verify().stderr)

        missing_flag = bytearray(self.pe())
        struct.pack_into("<H", missing_flag, 0x96, 0)
        self.stage_release(overrides={"CardinalNative.exe": bytes(missing_flag)})
        self.assertIn("executable-image flag is missing", self.verify().stderr)

    def test_release_gate_rejects_casefold_ambiguous_windows_paths(self) -> None:
        for path in ("cardinaljack.EXE", "Readme.md", "Cardinal.lv2/MANIFEST.TTL",
                     "cardinal.clap/cardinalfx.clap"):
            with self.subTest(path=path):
                self.stage_release(additions={path: b"ambiguous shadow"})
                result = self.verify()
                self.assertEqual(1, result.returncode)
                self.assertIn("Windows ZIP path collision", result.stderr)

    def test_release_gate_rejects_ntfs_ambiguous_or_reserved_names(self) -> None:
        for path in ("vendor/file.", "vendor/file ", "vendor/CON.txt",
                     "vendor/com1/readme", "vendor/thing\x01.txt"):
            with self.subTest(path=path):
                self.stage_release(additions={path: b"invalid on Windows"})
                result = self.verify()
                self.assertEqual(1, result.returncode)
                self.assertRegex(result.stderr, r"(?:unsafe Windows|reserved Windows) ZIP member")

    def test_release_gate_rejects_file_used_as_parent_directory(self) -> None:
        self.stage_release(additions={
            "vendor/cabinet": b"a file, not a directory",
            "vendor/cabinet/plug.dat": b"nested payload",
        })
        result = self.verify()
        self.assertEqual(1, result.returncode)
        self.assertIn("file/directory collision", result.stderr)

    def test_release_gate_rejects_special_archive_members(self) -> None:
        self.stage_release()
        archive = self.cwd / "MODULAR-SYNTH-win64-v26.02.zip"
        with zipfile.ZipFile(archive, "a") as zf:
            entry = zipfile.ZipInfo("vendor/pipe")
            entry.create_system = 3
            entry.external_attr = (0o010644 << 16)  # Unix named FIFO.
            zf.writestr(entry, b"not a regular payload")
        self.assertIn("special ZIP member", self.verify().stderr)

    def test_release_gate_rejects_inconsistent_directory_metadata(self) -> None:
        self.stage_release()
        archive = self.cwd / "MODULAR-SYNTH-win64-v26.02.zip"
        with zipfile.ZipFile(archive, "a") as zf:
            entry = zipfile.ZipInfo("vendor/looks-regular")
            entry.create_system = 3
            entry.external_attr = (0o040755 << 16)  # Claims directory without '/'.
            zf.writestr(entry, b"not really a directory")
        self.assertIn("inconsistent ZIP directory", self.verify().stderr)

        self.stage_release()
        with zipfile.ZipFile(archive, "a") as zf:
            entry = zipfile.ZipInfo("vendor/invalid-dir/")
            entry.create_system = 3
            entry.external_attr = (0o040755 << 16)
            zf.writestr(entry, b"directory with unexpected file data")
        self.assertIn("inconsistent ZIP directory", self.verify().stderr)

    def test_release_gate_rejects_corrupt_zip_and_unsafe_paths(self) -> None:
        self.stage_release()
        archive = self.cwd / "MODULAR-SYNTH-win64-v26.02.zip"
        contents = archive.read_bytes()
        self.assertIn(b"synthetic release fixture", contents)
        archive.write_bytes(contents.replace(b"synthetic release fixture", b"synthetic RELEASE fixture", 1))
        self.assertIn("CRC/decompression failed", self.verify().stderr)

        self.stage_release(additions={"../outside.exe": self.pe()})
        self.assertIn("unsafe ZIP member", self.verify().stderr)

        self.stage_release(additions={"vendor/./shadow.dat": b"bad path"})
        self.assertIn("unsafe ZIP member", self.verify().stderr)

    def test_release_gate_validates_unlisted_pe_members(self) -> None:
        cases = (
            ("vendor/utility.EXE", self.pe("win32"), "machine"),
            ("vendor/bridge.DLL", self.pe("win32", dll=True), "machine"),
            ("vendor/legacy.clap", b"not a PE binary", "DOS/PE"),
            ("vendor/Extra.vst3", self.pe("win64", dll=False), "DLL/plugin"),
        )
        for name, data, diagnostic in cases:
            with self.subTest(member=name):
                self.stage_release(additions={name: data})
                result = self.verify()
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(name, result.stderr)
                self.assertIn(diagnostic, result.stderr)

        self.stage_release(additions={
            "vendor/utility.EXE": self.pe(),
            "vendor/bridge.DLL": self.pe(dll=True),
            "vendor/legacy.clap": self.pe(dll=True),
            "vendor/Extra.vst3": self.pe(dll=True),
        })
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_release_gate_rejects_duplicate_zip_members(self) -> None:
        self.stage_release()
        archive = self.cwd / "MODULAR-SYNTH-win64-v26.02.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(archive, "a") as zf:
                zf.writestr("CardinalJACK.exe", self.pe())
        self.assertIn("duplicate ZIP member", self.verify().stderr)

    def test_release_gate_rejects_symlink_and_empty_member(self) -> None:
        self.stage_release(overrides={"Cardinal.lv2/manifest.ttl": b""})
        self.assertIn("ZIP member is empty", self.verify().stderr)

        self.stage_release()
        archive = self.cwd / "MODULAR-SYNTH-win64-v26.02.zip"
        with zipfile.ZipFile(archive, "a") as zf:
            entry = zipfile.ZipInfo("vendor/resource")
            entry.create_system = 3  # Unix mode metadata
            entry.external_attr = (0o120777 << 16)  # symlink file type
            zf.writestr(entry, b"../../outside")
        self.assertIn("symlink ZIP member", self.verify().stderr)

    def test_workflow_upload_and_release_match_actual_fork_names(self) -> None:
        match = WINDOWS_JOB.search(WORKFLOW.read_text(encoding="utf-8"))
        self.assertIsNotNone(match, "Windows matrix job missing from full build")
        job = match.group(1)

        self.assertIn("${{ github.event.repository.name }}-${{ matrix.target }}-${{ github.event.pull_request.number || env.SHA8 }}.zip", job)
        self.assertIn("      - name: Verify Windows installer and ZIP before every upload\n        shell: bash", job)
        self.assertIn("bash .github/workflows/scripts/verify-windows-release-artifacts.sh", job)
        # Non-tag/main artifacts must be audited before upload as well; a
        # tag-only if condition would leave historical successful main jobs
        # with no actual ZIP/installer integrity evidence.
        integrity = job.split("      - name: Verify Windows installer and ZIP before every upload\n", 1)[1].split("      - uses: actions/upload-artifact@v4\n", 1)[0]
        self.assertNotRegex(integrity, r"(?m)^\s+if:\s*startsWith\(github\.ref")
        self.assertIn("${{ github.event.pull_request.number || env.SHA8 }}", integrity)
        self.assertLess(job.index("      - name: Pack binaries\n"), job.index("      - name: Verify Windows installer and ZIP before every upload\n"))
        self.assertLess(job.index("      - name: Verify Windows installer and ZIP before every upload\n"), job.index("      - uses: actions/upload-artifact@v4\n"))
        script = VERIFIER.read_text(encoding="utf-8")
        self.assertIn("verify-windows-payload.py", script)
        upload = job.split("      - uses: actions/upload-artifact@v4\n", 1)[1].split("      - uses:", 1)[0]
        release = job.split("      - uses: softprops/action-gh-release@v1\n", 1)[1]
        for step in (upload, release):
            self.assertIn("Cardinal-${{ matrix.target }}-*-installer.exe", step)
            self.assertIn("${{ github.event.repository.name }}-${{ matrix.target }}-*.zip", step)
            self.assertNotIn("Cardinal-*.zip", step)
        self.assertIn("if-no-files-found: ${{ startsWith(github.ref, 'refs/tags/') && 'error' || 'warn' }}", upload)
        self.assertIn("fail_on_unmatched_files: true", release)
        self.assertIn("if: startsWith(github.ref, 'refs/tags/')", release)

    def test_windows_wine_metadata_keeps_default_seccomp_and_stable_host(self) -> None:
        """Older 32-bit Wine needs socketcall, denied by Docker 29.4.2.

        This test guards the temporary runner pin and, importantly, ensures
        the fix cannot silently bypass LV2 metadata generation or security.
        """
        workflow = WORKFLOW.read_text(encoding="utf-8")
        match = WINDOWS_JOB.search(workflow)
        self.assertIsNotNone(match, "Windows cross-build job is required")
        job = match.group(1)

        self.assertIn("    runs-on: ubuntu-24.04\n", job)
        self.assertIn("    container:\n      image: ubuntu:22.04\n", job)
        self.assertIn("target: [win32, win64]", job)
        self.assertIn("xvfb-run make NOOPT=true -j $(nproc)", job)
        self.assertIn("xvfb-run ./utils/create-windows-installer.sh", job)
        self.assertNotIn("seccomp=unconfined", job)
        self.assertNotIn("privileged:", job)
        self.assertNotIn("CROSS_COMPILING=true", job)
        # The original LV2 .ttl generator must still run, not be replaced by
        # an unconditional success or skipped because Wine is unavailable.
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertRegex(makefile, r"(?m)^gen: cardinal resources dpf/utils/lv2_ttl_generator$")
        self.assertIn("@$(CURDIR)/dpf/utils/generate-ttl.sh", makefile)

    def test_installer_source_matches_its_target_specific_release_pattern(self) -> None:
        for target in ("win32", "win64"):
            with self.subTest(target=target):
                installer_script = (ROOT / "utils" / "inno" / f"{target}.iss").read_text(encoding="utf-8")
                self.assertIn(f"OutputBaseFilename=Cardinal-{target}-{{#VERSION}}-installer", installer_script)
        create_installer = (ROOT / "utils" / "create-windows-installer.sh").read_text(encoding="utf-8")
        self.assertIn("mv utils/inno/*.exe .", create_installer)


if __name__ == "__main__":
    unittest.main()
