#!/usr/bin/env python3
"""Source-only check of Macro8's five-scene recall rail.

Unlike the plug-in GUI, this can measure only literal SVG paint and the
checked-in positions/label palette. It cannot establish the rendered NanoVG
text's contrast, the Rack LED widget's dimensions, or input ergonomics.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from contrast_audit import HEX_RGB_CALL, contrast_ratio, rgb
from port_rail_audit import direct_rect, _inside, SVG_NS

SLOTS = re.compile(r"constexpr float slots\[5\]\s*=\s*\{([^{}]+)\}")
LABELS = re.compile(r'constexpr const char\* labels\[5\]\s*=\s*\{\s*"A"\s*,\s*"B"\s*,\s*"C"\s*,\s*"D"\s*,\s*"LIVE"\s*\}')


def audit_scene(root: Path) -> str:
    source = (root / "plugins/ModularSynth/src/Macro8.cpp").read_text(encoding="utf-8")
    svg = ET.parse(root / "plugins/ModularSynth/res/Macro8.svg").getroot()
    if svg.tag != SVG_NS + "svg":
        raise ValueError("Macro8: expected namespaced SVG root")
    dock = direct_rect(svg, "macroSceneRail")
    try:
        box = tuple(float(dock.get(a, "nan")) for a in ("x", "y", "width", "height"))
        stroke_width = float(dock.get("stroke-width", "nan"))
    except ValueError as error:
        raise ValueError("Macro8: bad scene dock geometry") from error
    if (not all(math.isfinite(n) for n in (*box, stroke_width)) or
            box[2] <= 0 or box[3] <= 0 or stroke_width < 1.5):
        raise ValueError("Macro8: invalid scene dock dimensions/border")
    fill, stroke = rgb(dock.get("fill")), rgb(dock.get("stroke"))
    if fill is None or stroke is None:
        raise ValueError("Macro8: scene dock needs literal opaque RGB colors")
    frame = contrast_ratio(fill, stroke)
    if frame < 3:
        raise ValueError(f"Macro8: scene dock frame/fill palette {frame:.2f}:1 below 3:1")

    definitions = SLOTS.findall(source)
    if len(definitions) != 2:
        raise ValueError("Macro8: expected matching widget and NanoVG scene slot arrays")
    try:
        slot_arrays = [tuple(float(s.strip().rstrip("fF")) for s in raw.split(","))
                       for raw in definitions]
    except ValueError as error:
        raise ValueError("Macro8: bad scene slot coordinate") from error
    if (len(slot_arrays[0]) != 5 or slot_arrays[0] != slot_arrays[1] or
            not all(math.isfinite(x) for x in slot_arrays[0])):
        raise ValueError("Macro8: scene widget/label columns drifted")
    if not LABELS.search(source):
        raise ValueError("Macro8: A/B/C/D/LIVE label contract missing")
    # Bind the color to the actual label draw call, not an earlier heading.
    label_match = re.search(
        r'nvgFillColor\s*\(\s*args\.vg\s*,\s*nvgRGB\([^;]+;\s*'
        r'constexpr float slots\[5\][^;]+;\s*'
        r'constexpr const char\* labels\[5\][^;]+;\s*'
        r'for\s*\(int i = 0; i < 5; \+\+i\)\s*'
        r'nvgText\(args\.vg, slots\[i\], 304, labels\[i\], nullptr\);',
        source, re.S)
    if label_match is None:
        raise ValueError("Macro8: NanoVG scene label placement/palette is not statically verified")
    color_call = HEX_RGB_CALL.search(label_match.group())
    if color_call is None:
        raise ValueError("Macro8: scene label color not literal")
    text_color = tuple(int(s, 16) for s in color_call.groups())
    label_ratio = contrast_ratio(fill, text_color)
    if label_ratio < 4.5:
        raise ValueError(f"Macro8: scene label palette {label_ratio:.2f}:1 below 4.5:1")
    if "Vec(slots[i], 329)" not in source or "Vec(slots[4], 329)" not in source:
        raise ValueError("Macro8: A/B/C/D/LIVE scene button placements changed")
    if "Vec(slots[i], 350)" not in source or "Vec(slots[4], 350)" not in source:
        raise ValueError("Macro8: A/B/C/D/LIVE scene LED placements changed")

    for x in slot_arrays[0]:
        for y, radius in ((329.0, 17.0), (350.0, 4.0)):
            circles = [node for node in svg.iter() if node.tag == SVG_NS + "circle" and
                       float(node.get("cx", "nan")) == x and
                       float(node.get("cy", "nan")) == y and
                       float(node.get("r", "nan")) == radius]
            if len(circles) != 1 or not _inside(box, x, y, radius + 1):
                raise ValueError(f"Macro8: scene {x:g}/{y:g} decoration absent or dock-clipped")
    return (f"Macro8/macroSceneRail: five aligned A/B/C/D/LIVE controls; "
            f"frame {frame:.2f}:1; labels {label_ratio:.2f}:1 (source palette)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    try:
        print(audit_scene(args.root))
    except (OSError, ValueError, ET.ParseError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: one Macro8 scene dock, five controls; rendered Rack overlap unverified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
