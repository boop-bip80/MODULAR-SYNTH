#!/usr/bin/env python3
"""Source-backed, advisory contrast audit for first-party Rack panels.

The audit reads NanoVG nvgRGB()/nvgText() calls and SVG paint colors. A ratio
for a solid SVG fill/stroke pair is a palette measurement, not a rendered
control hit-area or WCAG conformance result. Gradient/layered text underlays
are UNKNOWN; stop-color swatches are merely reference comparisons.
"""
from __future__ import annotations

import argparse
from collections import Counter
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

MODULES = ("MorphVCO", "StateFilter", "Macro8")
TEXT_ADVISORY = 4.5
OUTLINE_ADVISORY = 3.0
COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
HEX_RGB_CALL = re.compile(
    r"nvgRGB\s*\(\s*0x([0-9a-fA-F]{2})\s*,\s*"
    r"0x([0-9a-fA-F]{2})\s*,\s*0x([0-9a-fA-F]{2})\s*\)"
)
DRAW = re.compile(r"\bvoid\s+draw\s*\(\s*const\s+DrawArgs\s*&\s*args\s*\)\s*override")
CALL = re.compile(r"\bnvg(?:FillColor|FontSize|Text)\s*\([^;]*?\)\s*;", re.S)
TEXT_CALL = re.compile(
    r"\bnvgText\s*\(\s*args\.vg\s*,\s*([^,]+),\s*([^,]+),\s*"
    r"(.+),\s*nullptr\s*\)\s*;", re.S
)
FONT_CALL = re.compile(r"\bnvgFontSize\s*\(\s*args\.vg\s*,\s*([^,)]+)\s*\)")
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?[fF]?")


def rgb(raw: str | None) -> tuple[int, int, int] | None:
    if raw is None or not COLOR.fullmatch(raw.strip()):
        return None
    value = raw.strip()[1:]
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def hex_color(color: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02X}" for channel in color)


def luminance(color: tuple[int, int, int]) -> float:
    def linear(channel: int) -> float:
        s = channel / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
    return (0.2126 * linear(color[0]) +
            0.7152 * linear(color[1]) +
            0.0722 * linear(color[2]))


def contrast_ratio(a: tuple[int, int, int],
                   b: tuple[int, int, int]) -> float:
    bright, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (bright + 0.05) / (dark + 0.05)


def cpp_number(raw: str) -> float | None:
    raw = raw.strip()
    if not NUMBER.fullmatch(raw):
        return None
    value = float(raw.rstrip("fF"))
    return value if math.isfinite(value) else None


def _local_name(tag: str) -> str:
    return tag.split("}")[-1]


def extract_labels(source: str) -> list[dict[str, object]]:
    draw = DRAW.search(source)
    if draw is None:
        raise ValueError("no ModuleWidget::draw(const DrawArgs&) override")
    ends = [source.find(token, draw.end()) for token in
            ("void appendContextMenu", "#else")]
    ends = [offset for offset in ends if offset >= 0]
    body = source[draw.start():min(ends)] if ends else source[draw.start():]

    current_color: tuple[int, int, int] | None = None
    font_size: float | None = None
    labels: list[dict[str, object]] = []
    for call in CALL.finditer(body):
        text = call.group()
        if text.startswith("nvgFillColor"):
            parsed = HEX_RGB_CALL.search(text)
            current_color = (tuple(int(x, 16) for x in parsed.groups())
                             if parsed else None)
        elif text.startswith("nvgFontSize"):
            parsed = FONT_CALL.search(text)
            font_size = cpp_number(parsed.group(1)) if parsed else None
        elif text.startswith("nvgText"):
            parsed = TEXT_CALL.search(text)
            if parsed is None:
                # An unfamiliar draw expression is unknown rather than
                # silently skipped as a contrast pass.
                labels.append({"name": "<unparsed nvgText>", "color": current_color,
                               "size": font_size, "position": None})
                continue
            x, y, name = (part.strip() for part in parsed.groups())
            if len(name) >= 2 and name.startswith('"') and name.endswith('"'):
                display = name[1:-1]
            else:
                display = "<dynamic: " + name[:45] + ">"
            px, py = cpp_number(x), cpp_number(y)
            labels.append({"name": display, "color": current_color,
                           "size": font_size,
                           "position": (px, py) if px is not None and py is not None else None})
    if not labels:
        raise ValueError("no nvgText() draw labels located")
    return labels


def _svg_underlay(root: ET.Element) -> tuple[str, tuple[int, int, int] | None,
                                                list[tuple[int, int, int]]]:
    """Resolve a full-panel solid base only if no other SVG paint layers exist."""
    painted = [node for node in root if _local_name(node.tag) != "defs"]
    if not painted or _local_name(painted[0].tag) != "rect":
        return "no recognizable full-panel rectangle", None, []
    base = painted[0]
    try:
        _, _, width, height = (float(part) for part in
                               re.split(r"[\s,]+", root.attrib["viewBox"].strip()))
        x = float(base.get("x", "0"))
        y = float(base.get("y", "0"))
        w = float(base.attrib["width"])
        h = float(base.attrib["height"])
    except (ValueError, KeyError):
        return "base rectangle dimensions unparseable", None, []
    if not all(math.isfinite(v) for v in (width, height, x, y, w, h)):
        return "nonfinite base geometry", None, []
    if x != 0 or y != 0 or w != width or h != height:
        return "no known full-panel base rectangle", None, []

    paint = base.get("fill", "")
    solid = rgb(paint)
    if solid is not None:
        if len(painted) == 1 and base.get("opacity", "1") == "1":
            return "known solid base", solid, []
        return "layered SVG artwork over solid base", None, []

    gradient = re.fullmatch(r"url\(#([^)]+)\)", paint)
    if gradient is not None:
        colors: list[tuple[int, int, int]] = []
        for node in root.iter():
            if (node.get("id") == gradient.group(1) and
                    _local_name(node.tag) in {"linearGradient", "radialGradient"}):
                for stop in node:
                    if _local_name(stop.tag) == "stop":
                        parsed = rgb(stop.get("stop-color"))
                        if parsed is not None:
                            colors.append(parsed)
        return f"gradient url(#{gradient.group(1)}) (pixels not sampled)", None, colors
    return f"unresolved base fill {paint!r}", None, []


