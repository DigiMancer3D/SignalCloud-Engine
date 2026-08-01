from __future__ import annotations

import ctypes
import ctypes.util
import math
from dataclasses import dataclass
from pathlib import Path


class FreeTypeError(ValueError):
    pass


FT_Long = ctypes.c_long
FT_ULong = ctypes.c_ulong
FT_Pos = ctypes.c_long
FT_Fixed = ctypes.c_long
FT_Int = ctypes.c_int
FT_UInt = ctypes.c_uint
FT_Short = ctypes.c_short
FT_UShort = ctypes.c_ushort
FT_Byte = ctypes.c_ubyte


class FT_Generic(ctypes.Structure):
    _fields_ = [("data", ctypes.c_void_p), ("finalizer", ctypes.c_void_p)]


class FT_BBox(ctypes.Structure):
    _fields_ = [("xMin", FT_Pos), ("yMin", FT_Pos), ("xMax", FT_Pos), ("yMax", FT_Pos)]


class FT_Vector(ctypes.Structure):
    _fields_ = [("x", FT_Pos), ("y", FT_Pos)]


class FT_Glyph_Metrics(ctypes.Structure):
    _fields_ = [
        ("width", FT_Pos), ("height", FT_Pos),
        ("horiBearingX", FT_Pos), ("horiBearingY", FT_Pos), ("horiAdvance", FT_Pos),
        ("vertBearingX", FT_Pos), ("vertBearingY", FT_Pos), ("vertAdvance", FT_Pos),
    ]


class FT_Bitmap(ctypes.Structure):
    _fields_ = [
        ("rows", FT_UInt), ("width", FT_UInt), ("pitch", FT_Int),
        ("buffer", ctypes.POINTER(FT_Byte)), ("num_grays", FT_UShort),
        ("pixel_mode", FT_Byte), ("palette_mode", FT_Byte), ("palette", ctypes.c_void_p),
    ]


class FT_GlyphSlotRec(ctypes.Structure):
    pass


FT_GlyphSlot = ctypes.POINTER(FT_GlyphSlotRec)

FT_GlyphSlotRec._fields_ = [
    ("library", ctypes.c_void_p), ("face", ctypes.c_void_p), ("next", FT_GlyphSlot),
    ("glyph_index", FT_UInt), ("generic", FT_Generic), ("metrics", FT_Glyph_Metrics),
    ("linearHoriAdvance", FT_Fixed), ("linearVertAdvance", FT_Fixed),
    ("advance", FT_Vector), ("format", ctypes.c_uint32), ("bitmap", FT_Bitmap),
    ("bitmap_left", FT_Int), ("bitmap_top", FT_Int),
]


class FT_FaceRec(ctypes.Structure):
    _fields_ = [
        ("num_faces", FT_Long), ("face_index", FT_Long), ("face_flags", FT_Long),
        ("style_flags", FT_Long), ("num_glyphs", FT_Long),
        ("family_name", ctypes.c_char_p), ("style_name", ctypes.c_char_p),
        ("num_fixed_sizes", FT_Int), ("available_sizes", ctypes.c_void_p),
        ("num_charmaps", FT_Int), ("charmaps", ctypes.c_void_p),
        ("generic", FT_Generic), ("bbox", FT_BBox), ("units_per_EM", FT_UShort),
        ("ascender", FT_Short), ("descender", FT_Short), ("height", FT_Short),
        ("max_advance_width", FT_Short), ("max_advance_height", FT_Short),
        ("underline_position", FT_Short), ("underline_thickness", FT_Short),
        ("glyph", FT_GlyphSlot), ("size", ctypes.c_void_p), ("charmap", ctypes.c_void_p),
    ]


FT_Face = ctypes.POINTER(FT_FaceRec)


@dataclass(frozen=True)
class RasterGlyph:
    width: int
    height: int
    pixels: bytes
    advance: float


def _load_library():
    name = ctypes.util.find_library("freetype") or "libfreetype.so.6"
    try:
        library = ctypes.CDLL(name)
    except OSError as exc:
        raise FreeTypeError(
            "The system FreeType library was not found. Install libfreetype6."
        ) from exc
    library.FT_Init_FreeType.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    library.FT_Init_FreeType.restype = FT_Int
    library.FT_Done_FreeType.argtypes = [ctypes.c_void_p]
    library.FT_New_Face.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, FT_Long, ctypes.POINTER(FT_Face),
    ]
    library.FT_New_Face.restype = FT_Int
    library.FT_Done_Face.argtypes = [FT_Face]
    library.FT_Set_Pixel_Sizes.argtypes = [FT_Face, FT_UInt, FT_UInt]
    library.FT_Set_Pixel_Sizes.restype = FT_Int
    library.FT_Get_Char_Index.argtypes = [FT_Face, FT_ULong]
    library.FT_Get_Char_Index.restype = FT_UInt
    library.FT_Load_Char.argtypes = [FT_Face, FT_ULong, FT_Int]
    library.FT_Load_Char.restype = FT_Int
    return library


