"""Deterministic, desktop-free disassembly images from a database snapshot.

Nothing here executes imported instructions or interprets annotations as markup.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
import re
import unicodedata

from PIL import Image, ImageDraw, ImageFont

_WIDTH = 1560
_PAD = 36
_LINE = 28
_MAX_ROWS = 200
_MAX_HEIGHT = 24000
_COLORS = {
    "background": "#101722", "panel": "#182334", "line": "#2d3d52",
    "text": "#f1f5fb", "muted": "#afbdd0", "address": "#95bdff",
    "bytes": "#acbbce", "mnemonic": "#8ce4d3", "comment": "#efcc87",
    "name": "#c5b6ff",
}


@dataclass(frozen=True)
class _Text:
    x: int
    y: int
    text: str
    color: str
    size: int = 18
    bold: bool = False


def _clean(value: object, *, limit: int = 4096) -> str:
    """Keep text, remove control characters (including bidi controls)."""
    text = "" if value is None else str(value)
    if len(text) > limit:
        raise ValueError(f"render text exceeds {limit} characters; request a smaller view")
    return "".join(" " if ch.isspace() else ch for ch in text
                   if ch.isspace() or not unicodedata.category(ch).startswith("C"))


def _wrap(text: str, width: int) -> list[str]:
    # Count wide Unicode glyphs as two cells so CJK annotations also fit.
    if not text:
        return [""]
    lines = []
    remaining = text
    while remaining:
        used = 0
        end = 0
        last_space = 0
        for index, character in enumerate(remaining):
            cells = 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
            if used + cells > width:
                break
            used += cells
            end = index + 1
            if character.isspace():
                last_space = end
        if end == len(remaining):
            lines.append(remaining.rstrip())
            break
        if last_space:
            end = last_space
        lines.append(remaining[:end].rstrip())
        remaining = remaining[end:].lstrip()
    return lines


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # System fonts only; exports do not depend on downloading a font.
    stem = "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"
    candidates = [stem, f"/usr/share/fonts/truetype/dejavu/{stem}",
                  "/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Monaco.ttf",
                  "C:/Windows/Fonts/consola.ttf"]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow versions before scalable default-font support.
        return ImageFont.load_default()


def _layout(snapshot: dict) -> tuple[list[_Text], list[tuple[int, int, str]], int]:
    rows = snapshot.get("instructions", [])
    if not isinstance(rows, list) or len(rows) > _MAX_ROWS:
        raise ValueError(f"render requires a list of at most {_MAX_ROWS} instructions")
    texts: list[_Text] = []
    rules: list[tuple[int, int, str]] = []

    def add(x: int, y: int, value: object, color: str = "text", size: int = 18,
            bold: bool = False) -> None:
        texts.append(_Text(x, y, _clean(value), _COLORS[color], size, bold))

    add(_PAD, 28, "fDisBull  /  DISASSEMBLY", "text", 25, True)
    title = _clean(snapshot.get("title", "Untitled binary"), limit=256)
    y = 70
    for line in _wrap(title, 125):
        add(_PAD, y, line, "text")
        y += _LINE
    arch = _clean(snapshot.get("arch", "unknown"), limit=32)
    bits = _clean(snapshot.get("bits", "?"), limit=8)
    version = _clean(snapshot.get("version", "?"), limit=80)
    for line in _wrap(f"{arch} / {bits}-bit / little-endian     VERSION {version}     {len(rows)} instructions", 130):
        add(_PAD, y + 2, line, "muted")
        y += _LINE
    y += 4
    sha = _clean(snapshot.get("sha256", "unavailable"), limit=128)
    add(_PAD, y, f"SNAPSHOT SHA-256  {sha}", "muted", 15)
    y += 40
    rules.append((y - 10, _WIDTH - _PAD, _COLORS["line"]))
    for x, label in [(36, "ADDRESS"), (260, "BYTES (HEX)"), (620, "MNEMONIC"), (754, "OPERANDS")]:
        add(x, y, label, "muted", 15, True)
    y += 33
    if not rows:
        add(_PAD, y + 8, "No decoded instructions in this range.", "muted")
        y += 54
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("every render instruction must be an object")
        name = _clean(row.get("name"))
        if name:
            y += 9
            for line in _wrap(name + ":", 128):
                add(_PAD, y, line, "name", bold=True)
                y += _LINE
        address = _clean(row.get("address", "?"), limit=18)
        byte_text = _clean(row.get("bytes", ""), limit=64).replace(" ", "")
        if byte_text and (not re.fullmatch(r"[0-9a-fA-F]+", byte_text) or len(byte_text) % 2):
            raise ValueError("instruction bytes must be an even-length hexadecimal string")
        mnemonic = _clean(row.get("mnemonic", "?"), limit=40)
        operands = _clean(row.get("operands", ""))
        byte_lines = _wrap(byte_text.lower(), 30)
        mnemonic_lines = _wrap(mnemonic, 10)
        operand_lines = _wrap(operands, 69)
        add(36, y, address, "address")
        for line_index in range(max(len(byte_lines), len(mnemonic_lines), len(operand_lines))):
            row_y = y + line_index * _LINE
            if line_index < len(byte_lines):
                add(260, row_y, byte_lines[line_index], "bytes")
            if line_index < len(mnemonic_lines):
                add(620, row_y, mnemonic_lines[line_index], "mnemonic", bold=True)
            if line_index < len(operand_lines):
                add(754, row_y, operand_lines[line_index])
        y += max(len(byte_lines), len(mnemonic_lines), len(operand_lines)) * _LINE
        comment = _clean(row.get("comment"))
        if comment:
            for line in _wrap("; " + comment, 112):
                add(260, y, line, "comment")
                y += _LINE
        xrefs = row.get("xrefs") or []
        if not isinstance(xrefs, list):
            raise ValueError("instruction xrefs must be a list")
        if xrefs:
            refs = []
            for ref in xrefs[:4]:
                if not isinstance(ref, dict):
                    raise ValueError("every cross-reference must be an object")
                source = ref.get("source", ref.get("from", "?"))
                target = ref.get("target", ref.get("to", "?"))
                kind = ref.get("kind", ref.get("type", "reference"))
                refs.append(f"{_clean(kind)} {_clean(source)} -> {_clean(target)}")
            label = "XREF  " + "  |  ".join(refs)
            if len(xrefs) > 4:
                label += f"  |  +{len(xrefs) - 4} more (query xrefs for full list)"
            for line in _wrap(label, 126):
                add(36, y, line, "muted", 16)
                y += 25
        y += 7
        if y > _MAX_HEIGHT - 90:
            raise ValueError("render exceeds maximum image height; request fewer instructions")
    y += 15
    rules.append((y, _WIDTH - _PAD, _COLORS["line"]))
    add(36, y + 18, "DATABASE SNAPSHOT  /  Static decode; analysis and annotations are interpretations.", "muted", 15)
    return texts, rules, y + 63


def render_snapshot(snapshot: dict, output: str | Path, format: str | None = None) -> dict:
    """Render at most 200 instructions as an SVG or PNG, without a live GUI.

    Long fields wrap. Overlarge snapshots fail explicitly instead of silently
    omitting instructions or cropping evidence. Cross-reference summaries show
    four entries and explicitly label any remainder.
    """
    if not isinstance(snapshot, dict):
        raise ValueError("render snapshot must be an object")
    output = Path(output).expanduser().resolve()
    kind = (format or output.suffix.lstrip(".")).lower()
    if kind not in {"svg", "png"}:
        raise ValueError("render format must be png or svg")
    texts, rules, height = _layout(snapshot)
    output.parent.mkdir(parents=True, exist_ok=True)
    if kind == "svg":
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{_WIDTH}" height="{height}" '
                 f'viewBox="0 0 {_WIDTH} {height}" role="img">',
                 f'<title>{escape(_clean(snapshot.get("title", "Disassembly")))}</title>',
                 '<desc>Disassembly exported from a versioned fDisBull database snapshot.</desc>',
                 f'<rect width="100%" height="100%" fill="{_COLORS["background"]}"/>',
                 '<g font-family="DejaVu Sans Mono, Menlo, Consolas, monospace">']
        for y, x2, color in rules:
            parts.append(f'<line x1="{_PAD}" y1="{y}" x2="{x2}" y2="{y}" stroke="{color}"/>')
        for item in texts:
            weight = ' font-weight="700"' if item.bold else ""
            parts.append(f'<text x="{item.x}" y="{item.y + item.size}" font-size="{item.size}" '
                         f'fill="{item.color}"{weight} xml:space="preserve">{escape(item.text)}</text>')
        parts.append("</g></svg>\n")
        output.write_text("\n".join(parts), encoding="utf-8")
    else:
        image = Image.new("RGB", (_WIDTH, height), _COLORS["background"])
        draw = ImageDraw.Draw(image)
        fonts = {(item.size, item.bold): _font(item.size, item.bold) for item in texts}
        for y, x2, color in rules:
            draw.line((_PAD, y, x2, y), fill=color, width=1)
        for item in texts:
            font = fonts[item.size, item.bold]
            try:
                draw.text((item.x, item.y), item.text, fill=item.color, font=font)
            except UnicodeEncodeError:
                # Older Pillow's emergency bitmap font has Latin-1 coverage.
                # Make missing glyphs explicit rather than failing the export.
                fallback = item.text.encode("latin-1", "backslashreplace").decode("latin-1")
                draw.text((item.x, item.y), fallback, fill=item.color, font=font)
        image.save(output, format="PNG")
    return {"path": str(output), "format": kind, "width": _WIDTH, "height": height}
