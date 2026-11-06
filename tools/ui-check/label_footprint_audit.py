#!/usr/bin/env python3
"""Source-level label and port-row footprint audit of the original panels.

The NanoVG labels are drawn at runtime, *not* encoded as SVG <text>. This
check combines the actual nvgText coordinates/sizes with each SVG viewBox and
the PJ301MPort callsites. ShareTechMono glyph advances are approximated at
0.60 em: these rectangles are conservative layout heuristics, NOT rendered
glyph bounds, host screenshots, accessibility certification or a font test.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from contrast_audit import MODULES, extract_labels
from port_rail_audit import PORT_CALL, ZONES, direct_rect

MIN_STATIC_FONT = 10.0
MIN_EDGE = 3.0
MIN_TEXT_GAP = 1.0
FONT_ADVANCE_EM = 0.60  # estimated width of Rack's monospaced UI font
FONT_SYSTEM = 'res/fonts/ShareTechMono-Regular.ttf'
SVG_RECT = '{http://www.w3.org/2000/svg}rect'
SVG_CIRCLE = '{http://www.w3.org/2000/svg}circle'
LOAD_FONT = re.compile(r'loadFont\s*\(\s*asset::(?P<kind>system|plugin)\s*\(\s*'
                       r'(?:(?:pluginInstance\s*,\s*)?)"(?P<path>[^"]+)"\s*\)\s*\)', re.S)

# Four panels have independent CV/input/output lanes rather than the named
# solid rectangles used by port_rail_audit. This maps exact widget IDs to
# visible NanoVG legends. The six named-rail panels reuse that audit's map.
OTHER_PORTS: dict[str, tuple[tuple[str, str, str], ...]] = {
    'ClockedLFO': (
        ('Input', 'RATE_CV_INPUT', 'RATE'), ('Input', 'CLOCK_INPUT', 'CLK'),
        ('Input', 'RESET_INPUT', 'RESET'), ('Input', 'PHASE_CV_INPUT', 'PHASE'),
        ('Input', 'WIDTH_CV_INPUT', 'WIDTH'), ('Output', 'SINE_OUTPUT', 'SIN'),
        ('Output', 'TRIANGLE_OUTPUT', 'TRI'), ('Output', 'RAMP_OUTPUT', 'RAMP'),
        ('Output', 'PULSE_OUTPUT', 'PULSE'), ('Output', 'EOC_OUTPUT', 'EOC'),
    ),
    'ChanceHold': (
        ('Input', 'RATE_CV_INPUT', 'RATE'), ('Input', 'CLOCK_INPUT', 'CLK'),
        ('Input', 'RESET_INPUT', 'RESET'), ('Input', 'CHANCE_CV_INPUT', 'PROB'),
        ('Input', 'GLIDE_CV_INPUT', 'GLIDE'), ('Output', 'HOLD_OUTPUT', 'STEP'),
        ('Output', 'GLIDE_OUTPUT', 'SMOOTH'), ('Output', 'TRIGGER_OUTPUT', 'HIT'),
    ),
    'SlewGlide': (
        ('Input', 'SIGNAL_INPUT', 'CV IN'), ('Input', 'RISE_CV_INPUT', 'RISE CV'),
        ('Input', 'FALL_CV_INPUT', 'FALL CV'), ('Output', 'LINEAR_OUTPUT', 'LINEAR'),
        ('Output', 'EXPONENTIAL_OUTPUT', 'EXP'), ('Output', 'MOVING_OUTPUT', 'MOVING'),
    ),
    'ScaleQuantizer': (
        ('Input', 'PITCH_INPUT', 'PITCH'),
        ('Input', 'TRANSPOSE_CV_INPUT', 'TRANS'),
        ('Input', 'ROOT_CV_INPUT', 'ROOT'),
        ('Output', 'PITCH_OUTPUT', 'QUANT'),
        ('Output', 'CHANGE_OUTPUT', 'CHANGE'),
    ),
}


def text_box(label: dict[str, object]) -> tuple[float, float, float, float]:
    """Approximate centered NanoVG label using the declared monospaced face."""
    x, y = label['position']  # caller established literal numeric coordinates
    size = label['size']
    half_width = FONT_ADVANCE_EM * size * len(label['name']) / 2
    return (x - half_width, y - size / 2, x + half_width, y + size / 2)


def intersecting(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    """True if approximate glyph boxes touch or violate the minimum clearance."""
    return (a[0] < b[2] + MIN_TEXT_GAP and b[0] < a[2] + MIN_TEXT_GAP and
            a[1] < b[3] + MIN_TEXT_GAP and b[1] < a[3] + MIN_TEXT_GAP)


def box_of_rect(rect: ET.Element) -> tuple[float, float, float, float]:
    return tuple(float(rect.attrib[attr]) for attr in ('x', 'y', 'width', 'height'))


def rail_contains(rect: tuple[float, float, float, float], x: float,
                  y: float, inset: float) -> bool:
    rx, ry, rw, rh = rect
    return rx + inset <= x <= rx + rw - inset and ry + inset <= y <= ry + rh - inset


def label_fits_rail(rect: tuple[float, float, float, float],
                    label: dict[str, object]) -> bool:
    x, y, xmax, ymax = text_box(label)
    rx, ry, rw, rh = rect
    return (rx + MIN_EDGE <= x and ry + MIN_EDGE <= y and
            xmax <= rx + rw - MIN_EDGE and ymax <= ry + rh - MIN_EDGE)


def audit_panel(root: Path, model: str) -> tuple[int, int, list[str]]:
    path = root / 'plugins' / 'ModularSynth'
    source = (path / 'src' / (model + '.cpp')).read_text(encoding='utf-8')
    svg = ET.parse(path / 'res' / (model + '.svg')).getroot()
    try:
        _, _, width, height = [float(n) for n in svg.attrib['viewBox'].replace(',', ' ').split()]
    except (KeyError, ValueError) as exc:
        raise ValueError(f'{model}: invalid SVG viewBox') from exc
    fonts = LOAD_FONT.findall(source)
    if len(fonts) != 1:
        raise ValueError(f'{model}: missing/ambiguous font load: {fonts}')
    kind, asset = fonts[0]
    if kind == 'system':
        if asset != FONT_SYSTEM:
            raise ValueError(f'{model}: unknown Rack system font dependency {asset!r}')
    elif not asset.startswith('res/fonts/') or not (path / asset).is_file():
        raise ValueError(f'{model}: missing/nonlocal plugin font asset {asset!r}')
    # Rack owns system fonts; a repo-only audit cannot certify the host asset.
    if ('nvgFontFaceId(args.vg, labelFont->handle);' not in source or
            'nvgTextAlign(args.vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);' not in source):
        raise ValueError(f'{model}: expected centered NanoVG text with loaded labelFont')

    labels = extract_labels(source)
    static: list[dict[str, object]] = []
    for label in labels:
        if label['name'].startswith('<dynamic:'):
            continue  # Macro8 dynamic names get their own worst-case bound below.
        if not isinstance(label['size'], (int, float)) or label['size'] < MIN_STATIC_FONT:
            raise ValueError(f'{model}: tiny/unknown font size for {label["name"]!r}: {label["size"]}')
        if label['position'] is None:
            raise ValueError(f'{model}: unresolvable label position for {label["name"]!r}')
        box = text_box(label)
        if box[0] < MIN_EDGE or box[1] < MIN_EDGE or box[2] > width - MIN_EDGE or box[3] > height - MIN_EDGE:
            raise ValueError(f'{model}: {label["name"]!r} estimated text clipped at panel edge: {box!r}')
        for other in static:
            if intersecting(box, text_box(other)):
                raise ValueError(f'{model}: probable label overlap: {label["name"]!r} / {other["name"]!r}')
        static.append(label)

    if model == 'Macro8':
        # User-created names are capped at 12 printable ASCII characters by
        # macro8CleanName. Their runtime text must be fitted to a column.
        if 'if (name.size() >= 12)' not in source:
            raise ValueError('Macro8: renamed macro label length cap changed')
        if 'nvgTextBounds(args.vg, 0.0f, 0.0f, label.c_str()' not in source:
            raise ValueError('Macro8: dynamic names lack per-column width fitting')
        if 'constexpr float maxLabelWidth = 65.0f;' not in source:
            raise ValueError('Macro8: dynamic name fit target is not 65px')

    if model in ZONES:
        ports = tuple(port for rail in ZONES[model].values() for port in rail)
    else:
        ports = OTHER_PORTS.get(model, ())
    callsites = [match for match in PORT_CALL.finditer(source) if match.group('model') == model]
    actual = {(m.group('role'), m.group('port')): m for m in callsites}
    expected = {(role, port): name for role, port, name in ports}
    if model != 'Macro8' and (len(actual) != len(callsites) or set(actual) != set(expected)):
        raise ValueError(f'{model}: jack ID or role drift (expected {sorted(expected)}, observed {sorted(actual)})')
    for (role, port), caption in expected.items():
        widget = actual[(role, port)]
        jack_x, jack_y = float(widget.group('x')), float(widget.group('y'))
        nearby = [label for label in static if label['name'] == caption and
                  label['position'] is not None and
                  abs(label['position'][0] - jack_x) <= 3 and
                  15 <= jack_y - label['position'][1] <= 38]
        if len(nearby) != 1:
            raise ValueError(f'{model}: {role}:{port} missing/offset/ambiguous jack caption {caption!r}')
        if model in ZONES:
            zone_id = next(zone for zone, entries in ZONES[model].items()
                           if (role, port, caption) in entries)
            matching = [box_of_rect(direct_rect(svg, zone_id))]
        else:
            # Remaining three patching modules use two simple outline rails
            # without IDs. A full-panel rectangle cannot accidentally count.
            matching = [box_of_rect(node) for node in svg
                        if node.tag == SVG_RECT and node.get('stroke') and
                        node.get('fill') == 'none' and
                        50 <= float(node.get('height', '0')) <= 90 and
                        100 <= float(node.get('width', '0')) <= width and
                        all(attr in node.attrib for attr in ('x', 'y', 'width', 'height'))]
        complete = [box for box in matching
                    if rail_contains(box, jack_x, jack_y, 13.0) and
                    label_fits_rail(box, nearby[0])]
        if len(complete) != 1:
            raise ValueError(f'{model}: {role}:{port} label/jack escapes its outlined lane '
                             f'(approximate text box {text_box(nearby[0])!r})')

    notes = []
    if model == 'Macro8':
        # These labels are populated from loops and cannot be captured by the
        # literal nvgText regex. Check their center arrays, not pixel render.
        if 'constexpr float columns[4] = {40.0f, 113.0f, 187.0f, 260.0f};' not in source:
            raise ValueError('Macro8: per-column name centers changed')
        if 'constexpr float slots[5] = {34.0f, 91.0f, 148.0f, 205.0f, 262.0f};' not in source:
            raise ValueError('Macro8: scene label centers changed')
        # The 8 NanoVG draw labels are dynamic. Their 65px fitted width
        # leaves at least 7.5px at the narrowest panel edge and 8px between
        # text lanes. Decorative jack rings must still align with loop ports.
        if 'Vec(x, outputY), module, ModularSynthMacro8::MACRO_1_OUTPUT + i' not in source:
            raise ValueError('Macro8: macro output loop no longer uses expected port centers')
        rings = {(float(circle.attrib['cx']), float(circle.attrib['cy']))
                 for circle in svg.iter() if circle.tag == SVG_CIRCLE and
                 circle.get('cx') and circle.get('cy')}
        for y in (125.0, 215.0):
            for x in (40.0, 113.0, 187.0, 260.0):
                if (x, y) not in rings:
                    raise ValueError(f'Macro8: output ring missing at {x:g},{y:g}')
        notes.append('8 fitted dynamic macro names + 5 scene captions checked by source contract')
    return len(static), len(ports), notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    errors, notes = [], []
    static_count = jack_count = 0
    for model in MODULES:
        try:
            count, jacks, findings = audit_panel(args.root, model)
            static_count += count
            jack_count += jacks
            print(f'{model}: {count} literal NanoVG labels, {jacks} ID-linked jack captions; '
                  f'font dependency Rack system/{FONT_SYSTEM}')
            notes.extend(findings)
        except (OSError, ValueError, ET.ParseError, TypeError) as error:
            errors.append(f'{model}: {error}')
    for finding in notes:
        print(f'NOTE: {finding}')
    for error in errors:
        print(f'FAIL: {error}', file=sys.stderr)
    if errors:
        return 1
    print(f'PASS: {len(MODULES)} original panels, {static_count} static labels, {jack_count} '
          'ID-linked jack captions; font-host/physical pixels unverified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
