#!/usr/bin/env python3
"""Source-only notice/provenance preflight for MODULAR-SYNTH Originals.

Not a license-compatibility analysis, rights clearance, or binary audit.
Inherited Cardinal/Rack/DPF and third-party sources are deliberately not scanned.
"""
from __future__ import annotations

import argparse
import ast
import configparser
import json
from pathlib import Path
import re
import sys
from typing import Any
from xml.etree import ElementTree


EXPECTED_LICENSE = "GPL-3.0-or-later"
EXPECTED_REPOSITORY = "https://github.com/boop-bip80/MODULAR-SYNTH"
SPDX = re.compile(r"SPDX-License-Identifier:\s*([A-Za-z0-9.+-]+)")
COPYRIGHT = re.compile(r"Copyright\s*\(C\)\s*\d{4}", re.IGNORECASE)
VALID_SLUG = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\Z")
TEMPLATE_SOURCE = ("SOURCE_TEMPLATE", "EFFECT_SOURCE_TEMPLATE", "EFFECT_CORE_TEMPLATE")
TEMPLATE_PANELS = ("PANEL_TEMPLATE", "EFFECT_PANEL_TEMPLATE")
TEMPLATE_INTEGRATIONS = ("INTEGRATION_TEMPLATE", "EFFECT_INTEGRATION_TEMPLATE")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate manifest JSON key: {key}")
        result[key] = value
    return result


def _finding(findings: list[dict[str, str]], level: str, code: str, path: str, message: str) -> None:
    findings.append({"level": level, "code": code, "path": path, "message": message})


def _read_text(
    root: Path, relative: str, checked: set[str], findings: list[dict[str, str]],
) -> str | None:
    path = root / relative
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        _finding(findings, "error", "missing_or_unreadable", relative, str(exc))
        return None
    checked.add(relative)
    return content


def _notice(
    content: str, relative: str, findings: list[dict[str, str]], *, panel: bool = False,
) -> None:
    """Require consistent C++ notices; report legacy SVG notice gaps explicitly."""
    prefix = "\n".join(content.splitlines()[:24])
    declared = SPDX.findall(prefix)
    if not declared:
        level = "warning" if panel else "error"
        _finding(
            findings, level, "missing_spdx", relative,
            f"add an explicit SPDX-License-Identifier: {EXPECTED_LICENSE} notice",
        )
    elif len(declared) != 1 or declared[0] != EXPECTED_LICENSE:
        _finding(
            findings, "error", "inconsistent_spdx", relative,
            f"expected one {EXPECTED_LICENSE} identifier, found {declared!r}",
        )
    if not panel and not COPYRIGHT.search(prefix):
        _finding(findings, "error", "missing_copyright", relative,
                 "first-party C++ requires an attributable copyright notice near the header")
    if panel and not (
        "modular-synth" in prefix.lower() and "original" in prefix.lower()
    ):
        _finding(findings, "error", "missing_panel_origin", relative,
                 "first-party SVG needs an Original MODULAR-SYNTH provenance comment")


def _manifest(
    root: Path, checked: set[str], findings: list[dict[str, str]],
) -> list[str]:
    relative = "plugins/ModularSynth/plugin.json"
    text = _read_text(root, relative, checked, findings)
    if text is None:
        return []
    try:
        manifest = json.loads(text, object_pairs_hook=_unique_json_object)
    except ValueError as exc:
        _finding(findings, "error", "manifest_json", relative, str(exc))
        return []
    if not isinstance(manifest, dict):
        _finding(findings, "error", "manifest_shape", relative, "manifest must be an object")
        return []
    if manifest.get("slug") != "ModularSynth":
        _finding(findings, "error", "manifest_slug", relative,
                 "expected slug ModularSynth for the first-party collection")
    if manifest.get("license") != EXPECTED_LICENSE:
        _finding(findings, "error", "manifest_license", relative,
                 f"license must match the first-party C++ notices: {EXPECTED_LICENSE}")
    author = manifest.get("author")
    if not isinstance(author, str) or not author.strip():
        _finding(findings, "error", "manifest_author", relative,
                 "first-party manifest requires an author attribution")
    for field in ("sourceUrl", "pluginUrl", "authorUrl"):
        value = manifest.get(field)
        if not isinstance(value, str) or not value.startswith("https://github.com/"):
            _finding(findings, "error", "manifest_provenance", relative,
                     f"{field} must be a non-empty HTTPS GitHub provenance URL")
    if manifest.get("sourceUrl") != EXPECTED_REPOSITORY:
        _finding(findings, "error", "source_url", relative,
                 f"sourceUrl must point to this fork: {EXPECTED_REPOSITORY}")
    modules = manifest.get("modules")
    if not isinstance(modules, list) or not modules:
        _finding(findings, "error", "manifest_modules", relative,
                 "modules must be a non-empty list")
        return []
    slugs: list[str] = []
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            _finding(findings, "error", "manifest_model", relative,
                     f"modules[{index}] must be an object")
            continue
        slug = module.get("slug")
        if not isinstance(slug, str) or not VALID_SLUG.fullmatch(slug):
            _finding(findings, "error", "manifest_model_slug", relative,
                     f"modules[{index}].slug must be a safe source basename")
            continue
        if slug in slugs:
            _finding(findings, "error", "duplicate_model", relative,
                     f"duplicate first-party module slug {slug}")
        else:
            slugs.append(slug)
        if not isinstance(module.get("name"), str) or not module["name"].strip():
            _finding(findings, "error", "model_name", relative,
                     f"{slug}: manifest name is missing")
    return sorted(set(slugs))


