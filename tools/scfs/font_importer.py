from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

from .freetype_raster import FreeTypeError, NativeFreeTypeFace
from .model import FontDocument, Glyph, Layer, Metrics, Point


class FontImportError(ValueError):
    pass


@dataclass(frozen=True)
class FontProbe:
    path: Path
    format: str
    family: str
    style: str
    codepoints: tuple[int, ...]
    supported: bool
    detail: str = ""


def _pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise FontImportError(
            "The system FreeType path failed and the optional Pillow fallback is "
            "unavailable. On Kubuntu verify libfreetype6, or install python3-pil."
        ) from exc
    return Image, ImageDraw, ImageFont


def _mapped_codepoints(path: Path) -> tuple[int, ...]:
    try:
        from fontTools.ttLib import TTFont

        font = TTFont(path, lazy=True)
        cmap = font.getBestCmap() or {}
        font.close()
        return tuple(sorted(code for code in cmap if 0 <= code <= 0x10FFFF))
    except Exception:
        pass
    # Small dependency-free sfnt cmap fallback (formats 4 and 12).
    try:
        data = Path(path).read_bytes()
        table_count = struct.unpack_from(">H", data, 4)[0]
        cmap_offset = None
        for index in range(table_count):
            position = 12 + index * 16
            tag, _checksum, offset, _length = struct.unpack_from(">4sIII", data, position)
            if tag == b"cmap":
                cmap_offset = offset
                break
        if cmap_offset is None:
            return ()
        _version, count = struct.unpack_from(">HH", data, cmap_offset)
        subtables: list[int] = []
        for index in range(count):
            _platform, _encoding, relative = struct.unpack_from(">HHI", data, cmap_offset + 4 + index * 8)
            subtables.append(cmap_offset + relative)
        values: set[int] = set()
        for offset in subtables:
            fmt = struct.unpack_from(">H", data, offset)[0]
            if fmt == 12:
                groups = struct.unpack_from(">I", data, offset + 12)[0]
                for index in range(groups):
                    start, end, _glyph = struct.unpack_from(">III", data, offset + 16 + index * 12)
                    values.update(range(start, min(end, 0x10FFFF) + 1))
            elif fmt == 4:
                seg_count = struct.unpack_from(">H", data, offset + 6)[0] // 2
                end_base = offset + 14
                start_base = end_base + seg_count * 2 + 2
                for index in range(seg_count):
                    end = struct.unpack_from(">H", data, end_base + index * 2)[0]
                    start = struct.unpack_from(">H", data, start_base + index * 2)[0]
                    if start <= end and start != 0xFFFF:
                        values.update(range(start, end + 1))
        return tuple(sorted(values))
    except Exception:
        return ()


def probe_font(path: Path) -> FontProbe:
    path = Path(path)
    header = path.read_bytes()[:64]
    if header.startswith(b"RFB2"):
        end = header.find(b"\x03", 6)
        family = header[6:end if end > 6 else 32].decode("utf-8", "replace").strip("\0 ")
        return FontProbe(
            path, "RFB2", family or path.stem, "", (), False,
            "RFB2 is a custom raster-font project container. Its glyph records are "
            "recognized, but this release will not guess at undocumented compression.",
        )
    try:
        with NativeFreeTypeFace(path, 16) as font:
            family, style = font.family, font.style
    except Exception as exc:
        custom = _probe_expanded_sfnt(path)
        if custom:
            return FontProbe(
                path, "Extended/custom TTF", custom, "", (), False,
                "This export uses a nonstandard widened SFNT directory and custom "
                "glyph/head records. It is not an ordinary FontForge TrueType font.",
            )
        return FontProbe(
            path, path.suffix.lstrip(".").upper() or "Unknown", path.stem, "", (), False,
            f"The system FreeType loader rejected this file: {exc}",
        )
    fmt = "OpenType" if path.suffix.lower() == ".otf" else "TrueType"
    return FontProbe(path, fmt, family, style, _mapped_codepoints(path), True)


def _probe_expanded_sfnt(path: Path) -> str:
    try:
        data = Path(path).read_bytes()
        count = struct.unpack_from(">H", data, 4)[0]
        tags = [data[12 + index * 32:16 + index * 32] for index in range(count)]
        if b"glyf" not in tags or b"head" not in tags:
            return ""
        for index, tag in enumerate(tags):
            position = 12 + index * 32
            offset = struct.unpack_from(">I", data, position + 16)[0]
            length = struct.unpack_from(">I", data, position + 24)[0]
            if not tag.strip(b"\0") or offset + length > len(data):
                return ""
        return Path(path).stem
    except Exception:
        return ""


def choose_codepoints(probe: FontProbe, preset: str, text: str = "") -> tuple[int, ...]:
    mapped = set(probe.codepoints)
    if preset == "Text characters":
        values = {ord(char) for char in text if char not in "\r\n\t"}
    elif preset == "All mapped glyphs":
        if not mapped:
            raise FontImportError("This font has no readable Unicode character map.")
        values = mapped
    elif preset == "Latin-1":
        values = set(range(0x20, 0x100))
    else:
        values = set(range(0x20, 0x7F))
    if mapped:
        values &= mapped
    return tuple(sorted(values))


