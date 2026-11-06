#!/usr/bin/env python3
"""Package *externally recorded* host audio for the opt-in CI evidence gate.

This copies supplied bytes, never records, renders, generates or alters audio.
Host identity and recording origin remain operator-attested, not proven here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from verify_host_audio_capture import (
    CaptureError, HASH, SHA, MAX_AUDIO, MAX_MIDI, MAX_PLUGIN, verify,
)


def _no_symlink_components(path: Path) -> Path:
    """Return an absolute path only if each existing component is not a link."""
    path = path.absolute()
    cursor = Path(path.anchor)
    for component in path.parts[1:]:
        cursor /= component
        try:
            if stat.S_ISLNK(cursor.lstat().st_mode):
                raise CaptureError(f"symlink path component refused: {cursor}")
        except FileNotFoundError:
            continue
    return path


def _git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True,
            text=True, timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise CaptureError(f"cannot verify source repository: {exc}") from exc
    return result.stdout.strip()


def _source_commit(repo: Path, claimed: str) -> None:
    if not SHA.fullmatch(claimed):
        raise CaptureError("source SHA must be the exact lowercase 40-character commit")
    if not repo.is_dir() or Path(_git(repo, "rev-parse", "--show-toplevel")) != repo:
        raise CaptureError("--repo must be the Git worktree root")
    if _git(repo, "rev-parse", "HEAD") != claimed:
        raise CaptureError("source SHA does not match checked-out HEAD")
    if _git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise CaptureError("source checkout is dirty; commit or clean it before packaging")


def _copy_checked(src: Path, dst: Path, limit: int) -> tuple[str, tuple[int, int]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(src, flags)
        with os.fdopen(fd, "rb") as read:
            before = os.fstat(read.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
                raise CaptureError(f"input is not a nonempty bounded regular file: {src}")
            digest = hashlib.sha256()
            total = 0
            with dst.open("xb") as write:
                while chunk := read.read(1024 * 1024):
                    total += len(chunk)
                    if total > limit:
                        raise CaptureError(f"input exceeds size limit while copying: {src}")
                    digest.update(chunk)
                    write.write(chunk)
            after = os.fstat(read.fileno())
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if identity(before) != identity(after) or total != before.st_size:
                raise CaptureError(f"input changed during packaging: {src}")
            return digest.hexdigest(), (before.st_dev, before.st_ino)
    except OSError as exc:
        raise CaptureError(f"cannot securely copy input {src}: {exc}") from exc


def package(args: argparse.Namespace) -> Path:
    repo = _no_symlink_components(args.repo)
    _source_commit(repo, args.source_sha)
    if not HASH.fullmatch(args.plugin_sha256):
        raise CaptureError("plugin SHA-256 must be the independently obtained lowercase digest")
    if args.mode == "synth" and args.stimulus.suffix.lower() != ".mid":
        raise CaptureError("synth stimulus must be external .mid MIDI")
    if args.mode == "effect" and args.stimulus.suffix.lower() != ".wav":
        raise CaptureError("effect stimulus must be external .wav audio")
    if args.patch.suffix.lower() != ".vcv":
        raise CaptureError("patch must be a saved .vcv file")
    for src in (args.render, args.baseline):
        if src.suffix.lower() != ".wav":
            raise CaptureError("render and baseline must be supplied WAV files")
    output = _no_symlink_components(args.output_dir)
    parent = _no_symlink_components(output.parent)
    if not parent.is_dir() or output.exists() or output.is_symlink():
        raise CaptureError("output parent must exist and output directory must not exist")
    files = {
        "plugin": (args.plugin, "plugin.so", MAX_PLUGIN),
        "patch": (args.patch, "patch.vcv", 4 * 1024 * 1024),
        "stimulus": (args.stimulus, "stimulus.mid" if args.mode == "synth" else "stimulus.wav",
                     MAX_MIDI if args.mode == "synth" else MAX_AUDIO),
        "render": (args.render, "render.wav", MAX_AUDIO),
        "baseline": (args.baseline, "baseline.wav", MAX_AUDIO),
    }
    sources = {key: _no_symlink_components(src) for key, (src, _, _) in files.items()}
    if any(src == output or output in src.parents for src in sources.values()):
        raise CaptureError("input must not reside inside the output directory")
    stage = Path(tempfile.mkdtemp(prefix=".host-audio-stage-", dir=parent))
    published = False
    try:
        entries = {}
        identities = set()
        for key, (_, filename, limit) in files.items():
            sha, identity = _copy_checked(sources[key], stage / filename, limit)
            if identity in identities:
                raise CaptureError("evidence inputs must be five distinct physical files")
            identities.add(identity)
            entries[key] = {"path": filename, "sha256": sha}
        if entries["plugin"]["sha256"] != args.plugin_sha256:
            raise CaptureError("plugin bytes do not match independently supplied SHA-256")
        manifest = {
            "schema": "modular-host-audio-v1", "source_sha": args.source_sha,
            "host": {"name": args.host_name, "version": args.host_version,
                     "os": "Linux", "plugin_format": args.plugin_format,
                     "capture_method": args.capture_method},
            "plugin": entries["plugin"], "patch": entries["patch"],
            "mode": args.mode, "stimulus": entries["stimulus"],
            "render": entries["render"], "baseline": entries["baseline"],
        }
        (stage / "capture.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verify(manifest, stage, args.source_sha)
        # Exclusive publication: never replace an existing user directory.
        output.mkdir(mode=0o700)
        published = True
        for filename in ("capture.json", *(entry["path"] for entry in entries.values())):
            (stage / filename).replace(output / filename)
        return output
    except Exception:
        if published:
            shutil.rmtree(output)
        raise
    finally:
        shutil.rmtree(stage)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "plugin", "patch", "stimulus", "render", "baseline", "output-dir"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("source-sha", "plugin-sha256", "host-name", "host-version", "capture-method"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--plugin-format", choices=("LV2", "VST2", "VST3"), required=True)
    parser.add_argument("--mode", choices=("synth", "effect"), required=True)
    args = parser.parse_args(argv)
    try:
        output = package(args)
    except (CaptureError, OSError, ValueError) as exc:
        print(f"FAIL: capture package not published: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: verified local evidence package: {output}")
    print("WARNING: origin of host audio and DAW loading remain operator-attested, not independently proven.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