def _scan_first_party(
    root: Path, slugs: list[str], checked: set[str], findings: list[dict[str, str]],
) -> tuple[int, int]:
    src = root / "plugins" / "ModularSynth" / "src"
    res = root / "plugins" / "ModularSynth" / "res"
    for slug in slugs:
        for suffix, directory in ((".cpp", src), (".svg", res)):
            file = directory / f"{slug}{suffix}"
            if not file.is_file():
                _finding(findings, "error", "model_asset_missing",
                         file.relative_to(root).as_posix(),
                         f"{slug} is declared in the first-party manifest")
    cpp_count = 0
    for path in sorted(src.rglob("*")) if src.is_dir() else []:
        if path.is_file() and path.suffix in (".cpp", ".hpp"):
            relative = path.relative_to(root).as_posix()
            content = _read_text(root, relative, checked, findings)
            if content is not None:
                cpp_count += 1
                _notice(content, relative, findings)

    panel_count = 0
    for path in sorted(res.rglob("*.svg")) if res.is_dir() else []:
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        content = _read_text(root, relative, checked, findings)
        if content is None:
            continue
        panel_count += 1
        _notice(content, relative, findings, panel=True)
        try:
            svg = ElementTree.fromstring(content)
            if svg.tag.rsplit("}", 1)[-1] != "svg":
                raise ValueError("document root is not svg")
        except (ElementTree.ParseError, ValueError) as exc:
            _finding(findings, "error", "invalid_svg", relative, str(exc))
    if cpp_count == 0:
        _finding(findings, "error", "no_cpp", "plugins/ModularSynth/src",
                 "no first-party C++/header files were found")
    if panel_count == 0:
        _finding(findings, "error", "no_panels", "plugins/ModularSynth/res",
                 "no first-party SVG panels were found")
    return cpp_count, panel_count


def _module_forge(
    root: Path, checked: set[str], findings: list[dict[str, str]],
) -> None:
    relative = "tools/module-forge/module_forge.py"
    text = _read_text(root, relative, checked, findings)
    if text is None:
        return
    try:
        tree = ast.parse(text, filename=relative)
    except SyntaxError as exc:
        _finding(findings, "error", "forge_syntax", relative, str(exc))
        return
    literals: dict[str, str] = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    literals[target.id] = node.value.value
    for name in (*TEMPLATE_SOURCE, *TEMPLATE_PANELS, *TEMPLATE_INTEGRATIONS):
        if name not in literals:
            _finding(findings, "error", "forge_template_missing", relative,
                     f"cannot inspect literal {name}; review the generator structure")
    for name in TEMPLATE_SOURCE:
        if name not in literals:
            continue
        source = literals[name]
        if EXPECTED_LICENSE not in source[:280] or "Generated by Module Forge" not in source[:280]:
            _finding(findings, "error", "forge_license", relative,
                     f"{name} needs a generated-by marker and {EXPECTED_LICENSE} notice")
        if not SPDX.search(source[:280]):
            _finding(findings, "warning", "forge_spdx_recommended", relative,
                     f"{name}: generated C++ should use an explicit SPDX identifier")
    for name in TEMPLATE_PANELS:
        if name in literals:
            if "<svg" not in literals[name]:
                _finding(findings, "error", "forge_panel_shape", relative,
                         f"{name} does not contain SVG markup")
            if not SPDX.search(literals[name][:500]):
                _finding(findings, "warning", "forge_panel_notice", relative,
                         f"{name}: generated panel should include an SPDX/provenance XML comment")
    for name in TEMPLATE_INTEGRATIONS:
        if name in literals:
            text = literals[name].lower()
            if "license" not in text and "attribution" not in text and "copyright" not in text:
                _finding(findings, "warning", "forge_integration_attribution", relative,
                         f"{name}: mention license and artwork/provenance review")


