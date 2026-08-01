from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import zlib
from pathlib import Path
from typing import Iterable

from tools.pcp3.io import import_ply, load_project, read_cloud, slugify
from tools.pcp3.model import PCPDocument, PCPPoint

from .model import PhysicsProfile, ShowcaseAsset

MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_IMPORTED_POINTS = 250_000


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_source(path: Path) -> Path:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Showcase source does not exist: {source}")
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Showcase source exceeds the 64 MiB Alpha import limit")
    return source


def _new_document(path: Path, kind: str) -> PCPDocument:
    doc = PCPDocument.new("environment_object")
    doc.asset_id = slugify(path.stem)
    doc.display_name = path.stem.replace("_", " ").strip().title() or "Imported Showcase Asset"
    doc.author.title = doc.display_name
    doc.author.asset_type = "environment_object"
    doc.author.description = f"Safely imported {kind} source for the SignalCloud A7 Showcase."
    doc.author.tags = ["showcase", "imported", kind]
    doc.metadata.update({
        "showcase_schema": "signalcloud.showcase-import-v1",
        "showcase_source_kind": kind,
        "showcase_import_policy": "data_only_no_execution",
        "showcase_source_name": path.name,
    })
    doc.runtime.update({
        "enabled": True,
        "auto_preview_in_game": False,
        "stress_spawn_policy": "showcase_test_object",
    })
    return doc


