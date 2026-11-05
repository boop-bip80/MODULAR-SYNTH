#!/usr/bin/env python3
"""Source-backed audit of solid input/output zones on two original panels.

The geometry comes from the actual Rack PJ301MPort widget callsites; the
labels and foreground colors come from the NanoVG draw override. Measurements
are SVG/NanoVG source palette ratios, NOT sampled host pixels or a WCAG claim.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from contrast_audit import contrast_ratio, extract_labels, rgb


PORT_CALL = re.compile(
    r"\badd(?P<role>Input|Output)\s*\(\s*"
    r"create(?P=role)Centered<PJ301MPort>\s*\(\s*Vec\(\s*"
    r"(?P<x>\d+(?:\.\d+)?)f?\s*,\s*(?P<y>\d+(?:\.\d+)?)f?\s*\)"
    r"\s*,\s*module\s*,\s*ModularSynth(?P<model>\w+)::"
    r"(?P<port>[A-Z][A-Z0-9_]+)\s*\)\s*\)"
)

# Only the actual signal-path jacks are covered: the panels' other decorative
# knob rings remain subject to the existing broad contrast advisory.
ZONES: dict[str, dict[str, tuple[tuple[str, str, str], ...]]] = {
    "DualVCA": {
        "dualInputRail": (
            ("Input", "AUDIO_A_INPUT", "A IN"),
            ("Input", "CV_A_INPUT", "A CV"),
            ("Input", "AUDIO_B_INPUT", "B IN"),
            ("Input", "CV_B_INPUT", "B CV"),
        ),
        "dualOutputRail": (
            ("Output", "AUDIO_A_OUTPUT", "A"),
            ("Output", "AUDIO_B_OUTPUT", "B"),
            ("Output", "SUM_OUTPUT", "SUM"),
        ),
    },
    "StereoEcho": {
        "echoInputRail": (
            ("Input", "LEFT_INPUT", "IN L"),
            ("Input", "RIGHT_INPUT", "IN R"),
            ("Input", "TIME_CV_INPUT", "TIME CV"),
            ("Input", "FEEDBACK_CV_INPUT", "FB CV"),
        ),
        # MIX CV is an input even though its socket is beside the outputs.
        "echoMixCvRail": (("Input", "MIX_CV_INPUT", "MIX CV"),),
        "echoOutputRail": (
            ("Output", "LEFT_OUTPUT", "L OUT"),
            ("Output", "RIGHT_OUTPUT", "R OUT"),
        ),
    },
}
SVG_NS = "{http://www.w3.org/2000/svg}"
MIN_FRAME_RATIO = 3.0
MIN_LABEL_RATIO = 4.5
PORT_INSET = 13.0
LABEL_INSET = 5.0


def direct_rect(root: ET.Element, identifier: str) -> ET.Element:
    found = [n for n in root if n.tag == SVG_NS + "rect" and n.get("id") == identifier]
    if len(found) != 1:
        raise ValueError(f"{identifier}: expected exactly one direct solid rail rectangle")
    rect = found[0]
    if any(rect.get(attr) is not None for attr in (
        "style", "class", "transform", "filter", "mask", "clip-path",
        "opacity", "fill-opacity", "stroke-opacity"
    )):
        raise ValueError(f"{identifier}: styled/transformed/translucent rail not statically measurable")
    return rect


def _inside(rect: tuple[float, float, float, float],
            x: float, y: float, inset: float) -> bool:
    left, top, width, height = rect
    return (left + inset <= x <= left + width - inset and
            top + inset <= y <= top + height - inset)


def audit_panel(root: Path, model: str) -> list[str]:
    source_path = root / "plugins" / "ModularSynth" / "src" / (model + ".cpp")
    svg_path = root / "plugins" / "ModularSynth" / "res" / (model + ".svg")
    source = source_path.read_text(encoding="utf-8")
    svg = ET.parse(svg_path).getroot()
    if svg.tag != SVG_NS + "svg":
        raise ValueError(f"{model}: expected SVG root namespace")

    callsites = [m for m in PORT_CALL.finditer(source) if m.group("model") == model]
    expected = {f"{role}:{port}": (zone_id, label)
                for zone_id, ports in ZONES[model].items()
                for role, port, label in ports}
    observed = {f"{m.group('role')}:{m.group('port')}": m for m in callsites}
    if len(callsites) != len(observed) or set(observed) != set(expected):
        raise ValueError(
            f"{model}: port roles/IDs mismatch; missing={sorted(set(expected) - set(observed))}, "
            f"unexpected={sorted(set(observed) - set(expected))}"
        )

    labels = extract_labels(source)
    records: list[str] = []
    for zone_id, ports in ZONES[model].items():
        rect = direct_rect(svg, zone_id)
        try:
            box = tuple(float(rect.get(attr, "")) for attr in ("x", "y", "width", "height"))
            width = float(rect.get("stroke-width", ""))
        except ValueError as error:
            raise ValueError(f"{model}/{zone_id}: invalid geometry") from error
        if not all(math.isfinite(num) for num in (*box, width)) or (
            box[2] <= 0 or box[3] <= 0 or width < 1.5
        ):
            raise ValueError(f"{model}/{zone_id}: invalid rail dimensions or thin border")
        fill, border = rgb(rect.get("fill")), rgb(rect.get("stroke"))
        if fill is None or border is None:
            raise ValueError(f"{model}/{zone_id}: rail must use literal opaque RGB colors")
        frame_ratio = contrast_ratio(fill, border)
        if frame_ratio < MIN_FRAME_RATIO:
            raise ValueError(f"{model}/{zone_id}: border/fill {frame_ratio:.2f}:1 "
                             f"below {MIN_FRAME_RATIO:.1f}:1 source-palette advisory")

        label_ratios = []
        for role, port, text in ports:
            match = observed[f"{role}:{port}"]
            x, y = float(match.group("x")), float(match.group("y"))
            if not _inside(box, x, y, PORT_INSET):
                raise ValueError(f"{model}/{zone_id}: {role}:{port} "
                                 f"center ({x:g}, {y:g}) outside {PORT_INSET:g}px-inset rail")
            # The decorative rings are behind real Rack ports; enforce their
            # centers and full circumferences stay inside the corresponding lane.
            rings = [n for n in svg.iter() if n.tag == SVG_NS + "circle" and
                     float(n.get("cx", "nan")) == x and float(n.get("cy", "nan")) == y]
            if len(rings) != 1:
                raise ValueError(f"{model}/{zone_id}: {port} missing unique jack ring")
            ring = rings[0]
            try:
                radius = float(ring.get("r", "nan"))
                outline = float(ring.get("stroke-width", "1.4"))
            except ValueError as error:
                raise ValueError(f"{model}/{zone_id}: {port} invalid ring radius") from error
            if not math.isfinite(radius) or radius <= 0 or not math.isfinite(outline) or outline <= 0:
                raise ValueError(f"{model}/{zone_id}: {port} invalid jack ring radius/stroke")
            if not _inside(box, x, y, radius + outline / 2):
                raise ValueError(f"{model}/{zone_id}: {port} jack ring protrudes across rail edge")

            associated = [label for label in labels if label["name"] == text]
            if len(associated) != 1:
                raise ValueError(f"{model}/{zone_id}: {port} missing unique NanoVG label {text!r}")
            label = associated[0]
            position = label["position"]
            if position is None or not _inside(box, position[0], position[1], LABEL_INSET):
                raise ValueError(f"{model}/{zone_id}: label {text!r} outside solid rail")
            if label["color"] is None:
                raise ValueError(f"{model}/{zone_id}: label {text!r} foreground unknown")
            text_ratio = contrast_ratio(fill, label["color"])
            if text_ratio < MIN_LABEL_RATIO:
                raise ValueError(f"{model}/{zone_id}: label {text!r} palette {text_ratio:.2f}:1 "
                                 f"below {MIN_LABEL_RATIO:.1f}:1 advisory")
            label_ratios.append(text_ratio)
        records.append(f"{model}/{zone_id}: {len(ports)} ports; "
                       f"frame {frame_ratio:.2f}:1; labels ≥{min(label_ratios):.2f}:1")
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    arguments = parser.parse_args(argv)
    errors = []
    reports = []
    for model in ZONES:
        try:
            reports.extend(audit_panel(arguments.root, model))
        except (OSError, ValueError, ET.ParseError) as error:
            errors.append(f"FAIL: {error}")
    for record in reports:
        print(record)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("PASS: 2 source-backed signal-zone panels, 5 rails, 14 jacks and 14 labels "
          "(no rendered contrast or Rack widget footprint verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
