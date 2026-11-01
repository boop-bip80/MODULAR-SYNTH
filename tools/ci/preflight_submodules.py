#!/usr/bin/env python3
"""Offline Gitlink and SpeexDSP mirror preflight; never fetches dependencies.

Run from any working directory:
    python3 tools/ci/preflight_submodules.py
    python3 tools/ci/preflight_submodules.py --require-populated

The default checks root Gitlinks and CI URL rewriting while tolerating
uninitialized submodules. Strict mode requires every declared top-level
submodule and Rack's nested SpeexDSP checkout at its pinned HEAD; it does
not traverse other nested plugin dependencies.
"""
from __future__ import annotations

import argparse
import configparser
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

SOURCE_URL = "https://gitlab.xiph.org/xiph/speexdsp.git"
MIRROR_URL = "https://github.com/xiph/speexdsp.git"
RACK_PATH = "src/Rack"
SPEEX_PATH = "dep/speexdsp"


class PreflightError(Exception):
    """An offline source/metadata validation could not complete safely."""


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    command = ["git", "-C", str(repo), *args]
    completed = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PreflightError(f"{' '.join(args)} failed in {repo}: {detail}")
    return completed.stdout.strip()


def gitlinks(repo: Path) -> dict[str, str]:
    command = ["git", "-C", str(repo), "ls-tree", "-rz", "HEAD"]
    completed = subprocess.run(command, capture_output=True, check=False)
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise PreflightError(f"cannot inspect committed Gitlinks in {repo}: {detail}")
    links: dict[str, str] = {}
    for record in completed.stdout.split(b"\0"):
        if not record:
            continue
        try:
            metadata, path_bytes = record.split(b"\t", 1)
            mode, object_type, sha = metadata.decode("ascii").split()
        except (ValueError, UnicodeDecodeError) as error:
            raise PreflightError(f"malformed ls-tree entry in {repo}") from error
        if mode != "160000":
            continue
        if object_type != "commit":
            raise PreflightError(f"Gitlink has unexpected object type: {path_bytes!r}")
        path = path_bytes.decode("utf-8", "surrogateescape")
        links[path] = sha
    return links


def declarations(file: Path) -> dict[str, str]:
    if not file.is_file():
        raise PreflightError(f"missing required submodule manifest: {file}")
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        with file.open(encoding="utf-8") as stream:
            parser.read_file(stream)
    except (OSError, configparser.Error) as error:
        raise PreflightError(f"cannot parse {file}: {error}") from error
    urls: dict[str, str] = {}
    for section in parser.sections():
        if not section.startswith('submodule "'):
            raise PreflightError(f"invalid .gitmodules section: {section}")
        if not parser.has_option(section, "path") or not parser.has_option(section, "url"):
            raise PreflightError(f"{section} lacks path or url")
        path = parser.get(section, "path")
        url = parser.get(section, "url")
        posix = PurePosixPath(path)
        if not path or posix.is_absolute() or ".." in posix.parts or path.startswith("./"):
            raise PreflightError(f"unsafe submodule path: {path!r}")
        if path in urls:
            raise PreflightError(f"duplicate .gitmodules path: {path}")
        if not url.startswith("https://"):
            raise PreflightError(f"submodule URL is not HTTPS: {path}")
        urls[path] = url
    if not urls:
        raise PreflightError(f"no submodules declared in {file}")
    return urls


def mirror_environment(workflow: Path) -> dict[str, str]:
    if not workflow.is_file():
        raise PreflightError(f"missing build workflow: {workflow}")
    content = workflow.read_text(encoding="utf-8")
    block = re.search(r"^env:\s*\n(?P<body>(?:[ \t].*\n)*)", content, re.M)
    if not block:
        raise PreflightError("build.yml has no top-level Git mirror environment")
    values: dict[str, str] = {}
    for line in block.group("body").splitlines():
        match = re.fullmatch(r"\s{2}(GIT_CONFIG_[A-Z0-9_]+):\s*(.*?)\s*", line)
        if not match:
            continue
        key, value = match.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    expected = {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.{MIRROR_URL}.insteadOf",
        "GIT_CONFIG_VALUE_0": SOURCE_URL,
    }
    for key, value in expected.items():
        if values.get(key) != value:
            raise PreflightError(f"build.yml {key} must equal {value!r}, got {values.get(key)!r}")
    if set(values) != set(expected):
        raise PreflightError(f"unexpected Git config keys in build.yml: {sorted(set(values) - set(expected))}")
    return values