def import_outline_font(
    path: Path,
    *,
    grid_height: int = 16,
    threshold: int = 72,
    codepoints: tuple[int, ...] | None = None,
    color: str = "#45d8ef",
    preserve_alpha: bool = True,
) -> FontDocument:
    if not 5 <= grid_height <= 64:
        raise FontImportError("Grid height must be between 5 and 64.")
    if not 1 <= threshold <= 254:
        raise FontImportError("Threshold must be between 1 and 254.")
    probe = probe_font(path)
    if not probe.supported:
        raise FontImportError(f"{probe.format} cannot be imported: {probe.detail}")
    codes = tuple(codepoints if codepoints is not None else choose_codepoints(probe, "Basic Latin"))
    if not codes:
        raise FontImportError("No mapped characters matched the selected import range.")
    try:
        return _import_with_native_freetype(
            path, probe, grid_height, threshold, codes, color, preserve_alpha
        )
    except FreeTypeError:
        # Pillow may carry its own working FreeType even when the system library is absent.
        pass
    Image, ImageDraw, ImageFont = _pillow()
    render_size = grid_height * 4
    font = ImageFont.truetype(str(path), render_size)
    ascent, descent = font.getmetrics()
    line_pixels = max(1, ascent + descent)
    scale = grid_height / line_pixels
    document = FontDocument(f"{probe.family} SignalCloud Import")
    cap_box = font.getbbox("H", anchor="ls")
    x_box = font.getbbox("x", anchor="ls")
    document.metrics = Metrics(
        em_size=float(grid_height),
        cap_height=max(1.0, -cap_box[1] * scale),
        x_height=max(1.0, -x_box[1] * scale),
        baseline=ascent * scale,
        ascender=0.0,
        descender=descent * scale,
        letter_spacing=max(0.5, scale),
        word_spacing=float(font.getlength(" ")) * scale,
        line_height=float(grid_height + max(1, round(grid_height * 0.18))),
    )

    for code in codes:
        char = chr(code)
        advance_pixels = max(0.0, float(font.getlength(char)))
        left, top, right, bottom = font.getbbox(char, anchor="ls")
        min_x = min(0, left)
        max_x = max(int(round(advance_pixels)), right)
        source_width = max(1, max_x - min_x)
        canvas = Image.new("L", (source_width, line_pixels), 0)
        ImageDraw.Draw(canvas).text((-min_x, ascent), char, font=font, fill=255, anchor="ls")
        target_width = max(1, int(round(source_width * scale)))
        reduced = canvas.resize((target_width, grid_height), Image.Resampling.LANCZOS)
        points: list[Point] = []
        pixels = reduced.load()
        for y in range(grid_height):
            for x in range(target_width):
                coverage = int(pixels[x, y])
                if coverage >= threshold:
                    alpha = max(0.05, coverage / 255.0) if preserve_alpha else 1.0
                    points.append(Point(float(x), float(y), alpha=alpha, color=color))
        advance = max(0.0, advance_pixels * scale)
        document.glyphs[code] = Glyph(
            code, advance, [Layer(f"Imported {probe.format} outline", 1.0, True, points)]
        )
    errors = document.validate()
    if errors:
        raise FontImportError("\n".join(errors))
    return document


def _import_with_native_freetype(
    path: Path,
    probe: FontProbe,
    grid_height: int,
    threshold: int,
    codes: tuple[int, ...],
    color: str,
    preserve_alpha: bool,
) -> FontDocument:
    with NativeFreeTypeFace(path, grid_height) as face:
        document = FontDocument(f"{probe.family} SignalCloud Import")
        baseline = face.baseline * face.scale
        document.metrics = Metrics(
            em_size=float(grid_height),
            cap_height=max(1.0, baseline * 0.72),
            x_height=max(1.0, baseline * 0.52),
            baseline=baseline,
            ascender=0.0,
            descender=max(0.0, grid_height - baseline),
            letter_spacing=max(0.5, face.scale),
            word_spacing=0.0,
            line_height=float(grid_height + max(1, round(grid_height * 0.18))),
        )
        for code in codes:
            raster = face.raster(code, grid_height)
            points: list[Point] = []
            for y in range(raster.height):
                for x in range(raster.width):
                    coverage = raster.pixels[y * raster.width + x]
                    if coverage >= threshold:
                        alpha = max(0.05, coverage / 255.0) if preserve_alpha else 1.0
                        points.append(Point(float(x), float(y), alpha=alpha, color=color))
            document.glyphs[code] = Glyph(
                code, raster.advance,
                [Layer(f"Imported {probe.format} outline", 1.0, True, points)],
            )
        if 0x20 in document.glyphs:
            document.metrics.word_spacing = document.glyphs[0x20].advance
        if ord("H") in document.glyphs:
            ys = [point.y for point in document.glyphs[ord("H")].layers[0].points]
            if ys:
                document.metrics.cap_height = max(1.0, baseline - min(ys))
        if ord("x") in document.glyphs:
            ys = [point.y for point in document.glyphs[ord("x")].layers[0].points]
            if ys:
                document.metrics.x_height = max(1.0, baseline - min(ys))
        errors = document.validate()
        if errors:
            raise FontImportError("\n".join(errors))
        return document
