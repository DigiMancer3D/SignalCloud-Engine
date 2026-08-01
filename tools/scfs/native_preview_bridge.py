from __future__ import annotations

import hashlib
import os
import struct
import subprocess
from pathlib import Path

from .model import FontDocument

MAGIC = b"PCP3CLD1"
HEADER = struct.Struct("<8sIIQ32sQ")
RECORD = struct.Struct("<12fII2f")


def encode_font_cloud(document: FontDocument, text: str, *, simple: bool) -> bytes:
    payload = bytearray()
    for offset_x, offset_y, point, _, layer_index in document.layout(text):
        color = point.color.removeprefix("#")
        red = int(color[0:2], 16)/255.0
        green = int(color[2:4], 16)/255.0
        blue = int(color[4:6], 16)/255.0
        payload += RECORD.pack(
            float(offset_x+point.x), float(-(offset_y+point.y)),
            0.0 if simple else float(point.z), 2.8,
            red, green, blue, float(point.alpha),
            0.0, 0.0, 1.0, 1.0,
            int(layer_index+1), 0, 0.0, 0.0,
        )
    digest = hashlib.sha256(payload).digest()
    return HEADER.pack(MAGIC, 1, RECORD.size, len(payload)//RECORD.size, digest, 0) + payload


def write_font_cloud(path: Path, document: FontDocument, text: str, *, simple: bool) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_bytes(encode_font_cloud(document, text, simple=simple))
    os.replace(temporary, path)
    return path


def find_native_preview(project_root: Path) -> Path | None:
    root = Path(project_root).resolve()
    candidates = [
        root/"build"/"almond_signal_pcp_preview",
        root.parent/"build"/"almond_signal_pcp_preview",
        root.parent/"build-core"/"almond_signal_pcp_preview",
    ]
    try:
        for sibling in root.parent.iterdir():
            if sibling.is_dir():
                candidates.extend([
                    sibling/"build"/"almond_signal_pcp_preview",
                    sibling/"build-core"/"almond_signal_pcp_preview",
                ])
    except OSError:
        pass
    return next((path for path in candidates if path.is_file() and os.access(path, os.X_OK)), None)


def launch_native_preview(project_root: Path, document: FontDocument, text: str,
                          *, simple: bool) -> subprocess.Popen[bytes]:
    binary = find_native_preview(project_root)
    if binary is None:
        raise FileNotFoundError(
            "almond_signal_pcp_preview was not found in +SCFS+ or neighboring engine build folders."
        )
    cloud = write_font_cloud(
        Path(project_root)/"user_data"/"scfs"/"render_preview"/"scfs_text_preview.pcp3cloud",
        document, text, simple=simple,
    )
    return subprocess.Popen([str(binary), f"--asset={cloud}"], cwd=binary.parent.parent)
