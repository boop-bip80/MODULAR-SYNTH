"""Regression tests for the full-build SpeexDSP checkout mirror.

These run without downloading any submodule or contacting the network. Git's
insteadOf rewrites the *URL only*; Gitlinks still pin their exact object IDs.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
SOURCE = "https://gitlab.xiph.org/xiph/speexdsp.git"
MIRROR = "https://github.com/xiph/speexdsp.git"
REQUIRED_KEYS = ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0")
RECURSIVE_CHECKOUT = ROOT / "tools" / "ci" / "update_pinned_submodules.sh"
WORKSPACE_TRUST = ROOT / "tools" / "ci" / "trust_checkout_workspace.sh"


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

    def test_all_full_build_jobs_use_explicit_retry_after_initial_checkout(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        checkouts = re.findall(
            r"^\s*- uses: actions/checkout@v4\n"
            r"\s*with:\n\s*submodules: true\n"
            r"\s*- name: Complete pinned recursive submodule checkout \(retry\)\n"
            r"\s*shell: bash\n\s*run: bash tools/ci/update_pinned_submodules.sh$",
            workflow,
            re.M,
        )
        self.assertEqual(11, len(checkouts), "Every full-build checkout must be retried")
        self.assertNotIn("submodules: recursive", workflow)
        subprocess.run(["bash", "-n", str(RECURSIVE_CHECKOUT)], check=True)
        subprocess.run(["bash", "-n", str(WORKSPACE_TRUST)], check=True)
        script = RECURSIVE_CHECKOUT.read_text(encoding="utf-8")
        self.assertLess(
            script.index('trust_checkout_workspace.sh'),
            script.index("source_url='https://gitlab.xiph.org/xiph/speexdsp.git'"),
            "CI checkout must establish narrowly scoped Git trust before other Git operations",
        )

    def test_nested_checkout_retries_pinned_gitlinks_without_network(self) -> None:
        # Replace git/sleep with local stubs: test both retry policy and exact
        # Gitlink status validation, without network or a Python CI dependency.
        with tempfile.TemporaryDirectory(prefix="pinned-submodule-retry-") as temp:
            fake_bin = Path(temp)
            state = fake_bin / "attempts"
            commands = fake_bin / "commands"
            fake_git = fake_bin / "git"
            fake_git.write_text(
                '#!/usr/bin/env bash\n'
                'printf "%s\\n" "$*" >> "$FAKE_COMMAND_LOG"\n'
                'if [[ " $* " == *" config --global --add safe.directory "* ]]; then exit 0; fi\n'
                'if [[ " $* " == *" ls-remote --get-url "* ]]; then\n'
                '  if [[ "$FAKE_WRONG_MIRROR" = 1 ]]; then echo https://untrusted.invalid; exit 0; fi\n'
                '  raw="${@: -1}"\n'
                '  if [[ "$raw" == */ ]]; then echo https://github.com/xiph/speexdsp.git/; '
                'else echo https://github.com/xiph/speexdsp.git; fi\n'
                '  exit 0\n'
                'fi\n'
                'if [[ " $* " == *" submodule update --init --recursive"* ]]; then\n'
                '  n=0; [[ -f "$FAKE_ATTEMPTS_FILE" ]] && read -r n < "$FAKE_ATTEMPTS_FILE"\n'
                '  n=$((n+1)); printf "%s\\n" "$n" > "$FAKE_ATTEMPTS_FILE"\n'
                '  ((n>FAKE_FAILURES)) && exit 0 || exit 1\n'
                'fi\n'
                'if [[ " $* " == *" submodule status --recursive"* ]]; then\n'
                '  if [[ "$FAKE_BAD_STATUS" = 1 ]]; then\n'
                '    printf "+%040d src/Rack/dep/speexdsp (wrong checkout)\\n" 0\n'
                '  else\n'
                '    printf " %040d src/Rack/dep/speexdsp (exact pin)\\n" 0\n'
                '  fi\n'
                '  exit 0\n'
                'fi\n'
                'exit 99\n',
                encoding="utf-8",
            )
            fake_sleep = fake_bin / "sleep"
            fake_sleep.write_text('#!/usr/bin/env bash\nexit 0\n', encoding="utf-8")
            for command in (fake_git, fake_sleep):
                command.chmod(0o755)

            def invoke(failures: int, wrong_mirror: bool = False,
                       bad_status: bool = False,
                       ci: bool = False) -> subprocess.CompletedProcess[str]:
                state.unlink(missing_ok=True)
                commands.unlink(missing_ok=True)
                env = os.environ.copy()
                env.update({
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                    "FAKE_FAILURES": str(failures),
                    "FAKE_WRONG_MIRROR": "1" if wrong_mirror else "0",
                    "FAKE_BAD_STATUS": "1" if bad_status else "0",
                    "FAKE_ATTEMPTS_FILE": str(state),
                    "FAKE_COMMAND_LOG": str(commands),
                    "GITHUB_ACTIONS": "true" if ci else "false",
                    "GITHUB_WORKSPACE": str(ROOT),
                })
                return subprocess.run(
                    ["bash", str(RECURSIVE_CHECKOUT)], cwd=ROOT, env=env,
                    capture_output=True, text=True, timeout=15,
                )

            result = invoke(failures=2)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("3", state.read_text(encoding="utf-8").strip())

            result = invoke(failures=3)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("3", state.read_text(encoding="utf-8").strip())

            result = invoke(failures=0, wrong_mirror=True)
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(state.exists(), "Untrusted URL must fail before fetching")

            result = invoke(failures=0, bad_status=True)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("non-pinned submodule", result.stderr)

            result = invoke(failures=0, ci=True)
            self.assertEqual(0, result.returncode, result.stderr)
            calls = commands.read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                f"config --global --add safe.directory {ROOT}", calls[0],
                "Trust must be scoped to the checkout and established before checkout retry",
            )

    def test_ci_workspace_trust_restores_git_after_checkout_temporary_home(self) -> None:
        # Git >=2.35 exposes a test-only ownership override, reproducing the
        # hosted container's dubious-owner rejection on a disposable repo.
        with tempfile.TemporaryDirectory(prefix="ci-safe-workspace-") as temp:
            test_root = Path(temp)
            workspace = test_root / "checked-out-project"
            workspace.mkdir()
            subprocess.run(["git", "init", "-q", str(workspace)], check=True)
            unrelated = test_root / "other-project"
            unrelated.mkdir()
            subprocess.run(["git", "init", "-q", str(unrelated)], check=True)

            job_home = test_root / "job-home"
            job_home.mkdir()
            config_home = test_root / "xdg-config"
            config_home.mkdir()
            env = os.environ.copy()
            env.update({
                "GITHUB_ACTIONS": "true",
                "GITHUB_WORKSPACE": str(workspace),
                "HOME": str(job_home),
                "XDG_CONFIG_HOME": str(config_home),
                "GIT_TEST_ASSUME_DIFFERENT_OWNER": "1",
            })

            def inspect(repo: Path) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=repo, env=env, capture_output=True, text=True,
                )

            before = inspect(workspace)
            if before.returncode == 0:
                self.skipTest("Git has no test-only different-owner guard")
            self.assertIn("dubious ownership", before.stderr)

            recovery = subprocess.run(
                ["bash", str(WORKSPACE_TRUST)], cwd=workspace, env=env,
                capture_output=True, text=True, check=True,
            )
            self.assertEqual("", recovery.stderr)
            self.assertEqual(str(workspace), inspect(workspace).stdout.strip())
            self.assertIn("dubious ownership", inspect(unrelated).stderr,
                          "Siblings must stay untrusted")
            trusted = subprocess.check_output(
                ["git", "config", "--global", "--get-all", "safe.directory"],
                cwd=workspace, env=env, text=True,
            ).splitlines()
            self.assertEqual([str(workspace)], trusted)

    def test_ci_workspace_trust_rejects_wrong_workspace(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ci-safe-workspace-wrong-") as temp:
            project = Path(temp) / "project"
            project.mkdir()
            (project / ".git").mkdir()
            other = Path(temp) / "other"
            other.mkdir()
            job_home = Path(temp) / "job-home"
            job_home.mkdir()
            env = os.environ.copy()
            env.update({
                "GITHUB_ACTIONS": "true",
                "GITHUB_WORKSPACE": str(other),
                "HOME": str(job_home),
            })
            result = subprocess.run(
                ["bash", str(WORKSPACE_TRUST)], cwd=project, env=env,
                capture_output=True, text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("Refusing to trust", result.stderr)
            self.assertFalse((job_home / ".gitconfig").exists())

    def test_workspace_trust_is_noop_outside_github_actions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ci-safe-workspace-local-") as temp:
            result = subprocess.run(
                ["bash", str(WORKSPACE_TRUST)], cwd=temp,
                env={"PATH": os.environ.get("PATH", ""), "GITHUB_ACTIONS": "false"},
                capture_output=True, text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
