from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from .certificate import checksum_files, new_certificate, update_certificate, validate_certificate
from .model import PCPDocument, PCPPoint, SEMANTIC_FLAGS

MAGIC = b"PCP3CLD1"
CLOUD_VERSION = 1
CLOUD_RECORD_SIZE = 64
HEADER_STRUCT = struct.Struct("<8sIIQ32sQ")
RECORD_STRUCT = struct.Struct("<12fII2f")

SLUG_RE = re.compile(r"[^a-z0-9_]+")


def slugify(value: str) -> str:
    value = value.strip().lower().replace("-", "_").replace(" ", "_")
    value = SLUG_RE.sub("_", value).strip("_")
    return value or "untitled_asset"


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def point_payload(points: Iterable[PCPPoint]) -> bytes:
    output = bytearray()
    for point in points:
        output += RECORD_STRUCT.pack(
            float(point.x), float(point.y), float(point.z), float(point.radius),
            float(point.r), float(point.g), float(point.b), float(point.a),
            float(point.nx), float(point.ny), float(point.nz), float(point.density),
            int(point.layer_id) & 0xFFFFFFFF,
            int(point.flags) & 0xFFFFFFFF,
            float(point.attribute0), float(point.attribute1),
        )
    return bytes(output)


def encode_cloud(points: list[PCPPoint]) -> tuple[bytes, str]:
    payload = point_payload(points)
    digest = hashlib.sha256(payload).digest()
    header = HEADER_STRUCT.pack(MAGIC, CLOUD_VERSION, CLOUD_RECORD_SIZE, len(points), digest, 0)
    return header + payload, digest.hex()


def decode_cloud(data: bytes) -> tuple[list[PCPPoint], str]:
    if len(data) < HEADER_STRUCT.size:
        raise ValueError("PCP3 cloud is smaller than its header.")
    magic, version, record_size, count, expected_digest, _flags = HEADER_STRUCT.unpack_from(data, 0)
    if magic != MAGIC:
        raise ValueError("PCP3 cloud magic does not match PCP3CLD1.")
    if version != CLOUD_VERSION:
        raise ValueError(f"Unsupported PCP3 cloud version: {version}")
    if record_size != CLOUD_RECORD_SIZE:
        raise ValueError(f"Unsupported PCP3 record size: {record_size}")
    payload = data[HEADER_STRUCT.size:]
    expected_size = int(count) * record_size
    if len(payload) != expected_size:
        raise ValueError(f"PCP3 payload size mismatch: expected {expected_size}, got {len(payload)}")
    digest = hashlib.sha256(payload).digest()
    if digest != expected_digest:
        raise ValueError("PCP3 cloud SHA-256 does not match the embedded checksum.")
    points: list[PCPPoint] = []
    for offset in range(0, len(payload), record_size):
        values = RECORD_STRUCT.unpack_from(payload, offset)
        points.append(PCPPoint(
            x=values[0], y=values[1], z=values[2], radius=values[3],
            r=values[4], g=values[5], b=values[6], a=values[7],
            nx=values[8], ny=values[9], nz=values[10], density=values[11],
            layer_id=int(values[12]), flags=int(values[13]),
            attribute0=values[14], attribute1=values[15],
        ))
    return points, digest.hex()


def write_cloud(path: Path, points: list[PCPPoint]) -> str:
    encoded, digest = encode_cloud(points)
    atomic_write_bytes(path, encoded)
    return digest


def read_cloud(path: Path) -> tuple[list[PCPPoint], str]:
    return decode_cloud(path.read_bytes())


