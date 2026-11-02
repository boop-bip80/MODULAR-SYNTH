"""Prevent regression of the RISC-V cross-build dpkg architecture preflight.

Run 41337664898 reached apt installation but dpkg rejected riscv64 packages
because the amd64 host had not registered riscv64 as a foreign architecture.
These static/executed source-contract checks are not a hosted build pass.
"""

from pathlib import Path
import re
import subprocess
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/build.yml"


def riscv_setup() -> str:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    marker = 'if [[ "$' + '{{ matrix.target }}" = "riscv64" ]]; then'
    return workflow.split(marker, 1)[1].split("\n          fi", 1)[0]


class RiscvMultiarchWorkflowTests(unittest.TestCase):
    def test_registers_foreign_architecture_before_apt(self):
        section = riscv_setup()
        steps = [
            "dpkg --add-architecture riscv64",
            "sed -i -E ",
            "deb [arch=riscv64] http://ports.ubuntu.com",
            "apt-get update -qq",
            "apt-get install -yqq libtinfo6:riscv64",
        ]
        offsets = [section.index(step) for step in steps]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn(
            "dpkg --print-foreign-architectures | grep -qx riscv64", section
        )

    def test_stock_mirrors_restricted_to_native_arch(self):
        section = riscv_setup()
        match = re.search(
            r"sed -i -E '([^']+)' /etc/apt/sources.list", section
        )
        self.assertIsNotNone(match)
        fixture = (
            "deb http://archive.ubuntu.com/ubuntu jammy main\n"
            "deb https://security.ubuntu.com/ubuntu jammy-security main\n"
            "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports jammy main\n"
            "deb-src http://archive.ubuntu.com/ubuntu jammy main\n"
        )
        result = subprocess.run(
            ["sed", "-E", match.group(1)],
            input=fixture, text=True, capture_output=True, check=True,
        )
        self.assertEqual(
            result.stdout,
            (
                "deb [arch=amd64] http://archive.ubuntu.com/ubuntu jammy main\n"
                "deb [arch=amd64] https://security.ubuntu.com/ubuntu jammy-security main\n"
                "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports jammy main\n"
                "deb-src http://archive.ubuntu.com/ubuntu jammy main\n"
            ),
        )

    def test_riscv_indices_use_ubuntu_ports(self):
        section = riscv_setup()
        for pocket in ("jammy", "jammy-updates", "jammy-backports"):
            self.assertIn(
                f"deb [arch=riscv64] http://ports.ubuntu.com/ubuntu-ports {pocket}",
                section,
            )


if __name__ == "__main__":
    unittest.main()
