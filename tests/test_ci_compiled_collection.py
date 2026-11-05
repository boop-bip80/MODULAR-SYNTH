"""ELF inventory gate tests with synthetic adversarial and linked C fixtures.

These fixtures are not compiled Cardinal objects or host-loadability evidence.
"""
from __future__ import annotations

import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools/ci/verify_compiled_collection.py"
MANIFEST = REPO / "plugins/ModularSynth/plugin.json"
WORKFLOW = (REPO / ".github/workflows/build.yml").read_text(encoding="utf-8")


class CompiledFirstPartyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "Cardinal"
        self.manifest = self.root / "plugin.json"
        self.data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        # This source-hardening branch was cut before the independently built
        # SlewGlide module landed. Validate the new ten-module release contract
        # with the same fixture both before and after integration.
        if not any(entry.get("slug") == "SlewGlide"
                   for entry in self.data["modules"]):
            self.data["modules"].append({"slug": "SlewGlide"})
        self.write_manifest()

    def write_manifest(self) -> None:
        self.manifest.write_text(json.dumps(self.data), encoding="utf-8")

    def write_image(self, *, markers: tuple[str, ...] | None = None,
                    header: bytes | None = None,
                    trailer_markers: tuple[str, ...] = (),
                    load_flags: int = 4,
                    section_type: int | None = None,
                    section_flags: int = 2) -> None:
        marker_names = markers if markers is not None else (
            "ModularSynth",
            *(entry["slug"] for entry in self.data["modules"]),
        )
        # Minimal synthetic ELF64 with a file-backed PT_LOAD segment at 0x100.
        # It is deliberately not guaranteed to load or execute in the OS.
        mapped = b"\0".join(m.encode("ascii") for m in marker_names) + b"\0"
        elf = bytearray(0x100 + len(mapped))
        elf[:7] = b"\x7fELF\x02\x01\x01"
        struct.pack_into("<HHI", elf, 16, 3, 62, 1)  # ET_DYN, EM_X86_64, v1
        struct.pack_into("<Q", elf, 32, 64)  # program header offset
        struct.pack_into("<HHH", elf, 52, 64, 56, 1)  # EHDR, PHDR sizes/count
        struct.pack_into("<IIQQQQQQ", elf, 64,
                         1, load_flags, 0x100, 0x100, 0, len(mapped), len(mapped), 0x1000)
        elf[0x100:] = mapped
        if section_type is not None:
            # Optional real-style section table: SHT_NULL plus a marker-bearing
            # section inside the PT_LOAD range. The section table is unmapped.
            section_table = len(elf)
            elf.extend(b"\0" * 128)
            struct.pack_into("<Q", elf, 40, section_table)  # e_shoff
            struct.pack_into("<HHH", elf, 58, 64, 2, 0)
            struct.pack_into("<IIQQQQIIQQ", elf, section_table + 64,
                             0, section_type, section_flags, 0x100, 0x100,
                             len(mapped), 0, 0, 1, 0)
        if header is not None:
            elf[:len(header)] = header
        if trailer_markers:
            elf += b"\0".join(m.encode("ascii") for m in trailer_markers) + b"\0"
        self.binary.write_bytes(elf)

    def run_gate(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--binary", str(self.binary),
             "--manifest", str(self.manifest)],
            text=True, capture_output=True, check=False,
        )

    def test_accepts_current_manifest_marker_inventory(self) -> None:
        self.write_image()
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not proof of model registration or host loadability", result.stdout)

    def test_rejects_missing_original_or_new_manifest_identifier(self) -> None:
        markers = ("ModularSynth", *(
            entry["slug"] for entry in self.data["modules"][:-1]
        ))
        self.write_image(markers=markers)
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn(self.data["modules"][-1]["slug"], result.stderr)
        # A future module is required automatically, with no hand-edited list.
        self.data["modules"].append({"slug": "NewFutureModule"})
        self.write_manifest()
        self.write_image(markers=("ModularSynth", *(
            entry["slug"] for entry in self.data["modules"][:-1]
        )))
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("NewFutureModule", result.stderr)

    def test_rejects_missing_or_non_elf_or_unlinked_object(self) -> None:
        self.assertEqual(self.run_gate().returncode, 1)
        self.write_image(header=b"not an ELF")
        self.assertEqual(self.run_gate().returncode, 1)
        self.write_image()
        payload = bytearray(self.binary.read_bytes())
        payload[16:18] = (1).to_bytes(2, "little")  # ET_REL object, not linked
        self.binary.write_bytes(payload)
        self.assertEqual(self.run_gate().returncode, 1)

    def test_rejects_strings_appended_outside_runtime_load_segments(self) -> None:
        missing = self.data["modules"][-1]["slug"]
        self.write_image(
            markers=("ModularSynth", *(entry["slug"] for entry in self.data["modules"][:-1])),
            trailer_markers=(missing,),
        )
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn(missing, result.stderr)

    def test_rejects_missing_or_out_of_bounds_elf_program_headers(self) -> None:
        self.write_image()
        payload = bytearray(self.binary.read_bytes())
        struct.pack_into("<H", payload, 56, 0)  # e_phnum
        self.binary.write_bytes(payload)
        self.assertIn("program header table", self.run_gate().stderr)
        self.write_image()
        payload = bytearray(self.binary.read_bytes())
        struct.pack_into("<Q", payload, 64 + 32, len(payload) + 1)  # p_filesz
        self.binary.write_bytes(payload)
        self.assertIn("load segment", self.run_gate().stderr)

    def test_rejects_model_strings_in_nonloadable_segment(self) -> None:
        self.write_image()
        payload = bytearray(self.binary.read_bytes())
        struct.pack_into("<I", payload, 64, 4)  # PT_NOTE, not PT_LOAD
        self.binary.write_bytes(payload)
        self.assertIn("no file-backed load segments", self.run_gate().stderr)

    def test_rejects_marker_suffix_of_unrelated_identifier(self) -> None:
        self.write_image(markers=(
            "NotModularSynth", *(entry["slug"] for entry in self.data["modules"])
        ))
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("ModularSynth", result.stderr)

    def test_rejects_identifiers_only_in_writable_load_segment(self) -> None:
        self.write_image(load_flags=6)  # PF_R | PF_W, not a constant pool.
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("no read-only", result.stderr)

    def test_section_table_can_prove_readonly_allocated_literal_storage(self) -> None:
        self.write_image(section_type=1, section_flags=2)  # PROGBITS, ALLOC.
        checked = self.run_gate()
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.write_image(section_type=7, section_flags=2)  # NOTE, not literals.
        self.assertIn("literal sections", self.run_gate().stderr)
        self.write_image(section_type=1, section_flags=3)  # Writable PROGBITS.
        self.assertIn("literal sections", self.run_gate().stderr)
        self.write_image(section_type=1, section_flags=0)  # Nonallocated data.
        self.assertIn("literal sections", self.run_gate().stderr)
        self.write_image(section_type=1, section_flags=6)  # Executable code.
        self.assertIn("literal sections", self.run_gate().stderr)

    def test_rejects_invalid_section_table_boundaries(self) -> None:
        self.write_image(section_type=1)
        elf = bytearray(self.binary.read_bytes())
        struct.pack_into("<Q", elf, 40, len(elf) + 1)
        self.binary.write_bytes(elf)
        self.assertIn("section header table", self.run_gate().stderr)
        self.write_image(section_type=1)
        elf = bytearray(self.binary.read_bytes())
        section = struct.unpack_from("<Q", elf, 40)[0]
        struct.pack_into("<Q", elf, section + 64 + 32, len(elf) + 1)
        self.binary.write_bytes(elf)
        self.assertIn("literal section", self.run_gate().stderr)

    def test_rejects_impossible_architecture_and_bad_load_alignment(self) -> None:
        self.write_image()
        elf = bytearray(self.binary.read_bytes())
        struct.pack_into("<H", elf, 18, 3)  # EM_386 with ELF64, impossible.
        self.binary.write_bytes(elf)
        self.assertIn("machine", self.run_gate().stderr)
        self.write_image()
        elf = bytearray(self.binary.read_bytes())
        struct.pack_into("<Q", elf, 64 + 48, 3)  # Non-power-of-two align.
        self.binary.write_bytes(elf)
        self.assertIn("alignment", self.run_gate().stderr)
        self.write_image()
        elf = bytearray(self.binary.read_bytes())
        struct.pack_into("<Q", elf, 64 + 16, 0x101)  # p_vaddr misaligned.
        self.binary.write_bytes(elf)
        self.assertIn("alignment", self.run_gate().stderr)

    def test_accepts_file_backed_elf32_program_headers(self) -> None:
        mapped = b"\0".join(s.encode("ascii") for s in (
            "ModularSynth", *(entry["slug"] for entry in self.data["modules"])
        )) + b"\0"
        elf = bytearray(0x100 + len(mapped))
        elf[:7] = b"\x7fELF\x01\x01\x01"
        struct.pack_into("<HHI", elf, 16, 2, 3, 1)  # ET_EXEC, EM_386
        struct.pack_into("<I", elf, 28, 52)
        struct.pack_into("<HHH", elf, 40, 52, 32, 1)
        struct.pack_into("<IIIIIIII", elf, 52,
                         1, 0x100, 0x100, 0, len(mapped), len(mapped), 4, 0x1000)
        elf[0x100:] = mapped
        self.binary.write_bytes(elf)
        checked = self.run_gate()
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_new_original_modules_are_required_even_if_manifest_omits_them(self) -> None:
        for missing in ("DualVCA", "SlewGlide"):
            with self.subTest(missing=missing):
                retained = list(self.data["modules"])
                self.data["modules"] = [
                    entry for entry in retained if entry["slug"] != missing
                ]
                self.write_manifest()
                self.write_image()
                result = self.run_gate()
                self.assertEqual(result.returncode, 1)
                self.assertIn(missing, result.stderr)
                self.data["modules"] = retained

    def test_accepts_an_actual_linked_elf_with_loadable_model_strings(self) -> None:
        if not sys.platform.startswith("linux"):
            self.skipTest("host toolchain does not necessarily emit Linux ELF")
        compiler = shutil.which("cc")
        if compiler is None:
            self.skipTest("no host C compiler available")
        identifiers = ["ModularSynth", *(entry["slug"] for entry in self.data["modules"])]
        quoted = ", ".join(json.dumps(s) for s in identifiers)
        source = self.root / "linked-marker-fixture.c"
        source.write_text(
            "static const char * const models[] = {" + quoted + "};\n"
            "int main(void) { unsigned n = 0; for (unsigned i = 0; "
            "i < sizeof(models) / sizeof(models[0]); i++) n += models[i][0]; "
            "return n == 0; }\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [compiler, "-std=c11", "-O0", "-o", str(self.binary), str(source)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        checked = self.run_gate()
        self.assertEqual(checked.returncode, 0, checked.stderr)
        stripper = shutil.which("strip")
        if stripper is not None:
            stripped = subprocess.run(
                [stripper, "--strip-all", str(self.binary)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(stripped.returncode, 0, stripped.stderr)
            after_strip = self.run_gate()
            self.assertEqual(after_strip.returncode, 0, after_strip.stderr)

    def test_rejects_bad_manifest_identity_duplicate_or_invalid_slugs(self) -> None:
        self.write_image()
        self.data["slug"] = "DifferentPlugin"
        self.write_manifest()
        self.assertEqual(self.run_gate().returncode, 1)
        self.data["slug"] = "ModularSynth"
        self.data["modules"].append({"slug": self.data["modules"][0]["slug"].lower()})
        self.write_manifest()
        self.assertEqual(self.run_gate().returncode, 1)
        self.data["modules"][-1]["slug"] = "../Escape"
        self.write_manifest()
        self.assertEqual(self.run_gate().returncode, 1)

    def test_plugin_validation_invokes_gate_after_link_before_runtime_selftest(self) -> None:
        job = WORKFLOW.split("\n  plugin-validation:\n", 1)[1]
        compile_done = job.index("- name: Build Cardinal (final build stage)")
        gate = job.index("- name: Verify linked first-party collection")
        selftest = job.index("- name: Run Cardinal self-tests")
        self.assertLess(compile_done, gate)
        self.assertLess(gate, selftest)
        self.assertIn("python3 -B tools/ci/verify_compiled_collection.py --binary bin/Cardinal", job)


if __name__ == "__main__":
    unittest.main()
