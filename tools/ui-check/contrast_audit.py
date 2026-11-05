#!/usr/bin/env python3
"""Source-backed, advisory contrast audit for first-party Rack panels.

The audit reads NanoVG nvgRGB()/nvgText() calls and SVG paint colors. A ratio
for a solid SVG fill/stroke pair is a palette measurement, not a rendered
control hit-area or WCAG conformance result. Gradient/layered text underlays
remain UNKNOWN. Valid opaque gradient stops additionally give a conservative
contrast lower bound for the *base palette only*, not the rendered text layer.
"""
from __future__ import annotations

import argparse
from collections import Counter
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

MODULES = ("MorphVCO", "StateFilter", "FoldDrive", "Macro8", "StereoEcho",
           "ClockedLFO", "FMVoice", "ChanceHold", "DualVCA", "SlewGlide")
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


def opaque_base_gradient_stops(
    root: ET.Element, underlay_description: str
) -> list[tuple[int, int, int]] | None:
    """Validate opaque base-gradient stops for a *base-only* RGB envelope.

    This is deliberately NOT a local label-underlay detector. Extra SVG paths,
    circles and Rack controls can cover any label; their actual pixels remain
    UNKNOWN. A valid opaque gradient only bounds the color of the bottom layer.
    """
    match = re.fullmatch(r"gradient url\(#([^)]+)\) \(pixels not sampled\)",
                         underlay_description)
    if match is None:
        return None
    # Stylesheets/inherited styles can override source attributes.
    if any(_local_name(node.tag) in {"style", "script", "animate", "set"}
           for node in root.iter()):
        return None
    if any(root.get(key) is not None for key in
           ("style", "class", "filter", "opacity")):
        return None
    painted = [node for node in root if _local_name(node.tag) != "defs"]
    if not painted:
        return None
    base = painted[0]  # _svg_underlay has already checked full-panel geometry.
    if any(base.get(key) is not None for key in
           ("style", "class", "filter", "mask", "clip-path", "transform",
            "stroke", "mix-blend-mode")):
        return None
    if any(base.get(key, "1") not in ("1", "1.0") for key in
           ("opacity", "fill-opacity")):
        return None

    gradient_id = match.group(1)
    matched_ids = [node for node in root.iter()
                   if node.get("id") == gradient_id]
    if len(matched_ids) != 1:
        return None
    gradient = matched_ids[0]
    if _local_name(gradient.tag) not in ("linearGradient", "radialGradient"):
        return None
    if any(gradient.get(key) is not None for key in
           ("style", "class", "filter", "mask", "gradientTransform",
            "spreadMethod")):
        return None
    if any(_local_name(key) == "href" for key in gradient.attrib):
        return None
    if gradient.get("color-interpolation", "sRGB") != "sRGB":
        return None

    stops: list[tuple[int, int, int]] = []
    previous_offset = -1.0
    for stop in gradient:
        if _local_name(stop.tag) != "stop":
            return None
        if stop.get("style") is not None or stop.get("class") is not None or list(stop):
            return None
        if any(stop.get(key, "1") not in ("1", "1.0") for key in
               ("opacity", "stop-opacity")):
            return None
        color = rgb(stop.get("stop-color"))
        raw_offset = stop.get("offset", "").strip()
        try:
            offset = (float(raw_offset[:-1]) / 100.0 if raw_offset.endswith("%")
                      else float(raw_offset))
        except ValueError:
            return None
        if (color is None or not math.isfinite(offset) or
                offset < previous_offset or not 0.0 <= offset <= 1.0):
            return None
        previous_offset = offset
        stops.append(color)
    return stops if len(stops) >= 2 else None


