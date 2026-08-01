from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

MAX_GLYPHS = 65_536
MAX_POINTS = 10_000_000
LAYER_DEPTH_STEP = 0.5
BASE_LAYER_NAMES = {"base", "legacy core", "starting layer", "start", "core"}


def _quoted(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def _unquoted(text: str) -> tuple[str, str]:
    match = re.match(r'^"((?:\\.|[^"])*)"(.*)$', text.strip())
    if not match:
        raise ValueError("expected quoted text")
    value = json.loads('"' + match.group(1) + '"')
    return value, match.group(2).strip()


@dataclass
class Point:
    x: float
    y: float
    z: float = 0.0
    alpha: float = 1.0
    color: str = "#45d8ef"
    group: int = 0

    def key(self) -> tuple[float, float, float]:
        return round(self.x, 4), round(self.y, 4), round(self.z, 4)


@dataclass
class Layer:
    name: str = "Base"
    opacity: float = 1.0
    visible: bool = True
    points: list[Point] = field(default_factory=list)


@dataclass
class Glyph:
    codepoint: int
    advance: float = 6.0
    layers: list[Layer] = field(default_factory=lambda: [Layer()])


@dataclass
class GlyphClipboard:
    source_codepoint: int
    source_layer_index: int
    glyph: Glyph


def base_layer_index(glyph: Glyph) -> int:
    for index, layer in enumerate(glyph.layers):
        if layer.name.strip().casefold() in BASE_LAYER_NAMES:
            return index
    return 0


def layer_depth_offset(glyph: Glyph, layer_index: int) -> float:
    """Map SCFS list order to authored rich-text depth.

    Layers above the base are behind it; layers below the base are in front.
    Simple text deliberately ignores this value.
    """
    return float(layer_index - base_layer_index(glyph)) * LAYER_DEPTH_STEP


def copy_glyph_snapshot(glyph: Glyph, source_codepoint: int,
                        active_layer_index: int) -> GlyphClipboard:
    bounded = max(0, min(active_layer_index, max(0, len(glyph.layers) - 1)))
    return GlyphClipboard(source_codepoint, bounded, copy.deepcopy(glyph))


def paste_glyph_snapshot(document: "FontDocument", target_codepoint: int,
                         target_layer_index: int, clipboard: GlyphClipboard) -> tuple[str, int]:
    """Paste a full glyph across glyphs, or one copied layer within the same glyph."""
    if target_codepoint != clipboard.source_codepoint:
        copied = copy.deepcopy(clipboard.glyph)
        copied.codepoint = target_codepoint
        document.glyphs[target_codepoint] = copied
        active = max(0, min(clipboard.source_layer_index, max(0, len(copied.layers) - 1)))
        return "glyph", active

    target = document.ensure_glyph(target_codepoint)
    if not target.layers:
        target.layers.append(Layer())
    destination = max(0, min(target_layer_index, len(target.layers) - 1))
    source = max(0, min(clipboard.source_layer_index, max(0, len(clipboard.glyph.layers) - 1)))
    source_layer = copy.deepcopy(clipboard.glyph.layers[source])
    # Keep the destination identity/order while replacing its authored contents.
    target_layer = target.layers[destination]
    target_layer.opacity = source_layer.opacity
    target_layer.visible = source_layer.visible
    target_layer.points = source_layer.points
    return "layer", destination


@dataclass
class Metrics:
    em_size: float = 9.0
    cap_height: float = 8.0
    x_height: float = 5.0
    baseline: float = 7.0
    ascender: float = 0.0
    descender: float = 2.0
    letter_spacing: float = 1.0
    word_spacing: float = 4.0
    line_height: float = 11.0


@dataclass
class FontDocument:
    name: str = "Untitled SignalCloud Font"
    metrics: Metrics = field(default_factory=Metrics)
    glyphs: dict[int, Glyph] = field(default_factory=dict)

    def clone(self) -> "FontDocument":
        return copy.deepcopy(self)

    def ensure_glyph(self, codepoint: int) -> Glyph:
        if codepoint not in self.glyphs:
            self.glyphs[codepoint] = Glyph(codepoint)
        return self.glyphs[codepoint]

    def glyph_for_codepoint(self, codepoint: int) -> Glyph | None:
        return self.glyphs.get(codepoint) or self.glyphs.get(0xFFFD)

    def character_advance(self, char: str, scale: float = 1.0) -> float:
        if char == "\n":
            return 0.0
        if char.isspace():
            return self.metrics.word_spacing * scale
        glyph = self.glyph_for_codepoint(ord(char))
        if glyph is None:
            return self.metrics.word_spacing * scale
        return (glyph.advance + self.metrics.letter_spacing) * scale

    def measure_line_advance(self, text: str, scale: float = 1.0) -> float:
        return sum(self.character_advance(char, scale) for char in text if char != "\n")

    def wrap_text(self, text: str, maximum_width: float, scale: float = 1.0) -> str:
        """Wrap text by glyph Advance while preserving explicit newlines.

        Whole words remain together when they fit. A single word wider than the
        available width is split by Unicode character so preview layouts cannot
        create a horizontal scroll region.
        """
        if not math.isfinite(maximum_width) or maximum_width <= 0:
            raise ValueError("Wrap width must be positive and finite.")
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError("Wrap scale must be positive and finite.")

        def split_long_word(word: str) -> list[str]:
            chunks: list[str] = []
            current = ""
            width = 0.0
            for char in word:
                advance = self.character_advance(char, scale)
                if current and width + advance > maximum_width:
                    chunks.append(current)
                    current = char
                    width = advance
                else:
                    current += char
                    width += advance
            if current:
                chunks.append(current)
            return chunks

        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        output: list[str] = []
        for paragraph in normalized.split("\n"):
            words = paragraph.split()
            if not words:
                output.append("")
                continue

            line = ""
            line_width = 0.0
            for word in words:
                word_width = self.measure_line_advance(word, scale)
                separator_width = (
                    self.character_advance(" ", scale) if line else 0.0
                )
                if line and line_width + separator_width + word_width <= maximum_width:
                    line += " " + word
                    line_width += separator_width + word_width
                    continue

                if line:
                    output.append(line)
                    line = ""
                    line_width = 0.0

                if word_width <= maximum_width:
                    line = word
                    line_width = word_width
                    continue

                chunks = split_long_word(word)
                output.extend(chunks[:-1])
                line = chunks[-1] if chunks else ""
                line_width = self.measure_line_advance(line, scale)

            output.append(line)
        return "\n".join(output)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.name.strip():
            errors.append("Font name cannot be empty.")
        if self.metrics.em_size <= 0 or self.metrics.line_height <= 0:
            errors.append("Em size and line height must be positive.")
        if len(self.glyphs) > MAX_GLYPHS:
            errors.append("Glyph safety limit exceeded.")
        total = 0
        for code, glyph in self.glyphs.items():
            if code != glyph.codepoint or not 0 <= code <= 0x10FFFF:
                errors.append(f"Invalid codepoint U+{code:04X}.")
            if glyph.advance < 0 or not math.isfinite(glyph.advance):
                errors.append(f"Invalid advance for U+{code:04X}.")
            for layer in glyph.layers:
                if not layer.name:
                    errors.append(f"Empty layer name in U+{code:04X}.")
                if not 0 <= layer.opacity <= 1:
                    errors.append(f"Layer opacity outside 0..1 in U+{code:04X}.")
                total += len(layer.points)
                for point in layer.points:
                    if not all(math.isfinite(v) for v in (point.x, point.y, point.z, point.alpha)):
                        errors.append(f"Non-finite point in U+{code:04X}.")
                    if not 0 <= point.alpha <= 1:
                        errors.append(f"Point alpha outside 0..1 in U+{code:04X}.")
                    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", point.color):
                        errors.append(f"Invalid point color in U+{code:04X}.")
        if total > MAX_POINTS:
            errors.append("Font point safety limit exceeded.")
        return errors

    def save(self, path: Path) -> None:
        errors = self.validate()
        if errors:
            raise ValueError("\n".join(errors))
        m = self.metrics
        lines = [
            "SCFONT 1",
            f"FONT {_quoted(self.name)}",
            "METRICS " + " ".join(
                f"{value:.8g}" for value in (
                    m.em_size, m.cap_height, m.x_height, m.baseline, m.ascender,
                    m.descender, m.letter_spacing, m.word_spacing, m.line_height,
                )
            ),
        ]
        for code in sorted(self.glyphs):
            glyph = self.glyphs[code]
            lines.append(f"GLYPH {code} {glyph.advance:.8g}")
            for layer in glyph.layers:
                lines.append(f"LAYER {_quoted(layer.name)} {layer.opacity:.8g} {int(layer.visible)}")
                for point in layer.points:
                    lines.append(
                        f"POINT {point.x:.8g} {point.y:.8g} {point.z:.8g} {point.alpha:.8g} "
                        f"{point.color[1:].upper()}FF {point.group}"
                    )
                lines.append("ENDLAYER")
            lines.append("ENDGLYPH")
        lines.append("END")
        path = Path(path)
        if path.suffix.lower() != ".scfont":
            path = path.with_suffix(".scfont")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        temporary.replace(path)

    @classmethod
    def load(cls, path: Path) -> "FontDocument":
        document = cls()
        glyph: Glyph | None = None
        layer: Layer | None = None
        header = False
        for number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            command, _, rest = line.partition(" ")
            try:
                if command == "SCFONT":
                    if rest.strip() != "1":
                        raise ValueError("unsupported version")
                    header = True
                elif command == "FONT":
                    document.name, _ = _unquoted(rest)
                elif command == "METRICS":
                    values = [float(item) for item in rest.split()]
                    if len(values) != 9:
                        raise ValueError("METRICS requires 9 values")
                    document.metrics = Metrics(*values)
                elif command == "GLYPH":
                    code, advance = rest.split()
                    glyph = Glyph(int(code), float(advance), [])
                    if glyph.codepoint in document.glyphs:
                        raise ValueError("duplicate glyph")
                    document.glyphs[glyph.codepoint] = glyph
                    layer = None
                elif command == "LAYER":
                    if glyph is None:
                        raise ValueError("LAYER outside GLYPH")
                    name, tail = _unquoted(rest)
                    opacity, visible = tail.split()
                    layer = Layer(name, float(opacity), bool(int(visible)), [])
                    glyph.layers.append(layer)
                elif command == "POINT":
                    if layer is None:
                        raise ValueError("POINT outside LAYER")
                    values = rest.split()
                    if len(values) < 4:
                        raise ValueError("POINT requires x y z alpha")
                    point = Point(*map(float, values[:4]))
                    if len(values) >= 5:
                        rgba = values[4]
                        if not re.fullmatch(r"[0-9A-Fa-f]{8}", rgba):
                            raise ValueError("POINT color must be RRGGBBAA")
                        point.color = "#" + rgba[:6].lower()
                    if len(values) >= 6:
                        point.group = int(values[5])
                    layer.points.append(point)
                elif command == "ENDLAYER":
                    layer = None
                elif command == "ENDGLYPH":
                    glyph = None
                    layer = None
                elif command == "END":
                    break
                else:
                    raise ValueError(f"unknown command {command}")
            except Exception as exc:
                raise ValueError(f"{path}:{number}: {exc}") from exc
        if not header:
            raise ValueError("missing SCFONT 1 header")
        errors = document.validate()
        if errors:
            raise ValueError("\n".join(errors))
        return document

    def layout(self, text: str, scale: float = 1.0) -> list[tuple[float, float, Point, int, int]]:
        output: list[tuple[float, float, Point, int, int]] = []
        cursor_x = cursor_y = 0.0
        for char in text:
            code = ord(char)
            if char == "\n":
                cursor_x = 0.0
                cursor_y += self.metrics.line_height * scale
                continue
            if char.isspace():
                cursor_x += self.metrics.word_spacing * scale
                continue
            glyph = self.glyph_for_codepoint(code)
            if glyph is None:
                cursor_x += self.metrics.word_spacing * scale
                continue
            for layer_index, layer in enumerate(glyph.layers):
                if not layer.visible:
                    continue
                depth_offset = layer_depth_offset(glyph, layer_index)
                for point in layer.points:
                    positioned = copy.copy(point)
                    positioned.z = point.z + depth_offset
                    positioned.alpha = point.alpha * layer.opacity
                    output.append((cursor_x, cursor_y, positioned, code, layer_index))
            cursor_x += (glyph.advance + self.metrics.letter_spacing) * scale
        return output


CURRENT_GLYPH7 = {
    "A":[0x0E,0x11,0x11,0x1F,0x11,0x11,0x11],"B":[0x1E,0x11,0x11,0x1E,0x11,0x11,0x1E],
    "C":[0x0E,0x11,0x10,0x10,0x10,0x11,0x0E],"D":[0x1E,0x11,0x11,0x11,0x11,0x11,0x1E],
    "E":[0x1F,0x10,0x10,0x1E,0x10,0x10,0x1F],"F":[0x1F,0x10,0x10,0x1E,0x10,0x10,0x10],
    "G":[0x0E,0x11,0x10,0x17,0x11,0x11,0x0E],"H":[0x11,0x11,0x11,0x1F,0x11,0x11,0x11],
    "I":[0x1F,0x04,0x04,0x04,0x04,0x04,0x1F],"J":[0x01,0x01,0x01,0x01,0x11,0x11,0x0E],
    "K":[0x11,0x12,0x14,0x18,0x14,0x12,0x11],"L":[0x10,0x10,0x10,0x10,0x10,0x10,0x1F],
    "M":[0x11,0x1B,0x15,0x15,0x11,0x11,0x11],"N":[0x11,0x19,0x15,0x13,0x11,0x11,0x11],
    "O":[0x0E,0x11,0x11,0x11,0x11,0x11,0x0E],"P":[0x1E,0x11,0x11,0x1E,0x10,0x10,0x10],
    "Q":[0x0E,0x11,0x11,0x11,0x15,0x12,0x0D],"R":[0x1E,0x11,0x11,0x1E,0x14,0x12,0x11],
    "S":[0x0F,0x10,0x10,0x0E,0x01,0x01,0x1E],"T":[0x1F,0x04,0x04,0x04,0x04,0x04,0x04],
    "U":[0x11,0x11,0x11,0x11,0x11,0x11,0x0E],"V":[0x11,0x11,0x11,0x11,0x11,0x0A,0x04],
    "W":[0x11,0x11,0x11,0x15,0x15,0x15,0x0A],"X":[0x11,0x11,0x0A,0x04,0x0A,0x11,0x11],
    "Y":[0x11,0x11,0x0A,0x04,0x04,0x04,0x04],"Z":[0x1F,0x01,0x02,0x04,0x08,0x10,0x1F],
    "0":[0x0E,0x11,0x13,0x15,0x19,0x11,0x0E],"1":[0x04,0x0C,0x04,0x04,0x04,0x04,0x0E],
    "2":[0x0E,0x11,0x01,0x02,0x04,0x08,0x1F],"3":[0x1E,0x01,0x01,0x0E,0x01,0x01,0x1E],
    "4":[0x02,0x06,0x0A,0x12,0x1F,0x02,0x02],"5":[0x1F,0x10,0x10,0x1E,0x01,0x01,0x1E],
    "6":[0x0E,0x10,0x10,0x1E,0x11,0x11,0x0E],"7":[0x1F,0x01,0x02,0x04,0x08,0x08,0x08],
    "8":[0x0E,0x11,0x11,0x0E,0x11,0x11,0x0E],"9":[0x0E,0x11,0x11,0x0F,0x01,0x01,0x0E],
    "-":[0,0,0,0x1F,0,0,0],"_":[0,0,0,0,0,0,0x1F],".":[0,0,0,0,0,0x0C,0x0C],
    ":":[0,0x0C,0x0C,0,0x0C,0x0C,0],"/":[1,2,2,4,8,8,0x10],"+":[0,4,4,0x1F,4,4,0],
    "?":[0x0E,0x11,1,2,4,0,4],"!":[4,4,4,4,4,0,4],
}


def current_engine_font() -> FontDocument:
    document = FontDocument("Almond Signal Legacy 5x9")
    for char, base in CURRENT_GLYPH7.items():
        rows = [base[0], base[0], *base[1:6], base[6], base[6]]
        points = [
            Point(float(column), float(row), color="#45d8ef")
            for row, bits in enumerate(rows)
            for column in range(5)
            if bits & (1 << (4 - column))
        ]
        document.glyphs[ord(char)] = Glyph(ord(char), 5.8, [Layer("Legacy Core", 1.0, True, points)])
    return document