def populated_head(root: Path, relative: str) -> str | None:
    path = root / relative
    if path.is_symlink():
        raise PreflightError(f"submodule path is a symlink: {relative}")
    if not (path / ".git").exists():
        return None
    top = Path(git(path, "rev-parse", "--show-toplevel")).resolve()
    if top != path.resolve():
        raise PreflightError(f"{relative} is not the root of its own Git checkout")
    return git(path, "rev-parse", "HEAD")


def check_worktree(
    root: Path,
    relative: str,
    pinned: str,
    strict: bool,
    errors: list[str],
    missing: list[str],
    display_path: str | None = None,
) -> bool:
    label = display_path or relative
    try:
        local = populated_head(root, relative)
    except PreflightError as error:
        errors.append(str(error))
        return False
    if local is None:
        missing.append(label)
        if strict:
            errors.append(f"{label} is not initialized; run git submodule update --init --recursive")
        return False
    if local != pinned:
        errors.append(f"{label} HEAD {local} does not match pinned Gitlink {pinned}")
        return False
    return True


def preflight(root: Path, strict: bool) -> int:
    errors: list[str] = []
    missing: list[str] = []
    try:
        top = Path(git(root, "rev-parse", "--show-toplevel")).resolve()
        if top != root.resolve():
            raise PreflightError(f"--repo must point at repository root (found {top})")
        expected = declarations(root / ".gitmodules")
        committed = gitlinks(root)
        undeclared = sorted(set(committed) - set(expected))
        unpinned = sorted(set(expected) - set(committed))
        if undeclared:
            errors.append("Gitlinks missing from .gitmodules: " + ", ".join(undeclared))
        if unpinned:
            errors.append(".gitmodules entries lack pinned Gitlinks: " + ", ".join(unpinned))

        mirror = mirror_environment(root / ".github" / "workflows" / "build.yml")
        env = os.environ.copy()
        env.update(mirror)
        resolved = git(root, "ls-remote", "--get-url", SOURCE_URL, env=env)
        if resolved != MIRROR_URL:
            errors.append(f"SpeexDSP URL resolved to {resolved!r}, expected {MIRROR_URL!r}")

        initialized: set[str] = set()
        for path in sorted(set(expected) & set(committed)):
            if check_worktree(root, path, committed[path], strict, errors, missing):
                initialized.add(path)

        if RACK_PATH in initialized:
            rack = root / RACK_PATH
            nested = gitlinks(rack)
            rack_declared = declarations(rack / ".gitmodules")
            if SPEEX_PATH not in nested:
                errors.append(f"{RACK_PATH} lacks pinned {SPEEX_PATH} Gitlink")
            if rack_declared.get(SPEEX_PATH) not in (SOURCE_URL, MIRROR_URL):
                errors.append(f"{RACK_PATH}/.gitmodules SpeexDSP URL is not covered by CI mirror")
            if SPEEX_PATH in nested:
                check_worktree(rack, SPEEX_PATH, nested[SPEEX_PATH], strict, errors, missing,
                               display_path=f"{RACK_PATH}/{SPEEX_PATH}")

        print(f"Offline preflight: {len(committed)} root Gitlinks; "
              f"{len(initialized)} initialized at pinned HEAD; "
              f"SpeexDSP URL resolves to {resolved}")
        if missing:
            sample = ", ".join(missing[:4])
            suffix = f", +{len(missing) - 4} more" if len(missing) > 4 else ""
            print(f"NOTE: {len(missing)} uninitialized submodule(s): {sample}{suffix}")
    except PreflightError as error:
        errors.append(str(error))
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    if errors:
        return 1
    print("PASS: offline submodule pins and CI mirror configuration")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2],
                        help="Repository root (defaults to this script's checkout)")
    parser.add_argument("--require-populated", action="store_true",
                        help="Require pinned HEADs for all root Gitlinks and nested Rack/SpeexDSP only")
    args = parser.parse_args()
    return preflight(args.repo.resolve(), args.require_populated)


if __name__ == "__main__":
    raise SystemExit(main())