def gradient_rgb_contrast_lower_bound(
    foreground: tuple[int, int, int],
    stops: list[tuple[int, int, int]],
) -> float | None:
    """Conservative *base-layer* ratio bound over sRGB stop interpolation.

    Every gradient pixel's RGB channels lie between the component-wise minima
    and maxima of opaque stops. Relative luminance is monotone in each channel,
    so the corresponding synthetic colors bound all base-gradient luminances.
    The bound is not a rendered/local contrast measurement; layered artwork,
    controls, antialiasing and font pixels are deliberately excluded.
    """
    if not stops:
        return None
    lower_rgb = tuple(min(c[index] for c in stops) for index in range(3))
    upper_rgb = tuple(max(c[index] for c in stops) for index in range(3))
    low_lum, high_lum = luminance(lower_rgb), luminance(upper_rgb)
    text_lum = luminance(foreground)
    if text_lum >= high_lum:
        return (text_lum + 0.05) / (high_lum + 0.05)
    if text_lum <= low_lum:
        return (low_lum + 0.05) / (text_lum + 0.05)
    return 1.0  # The palettes' luminance intervals overlap: no useful bound.


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
        # A sole rectangle is not necessarily a solid opaque underlay:
        # inherited CSS, per-paint alpha, blending or masks can invalidate
        # the ratio. Report UNKNOWN instead of certifying a swatch against it.
        inherited = any(node.get(key) is not None for node in (root, base)
                        for key in ("style", "class", "filter", "mask", "clip-path",
                                    "mix-blend-mode"))
        transformed = any(node.get("transform") is not None for node in (root, base))
        transparent = any(node.get(key, "1").strip() not in ("1", "1.0")
                          for node in (root, base)
                          for key in ("opacity", "fill-opacity"))
        css = any(_local_name(node.tag) in ("style", "script", "animate", "set")
                  for node in root.iter())
        if (len(painted) == 1 and not inherited and not transformed and
                not transparent and not css and base.get("stroke", "none") == "none"):
            return "known solid base", solid, []
        return "layered SVG artwork over solid base (or styled/nonopaque)", None, []

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


def _svg_outlines(root: ET.Element) -> tuple[
    Counter[tuple[tuple[int, int, int], tuple[int, int, int]]],
    Counter[tuple[str, str]]
]:
    """Collect measurable SVG fill/stroke pairs and explicitly unknown paints.

    A gradient-filled knob circle with a solid stroke is *not* a measurable
    local fill-vs-stroke ratio until actual rendering is sampled.
    """
    measured: Counter[tuple[tuple[int, int, int],
                            tuple[int, int, int]]] = Counter()
    unknown: Counter[tuple[str, str]] = Counter()

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
            f, edge = rgb(fill), rgb(stroke)
            if f is not None and edge is not None:
                measured[(f, edge)] += 1
            elif fill is not None and stroke is not None:
                unknown[(fill, stroke)] += 1
        for child in element:
            walk(child, fill, stroke, transparent)

    walk(root, None, None, False)
    return measured, unknown

def audit(repo_root: Path) -> tuple[list[str], list[str], dict[str, int]]:
    lines: list[str] = []
    errors: list[str] = []
    stats = {"labels": 0, "unknown_labels": 0, "measured_labels": 0,
             "gradient_base_bounds": 0, "weak_gradient_base_bounds": 0,
             "outlines": 0, "unknown_outlines": 0,
             "low_labels": 0, "low_outlines": 0}
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
        opaque_stops = opaque_base_gradient_stops(svg_root, underlay)
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
                if opaque_stops is not None:
                    bound = gradient_rgb_contrast_lower_bound(fore, opaque_stops)
                    if bound is not None:
                        stats["gradient_base_bounds"] += 1
                        stats["weak_gradient_base_bounds"] += int(bound < TEXT_ADVISORY)
                        swatch_info += (f"; opaque base-gradient lower bound "
                                        f"≥{bound:.2f}:1 (base layer only; "
                                        "local contrast UNKNOWN)")
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

        measured, unknown = _svg_outlines(svg_root)
        for (fill, stroke), count in sorted(measured.items()):
            ratio = contrast_ratio(fill, stroke)
            low = ratio < OUTLINE_ADVISORY
            stats["outlines"] += count
            stats["low_outlines"] += count if low else 0
            flag = "WARN SVG OUTLINE" if low else "SVG OUTLINE"
            lines.append(f"  {flag} {hex_color(stroke)} vs fill {hex_color(fill)}: "
                         f"{ratio:.2f}:1 (x{count}; advisory {OUTLINE_ADVISORY:g}:1)")
        for (fill, stroke), count in sorted(unknown.items()):
            stats["unknown_outlines"] += count
            lines.append(
                f"  UNKNOWN SVG OUTLINE {stroke} vs fill {fill} (x{count}): "
                "non-solid paint; local contrast not measured"
            )
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
        f"{stats['gradient_base_bounds']} source-only gradient-base bounds "
        f"({stats['weak_gradient_base_bounds']} inconclusive under {TEXT_ADVISORY:g}:1); "
        f"{stats['measured_labels']} measured text swatches; "
        f"{stats['outlines']} measured SVG outline shapes; "
        f"{stats['unknown_outlines']} UNKNOWN SVG outline shapes; "
        f"{stats['low_labels']} low text and {stats['low_outlines']} low outline swatches"
    )
    print("NOTE: gradient bounds constrain only opaque SVG base colors, not "
          "overlaid artwork or actual label pixels. Swatch ratios are advisory; "
          "no rendered contrast, overlap, font sizing, control visibility or "
          "WCAG conformance is claimed.")
    if args.fail_on_low_contrast and (stats["low_labels"] or stats["low_outlines"]):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
