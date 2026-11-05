"""Release asset guards for the non-matrix macOS packaging job."""

from pathlib import Path
import importlib.util
import re
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "build.yml"
VERIFIER = WORKFLOW.parent / "scripts" / "verify-macos-release-payload.py"
MACOS_JOB = re.compile(r"(?ms)^  macos:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)")
spec = importlib.util.spec_from_file_location("macos_release_payload", VERIFIER)
assert spec and spec.loader
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def fat_binary(arches: tuple[int, ...] = (0x01000007, 0x0100000C)) -> bytes:
    """Synthetic universal Mach-O container with bounded slices."""
    start = 8 + 20 * len(arches)
    data = bytearray(struct.pack(">II", 0xCAFEBABE, len(arches)))
    for index, arch in enumerate(arches):
        data.extend(struct.pack(">IIIII", arch, 3, start + index * 32, 32, 0))
    for arch in arches:
        data.extend(struct.pack("<IIIIIIII", 0xFEEDFACF, arch, 3, 8, 0, 0, 0, 0))
    return bytes(data)


def xar_package(names: tuple[str, ...] | None = None, *, broken: str = "") -> bytes:
    if names is None:
        names = tuple(sorted(verifier.PACKAGE_COMPONENTS)) + ("Distribution",)
    xar = ET.Element("xar")
    toc = ET.SubElement(xar, "toc")
    for name in names:
        entry = ET.SubElement(toc, "file")
        ET.SubElement(entry, "name").text = name
        ET.SubElement(entry, "type").text = "file"
        data = ET.SubElement(entry, "data")
        ET.SubElement(data, "offset").text = "0"
        ET.SubElement(data, "length").text = "1" if broken != "zero" else "0"
        ET.SubElement(data, "size").text = "1"
    xml = ET.tostring(xar)
    compressed = zlib.compress(xml)
    header = struct.pack(">IHHQQI", 0x78617221, 28, 1, len(compressed), len(xml), 1)
    return header + compressed + b"P"


class MacosReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        match = MACOS_JOB.search(WORKFLOW.read_text(encoding="utf-8"))
        if match is None:
            raise AssertionError("macos job missing from full-build workflow")
        cls.job = match.group(1)

    def test_release_gate_references_no_nonexistent_matrix_property(self) -> None:
        self.assertNotIn("strategy:\n", self.job)
        self.assertNotIn("matrix.debug", self.job)
        self.assertIn(
            "      - uses: softprops/action-gh-release@v1\n"
            "        if: startsWith(github.ref, 'refs/tags/')\n",
            self.job,
        )

    def test_release_requires_package_and_main_cache_warmup_can_warn(self) -> None:
        upload = self.job.split("      - uses: actions/upload-artifact@v4\n", 1)[1]
        upload = upload.split("      - uses:", 1)[0]
        release = self.job.split("      - uses: softprops/action-gh-release@v1\n", 1)[1]
        self.assertIn(
            "if-no-files-found: ${{ startsWith(github.ref, 'refs/tags/') "
            "&& 'error' || 'warn' }}",
            upload,
        )
        self.assertIn("fail_on_unmatched_files: true", release)
        self.assertIn("${{ github.event.repository.name }}-*.pkg", upload)
        self.assertIn("${{ github.event.repository.name }}-*.pkg", release)

    def test_release_verification_precedes_package_upload(self) -> None:
        self.assertIn(
            "      - name: Verify universal macOS build products\n"
            "        run: python3 -B .github/workflows/scripts/verify-macos-release-payload.py --binaries bin",
            self.job,
        )
        self.assertIn("      - name: Verify macOS installer XAR and component inventory", self.job)
        self.assertIn("--package", self.job)
        self.assertIn("--expected-name", self.job)
        self.assertLess(self.job.index("Verify universal macOS build products"),
                        self.job.index("Build macOS (packaging)"))
        self.assertLess(self.job.index("Verify macOS installer XAR and component inventory"),
                        self.job.index("actions/upload-artifact@v4"))


class MacosReleasePayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.pkg = self.directory / "MODULAR-SYNTH-macOS-universal-abc12345.pkg"

    def test_complete_xar_package_inventory_passes(self) -> None:
        self.pkg.write_bytes(xar_package())
        verifier.verify_package(self.pkg, self.pkg.name)

    def test_wrong_fork_filename_rejected(self) -> None:
        self.pkg.write_bytes(xar_package())
        with self.assertRaisesRegex(verifier.VerificationError, "name"):
            verifier.verify_package(self.pkg, "Cardinal-macOS.pkg")

    def test_missing_component_rejected(self) -> None:
        names = tuple(sorted(verifier.PACKAGE_COMPONENTS - {"dpf-cardinal-clapbundles.pkg"})) + ("Distribution",)
        self.pkg.write_bytes(xar_package(names))
        with self.assertRaisesRegex(verifier.VerificationError, "clapbundles"):
            verifier.verify_package(self.pkg, self.pkg.name)

    def test_empty_or_out_of_bounds_component_rejected(self) -> None:
        self.pkg.write_bytes(xar_package(broken="zero"))
        with self.assertRaisesRegex(verifier.VerificationError, "empty or truncated"):
            verifier.verify_package(self.pkg, self.pkg.name)
        self.pkg.write_bytes(xar_package()[:-1])
        with self.assertRaisesRegex(verifier.VerificationError, "empty or truncated"):
            verifier.verify_package(self.pkg, self.pkg.name)

    def test_non_xar_or_truncated_header_rejected(self) -> None:
        for broken in (b"PK\x03\x04fakezip", b"xar!", b"nope" + xar_package()[4:]):
            with self.subTest(broken=broken[:8]):
                self.pkg.write_bytes(broken)
                with self.assertRaises(verifier.VerificationError):
                    verifier.verify_package(self.pkg, self.pkg.name)

    def test_corrupt_or_truncated_toc_rejected(self) -> None:
        good = xar_package()
        for broken in (good[:28] + b"\x00" * (len(good) - 28),
                       good[:16] + struct.pack(">Q", 200000000) + good[24:],
                       good[:28] + good[28:-10]):
            with self.subTest(length=len(broken)):
                self.pkg.write_bytes(broken)
                with self.assertRaises(verifier.VerificationError):
                    verifier.verify_package(self.pkg, self.pkg.name)

    def test_unsafe_and_ambiguous_xar_names_rejected(self) -> None:
        base = tuple(sorted(verifier.PACKAGE_COMPONENTS)) + ("Distribution",)
        for names in (base + ("Distribution",), base + ("../escape",)):
            with self.subTest(names=names[-1]):
                self.pkg.write_bytes(xar_package(names))
                with self.assertRaises(verifier.VerificationError):
                    verifier.verify_package(self.pkg, self.pkg.name)

    def test_all_expected_bundle_types_have_universal_macho(self) -> None:
        for suffix in verifier.REQUIRED_BUNDLES:
            bundle = self.directory / "bin" / ("Cardinal." + suffix)
            exe = bundle / "Contents" / "MacOS" / "Cardinal"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(fat_binary())
        native = self.directory / "bin" / "CardinalNative.app" / "Contents" / "MacOS" / "CardinalNative"
        native.parent.mkdir(parents=True)
        native.write_bytes(fat_binary())
        verifier.verify_binaries(self.directory / "bin")

    def test_missing_or_thin_bundle_fails(self) -> None:
        for suffix in verifier.REQUIRED_BUNDLES:
            bundle = self.directory / "bin" / ("Cardinal." + suffix)
            exe = bundle / "Contents" / "MacOS" / "Cardinal"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(fat_binary())
        native = self.directory / "bin" / "CardinalNative.app" / "Contents" / "MacOS" / "CardinalNative"
        native.parent.mkdir(parents=True)
        native.write_bytes(fat_binary())
        wrong = self.directory / "bin" / "Cardinal.vst3" / "Contents" / "MacOS" / "Cardinal"
        wrong.write_bytes(fat_binary((0x01000007,)))
        with self.assertRaisesRegex(verifier.VerificationError, "universal"):
            verifier.verify_binaries(self.directory / "bin")
        wrong.write_bytes(fat_binary())
        (self.directory / "bin" / "Cardinal.clap" / "Contents" / "MacOS" / "Cardinal").unlink()
        with self.assertRaisesRegex(verifier.VerificationError, "universal"):
            verifier.verify_binaries(self.directory / "bin")
        (self.directory / "bin" / "Cardinal.clap" / "Contents" / "MacOS" / "Cardinal").write_bytes(fat_binary())
        native.unlink()
        with self.assertRaisesRegex(verifier.VerificationError, "universal"):
            verifier.verify_binaries(self.directory / "bin")

    def test_corrupt_fat_offsets_and_duplicate_arch_rejected(self) -> None:
        mach = self.directory / "Cardinal"
        data = bytearray(fat_binary())
        data[16:20] = struct.pack(">I", 0x7FFFFFFF)
        mach.write_bytes(data)
        self.assertEqual(frozenset(), verifier.mach_arches(mach))
        mach.write_bytes(fat_binary((0x01000007, 0x01000007)))
        self.assertEqual(frozenset(), verifier.mach_arches(mach))
        mach.write_bytes(fat_binary())
        self.assertEqual(verifier.EXPECTED_ARCHES, verifier.mach_arches(mach))

    def test_fat_wrapper_with_non_mach_payload_is_rejected(self) -> None:
        mach = self.directory / "Cardinal"
        data = bytearray(fat_binary())
        data[-64:] = b"X" * 64
        mach.write_bytes(data)
        self.assertEqual(frozenset(), verifier.mach_arches(mach))

    def test_fat_wrapper_with_overlapping_slices_is_rejected(self) -> None:
        mach = self.directory / "Cardinal"
        data = bytearray(fat_binary())
        data[36:40] = data[16:20]  # second slice offset = first
        mach.write_bytes(data)
        self.assertEqual(frozenset(), verifier.mach_arches(mach))


if __name__ == "__main__":
    unittest.main()
