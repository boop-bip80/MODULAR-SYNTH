#!/usr/bin/env python3
"""Deterministic offline SVG concept preview for .msinstrument Macro8 metadata.

This is a static portable performance-panel sketch, not a Rack/DAW renderer.
Only validated display metadata becomes text; there is no script or external URL.
"""
from __future__ import annotations

import math
from xml.sax.saxutils import escape

FORMAT = "modular-synth-source-instrument"
WIDTH = 960
HEADER_HEIGHT = 128
SECTION_HEIGHT = 444
FOOTER_HEIGHT = 68
CARD_WIDTH = 210
CARD_HEIGHT = 124
CARD_STEP = 222
SLOTS = "ABCD"

# Text/color pairings intentionally exceed WCAG AA 4.5:1.
COLORS = {
    "background": "#0B1220",
    "surface": "#18263A",
    "card": "#253B55",
    "text": "#F8FAFC",
    "muted": "#D6E4F2",
    "accent": "#67E8F9",
    "track": "#526B83",
    "active": "#FDE68A",
    "on_active": "#172033",
}


class PreviewError(ValueError):
    """The preview manifest is missing or has unsupported unsafe metadata."""


def _number(value: object, minimum: float, maximum: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise PreviewError(f"{field} must be a number")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise PreviewError(f"{field} is not a finite number") from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise PreviewError(f"{field} outside {minimum:g}..{maximum:g}")
    return number


def _preview_modules(manifest: dict) -> tuple[str, list[dict]]:
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise PreviewError("unsupported instrument manifest format")
    version = manifest.get("formatVersion")
    if type(version) is not int or version != 1:
        raise PreviewError("unsupported instrument manifest version")
    name = manifest.get("name")
    if (not isinstance(name, str) or not 1 <= len(name) <= 64
            or any(ord(c) < 32 or ord(c) > 126 for c in name)):
        raise PreviewError("invalid instrument display name")
    performance = manifest.get("performance")
    controllers = performance.get("macro8") if isinstance(performance, dict) else None
    if not isinstance(controllers, list) or not 1 <= len(controllers) <= 8:
        raise PreviewError("expected 1..8 Macro8 controllers")

    ids: set[int] = set()
    validated: list[dict] = []
    for item in controllers:
        if not isinstance(item, dict):
            raise PreviewError("Macro8 controller must be an object")
        module_id = item.get("moduleId")
        if (type(module_id) is not int or not 0 <= module_id <= 0x7fffffffffffffff
                or module_id in ids or item.get("stateVersion") != 1
                or type(item.get("stateVersion")) is not int):
            raise PreviewError("duplicate/invalid Macro8 module or state version")
        ids.add(module_id)
        names = item.get("names")
        ranges = item.get("ranges")
        values = item.get("liveValues")
        if not isinstance(names, list) or len(names) != 8:
            raise PreviewError("Macro8 must have eight names")
        for label in names:
            if (not isinstance(label, str) or not 1 <= len(label) <= 12
                    or any(ord(c) < 32 or ord(c) > 126 for c in label)):
                raise PreviewError("Macro8 names must be 1..12 printable ASCII chars")
        if (not isinstance(ranges, list) or len(ranges) != 8
                or any(mode not in ("unipolar", "bipolar") for mode in ranges)):
            raise PreviewError("Macro8 must have eight valid CV polarity modes")
        if not isinstance(values, list) or len(values) != 8:
            raise PreviewError("Macro8 must have eight live values")
        live = [_number(value, 0, 1, "live macro") for value in values]
        morph = _number(item.get("morphSeconds"), 0, 5, "morph seconds")
        action = item.get("snapshotAction")
        if action not in ("store", "recall"):
            raise PreviewError("invalid snapshot action")

        snapshots = item.get("snapshots")
        if not isinstance(snapshots, list) or len(snapshots) != 4:
            raise PreviewError("Macro8 requires four snapshot slots")
        verified_snapshots: list[list[float] | None] = []
        for slot, row in zip(SLOTS, snapshots):
            if row is None:
                verified_snapshots.append(None)
            elif isinstance(row, list) and len(row) == 8:
                verified_snapshots.append([
                    _number(value, 0, 1, f"snapshot {slot}")
                    for value in row
                ])
            else:
                raise PreviewError(f"malformed snapshot {slot}")
        selected = item.get("selectedSlot")
        if type(selected) is not int or selected not in (-1, 0, 1, 2, 3):
            raise PreviewError("invalid selected snapshot")
        if selected >= 0 and verified_snapshots[selected] is None:
            raise PreviewError("selected snapshot is empty")

        validated.append({
            "moduleId": module_id,
            "names": names,
            "ranges": ranges,
            "liveValues": live,
            "morphSeconds": morph,
            "snapshotAction": action,
            "snapshots": verified_snapshots,
            "selectedSlot": selected,
        })
    validated.sort(key=lambda entry: entry["moduleId"])
    return name, validated


def _title_lines(name: str) -> list[str]:
    """Fit a 64-char title into <=2 rows without SVG text overflow."""
    if len(name) <= 46:
        return [name]
    split = name.rfind(" ", 0, 47)
    if split < 20:
        split = 46
    first = name[:split].rstrip()
    second = name[split:].lstrip()
    return [first, second]


def _text(x: int, y: int, value: str, *, fill: str, size: int = 14,
          css_class: str = "", weight: str = "400") -> str:
    klass = f' class="{css_class}"' if css_class else ""
    return (
        f'<text{klass} x="{x}" y="{y}" fill="{fill}" '
        f'font-size="{size}" font-weight="{weight}" '
        f'font-family="DejaVu Sans Mono, monospace">{escape(value)}</text>\n'
    )


def render_svg(manifest: dict) -> bytes:
    """Return fully self-contained UTF-8 SVG bytes from checked manifest data."""
    name, controllers = _preview_modules(manifest)
    height = HEADER_HEIGHT + SECTION_HEIGHT * len(controllers) + FOOTER_HEIGHT
    c = COLORS
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
        f'height="{height}" viewBox="0 0 {WIDTH} {height}" '
        'role="img" aria-labelledby="panel-title panel-desc">\n',
        f'<title id="panel-title">{escape(name)} — performance concept</title>\n',
        '<desc id="panel-desc">Static offline Macro8 control panel concept; '
        'eight live controls per module, voltage ranges, four snapshot slots. '
        'Not an interactive Rack or plugin panel.</desc>\n',
        f'<rect width="{WIDTH}" height="{height}" fill="{c["background"]}"/>\n',
    ]
    for index, line in enumerate(_title_lines(name)):
        parts.append(_text(36, 45 + 29 * index, line, fill=c["text"],
                           size=23, css_class="instrument-title", weight="700"))
    parts.append(_text(
        36, 108, "MODULAR-SYNTH  /  STATIC PERFORMANCE CONCEPT",
        fill=c["accent"], size=14, weight="700"))

    for section_index, controller in enumerate(controllers):
        base = HEADER_HEIGHT + section_index * SECTION_HEIGHT
        module_id = controller["moduleId"]
        selected = controller["selectedSlot"]
        mode = controller["snapshotAction"].upper()
        morph = controller["morphSeconds"]
        selection = "LIVE" if selected < 0 else f"SNAPSHOT {SLOTS[selected]}"
        controller_number = section_index + 1
        parts.append(
            f'<g class="macro8-section" data-controller="{section_index}" '
            f'data-module-id="{module_id}" role="group" '
            f'aria-labelledby="controller-{section_index}-title '
            f'controller-{section_index}-desc">\n'
            f'<title id="controller-{section_index}-title">'
            f'Macro controller {controller_number}</title>\n'
            f'<desc id="controller-{section_index}-desc">'
            f'Original Rack module ID {module_id}; stable identity retained '
            f'in this source preview.</desc>\n'
            f'<rect x="20" y="{base + 4}" width="920" height="432" '
            f'rx="18" fill="{c["surface"]}"/>\n'
        )
        parts.append(_text(
            42, base + 39, f"MACRO CONTROLLER {controller_number}",
            fill=c["text"], size=17, weight="700"))
        # Static display chips for live/recall selection, store mode and morph.
        for kind, x, width, text, background, foreground in (
            ("selection", 478, 128, selection, c["active"], c["on_active"]),
            ("action", 614, 126, mode, c["card"], c["text"]),
            ("morph", 748, 172, f"TIME {morph:.2f} S", c["card"], c["accent"]),
        ):
            parts.append(
                f'<rect class="{kind}-chip" x="{x}" y="{base + 13}" '
                f'width="{width}" height="36" rx="12" '
                f'fill="{background}"/>\n'
            )
            parts.append(_text(x + 14, base + 37, text, fill=foreground,
                               size=13, weight="700"))

        for index, (label, polarity, value) in enumerate(zip(
            controller["names"], controller["ranges"], controller["liveValues"]
        )):
            x = 36 + (index % 4) * CARD_STEP
            y = base + (62 if index < 4 else 200)
            low_high = "0 TO +10 V" if polarity == "unipolar" else "-5 TO +5 V"
            voltage = value * 10 if polarity == "unipolar" else value * 10 - 5
            fill_width = round(174 * value)
            parts.append(
                f'<g class="macro-control" data-index="{index + 1}">\n'
                f'<rect x="{x}" y="{y}" width="{CARD_WIDTH}" '
                f'height="{CARD_HEIGHT}" rx="12" fill="{c["card"]}"/>\n'
            )
            parts.append(_text(x + 16, y + 28, label, fill=c["text"],
                               size=16, css_class="macro-label", weight="700"))
            parts.append(_text(
                x + 16, y + 53, f"{polarity.upper()}  /  {low_high}",
                fill=c["muted"], size=11))
            parts.append(
                f'<rect x="{x + 18}" y="{y + 73}" width="174" height="10" '
                f'rx="5" fill="{c["track"]}"/>\n'
                f'<rect class="live-meter" x="{x + 18}" y="{y + 73}" '
                f'width="{fill_width}" height="10" rx="5" fill="{c["accent"]}"/>\n'
            )
            parts.append(_text(
                x + 16, y + 106, f"LIVE {value:.2f}  /  {voltage:+.2f} V",
                fill=c["muted"], size=12))
            parts.append("</g>\n")

        for slot_index, snapshot in enumerate(controller["snapshots"]):
            x = 36 + slot_index * CARD_STEP
            y = base + 342
            active = selected == slot_index
            background = c["active"] if active else c["card"]
            foreground = c["on_active"] if active else c["text"]
            bars_color = c["on_active"] if active else c["accent"]
            status = "EMPTY" if snapshot is None else (
                "SELECTED" if active else "STORED")
            parts.append(
                f'<g class="snapshot-slot" data-slot="{SLOTS[slot_index]}">\n'
                f'<rect x="{x}" y="{y}" width="{CARD_WIDTH}" height="74" '
                f'rx="12" fill="{background}"/>\n'
            )
            parts.append(_text(
                x + 16, y + 25, f"{SLOTS[slot_index]}  /  {status}",
                fill=foreground, size=16, weight="700"))
            if snapshot is not None:
                for j, value in enumerate(snapshot):
                    bar = round(17 * value)
                    if bar:
                        parts.append(
                            f'<rect class="snapshot-meter" x="{x + 24 + 20 * j}" '
                            f'y="{y + 66 - bar}" width="12" height="{bar}" '
                            f'rx="2" fill="{bars_color}"/>\n'
                        )
            parts.append("</g>\n")
        parts.append("</g>\n")

    footer = HEADER_HEIGHT + SECTION_HEIGHT * len(controllers)
    parts.append(_text(
        36, footer + 37,
        "SOURCE PREVIEW ONLY  /  NOT AN AUDIO OR HOST UI RENDERER",
        fill=c["muted"], size=13))
    parts.append("</svg>\n")
    return "".join(parts).encode("utf-8")
