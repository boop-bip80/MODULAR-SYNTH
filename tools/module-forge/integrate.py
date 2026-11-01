#!/usr/bin/env python3
"""Safely prepare (or explicitly apply) a generated Module Forge module.

Dry-run is the default. The command only integrates a reviewed skeleton into
the first-party plugins/ModularSynth static collection; it is not a hot loader.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from module_forge import check_module, validate_slug

REGISTRY_FILES = (
    "plugins/Makefile",
    "plugins/plugins.cpp",
    "plugins/ModularSynth/src/plugin.hpp",
    "plugins/ModularSynth/plugin.json",
)


class IntegrationError(ValueError):
    """A preflight, collision, or safe-apply error."""


@dataclass(frozen=True)
class FileEdit:
    path: Path
    before: bytes | None
    after: bytes


def _within_root(root: Path, target: Path) -> Path:
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise IntegrationError(f"path outside repository: {target}") from exc
    current = root
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise IntegrationError(f"symlink target is not allowed: {relative}")
    return relative


def _read_checked(root: Path, relative: str) -> tuple[Path, bytes, str]:
    target = root / relative
    _within_root(root, target)
    if not target.is_file():
        raise IntegrationError(f"required repository file is missing: {relative}")
    data = target.read_bytes()
    try:
        return target, data, data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntegrationError(f"expected UTF-8 text: {relative}") from exc


def _insert_makefile(source: str, slug: str) -> str:
    if "-DpluginInstance=pluginInstance__ModularSynth" not in source:
        raise IntegrationError("ModularSynth compiler namespace rule is missing")
    item = f"ModularSynth/src/{slug}.cpp"
    if item in source:
        raise IntegrationError(f"module source is already registered: {item}")
    matches = list(re.finditer(
        r"(?m)^PLUGIN_FILES \+= ModularSynth/src/[A-Za-z0-9]+\.cpp$", source))
    if not matches:
        raise IntegrationError("ModularSynth PLUGIN_FILES anchor is missing")
    at = matches[-1].end()
    return source[:at] + f"\nPLUGIN_FILES += {item}" + source[at:]


def _insert_header(source: str, slug: str) -> str:
    symbol = f"modelMS{slug}"
    if re.search(r"\b" + re.escape(symbol) + r"\b", source):
        raise IntegrationError(f"model declaration already exists: {symbol}")
    matches = list(re.finditer(
        r"(?m)^extern Model\* model[A-Za-z0-9_]+;$", source))
    if not matches:
        raise IntegrationError("ModularSynth model declaration anchor is missing")
    at = matches[-1].end()
    return source[:at] + f"\nextern Model* {symbol};" + source[at:]


def _matching_brace(source: str, opening: int) -> int:
    if source[opening] != "{":
        raise IntegrationError("internal brace parser error")
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    raise IntegrationError("unterminated ModularSynth initialization block")


def _insert_registry(source: str, slug: str) -> str:
    symbol = f"modelMS{slug}"
    if re.search(r"\b" + re.escape(symbol) + r"\b", source):
        raise IntegrationError(f"model registry already exists: {symbol}")
    anchor = "static void initStatic__ModularSynth()"
    if source.count(anchor) != 1:
        raise IntegrationError("expected exactly one ModularSynth loader function")
    begin = source.index("{", source.index(anchor) + len(anchor))
    end = _matching_brace(source, begin)
    section = source[begin + 1:end]
    unbraced = re.search(
        r"(?m)^    if \(spl\.ok\(\)\)\n        "
        r"(?P<statement>p->addModel\(model[A-Za-z0-9_]+\);)$", section)
    if unbraced:
        old = unbraced.group(0)
        replacement = (
            "    if (spl.ok())\n"
            "    {\n"
            f"        {unbraced.group('statement')}\n"
            f"        p->addModel({symbol});\n"
            "    }")
        section = section.replace(old, replacement, 1)
    else:
        braced = re.search(r"(?m)^    if \(spl\.ok\(\)\)\n    \{$", section)
        if not braced:
            raise IntegrationError(
                "unsupported ModularSynth loader layout; integrate manually")
        open_brace = section.index("{", braced.start())
        close_brace = _matching_brace(section, open_brace)
        body = section[open_brace + 1:close_brace]
        models = list(re.finditer(
            r"(?m)^        p->addModel\(model[A-Za-z0-9_]+\);$", body))
        if not models:
            raise IntegrationError("no existing ModularSynth model registration")
        at = models[-1].end()
        body = body[:at] + f"\n        p->addModel({symbol});" + body[at:]
        section = section[:open_brace + 1] + body + section[close_brace:]
    return source[:begin + 1] + section + source[end:]


def _insert_manifest(source: str, fragment: dict) -> str:
    try:
        manifest = json.loads(source)
    except json.JSONDecodeError as exc:
        raise IntegrationError(f"invalid existing ModularSynth manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("slug") != "ModularSynth":
        raise IntegrationError("expected a ModularSynth collection manifest")
    modules = manifest.get("modules")
    if not isinstance(modules, list) or not all(
        isinstance(item, dict) and isinstance(item.get("slug"), str)
        for item in modules
    ):
        raise IntegrationError("manifest modules must be objects with slugs")
    slug = fragment["slug"]
    if any(item["slug"] == slug for item in modules):
        raise IntegrationError(f"duplicate module slug in manifest: {slug}")
    modules.append(fragment)
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def integration_plan(module_dir: Path, repo_root: Path) -> list[FileEdit]:
    root = repo_root.resolve(strict=True)
    module = module_dir.resolve(strict=True)
    if not module.is_dir():
        raise IntegrationError("generated module directory does not exist")
    slug = module.name
    validate_slug(slug)
    generated_paths = (
        module / f"{slug}.cpp",
        module / f"{slug}.svg",
        module / f"{slug}.module.json",
        module / "INTEGRATION.md",
    )
    if any(path.is_symlink() or not path.is_file() for path in generated_paths):
        raise IntegrationError("generated module has missing or symlinked files")
    errors = check_module(module)
    if errors:
        raise IntegrationError("; ".join(errors))
    try:
        fragment = json.loads((module / f"{slug}.module.json").read_text(
            encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IntegrationError(f"invalid generated module manifest: {exc}") from exc
    if not isinstance(fragment, dict) or fragment.get("slug") != slug:
        raise IntegrationError("generated module slug does not match")
    if not isinstance(fragment.get("tags"), list):
        raise IntegrationError("generated module tags must be a list")

    source_dest = root / "plugins" / "ModularSynth" / "src" / f"{slug}.cpp"
    panel_dest = root / "plugins" / "ModularSynth" / "res" / f"{slug}.svg"
    for target in (source_dest, panel_dest):
        relative = _within_root(root, target)
        if not target.parent.is_dir():
            raise IntegrationError(f"missing module destination directory: {relative.parent}")
        if target.exists() or target.is_symlink():
            raise IntegrationError(f"refusing to overwrite existing file: {relative}")
        if target.resolve(strict=False) in generated_paths:
            raise IntegrationError("generated source is already inside target collection")

    # Read and validate every preexisting file before planning any mutations.
    originals: dict[str, tuple[Path, bytes, str]] = {
        relative: _read_checked(root, relative) for relative in REGISTRY_FILES
    }
    makefile = _insert_makefile(originals["plugins/Makefile"][2], slug)
    loader = _insert_registry(originals["plugins/plugins.cpp"][2], slug)
    header = _insert_header(
        originals["plugins/ModularSynth/src/plugin.hpp"][2], slug)
    manifest = _insert_manifest(
        originals["plugins/ModularSynth/plugin.json"][2], fragment)
    outputs = {
        "plugins/Makefile": makefile,
        "plugins/plugins.cpp": loader,
        "plugins/ModularSynth/src/plugin.hpp": header,
        "plugins/ModularSynth/plugin.json": manifest,
    }
    edits: list[FileEdit] = []
    for relative, new_text in outputs.items():
        path, original, _ = originals[relative]
        data = new_text.encode("utf-8")
        if data == original:
            raise IntegrationError(f"registration produced no change: {relative}")
        edits.append(FileEdit(path=path, before=original, after=data))
    edits.append(FileEdit(
        source_dest, before=None,
        after=(module / f"{slug}.cpp").read_bytes()))
    edits.append(FileEdit(
        panel_dest, before=None,
        after=(module / f"{slug}.svg").read_bytes()))
    return sorted(edits, key=lambda item: str(item.path.relative_to(root)))


def plan_diff(edits: list[FileEdit], repo_root: Path) -> str:
    root = repo_root.resolve(strict=True)
    parts = []
    for edit in edits:
        name = edit.path.relative_to(root).as_posix()
        old = (edit.before or b"").decode("utf-8")
        new = edit.after.decode("utf-8")
        parts.extend(difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile="a/" + name if edit.before is not None else "/dev/null",
            tofile="b/" + name))
    return "".join(parts)


def _current_bytes(edit: FileEdit) -> bytes | None:
    if edit.path.is_symlink():
        raise IntegrationError(f"symlink appeared during apply: {edit.path}")
    if not edit.path.exists():
        return None
    if not edit.path.is_file():
        raise IntegrationError(f"not a regular file: {edit.path}")
    return edit.path.read_bytes()


def apply_plan(edits: list[FileEdit], repo_root: Path) -> None:
    root = repo_root.resolve(strict=True)
    for edit in edits:
        _within_root(root, edit.path)
        if _current_bytes(edit) != edit.before:
            raise IntegrationError(f"file changed after planning: {edit.path}")
    transaction_dir = Path(tempfile.mkdtemp(
        prefix=".module-forge-transaction-", dir=root))
    stages: list[Path] = []
    backups: list[Path | None] = []
    applied: list[int] = []
    rollback_failed = False
    try:
        for index, edit in enumerate(edits):
            stage = transaction_dir / f"{index}.new"
            stage.write_bytes(edit.after)
            if edit.before is not None:
                mode = stat.S_IMODE(edit.path.stat().st_mode)
                os.chmod(stage, mode)
                backup = transaction_dir / f"{index}.bak"
                backup.write_bytes(edit.before)
                os.chmod(backup, mode)
            else:
                os.chmod(stage, 0o644)
                backup = None
            stages.append(stage)
            backups.append(backup)
        for index, edit in enumerate(edits):
            if _current_bytes(edit) != edit.before:
                raise IntegrationError(f"concurrent file change: {edit.path}")
            if edit.before is None:
                # Hard link creation is atomic and fails if the target exists.
                os.link(stages[index], edit.path)
            else:
                os.replace(stages[index], edit.path)
            applied.append(index)
    except Exception:
        for index in reversed(applied):
            edit = edits[index]
            try:
                # Do not undo someone else's changes made after this tool's write.
                if _current_bytes(edit) != edit.after:
                    rollback_failed = True
                    continue
                if edit.before is None:
                    edit.path.unlink()
                else:
                    assert backups[index] is not None
                    os.replace(backups[index], edit.path)
            except Exception:
                rollback_failed = True
        if rollback_failed:
            print(
                f"Automatic rollback incomplete. Backups kept at {transaction_dir}",
                file=sys.stderr)
        raise
    finally:
        if not rollback_failed:
            shutil.rmtree(transaction_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", type=Path, help="generated module directory")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(),
                        help="Cardinal-derived repository root (default: cwd)")
    parser.add_argument("--apply", action="store_true",
                        help="explicitly apply validated edits; default is dry-run")
    args = parser.parse_args(argv)
    try:
        plan = integration_plan(args.module, args.repo_root)
        print(plan_diff(plan, args.repo_root), end="")
        if args.apply:
            apply_plan(plan, args.repo_root)
            print(f"\nApplied {len(plan)} staged file edits.")
        else:
            print(
                "\nDRY RUN: no files changed. Inspect the diff, "
                "then repeat with --apply.")
        return 0
    except (IntegrationError, ValueError, OSError) as exc:
        print(f"Module Forge integration refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