def _provenance(
    root: Path, checked: set[str], findings: list[dict[str, str]],
) -> int:
    inventory = {
        "LICENSE": ("GNU GENERAL PUBLIC LICENSE", "Version 3"),
        "docs/LICENSES.md": ("Cardinal", "Rack", "DPF"),
        "docs/LICENSE-PERMISSIONS.md": ("LICENSE PERMISSIONS",),
        "docs/MODULE_FORGE.md": ("licens", "attribution"),
        "README.md": ("DISTRHO/Cardinal", "VCV Rack", "DPF"),
    }
    for path, terms in inventory.items():
        content = _read_text(root, path, checked, findings)
        if content is not None:
            for term in terms:
                if term.lower() not in content.lower():
                    _finding(findings, "error", "attribution_pointer", path,
                             f"missing expected provenance/notice pointer: {term}")

    relative = ".gitmodules"
    content = _read_text(root, relative, checked, findings)
    if content is None:
        return 0
    config = configparser.ConfigParser(interpolation=None)
    try:
        config.read_string(content)
    except configparser.Error as exc:
        _finding(findings, "error", "gitmodules_syntax", relative, str(exc))
        return 0
    declared: set[str] = set()
    count = 0
    for section in sorted(config.sections()):
        if not section.startswith("submodule "):
            continue
        count += 1
        path = config.get(section, "path", fallback="").strip()
        url = config.get(section, "url", fallback="").strip()
        if not path or not url:
            _finding(findings, "error", "submodule_provenance", relative,
                     f"{section}: both path and upstream URL are required")
            continue
        if path in declared:
            _finding(findings, "error", "duplicate_submodule_path", relative,
                     f"duplicate path: {path}")
        declared.add(path)
    for essential in ("src/Rack", "dpf"):
        if essential not in declared:
            _finding(findings, "error", "upstream_pointer", relative,
                     f"expected upstream submodule provenance path: {essential}")
    if not any(path.startswith("plugins/") for path in declared):
        _finding(findings, "error", "thirdparty_pointer", relative,
                 "no bundled third-party module provenance paths were found")
    return count


def audit_repository(root: Path, *, strict: bool = False) -> dict[str, Any]:
    """Check only tracked attribution/first-party paths, never inherited sources."""
    root = Path(root)
    findings: list[dict[str, str]] = []
    checked: set[str] = set()
    slugs = _manifest(root, checked, findings)
    cpp_count, panel_count = _scan_first_party(root, slugs, checked, findings)
    _module_forge(root, checked, findings)
    submodules = _provenance(root, checked, findings)
    findings.sort(key=lambda item: (
        0 if item["level"] == "error" else 1, item["path"], item["code"], item["message"]
    ))
    errors = sum(item["level"] == "error" for item in findings)
    warnings = sum(item["level"] == "warning" for item in findings)
    return {
        "scope": "first-party code/panels, generator templates, manifest and inherited attribution pointers",
        "summary": {
            "passed": errors == 0 and (not strict or warnings == 0),
            "errors": errors, "warnings": warnings,
            "checked_files": len(checked),
            "first_party_models": len(slugs),
            "first_party_cpp_files": cpp_count,
            "first_party_svg_panels": panel_count,
            "upstream_submodule_pointers": submodules,
            "strict": strict,
        },
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--json", action="store_true", help="Deterministic machine-readable report")
    parser.add_argument("--strict", action="store_true", help="Also fail on advisory notice warnings")
    args = parser.parse_args(argv)
    if not args.repo_root.is_dir():
        print(f"ERROR: repository directory not found: {args.repo_root}", file=sys.stderr)
        return 2
    report = audit_repository(args.repo_root, strict=args.strict)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        status = "PASS" if report["summary"]["passed"] else "FAIL"
        count = report["summary"]
        print(
            f"{status}  license/provenance source preflight "
            f"({count['errors']} errors, {count['warnings']} warnings)"
        )
        print(
            f"  {count['first_party_models']} models; "
            f"{count['first_party_cpp_files']} C++/headers; "
            f"{count['first_party_svg_panels']} SVG panels; "
            f"{count['upstream_submodule_pointers']} submodule pointers"
        )
        for item in report["findings"]:
            print(f"  {item['level'].upper()} [{item['code']}] {item['path']}: {item['message']}")
    return 0 if report["summary"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