def portable_metadata(value: Any, project_root: Path) -> Any:
    """Return metadata safe for exported content without losing future fields."""
    root = Path(project_root).resolve()
    if isinstance(value, dict):
        return {key: portable_metadata(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [portable_metadata(item, root) for item in value]
    if isinstance(value, str):
        candidate = Path(value).expanduser()
        if candidate.is_absolute():
            normalized = value.replace("\\", "/")
            for marker in ("/content/", "/user_data/", "/reports/", "/exports/"):
                position = normalized.lower().find(marker)
                if position >= 0:
                    return normalized[position + 1:]
            try:
                return candidate.resolve().relative_to(root).as_posix()
            except (OSError, ValueError):
                return f"external://{candidate.name or 'resource'}"
    return value


def project_paths(project_path: Path) -> dict[str, Path]:
    if project_path.suffix.lower() != ".pcp3":
        project_path = project_path.with_suffix(".pcp3")
    return {
        "project": project_path,
        "cloud": project_path.with_suffix(".pcp3cloud"),
        "cert": project_path.with_suffix(".pcpcert.json"),
    }


def save_project(document: PCPDocument, project_path: Path, editor_name: str = "") -> dict[str, Path]:
    paths = project_paths(project_path)
    document.asset_id = slugify(document.asset_id or document.display_name)
    document.author.asset_type = document.environment_type
    cloud_digest = write_cloud(paths["cloud"], document.points)
    payload = document.to_dict(include_points=False)
    payload.update({
        "cloud_file": paths["cloud"].name,
        "cloud_sha256": cloud_digest,
        "certificate_file": paths["cert"].name,
        "point_record_size": CLOUD_RECORD_SIZE,
        "unknown_fields_policy": "preserve",
    })
    atomic_write_text(paths["project"], json.dumps(payload, indent=2, sort_keys=True) + "\n")
    content_checksum = checksum_files([paths["project"], paths["cloud"]])
    if paths["cert"].exists():
        certificate = json.loads(paths["cert"].read_text(encoding="utf-8"))
        certificate, _changed = update_certificate(certificate, asdict(document.author), content_checksum, editor_name)
    else:
        certificate = new_certificate(asdict(document.author), document.project_id, content_checksum)
    issues = validate_certificate(certificate)
    if issues:
        raise ValueError("Certificate validation failed: " + "; ".join(issues))
    atomic_write_text(paths["cert"], json.dumps(certificate, indent=2, sort_keys=True) + "\n")
    document.metadata["last_project_path"] = str(paths["project"])
    document.metadata["cloud_sha256"] = cloud_digest
    document.dirty = False
    return paths


def load_project(project_path: Path) -> PCPDocument:
    paths = project_paths(project_path)
    payload = json.loads(paths["project"].read_text(encoding="utf-8"))
    cloud_path = paths["project"].parent / str(payload.get("cloud_file", paths["cloud"].name))
    points, digest = read_cloud(cloud_path)
    expected = str(payload.get("cloud_sha256", ""))
    if expected and expected != digest:
        raise ValueError("Project cloud checksum does not match project metadata.")
    document = PCPDocument.from_dict(payload)
    document.points = points
    document.metadata["last_project_path"] = str(paths["project"])
    document.metadata["cloud_sha256"] = digest
    document.dirty = False
    return document


def json_value(value: Any) -> str:
    return json.dumps({"value": value}, separators=(",", ":"), ensure_ascii=False)


def udata_text(document: PCPDocument, cloud_name: str, project_name: str, cert_name: str,
               cloud_sha256: str, certificate: dict[str, Any]) -> str:
    lower, upper = document.bounds()
    layer_summary = [
        {
            "id": layer.id,
            "name": layer.name,
            "group": layer.group,
            "semantic": layer.semantic,
            "visible": layer.visible,
            "locked": layer.locked,
            "opacity": layer.opacity,
            "blend_mode": layer.blend_mode,
            "tags": layer.tags,
            "future_attributes": layer.future_attributes,
        }
        for layer in document.layers
    ]
    author = certificate.get("author", {})
    lines = [
        "@udata 1", "",
        "[header]",
        f"data_type: {json_value('pcp3_asset')};",
        f"schema: {json_value(document.schema)};",
        f"asset_id: {json_value(document.asset_id)};",
        f"display_name: {json_value(document.display_name)};",
        f"asset_kind: {json_value(document.environment_type)};",
        f"project_id: {json_value(document.project_id)};",
        "",
        "[body]",
        f"representation: {json_value('pcp3_layered_point_cloud')};",
        f"cloud_file: {json_value(cloud_name)};",
        f"project_file: {json_value(project_name)};",
        f"certificate_file: {json_value(cert_name)};",
        f"point_count: {json_value(len(document.points))};",
        f"point_record_size: {json_value(CLOUD_RECORD_SIZE)};",
        f"cloud_sha256: {json_value(cloud_sha256)};",
        f"bounds_min: {json_value(list(lower))};",
        f"bounds_max: {json_value(list(upper))};",
        f"layers: {json.dumps({'value': layer_summary}, separators=(',', ':'), ensure_ascii=False)};",
        "",
        "[runtime]",
    ]
    for key in ("enabled", "auto_preview_in_game", "preview_zone", "preview_position", "preview_scale", "stress_spawn_policy"):
        lines.append(f"{key}: {json_value(document.runtime.get(key))};")
    lines += [
        "loader_policy: " + json_value("forgiving_preserve_unknown") + ";",
        "unsupported_attribute_policy: " + json_value("retain_for_future_engine_versions") + ";",
        "",
        "[canvas]",
        f"width: {json_value(document.settings.width)};",
        f"height: {json_value(document.settings.height)};",
        f"depth: {json_value(document.settings.depth)};",
        f"ambient_light: {json_value(document.settings.ambient_light)};",
        f"point_scale: {json_value(document.settings.point_scale)};",
        f"density_scale: {json_value(document.settings.density_scale)};",
        f"grid_spacing: {json_value(document.settings.grid_spacing)};",
        f"background: {json_value(document.settings.background)};",
        f"future_attributes: {json.dumps({'value': document.settings.future_attributes}, separators=(',', ':'), ensure_ascii=False)};",
        "",
        "[authoring]",
        f"sidecar_file: {json_value(document.metadata.get('authoring_sidecar_file', ''))};",
        f"schema: {json_value('pcp3_advanced_authoring_v1' if document.metadata.get('advanced_authoring') else '')};",
        f"preserve_until_runtime_support: {json_value(True)};",
        "",
        "[runtime_preview]",
        f"sidecar_file: {json_value(document.metadata.get('runtime_sidecar_file', ''))};",
        f"schema: {json_value('pcp3_runtime_preview_v1' if document.metadata.get('runtime_sidecar_file') else '')};",
        f"execution_policy: {json_value('safe_non_destructive_preview_only')};",
        f"game_factory_status: {json_value('bridged_by_branch6_when_explicitly_enabled')};",
        "",
        "[runtime_factory]",
        f"json_sidecar_file: {json_value(document.metadata.get('factory_json_file', ''))};",
        f"udata_sidecar_file: {json_value(document.metadata.get('factory_udata_file', ''))};",
        f"schema: {json_value('pcp3_runtime_factory_v1' if document.metadata.get('factory_udata_file') else '')};",
        f"execution_policy: {json_value('guarded_explicit_opt_in_no_arbitrary_code')};",
        f"max_nesting_depth: {json_value(1)};",
        "",
        "[runtime_interaction]",
        f"json_sidecar_file: {json_value(document.metadata.get('interaction_json_file', ''))};",
        f"udata_sidecar_file: {json_value(document.metadata.get('interaction_udata_file', ''))};",
        f"schema: {json_value('pcp3_guarded_interaction_v1' if document.metadata.get('interaction_udata_file') else '')};",
        f"execution_policy: {json_value('bounded_reversible_visual_state_no_gameplay_mutation')};",
        f"blocked_gameplay_mutation: {json_value(True)};",
        "",
        "[runtime_entity]",
        f"json_sidecar_file: {json_value(document.metadata.get('entity_json_file', ''))};",
        f"udata_sidecar_file: {json_value(document.metadata.get('entity_udata_file', ''))};",
        f"schema: {json_value('pcp3_entity_runtime_v1' if document.metadata.get('entity_udata_file') else '')};",
        f"execution_policy: {json_value('guarded_entity_visual_runtime_no_damage_or_save_mutation')};",
        f"bone_weight_encoding: {json_value('attribute0_weight_attribute1_1000_plus_channel')};",
        "",
        "[runtime_world]",
        f"json_sidecar_file: {json_value(document.metadata.get('world_json_file', ''))};",
        f"udata_sidecar_file: {json_value(document.metadata.get('world_udata_file', ''))};",
        f"reference_audit_file: {json_value(document.metadata.get('world_reference_file', ''))};",
        f"schema: {json_value('pcp3_world_assembly_v1' if document.metadata.get('world_udata_file') else '')};",
        f"execution_policy: {json_value('guarded_world_assembly_one_level_no_arbitrary_code')};",
        f"portal_policy: {json_value('explicit_distance_bounded_cooldown_handoff')};",
        f"liquid_policy: {json_value('visual_wave_tint_flow_evidence_no_physics_force')};",
        "",
        "[runtime_encounter]",
        f"json_sidecar_file: {json_value(document.metadata.get('encounter_json_file', ''))};",
        f"udata_sidecar_file: {json_value(document.metadata.get('encounter_udata_file', ''))};",
        f"schema: {json_value('pcp3_encounter_runtime_v1' if document.metadata.get('encounter_udata_file') else '')};",
        f"execution_policy: {json_value('guarded_bounded_wave_scheduler_no_damage_economy_or_save_mutation')};",
        f"reward_policy: {json_value('telemetry_hook_until_explicit_game_approval')};",
        f"max_reference_depth: {json_value(1)};",
        "",
        "[runtime_streaming]",
        f"json_sidecar_file: {json_value(document.metadata.get('streaming_json_file', ''))};",
        f"udata_sidecar_file: {json_value(document.metadata.get('streaming_udata_file', ''))};",
        f"chunk_manifest_file: {json_value(document.metadata.get('streaming_chunks_file', ''))};",
        f"schema: {json_value('pcp3_streaming_runtime_v1' if document.metadata.get('streaming_udata_file') else '')};",
        f"execution_policy: {json_value('bounded_distance_lod_semantic_reserve_no_source_mutation')};",
        f"resident_environment_baseline: {json_value('adaptive_8m_preserved')};",
        "",
        "[certificate]",
        f"creator_name: {json_value(author.get('creator_name', ''))};",
        f"title: {json_value(author.get('title', ''))};",
        f"description: {json_value(author.get('description', ''))};",
        f"tags: {json_value(author.get('tags', []))};",
        f"serial_id: {json_value(certificate.get('serial_id', ''))};",
        f"created_epoch_octal: {json_value(certificate.get('created_epoch_octal', ''))};",
        f"hash_proof: {json_value(certificate.get('latest_hash_proof', certificate.get('initial_hash_proof', '')))};",
        f"checksum: {json_value(certificate.get('latest_checksum', certificate.get('initial_checksum', '')))};",
    ]
    if "version" in certificate:
        lines.append(f"version: {json_value(certificate['version'])};")
    lines += ["", "[future]", f"preserved_project_metadata: {json.dumps({'value': document.metadata}, separators=(',', ':'), ensure_ascii=False)};", ""]
    return "\n".join(lines)


def export_asset(document: PCPDocument, project_root: Path, project_path: Path | None = None,
                 editor_name: str = "") -> Path:
    document.asset_id = slugify(document.asset_id or document.display_name)
    environment = document.environment_type
    asset_dir = project_root / "content" / "pcp3_assets" / environment / document.asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    target_project = asset_dir / f"{document.asset_id}.pcp3"
    source_certificate: Path | None = None
    if project_path is not None and project_path.exists():
        source_paths = project_paths(project_path)
        source_certificate = source_paths["cert"] if source_paths["cert"].exists() else None
        loaded = load_project(project_path)
        loaded.asset_id = document.asset_id
        loaded.display_name = document.display_name
        loaded.environment_type = document.environment_type
        loaded.author = document.author
        loaded.runtime = document.runtime
        loaded.settings = document.settings
        loaded.metadata.update(document.metadata)
        document = loaded
    document.metadata = portable_metadata(document.metadata, project_root)
    target_paths = project_paths(target_project)
    if source_certificate is not None and source_certificate.resolve() != target_paths["cert"].resolve():
        target_paths["cert"].parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_certificate, target_paths["cert"])
    portable_target = target_project.relative_to(project_root.resolve()).as_posix()
    document.metadata["last_project_path"] = portable_target
    paths = save_project(document, target_project, editor_name=editor_name)
    document.metadata["last_project_path"] = portable_target
    certificate = json.loads(paths["cert"].read_text(encoding="utf-8"))
    cloud_sha256 = document.metadata.get("cloud_sha256") or hashlib.sha256(paths["cloud"].read_bytes()).hexdigest()
    udata_path = asset_dir / f"{document.asset_id}.udata"
    atomic_write_text(udata_path, udata_text(
        document, paths["cloud"].name, paths["project"].name, paths["cert"].name,
        str(cloud_sha256), certificate,
    ))
    from tools.asset_doctor.content_abi import write_asset_envelope
    write_asset_envelope(
        project_root / "content",
        paths["project"],
        asset_id=f"pcp3.{document.environment_type}.{document.asset_id}",
        asset_type="pcp3_project",
        family="point_cloud",
        pack="legacy",
        hot_reload="authoring-only",
    )
    return asset_dir


def export_ply(document: PCPDocument, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "ply", "format ascii 1.0", "comment Point Cloud Paint++ export",
        f"element vertex {len(document.points)}",
        "property float x", "property float y", "property float z",
        "property uchar red", "property uchar green", "property uchar blue", "property uchar alpha",
        "property float radius", "property uint layer_id", "property uint semantic_flags",
        "end_header",
    ]
    lines = list(header)
    for point in document.points:
        lines.append(
            f"{point.x:.7g} {point.y:.7g} {point.z:.7g} "
            f"{round(max(0.0, min(1.0, point.r)) * 255)} "
            f"{round(max(0.0, min(1.0, point.g)) * 255)} "
            f"{round(max(0.0, min(1.0, point.b)) * 255)} "
            f"{round(max(0.0, min(1.0, point.a)) * 255)} "
            f"{point.radius:.7g} {point.layer_id} {point.flags}"
        )
    atomic_write_text(path, "\n".join(lines) + "\n")


def import_ply(path: Path, layer_id: int = 1) -> list[PCPPoint]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or lines[0].strip() != "ply":
        raise ValueError("Only ASCII PLY point-cloud files are supported in the current PCP3 format.")
    properties: list[str] = []
    vertex_count = 0
    header_end = -1
    in_vertex = False
    for index, raw in enumerate(lines):
        line = raw.strip()
        if line == "format ascii 1.0":
            continue
        if line.startswith("element vertex "):
            vertex_count = int(line.split()[-1])
            in_vertex = True
            continue
        if line.startswith("element ") and not line.startswith("element vertex "):
            in_vertex = False
        if in_vertex and line.startswith("property "):
            properties.append(line.split()[-1])
        if line == "end_header":
            header_end = index
            break
    if header_end < 0:
        raise ValueError("PLY header is incomplete.")
    required = {"x", "y", "z"}
    if not required.issubset(properties):
        raise ValueError("PLY requires x, y, and z properties.")
    points: list[PCPPoint] = []
    rows = lines[header_end + 1: header_end + 1 + vertex_count]
    for raw in rows:
        values = raw.split()
        if len(values) < len(properties):
            continue
        record = dict(zip(properties, values))
        def f(name: str, default: float) -> float:
            try:
                return float(record.get(name, default))
            except (TypeError, ValueError):
                return default
        def color(name: str, default: float) -> float:
            value = f(name, default * 255.0)
            return value / 255.0 if value > 1.0 else value
        points.append(PCPPoint(
            f("x", 0.0), f("y", 0.0), f("z", 0.0), f("radius", 2.0),
            color("red", 0.85), color("green", 0.80), color("blue", 0.58), color("alpha", 1.0),
            f("nx", 0.0), f("ny", 1.0), f("nz", 0.0), f("density", 1.0),
            int(f("layer_id", layer_id)), int(f("semantic_flags", 0.0)),
        ))
    return points


def copy_project_bundle(source_project: Path, destination_project: Path) -> dict[str, Path]:
    source = project_paths(source_project)
    destination = project_paths(destination_project)
    destination["project"].parent.mkdir(parents=True, exist_ok=True)
    for key in source:
        if source[key].exists():
            shutil.copy2(source[key], destination[key])
    return destination