def _normalize_points(points: list[PCPPoint], *, target_extent: float = 4.0) -> list[PCPPoint]:
    if not points:
        return points
    min_x = min(point.x for point in points)
    min_y = min(point.y for point in points)
    min_z = min(point.z for point in points)
    max_x = max(point.x for point in points)
    max_y = max(point.y for point in points)
    max_z = max(point.z for point in points)
    center = ((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, (min_z + max_z) * 0.5)
    extent = max(max_x - min_x, max_y - min_y, max_z - min_z, 1.0e-6)
    scale = min(1000.0, target_extent / extent)
    for point in points:
        point.x = (point.x - center[0]) * scale
        point.y = (point.y - center[1]) * scale
        point.z = (point.z - center[2]) * scale
        point.radius = min(12.0, max(0.7, point.radius))
    return points


def _bounded(points: Iterable[PCPPoint]) -> list[PCPPoint]:
    result = list(points)
    if len(result) <= MAX_IMPORTED_POINTS:
        return result
    stride = math.ceil(len(result) / MAX_IMPORTED_POINTS)
    return result[::stride][:MAX_IMPORTED_POINTS]


def _parse_mtl(path: Path) -> dict[str, tuple[float, float, float]]:
    colors: dict[str, tuple[float, float, float]] = {}
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        return colors
    current = ""
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("newmtl "):
            current = line[7:].strip()
        elif current and line.startswith("Kd "):
            values = line.split()[1:4]
            if len(values) == 3:
                try:
                    colors[current] = tuple(max(0.0, min(1.0, float(v))) for v in values)  # type: ignore[assignment]
                except ValueError:
                    pass
    return colors


def _import_obj(path: Path) -> tuple[list[PCPPoint], list[str]]:
    vertices: list[tuple[float, float, float, float, float, float]] = []
    faces: list[tuple[list[int], str]] = []
    material = ""
    material_colors: dict[str, tuple[float, float, float]] = {}
    warnings: list[str] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("mtllib "):
            candidate = (path.parent / line[7:].strip()).resolve()
            try:
                candidate.relative_to(path.parent.resolve())
            except ValueError:
                warnings.append("OBJ material library escaped the source directory and was ignored")
            else:
                material_colors.update(_parse_mtl(candidate))
        elif line.startswith("usemtl "):
            material = line[7:].strip()
        elif line.startswith("v "):
            values = line.split()[1:]
            if len(values) < 3:
                continue
            try:
                x, y, z = (float(values[0]), float(values[1]), float(values[2]))
                if len(values) >= 6:
                    r, g, b = (float(values[3]), float(values[4]), float(values[5]))
                    if max(abs(r), abs(g), abs(b)) > 1.0:
                        r, g, b = r / 255.0, g / 255.0, b / 255.0
                else:
                    r, g, b = material_colors.get(material, (0.76, 0.81, 0.88))
                if all(math.isfinite(value) for value in (x, y, z, r, g, b)):
                    vertices.append((x, y, z, max(0.0, min(1.0, r)), max(0.0, min(1.0, g)), max(0.0, min(1.0, b))))
            except ValueError:
                continue
        elif line.startswith("f "):
            indices: list[int] = []
            for token in line.split()[1:]:
                try:
                    value = int(token.split("/", 1)[0])
                except ValueError:
                    continue
                index = value - 1 if value > 0 else len(vertices) + value
                if 0 <= index < len(vertices):
                    indices.append(index)
            if len(indices) >= 2:
                faces.append((indices, material))
    points = [PCPPoint(x, y, z, 2.0, r, g, b, 1.0, layer_id=1) for x, y, z, r, g, b in vertices]
    edge_budget = max(0, MAX_IMPORTED_POINTS - len(points))
    for indices, face_material in faces:
        color = material_colors.get(face_material, (0.64, 0.70, 0.78))
        for index, a_index in enumerate(indices):
            b_index = indices[(index + 1) % len(indices)]
            a = vertices[a_index]
            b = vertices[b_index]
            length = math.dist(a[:3], b[:3])
            samples = min(48, max(1, math.ceil(length / 0.08)))
            for step in range(1, samples):
                if edge_budget <= 0:
                    break
                t = step / samples
                points.append(PCPPoint(
                    a[0] + (b[0] - a[0]) * t,
                    a[1] + (b[1] - a[1]) * t,
                    a[2] + (b[2] - a[2]) * t,
                    1.7,
                    color[0], color[1], color[2], 1.0,
                    layer_id=1,
                ))
                edge_budget -= 1
            if edge_budget <= 0:
                break
        if edge_budget <= 0:
            break
    if not points:
        raise ValueError("OBJ import found no valid vertices")
    return _normalize_points(_bounded(points)), warnings


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def _decode_png(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG signature is invalid")
    offset = 8
    width = height = color_type = bit_depth = 0
    compressed = bytearray()
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        chunk_type = data[offset + 4:offset + 8]
        chunk_data = data[offset + 8:offset + 8 + length]
        if offset + 12 + length > len(data):
            raise ValueError("PNG chunk exceeds source size")
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(">IIBBBBB", chunk_data)
            if bit_depth != 8 or color_type not in (0, 2, 6) or compression != 0 or filter_method != 0 or interlace != 0:
                raise ValueError("Alpha PNG importer supports non-interlaced 8-bit grayscale/RGB/RGBA images")
            if width <= 0 or height <= 0 or width * height > 16_000_000:
                raise ValueError("PNG dimensions exceed the Alpha image import limit")
        elif chunk_type == b"IDAT":
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
        offset += 12 + length
    channels = {0: 1, 2: 3, 6: 4}.get(color_type, 0)
    if not width or not height or not channels:
        raise ValueError("PNG is missing a supported IHDR")
    raw = zlib.decompress(bytes(compressed))
    stride = width * channels
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise ValueError("PNG decompressed size does not match its dimensions")
    rows: list[bytearray] = []
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor:cursor + stride])
        cursor += stride
        prior = rows[-1] if rows else bytearray(stride)
        for i in range(stride):
            left = row[i - channels] if i >= channels else 0
            up = prior[i]
            up_left = prior[i - channels] if i >= channels else 0
            if filter_type == 1:
                row[i] = (row[i] + left) & 0xFF
            elif filter_type == 2:
                row[i] = (row[i] + up) & 0xFF
            elif filter_type == 3:
                row[i] = (row[i] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[i] = (row[i] + _paeth(left, up, up_left)) & 0xFF
            elif filter_type != 0:
                raise ValueError("PNG uses an unsupported filter")
        rows.append(row)
    pixels: list[tuple[int, int, int, int]] = []
    for row in rows:
        for x in range(width):
            base = x * channels
            if color_type == 0:
                value = row[base]
                pixels.append((value, value, value, 255))
            elif color_type == 2:
                pixels.append((row[base], row[base + 1], row[base + 2], 255))
            else:
                pixels.append((row[base], row[base + 1], row[base + 2], row[base + 3]))
    return width, height, pixels


def _decode_bmp(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    data = path.read_bytes()
    if len(data) < 54 or data[:2] != b"BM":
        raise ValueError("BMP signature is invalid")
    pixel_offset = struct.unpack_from("<I", data, 10)[0]
    dib_size = struct.unpack_from("<I", data, 14)[0]
    if dib_size < 40:
        raise ValueError("BMP DIB header is unsupported")
    width, signed_height, planes, bits, compression = struct.unpack_from("<iiHHI", data, 18)
    if width <= 0 or signed_height == 0 or planes != 1 or bits not in (24, 32) or compression != 0:
        raise ValueError("Alpha BMP importer supports uncompressed 24-bit and 32-bit BMP images")
    height = abs(signed_height)
    if width * height > 16_000_000:
        raise ValueError("BMP dimensions exceed the Alpha image import limit")
    top_down = signed_height < 0
    row_size = ((width * bits + 31) // 32) * 4
    pixels: list[tuple[int, int, int, int]] = []
    for y in range(height):
        source_y = y if top_down else height - 1 - y
        row_start = pixel_offset + source_y * row_size
        for x in range(width):
            base = row_start + x * (bits // 8)
            if base + bits // 8 > len(data):
                raise ValueError("BMP pixel data is truncated")
            b, g, r = data[base:base + 3]
            a = data[base + 3] if bits == 32 else 255
            pixels.append((r, g, b, a))
    return width, height, pixels


def _image_points(path: Path) -> tuple[list[PCPPoint], dict[str, object]]:
    if path.suffix.lower() == ".png":
        width, height, pixels = _decode_png(path)
    else:
        width, height, pixels = _decode_bmp(path)
    stride = max(1, math.ceil(math.sqrt(width * height / 120_000)))
    scale = 4.0 / max(width, height)
    points: list[PCPPoint] = []
    for y in range(0, height, stride):
        for x in range(0, width, stride):
            r, g, b, a = pixels[y * width + x]
            if a <= 3:
                continue
            luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
            points.append(PCPPoint(
                (x - (width - 1) * 0.5) * scale,
                ((height - 1) * 0.5 - y) * scale,
                (luminance - 0.5) * 0.16,
                max(1.0, 2.2 * stride),
                r / 255.0, g / 255.0, b / 255.0, a / 255.0,
                0.0, 0.0, 1.0, 1.0,
                1, 0,
            ))
    return _bounded(points), {"image_width": width, "image_height": height, "sample_stride": stride}


def _metadata_card(path: Path, kind: str) -> tuple[list[PCPPoint], dict[str, object]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > 4_000_000:
        raise ValueError("Metadata source exceeds the 4 MB text import limit")
    line_count = text.count("\n") + 1
    byte_count = len(text.encode("utf-8", errors="replace"))
    points: list[PCPPoint] = []
    width, height = 4.0, 2.5
    steps_x, steps_y = 80, 50
    for index in range(steps_x + 1):
        x = -width / 2 + width * index / steps_x
        points.append(PCPPoint(x, -height / 2, 0.0, 1.6, 0.28, 0.82, 0.94, 1.0))
        points.append(PCPPoint(x, height / 2, 0.0, 1.6, 0.28, 0.82, 0.94, 1.0))
    for index in range(steps_y + 1):
        y = -height / 2 + height * index / steps_y
        points.append(PCPPoint(-width / 2, y, 0.0, 1.6, 0.28, 0.82, 0.94, 1.0))
        points.append(PCPPoint(width / 2, y, 0.0, 1.6, 0.28, 0.82, 0.94, 1.0))
    # Data bars encode source size/line count without attempting to execute or render script syntax.
    bars = min(24, max(1, round(math.log2(max(2, byte_count)))))
    for bar in range(bars):
        x = -1.65 + bar * 0.14
        height_fraction = ((line_count + bar * 17) % 31 + 4) / 35.0
        for step in range(round(height_fraction * 24)):
            points.append(PCPPoint(x, -0.9 + step * 0.07, 0.02, 1.5, 0.56, 0.90, 0.42, 1.0))
    return points, {"metadata_kind": kind, "line_count": line_count, "byte_count": byte_count, "execution": "blocked"}


def import_source(path: Path, physics: PhysicsProfile | None = None) -> ShowcaseAsset:
    source = _safe_source(path)
    suffix = source.suffix.lower()
    warnings: list[str] = []
    kind = suffix.lstrip(".") or "unknown"
    profile = physics or PhysicsProfile(profile_id=f"showcase.{slugify(source.stem)}")

    if suffix == ".pcp3":
        document = load_project(source)
        document.metadata["showcase_source_kind"] = "pcp3"
        kind = "pcp3"
    elif suffix == ".pcp3cloud":
        points, digest = read_cloud(source)
        document = _new_document(source, "pcp3cloud")
        document.points = _bounded(points)
        document.metadata["imported_cloud_sha256"] = digest
        kind = "pcp3cloud"
    elif suffix == ".ply":
        document = _new_document(source, "ascii-ply")
        document.points = _normalize_points(_bounded(import_ply(source)))
        kind = "ascii-ply"
    elif suffix == ".obj":
        document = _new_document(source, "obj")
        document.points, warnings = _import_obj(source)
        kind = "obj"
    elif suffix in (".png", ".bmp"):
        document = _new_document(source, suffix[1:])
        document.points, image_metadata = _image_points(source)
        document.metadata.update(image_metadata)
        document.metadata["image_use"] = "sprite_height_sample_or_jmap_reference"
        kind = suffix[1:]
    elif suffix in (".udata", ".script"):
        document = _new_document(source, suffix[1:])
        document.points, metadata = _metadata_card(source, suffix[1:])
        document.metadata.update(metadata)
        kind = suffix[1:]
    else:
        raise ValueError("Supported Showcase imports: .pcp3, .pcp3cloud, ASCII .ply, .obj, .png, .bmp, .udata, .script")

    document.asset_id = slugify(document.asset_id or source.stem)
    document.metadata.update({
        "showcase_source_name": source.name,
        "showcase_source_sha256": _sha256(source),
        "showcase_source_kind": kind,
        "showcase_import_policy": "bounded_data_only_no_external_execution",
        "showcase_point_count": len(document.points),
    })
    provenance = {
        "schema": "signalcloud.showcase-provenance",
        "schema_major": 1,
        "source_name": source.name,
        "source_kind": kind,
        "source_sha256": _sha256(source),
        "importer": "SignalCloud Showcase A7a2",
        "execution_policy": "never_execute_source",
        "point_count": len(document.points),
    }
    profile.auto_fit(document.points)
    return ShowcaseAsset(source, kind, document, profile.normalize(), provenance, warnings)