def _decode(value: bytes | None, fallback: str) -> str:
    return value.decode("utf-8", "replace") if value else fallback


class NativeFreeTypeFace:
    """Tiny ctypes bridge used when Pillow cannot render a valid TTF/OTF face."""

    def __init__(self, path: Path, grid_height: int) -> None:
        self.path = Path(path)
        self.lib = _load_library()
        self.library = ctypes.c_void_p()
        if self.lib.FT_Init_FreeType(ctypes.byref(self.library)):
            raise FreeTypeError("FreeType initialization failed.")
        self.face = FT_Face()
        error = self.lib.FT_New_Face(
            self.library, str(self.path).encode("utf-8"), 0, ctypes.byref(self.face)
        )
        if error:
            self.close()
            raise FreeTypeError(f"FreeType rejected this font (error {error}).")
        record = self.face.contents
        self.family = _decode(record.family_name, self.path.stem)
        self.style = _decode(record.style_name, "")
        self.units_per_em = max(1, int(record.units_per_EM))
        self.ascender_units = int(record.ascender)
        self.descender_units = int(record.descender)
        line_units = max(1, self.ascender_units - self.descender_units)
        self.render_size = grid_height * 4
        self.source_height = max(1, round(line_units * self.render_size / self.units_per_em))
        self.baseline = round(self.ascender_units * self.render_size / self.units_per_em)
        self.scale = grid_height / self.source_height
        if self.lib.FT_Set_Pixel_Sizes(self.face, 0, self.render_size):
            self.close()
            raise FreeTypeError("FreeType could not set the requested raster size.")

    def close(self) -> None:
        if getattr(self, "face", None):
            self.lib.FT_Done_Face(self.face)
            self.face = FT_Face()
        if getattr(self, "library", None):
            self.lib.FT_Done_FreeType(self.library)
            self.library = ctypes.c_void_p()

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def has_char(self, codepoint: int) -> bool:
        return bool(self.lib.FT_Get_Char_Index(self.face, codepoint))

    @staticmethod
    def _pixel(bitmap: FT_Bitmap, x: int, y: int) -> int:
        pitch = int(bitmap.pitch)
        row = y if pitch >= 0 else int(bitmap.rows) - 1 - y
        address = ctypes.addressof(bitmap.buffer.contents) + row * abs(pitch)
        if bitmap.pixel_mode == 2:  # FT_PIXEL_MODE_GRAY
            return ctypes.c_ubyte.from_address(address + x).value
        if bitmap.pixel_mode == 1:  # FT_PIXEL_MODE_MONO
            byte = ctypes.c_ubyte.from_address(address + x // 8).value
            return 255 if byte & (0x80 >> (x % 8)) else 0
        return 0

    @staticmethod
    def _box_resize(source: bytearray, sw: int, sh: int, tw: int, th: int) -> bytes:
        target = bytearray(tw * th)
        for ty in range(th):
            y0, y1 = ty * sh / th, (ty + 1) * sh / th
            iy0, iy1 = int(math.floor(y0)), int(math.ceil(y1))
            for tx in range(tw):
                x0, x1 = tx * sw / tw, (tx + 1) * sw / tw
                ix0, ix1 = int(math.floor(x0)), int(math.ceil(x1))
                total = weight = 0.0
                for sy in range(iy0, min(iy1, sh)):
                    wy = min(y1, sy + 1) - max(y0, sy)
                    for sx in range(ix0, min(ix1, sw)):
                        wx = min(x1, sx + 1) - max(x0, sx)
                        w = wx * wy
                        total += source[sy * sw + sx] * w
                        weight += w
                target[ty * tw + tx] = round(total / weight) if weight else 0
        return bytes(target)

    def raster(self, codepoint: int, grid_height: int) -> RasterGlyph:
        if self.lib.FT_Load_Char(self.face, codepoint, 4):  # FT_LOAD_RENDER
            raise FreeTypeError(f"FreeType could not rasterize U+{codepoint:04X}.")
        slot = self.face.contents.glyph.contents
        bitmap = slot.bitmap
        advance_px = slot.advance.x / 64.0
        left = int(slot.bitmap_left)
        right = left + int(bitmap.width)
        min_x, max_x = min(0, left), max(round(advance_px), right)
        source_width = max(1, max_x - min_x)
        canvas = bytearray(source_width * self.source_height)
        top_y = self.baseline - int(slot.bitmap_top)
        for by in range(int(bitmap.rows)):
            y = top_y + by
            if not 0 <= y < self.source_height or not bitmap.buffer:
                continue
            for bx in range(int(bitmap.width)):
                x = left - min_x + bx
                if 0 <= x < source_width:
                    canvas[y * source_width + x] = self._pixel(bitmap, bx, by)
        target_width = max(1, round(source_width * self.scale))
        pixels = self._box_resize(
            canvas, source_width, self.source_height, target_width, grid_height
        )
        return RasterGlyph(target_width, grid_height, pixels, max(0.0, advance_px * self.scale))
