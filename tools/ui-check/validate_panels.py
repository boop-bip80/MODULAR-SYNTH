#!/usr/bin/env python3
"""Conservative source-level checks for the three MODULAR-SYNTH SVG panels.

Not a renderer: verifies XML, Rack 3U geometry, the exact panel asset used by
each widget, and the centers of statically resolvable centered controls. It
does not determine visual overlap, hit boxes, labels, fonts or display output.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

# Rack's panel coordinate grid is 15 px/HP by 380 px high. The shipped SVGs
# declare conventional Eurorack physical dimensions (5.08 mm/HP, 128.5 mm/3U).
PANELS = {"MorphVCO": 12, "StateFilter": 14, "Macro8": 20}
SVG_NS = "{http://www.w3.org/2000/svg}svg"
GRID_PX_PER_HP = 15.0
GRID_HEIGHT_PX = 380.0
HP_MM = 5.08
HEIGHT_3U_MM = 128.5
NUM = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
CSS_LENGTH = re.compile(rf"^\s*({NUM})\s*(mm|cm|in|pt|pc|px)?\s*$")
CPP_FLOAT = re.compile(rf"^{NUM}[fF]?$")
ARRAY = re.compile(
    r"\b(?:constexpr|const)\s+float\s+(\w+)\s*\[\s*(\d+)\s*\]\s*"
    r"=\s*\{([^{}]*)\}\s*;", re.S
)
SCALAR = re.compile(r"\b(?:constexpr|const)\s+float\s+(\w+)\s*=\s*([^;]+);")
ARRAY_ACCESS = re.compile(r"^(\w+)\s*\[\s*([^\]]+)\s*\]$")
CONTROL = re.compile(r"\bcreate(?P<kind>Param|Input|Output|Light)Centered\s*<")
VEC = re.compile(r"\bVec\s*\(\s*([^,()]+?)\s*,\s*([^,()]+?)\s*\)")
PANEL_ASSET = re.compile(
    r"setPanel\s*\(\s*APP\s*->\s*window\s*->\s*loadSvg\s*\(\s*"
    r'asset::plugin\s*\(\s*pluginInstance\s*,\s*"([^"]+)"\s*\)'
    r"\s*\)\s*\)", re.S
)
WIDGET_START = re.compile(r"\bstruct\s+ModularSynth(\w+)Widget\s*:\s*ModuleWidget\b")


def _finite(value: float) -> bool:
    return math.isfinite(value)


def _near(a: float, b: float) -> bool:
    # Allows harmless SVG decimal rounding, but not a wrong rack/grid size.
    return abs(a - b) <= max(0.05, abs(b) * 0.001)


def _length_ok(raw: str | None, expected_mm: float, expected_px: float) -> bool:
    if raw is None:
        return False
    match = CSS_LENGTH.fullmatch(raw)
    if not match:
        return False
    number = float(match.group(1))
    if not _finite(number) or number <= 0:
        return False
    unit = match.group(2) or "px"
    if unit == "px":
        return _near(number, expected_px)
    mm_per_unit = {"mm": 1.0, "cm": 10.0, "in": 25.4,
                   "pt": 25.4 / 72.0, "pc": 25.4 / 6.0}[unit]
    return _near(number * mm_per_unit, expected_mm)


def _check_svg(svg_path: Path, model: str, hp: int) -> list[str]:
    errors: list[str] = []
    if not svg_path.is_file():
        return [f"{svg_path}: missing panel SVG"]
    try:
        root = ET.parse(svg_path).getroot()
    except (ET.ParseError, OSError, ValueError) as exc:
        return [f"{svg_path}: invalid SVG/XML: {exc}"]
    if root.tag != SVG_NS:
        errors.append(f"{svg_path}: root must be namespaced SVG <svg>")
        return errors

    width_px = hp * GRID_PX_PER_HP
    if not _length_ok(root.get("width"), hp * HP_MM, width_px):
        errors.append(
            f"{svg_path}: width {root.get('width')!r} is not {hp}HP "
            f"({hp * HP_MM:g}mm or {width_px:g}px)"
        )
    if not _length_ok(root.get("height"), HEIGHT_3U_MM, GRID_HEIGHT_PX):
        errors.append(
            f"{svg_path}: height {root.get('height')!r} is not "
            f"3U ({HEIGHT_3U_MM:g}mm or {GRID_HEIGHT_PX:g}px)"
        )

    view_box = root.get("viewBox")
    parts = re.split(r"[\s,]+", view_box.strip()) if view_box else []
    if len(parts) != 4:
        errors.append(f"{svg_path}: viewBox must be '0 0 {width_px:g} 380'")
    else:
        try:
            values = [float(part) for part in parts]
        except ValueError:
            values = []
        if len(values) != 4 or not all(_finite(value) for value in values):
            errors.append(f"{svg_path}: viewBox contains invalid numbers")
        elif any(not _near(got, want) for got, want in
                 zip(values, (0.0, 0.0, width_px, GRID_HEIGHT_PX))):
            errors.append(
                f"{svg_path}: viewBox {view_box!r} is not "
                f"'0 0 {width_px:g} {GRID_HEIGHT_PX:g}'"
            )
    return errors


def _cpp_number(raw: str) -> float | None:
    raw = raw.strip()
    if not CPP_FLOAT.fullmatch(raw):
        return None
    value = float(raw.rstrip("fF"))
    return value if _finite(value) else None


def _resolve(expr: str, arrays: dict[str, tuple[float, ...]],
             scalars: dict[str, tuple[float, ...]]) -> tuple[float, ...] | None:
    expr = expr.strip()
    number = _cpp_number(expr)
    if number is not None:
        return (number,)
    if expr in scalars:
        return scalars[expr]
    access = ARRAY_ACCESS.fullmatch(expr)
    if access:
        name, index_expr = access.groups()
        numbers = arrays.get(name)
        if not numbers:
            return None
        if index_expr.strip().isdigit():
            index = int(index_expr.strip())
            return (numbers[index],) if index < len(numbers) else None
        # Loop-dependent array index: conservatively check every element.
        return numbers
    if "?" in expr and ":" in expr:
        # Only handle a simple constant-valued C++ conditional.
        _, alternatives = expr.split("?", 1)
        left, right = alternatives.split(":", 1)
        a = _resolve(left, arrays, scalars)
        b = _resolve(right, arrays, scalars)
        if a is not None and b is not None:
            return a + b
    return None


def _constants(widget: str) -> tuple[dict[str, tuple[float, ...]],
                                     dict[str, tuple[float, ...]]]:
    arrays: dict[str, tuple[float, ...]] = {}
    for match in ARRAY.finditer(widget):
        name, raw_length, initializer = match.groups()
        pieces = [part.strip() for part in initializer.split(",") if part.strip()]
        numbers = [_cpp_number(part) for part in pieces]
        if len(numbers) == int(raw_length) and all(n is not None for n in numbers):
            arrays[name] = tuple(n for n in numbers if n is not None)

    scalars: dict[str, tuple[float, ...]] = {}
    for match in SCALAR.finditer(widget):
        name, expr = match.groups()
        resolved = _resolve(expr, arrays, scalars)
        if resolved is not None:
            scalars[name] = resolved
    return arrays, scalars


def _check_widget(source_path: Path, model: str, hp: int
                  ) -> tuple[list[str], list[str], int]:
    if not source_path.is_file():
        return [f"{source_path}: missing widget source"], [], 0
    try:
        source = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{source_path}: unreadable widget source: {exc}"], [], 0

    errors: list[str] = []
    notes: list[str] = []
    expected_asset = f"res/{model}.svg"
    assets = PANEL_ASSET.findall(source)
    if assets != [expected_asset]:
        errors.append(
            f"{source_path}: expected exactly one setPanel() loading "
            f"{expected_asset!r}; found {assets!r}"
        )

    widget = WIDGET_START.search(source)
    if widget is None or widget.group(1) != model:
        return errors + [f"{source_path}: missing ModularSynth{model}Widget"], notes, 0
    # Controls are declared in the Widget constructor before draw(). This
    # intentionally ignores fallback HEADLESS widgets and decorative screws.
    end = source.find("void draw(", widget.end())
    body = source[widget.start():end] if end > widget.end() else source[widget.start():]
    arrays, scalars = _constants(body)
    width = hp * GRID_PX_PER_HP
    count = 0
    sites = 0
    for match in CONTROL.finditer(body):
        sites += 1
        after = body[match.end():body.find(";", match.end())]
        position = VEC.search(after)
        line = source[:widget.start()].count("\n") + body[:match.start()].count("\n") + 1
        if position is None:
            notes.append(f"{source_path}:{line}: {match.group('kind')} center not statically parsed")
            continue
        xs = _resolve(position.group(1), arrays, scalars)
        ys = _resolve(position.group(2), arrays, scalars)
        if xs is None or ys is None:
            notes.append(
                f"{source_path}:{line}: {match.group('kind')} center has "
                f"dynamic expression Vec({position.group(1)}, {position.group(2)}); skipped"
            )
            continue
        for x in xs:
            for y in ys:
                count += 1
                if not (0.0 <= x <= width and 0.0 <= y <= GRID_HEIGHT_PX):
                    errors.append(
                        f"{source_path}:{line}: {match.group('kind')} center "
                        f"({x:g}, {y:g}) outside {width:g}x{GRID_HEIGHT_PX:g} panel"
                    )
    if sites == 0:
        errors.append(f"{source_path}: no centered knob/jack/switch/light creation found")
    if count == 0:
        errors.append(f"{source_path}: no statically resolvable centered controls")
    return errors, notes, count


def validate_repository(repo_root: Path) -> tuple[list[str], list[str], int]:
    errors: list[str] = []
    notes: list[str] = []
    checked = 0
    base = repo_root / "plugins" / "ModularSynth"
    for model, hp in PANELS.items():
        errors.extend(_check_svg(base / "res" / f"{model}.svg", model, hp))
        issues, info, count = _check_widget(base / "src" / f"{model}.cpp", model, hp)
        errors.extend(issues)
        notes.extend(info)
        checked += count
    return errors, notes, checked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate original MODULAR-SYNTH SVG geometry and "
                    "statically extractable Rack widget centers."
    )
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2],
        help="repository root (default: inferred from script path)"
    )
    args = parser.parse_args(argv)
    errors, notes, checked = validate_repository(args.root.resolve())
    for note in notes:
        print(f"NOTE: {note}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAIL: {len(errors)} panel validation error(s)", file=sys.stderr)
        return 1
    print(
        f"PASS: {len(PANELS)} SVG panels, Rack 3U/HP geometry, source asset "
        f"links and {checked} conservative candidate widget centers checked"
    )
    print("NOTE: source-level checks only; visual rendering/overlap not verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
