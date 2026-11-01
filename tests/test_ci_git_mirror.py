"""Regression tests for the full-build SpeexDSP checkout mirror.

These run without downloading any submodule or contacting the network. Git's
insteadOf rewrites the *URL only*; Gitlinks still pin their exact object IDs.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
SOURCE = "https://gitlab.xiph.org/xiph/speexdsp.git"
MIRROR = "https://github.com/xiph/speexdsp.git"
REQUIRED_KEYS = ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0")


def build_git_config_environment() -> dict[str, str]:
    """Read the three top-level GIT_CONFIG variables without a YAML dependency."""
    text = WORKFLOW.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    # Only inspect the top-level env stanza, not individual job/step values.
    match = re.search(r"^env:\s*\n(?P<body>(?:[ \t].*\n)*)", text, re.M)
    if not match:
        raise ValueError("build.yml has no top-level env stanza")
    for line in match.group("body").splitlines():
        item = re.fullmatch(r"\s{2}(GIT_CONFIG_[A-Z0-9_]+):\s*(.*?)\s*", line)
        if not item:
            continue
        key, value = item.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        found[key] = value
    return found


class GitMirrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not shutil.which("git"):
            raise unittest.SkipTest("Git is unavailable")
        cls.config = build_git_config_environment()

    def test_git_mirror_rewrites_nested_checkout_url(self) -> None:
        for key in REQUIRED_KEYS:
            self.assertIn(key, self.config)
        self.assertEqual(self.config["GIT_CONFIG_COUNT"], "1")
        self.assertEqual(
            self.config["GIT_CONFIG_KEY_0"],
            f"url.{MIRROR}.insteadOf",
        )
        self.assertEqual(self.config["GIT_CONFIG_VALUE_0"], SOURCE)

        env = os.environ.copy()
        env.update(self.config)
        result = subprocess.run(
            ["git", "ls-remote", "--get-url", SOURCE],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), MIRROR)

    def test_url_rewrite_cannot_change_committed_gitlink_shas(self) -> None:
        if not (ROOT / ".git").exists():
            self.skipTest("Git index unavailable (source archive)")

        command = ["git", "ls-files", "--stage", "-z"]
        baseline = subprocess.check_output(command, cwd=ROOT)
        env = os.environ.copy()
        env.update(self.config)
        mirrored = subprocess.check_output(command, cwd=ROOT, env=env)
        self.assertEqual(baseline, mirrored, "URL rewrite altered Git index")
        self.assertIn(b"160000 ", baseline, "Expected pinned submodule gitlinks")


if __name__ == "__main__":
    unittest.main()
