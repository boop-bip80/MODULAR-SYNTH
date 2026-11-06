#!/usr/bin/env python3
"""Overlay source-verified jack centers on a first-party module's original SVG.

This is *static source-geometry evidence*, not a Rack/DAW screenshot. The
circles mark exact PJ301MPort widget centers from C++ callsites; their radius
is an illustration marker, NOT the hosted Rack widget footprint. The border
is the SVG viewBox. NanoVG runtime labels and hosted controls are not drawn.

Example:
    python3 tools/ui-check/jack_geometry_overlay.py --model MorphVCO \
        --output /tmp/MorphVCO-jack-centers.svg
"""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
import xml.etree.ElementTree as ET

from port_rail_audit import PORT_CALL, SVG_NS, ZONES, audit_panel


def make_overlay(repo: Path, model: str) -> ET.ElementTree:
    """Return original panel art plus a deterministic, source-backed overlay."""
    if model not in ZONES:
        raise ValueError(f"unsupported model {model!r}; choose from {', '.join(ZONES)}")

    # This existing audit verifies exact widget roles/IDs, their C++ centers,
    # source SVG rail placement and the decorative rings at those centers.
    audit_panel(repo, model)
    source = (repo / "plugins/ModularSynth/src" / f"{model}.cpp").read_text(encoding="utf-8")
    path = repo / "plugins/ModularSynth/res" / f"{model}.svg"
    tree = ET.parse(path)
    svg = tree.getroot()
    if svg.tag != SVG_NS + "svg":
        raise ValueError(f"{model}: missing SVG root")
    # XML preserves whitespace-only text nodes, including spaces on blank
    # lines. Remove only those spaces; preserve indentation around child tags
    # and any visible SVG label text.
    for element in svg.iter():
        for field in ("text", "tail"):
            value = getattr(element, field)
            if value is not None and not value.strip():
                setattr(element, field, re.sub(r"\n[ \t]+\n", "\n\n", value))
    try:
        left, top, width, height = (float(n) for n in svg.attrib["viewBox"].split())
    except (KeyError, ValueError) as error:
        raise ValueError(f"{model}: invalid viewBox") from error
    if not all(math.isfinite(n) for n in (left, top, width, height)) or width <= 0 or height <= 0:
        raise ValueError(f"{model}: invalid viewBox dimensions")

    callsites = {
        (match.group("role"), match.group("port")): (
            float(match.group("x")), float(match.group("y")))
        for match in PORT_CALL.finditer(source) if match.group("model") == model
    }
    expected = [(role, port) for rail in ZONES[model].values() for role, port, _ in rail]
    if len(callsites) != len(expected) or set(callsites) != set(expected):
        raise ValueError(f"{model}: jack center mapping incomplete or ambiguous")

    group = ET.SubElement(svg, SVG_NS + "g", {
        "id": "source-jack-geometry-overlay", "fill": "none",
        "stroke-width": "1.4", "pointer-events": "none",
    })
    ET.SubElement(group, SVG_NS + "title").text = f"{model}: static source jack geometry"
    ET.SubElement(group, SVG_NS + "desc").text = (
        "Centers are exact C++ PJ301MPort widget coordinates; circles are "
        "illustrative 3.5-unit markers, not Rack port sizes. Border is the "
        "original SVG viewBox. No runtime labels or host UI are represented."
    )
    ET.SubElement(group, SVG_NS + "rect", {
        "id": "source-panel-boundary", "x": f"{left:g}", "y": f"{top:g}",
        "width": f"{width:g}", "height": f"{height:g}",
        "stroke": "#ffe36b", "stroke-width": "2", "stroke-dasharray": "5 3",
    })
    for role, port in expected:
        x, y = callsites[(role, port)]
        if not (left <= x <= left + width and top <= y <= top + height):
            raise ValueError(f"{model}/{port}: source center outside SVG viewBox")
        circle = ET.SubElement(group, SVG_NS + "circle", {
            "cx": f"{x:g}", "cy": f"{y:g}", "r": "3.5",
            "stroke": "#54edff" if role == "Input" else "#ff88c7",
            "data-role": role, "data-port": port,
        })
        ET.SubElement(circle, SVG_NS + "title").text = (
            f"{role} {port}: C++ center ({x:g}, {y:g})"
        )
    return tree


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--model", choices=tuple(ZONES), default="MorphVCO")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    ET.register_namespace("", SVG_NS[1:-1])
    tree = make_overlay(args.root, args.model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(args.output, encoding="utf-8", xml_declaration=True)
    print(f"Wrote source geometry overlay: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