def _solid_outlines(root: ET.Element) -> Counter[tuple[tuple[int, int, int],
                                                      tuple[int, int, int]]]:
    """Collect explicit SVG circle/rect fill-vs-stroke swatches, with inheritance."""
    result: Counter[tuple[tuple[int, int, int],
                          tuple[int, int, int]]] = Counter()

    def walk(element: ET.Element, fill: str | None, stroke: str | None,
             transparent: bool) -> None:
        fill = element.get("fill", fill)
        stroke = element.get("stroke", stroke)
        opacity = [element.get(key) for key in
                   ("opacity", "fill-opacity", "stroke-opacity")]
        if any(value is not None and value.strip() != "1" for value in opacity):
            transparent = True
        if element.get("style"):
            # CSS styles can override inherited attributes; do not guess.
            transparent = True
        if _local_name(element.tag) in {"circle", "rect"} and not transparent:
            f, s = rgb(fill), rgb(stroke)
            if f is not None and s is not None:
                result[(f, s)] += 1
        for child in element:
            walk(child, fill, stroke, transparent)

    walk(root, None, None, False)
    return result


def audit(repo_root: Path) -> tuple[list[str], list[str], dict[str, int]]:
    lines: list[str] = []
    errors: list[str] = []
    stats = {"labels": 0, "unknown_labels": 0, "measured_labels": 0,
             "outlines": 0, "low_labels": 0, "low_outlines": 0}
    collection = repo_root / "plugins" / "ModularSynth"
    for model in MODULES:
        svg_path = collection / "res" / f"{model}.svg"
        source_path = collection / "src" / f"{model}.cpp"
        try:
            svg_root = ET.parse(svg_path).getroot()
            if _local_name(svg_root.tag) != "svg":
                raise ValueError("root is not SVG")
            labels = extract_labels(source_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ET.ParseError, ValueError) as exc:
            errors.append(f"{model}: unable to audit {svg_path} / {source_path}: {exc}")
            continue

        underlay, solid, stops = _svg_underlay(svg_root)
        lines.append(f"[{model}] label underlay: {underlay}")
        for label in labels:
            stats["labels"] += 1
            name = str(label["name"])
            fore = label["color"]
            if not isinstance(fore, tuple):
                lines.append(f"  UNKNOWN TEXT {name}: NanoVG foreground not a static nvgRGB")
                stats["unknown_labels"] += 1
                continue
            foreground = hex_color(fore)
            if solid is None or label["position"] is None:
                swatch_info = ""
                if stops:
                    ratios = [contrast_ratio(fore, stop) for stop in stops]
                    swatch_info = (f"; gradient-stop swatches {min(ratios):.2f}"
                                   f"–{max(ratios):.2f}:1 (not local contrast)")
                reason = underlay if solid is None else "dynamic label coordinates"
                lines.append(f"  UNKNOWN TEXT {name} {foreground}: {reason}{swatch_info}")
                stats["unknown_labels"] += 1
                continue
            ratio = contrast_ratio(fore, solid)
            stats["measured_labels"] += 1
            low = ratio < TEXT_ADVISORY
            stats["low_labels"] += int(low)
            flag = "WARN TEXT" if low else "MEASURED TEXT"
            lines.append(f"  {flag} {name} {foreground} vs {hex_color(solid)}: "
                         f"{ratio:.2f}:1 (advisory {TEXT_ADVISORY:g}:1)")

        for (fill, stroke), count in sorted(_solid_outlines(svg_root).items()):
            ratio = contrast_ratio(fill, stroke)
            low = ratio < OUTLINE_ADVISORY
            stats["outlines"] += count
            stats["low_outlines"] += count if low else 0
            flag = "WARN SVG OUTLINE" if low else "SVG OUTLINE"
            lines.append(f"  {flag} {hex_color(stroke)} vs fill {hex_color(fill)}: "
                         f"{ratio:.2f}:1 (x{count}; advisory {OUTLINE_ADVISORY:g}:1)")
    return lines, errors, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Advisory source-color/contrast audit; does not render SVG or certify WCAG"
    )
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2],
        help="repository root (inferred from script location by default)"
    )
    parser.add_argument(
        "--fail-on-low-contrast", action="store_true",
        help="exit 2 for measured text or decorative SVG outline swatches below advisory ratios"
    )
    args = parser.parse_args(argv)
    lines, errors, stats = audit(args.root.resolve())
    for line in lines:
        print(line)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"SUMMARY: {len(MODULES)} panels; {stats['labels']} nvgText sites; "
        f"{stats['unknown_labels']} UNKNOWN label backgrounds/positions; "
        f"{stats['measured_labels']} measured text swatches; "
        f"{stats['outlines']} SVG outline shapes; "
        f"{stats['low_labels']} low text and {stats['low_outlines']} low outline swatches"
    )
    print("NOTE: swatch ratios are advisory; no rendered contrast, overlap, "
          "font sizing, control visibility or WCAG conformance is claimed.")
    if args.fail_on_low_contrast and (stats["low_labels"] or stats["low_outlines"]):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
