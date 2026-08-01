from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Any, Iterable

from tools.pcp3.model import PCPPoint, SEMANTIC_FLAGS, primitive_box, primitive_cylinder, primitive_line, primitive_sphere


PRESET_GROUPS: dict[str, tuple[tuple[str, str], ...]] = {
    "Walls": (
        ("plaster_wall", "Plaster Walls"),
        ("rock_wall", "Rock Walls"),
        ("wood_wall", "Wood Walls"),
        ("plywood_wall", "Plywood Walls"),
    ),
    "Floors": (
        ("flat_floor", "Flat Floor"),
        ("rocky_floor", "Rocky Floor"),
        ("grass_floor", "Grass Floor"),
    ),
    "Ceilings": (
        ("flat_ceiling", "Ceiling"),
        ("vaulted_ceiling", "Vaulted Ceiling"),
        ("rounded_ceiling", "Rounded Ceiling"),
        ("domed_ceiling", "Domed Ceiling"),
        ("rock_ceiling", "Rock Ceiling"),
    ),
    "Fixtures": (
        ("chandelier", "Chandelier"),
        ("wall_light", "Wall Light"),
        ("ceiling_light", "Ceiling Light"),
        ("corner_camera", "Corner Camera"),
    ),
    "Openings": (
        ("window_frame", "Window (frame + hole)"),
        ("door_frame", "Door (frame + hole)"),
        ("portal_frame", "Portal (frame)"),
    ),
}

PRESET_LABELS = {key: label for entries in PRESET_GROUPS.values() for key, label in entries}
FRAME_STYLES = (
    "square",
    "circle",
    "oval",
    "crossed",
    "barred",
    "office_slit_upward",
    "office_slit_sideways",
)


@dataclass(frozen=True)
class Region3D:
    projection: str
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    center: tuple[float, float, float]
    size: tuple[float, float, float]

    @classmethod
    def from_points(
        cls,
        projection: str,
        a: tuple[float, float, float],
        b: tuple[float, float, float],
        *,
        missing_size: float = 0.5,
    ) -> "Region3D":
        minimum = tuple(min(a[index], b[index]) for index in range(3))
        maximum = tuple(max(a[index], b[index]) for index in range(3))
        sizes = [maximum[index] - minimum[index] for index in range(3)]
        if projection == "Top X/Z":
            sizes[1] = max(missing_size, sizes[1])
        elif projection == "Front X/Y":
            sizes[2] = max(missing_size, sizes[2])
        elif projection == "Side Z/Y":
            sizes[0] = max(missing_size, sizes[0])
        else:
            missing = min(range(3), key=lambda index: sizes[index])
            sizes[missing] = max(missing_size, sizes[missing])
        center = tuple((minimum[index] + maximum[index]) * 0.5 for index in range(3))
        return cls(projection, minimum, maximum, center, tuple(max(0.05, value) for value in sizes))


def semantic_for_preset(preset: str) -> str:
    if preset.endswith("wall"):
        return "wall"
    if preset.endswith("floor"):
        return "floor"
    if preset.endswith("ceiling"):
        return "ceiling"
    if preset in {"chandelier", "wall_light", "ceiling_light", "corner_camera"}:
        return "light"
    if preset.endswith("frame"):
        return "portal"
    return "generic"


def group_for_preset(preset: str) -> str:
    for group, entries in PRESET_GROUPS.items():
        if any(key == preset for key, _label in entries):
            return group
    return "Guided Shapes"


def default_parameters(preset: str, region: Region3D, *, spacing: float, room_height: float) -> dict[str, Any]:
    sx, sy, sz = region.size
    parameters: dict[str, Any] = {
        "spacing": max(0.05, spacing),
        "thickness": max(0.2, spacing * 2.0),
        "height": max(0.5, sy if region.projection != "Top X/Z" else room_height),
        "roughness": 0.12,
        "rise": max(0.5, min(sx, sz, max(1.0, room_height * 0.35))),
        "chain_length": max(0.8, room_height * 0.28),
        "stages": 3,
        "scale": max(0.1, max(sx / 6.0, sy / 5.0, sz / 9.0)),
        "frame_thickness": max(0.15, spacing * 2.0),
        "frame_depth": max(0.25, spacing * 3.0),
        "frame_style": "square",
    }
    if preset == "plaster_wall":
        parameters["thickness"] = max(0.2, spacing * 2.0)
        parameters["roughness"] = 0.02
    elif preset == "rock_wall":
        parameters["thickness"] = max(0.4, spacing * 3.0)
        parameters["roughness"] = 0.22
    elif preset == "wood_wall":
        parameters["thickness"] = max(0.25, spacing * 2.0)
        parameters["plank_size"] = max(0.35, spacing * 4.0)
    elif preset == "plywood_wall":
        parameters["thickness"] = max(0.2, spacing * 2.0)
        parameters["panel_size"] = max(1.0, spacing * 10.0)
    elif preset in {"flat_floor", "rocky_floor", "grass_floor"}:
        parameters["thickness"] = max(0.18, spacing * 2.0)
    elif preset.endswith("ceiling"):
        parameters["thickness"] = max(0.18, spacing * 2.0)
    elif preset == "chandelier":
        parameters["radius"] = max(0.5, min(sx, sz) * 0.35)
    elif preset in {"wall_light", "ceiling_light"}:
        parameters["depth"] = max(0.3, spacing * 3.0)
        parameters["width"] = max(0.5, sx)
        parameters["fixture_height"] = max(0.25, sy)
    return parameters


def preview_polyline(preset: str, region: Region3D, params: dict[str, Any]) -> list[tuple[float, float, float]]:
    """Return a lightweight cyan guide; detailed generation remains deferred until confirmation."""
    cx, cy, cz = region.center
    sx, sy, sz = region.size
    if preset.endswith("wall"):
        height = float(params.get("height", sy))
        thickness = float(params.get("thickness", 0.25))
        if region.projection == "Side Z/Y":
            sx, sy, sz = thickness, height, max(sz, 0.2)
        elif region.projection == "Top X/Z":
            if sx >= sz:
                sx, sy, sz = max(sx, 0.2), height, thickness
            else:
                sx, sy, sz = thickness, height, max(sz, 0.2)
        else:
            sx, sy, sz = max(sx, 0.2), height, thickness
        cy = region.minimum[1] + height * 0.5 if region.projection != "Top X/Z" else cy + height * 0.5
    elif preset.endswith("floor") or preset.endswith("ceiling"):
        sy = float(params.get("thickness", 0.2))
    elif preset.endswith("frame"):
        if region.projection == "Top X/Z":
            sy = max(1.0, float(params.get("height", region.size[1])))
        if region.projection == "Front X/Y":
            sz = float(params.get("frame_depth", 0.3))
        elif region.projection == "Side Z/Y":
            sx = float(params.get("frame_depth", 0.3))
    elif preset == "chandelier":
        radius = float(params.get("radius", 1.0))
        chain = float(params.get("chain_length", 1.5))
        return [
            (cx, cy, cz),
            (cx, cy - chain, cz),
            (cx + radius, cy - chain, cz),
            (cx, cy - chain, cz + radius),
            (cx - radius, cy - chain, cz),
            (cx, cy - chain, cz - radius),
            (cx + radius, cy - chain, cz),
        ]
    elif preset == "corner_camera":
        scale = float(params.get("scale", 0.2))
        sx, sy, sz = 6.0 * scale, 5.0 * scale, 9.0 * scale
    return box_polyline((cx, cy, cz), (sx, sy, sz))


def box_polyline(center: tuple[float, float, float], size: tuple[float, float, float]) -> list[tuple[float, float, float]]:
    cx, cy, cz = center
    sx, sy, sz = (max(0.01, value) * 0.5 for value in size)
    corners = {
        "000": (cx - sx, cy - sy, cz - sz),
        "100": (cx + sx, cy - sy, cz - sz),
        "110": (cx + sx, cy + sy, cz - sz),
        "010": (cx - sx, cy + sy, cz - sz),
        "001": (cx - sx, cy - sy, cz + sz),
        "101": (cx + sx, cy - sy, cz + sz),
        "111": (cx + sx, cy + sy, cz + sz),
        "011": (cx - sx, cy + sy, cz + sz),
    }
    order = ["000", "100", "110", "010", "000", "001", "101", "111", "011", "001", "101", "100", "110", "111", "011", "010"]
    return [corners[key] for key in order]


def _vary_color(color: tuple[float, float, float, float], factor: float) -> tuple[float, float, float, float]:
    return (
        max(0.0, min(1.0, color[0] * factor)),
        max(0.0, min(1.0, color[1] * factor)),
        max(0.0, min(1.0, color[2] * factor)),
        color[3],
    )


def _roughen(points: Iterable[PCPPoint], magnitude: float, seed: int) -> list[PCPPoint]:
    rng = random.Random(seed)
    output: list[PCPPoint] = []
    for point in points:
        point.x += rng.uniform(-magnitude, magnitude)
        point.y += rng.uniform(-magnitude, magnitude)
        point.z += rng.uniform(-magnitude, magnitude)
        factor = rng.uniform(0.78, 1.15)
        point.r = max(0.0, min(1.0, point.r * factor))
        point.g = max(0.0, min(1.0, point.g * factor))
        point.b = max(0.0, min(1.0, point.b * factor))
        output.append(point)
    return output


def _local_to_world(projection: str, center: tuple[float, float, float], u: float, v: float, w: float) -> tuple[float, float, float]:
    cx, cy, cz = center
    if projection == "Side Z/Y":
        return (cx + w, cy + v, cz + u)
    if projection == "Top X/Z":
        return (cx + u, cy + w, cz + v)
    return (cx + u, cy + v, cz + w)


def _local_size(projection: str, width: float, height: float, depth: float) -> tuple[float, float, float]:
    if projection == "Side Z/Y":
        return (depth, height, width)
    if projection == "Top X/Z":
        return (width, depth, height)
    return (width, height, depth)


def _box_local(
    projection: str,
    region_center: tuple[float, float, float],
    local_center: tuple[float, float, float],
    local_size: tuple[float, float, float],
    spacing: float,
    layer_id: int,
    color: tuple[float, float, float, float],
    radius: float,
    semantic: str,
) -> list[PCPPoint]:
    center = _local_to_world(projection, region_center, *local_center)
    size = _local_size(projection, *local_size)
    return primitive_box(center, size, spacing, layer_id, color, radius, semantic)


def _ring_local(
    projection: str,
    center: tuple[float, float, float],
    width_radius: float,
    height_radius: float,
    depth: float,
    spacing: float,
    layer_id: int,
    color: tuple[float, float, float, float],
    radius: float,
    semantic: str,
) -> list[PCPPoint]:
    circumference = math.tau * max(width_radius, height_radius)
    count = max(24, int(math.ceil(circumference / max(0.05, spacing))))
    points: list[PCPPoint] = []
    flag = SEMANTIC_FLAGS.get(semantic, 0)
    depth_steps = max(1, int(math.ceil(depth / max(0.05, spacing))))
    for depth_index in range(depth_steps + 1):
        w = -depth * 0.5 + depth * depth_index / max(1, depth_steps)
        for index in range(count):
            angle = math.tau * index / count
            u = math.cos(angle) * width_radius
            v = math.sin(angle) * height_radius
            x, y, z = _local_to_world(projection, center, u, v, w)
            points.append(PCPPoint(x, y, z, radius, *color, 0.0, 1.0, 0.0, 1.0, layer_id, flag))
    return points


def _wall_geometry(
    preset: str,
    region: Region3D,
    params: dict[str, Any],
    layer_id: int,
    color: tuple[float, float, float, float],
    point_radius: float,
) -> list[PCPPoint]:
    spacing = max(0.05, float(params["spacing"]))
    thickness = max(spacing * 2.0, float(params.get("thickness", 0.25)))
    height = max(spacing * 2.0, float(params.get("height", region.size[1])))
    cx, cy, cz = region.center
    sx, _sy, sz = region.size
    if region.projection == "Side Z/Y":
        size = (thickness, height, max(sz, spacing * 2.0))
        center = (cx, region.minimum[1] + height * 0.5, cz)
        horizontal = size[2]
    elif region.projection == "Top X/Z":
        if sx >= sz:
            size = (max(sx, spacing * 2.0), height, thickness)
            horizontal = size[0]
        else:
            size = (thickness, height, max(sz, spacing * 2.0))
            horizontal = size[2]
        center = (cx, cy + height * 0.5, cz)
    else:
        size = (max(sx, spacing * 2.0), height, thickness)
        center = (cx, region.minimum[1] + height * 0.5, cz)
        horizontal = size[0]

    if preset in {"plaster_wall", "rock_wall"}:
        points = primitive_box(center, size, spacing, layer_id, color, point_radius, "wall")
        if preset == "rock_wall":
            points = _roughen(points, max(spacing * 0.5, float(params.get("roughness", 0.2))), 0xA11CE)
        return points

    points: list[PCPPoint] = []
    if preset == "wood_wall":
        plank = max(spacing * 3.0, float(params.get("plank_size", 0.45)))
        count = max(1, int(math.ceil(height / plank)))
        for index in range(count):
            local_height = height / count
            y = center[1] - height * 0.5 + local_height * (index + 0.5)
            shade = 0.82 + 0.14 * (index % 3)
            points.extend(primitive_box((center[0], y, center[2]), (size[0], local_height * 0.92, size[2]), spacing, layer_id, _vary_color(color, shade), point_radius, "wall"))
    else:
        points.extend(primitive_box(center, size, spacing, layer_id, color, point_radius, "wall"))
        panel = max(0.5, float(params.get("panel_size", 1.2)))
        if region.projection == "Side Z/Y":
            u_start = center[2] - horizontal * 0.5
            u_end = center[2] + horizontal * 0.5
            for offset in range(1, max(1, int(horizontal / panel))):
                z = u_start + offset * panel
                points.extend(primitive_line((center[0] - thickness * 0.55, center[1] - height * 0.5, z), (center[0] - thickness * 0.55, center[1] + height * 0.5, z), spacing, layer_id, _vary_color(color, 0.7), point_radius, "wall"))
        else:
            u_start = center[0] - horizontal * 0.5
            for offset in range(1, max(1, int(horizontal / panel))):
                x = u_start + offset * panel
                points.extend(primitive_line((x, center[1] - height * 0.5, center[2] - thickness * 0.55), (x, center[1] + height * 0.5, center[2] - thickness * 0.55), spacing, layer_id, _vary_color(color, 0.7), point_radius, "wall"))
    return points


def _floor_geometry(
    preset: str,
    region: Region3D,
    params: dict[str, Any],
    layer_id: int,
    color: tuple[float, float, float, float],
    point_radius: float,
) -> list[PCPPoint]:
    spacing = max(0.05, float(params["spacing"]))
    thickness = max(spacing * 2.0, float(params.get("thickness", 0.2)))
    cx, cy, cz = region.center
    sx, sy, sz = region.size
    if region.projection == "Front X/Y":
        center = (cx, region.minimum[1] + thickness * 0.5, cz)
        size = (sx, thickness, max(sz, 4.0))
    elif region.projection == "Side Z/Y":
        center = (cx, region.minimum[1] + thickness * 0.5, cz)
        size = (max(sx, 4.0), thickness, sz)
    else:
        center = (cx, cy, cz)
        size = (sx, thickness, sz)
    points = primitive_box(center, size, spacing, layer_id, color, point_radius, "floor")
    if preset == "rocky_floor":
        return _roughen(points, max(spacing * 0.45, float(params.get("roughness", 0.18))), 0xF1007)
    if preset == "grass_floor":
        flag = SEMANTIC_FLAGS["floor"]
        rng = random.Random(0x6A455)
        nx = max(2, int(size[0] / max(spacing * 4.0, 0.25)))
        nz = max(2, int(size[2] / max(spacing * 4.0, 0.25)))
        top_y = center[1] + thickness * 0.5
        grass_color = _vary_color(color, 0.8)
        for ix in range(nx):
            for iz in range(nz):
                x = center[0] - size[0] * 0.5 + size[0] * (ix + 0.5) / nx
                z = center[2] - size[2] * 0.5 + size[2] * (iz + 0.5) / nz
                blade = spacing * rng.uniform(1.5, 4.0)
                points.append(PCPPoint(x, top_y + blade, z, point_radius, *grass_color, 0.0, 1.0, 0.0, 0.7, layer_id, flag, blade, 0.0))
        return points
    return points


def _ceiling_geometry(
    preset: str,
    region: Region3D,
    params: dict[str, Any],
    layer_id: int,
    color: tuple[float, float, float, float],
    point_radius: float,
) -> list[PCPPoint]:
    spacing = max(0.05, float(params["spacing"]))
    thickness = max(spacing * 2.0, float(params.get("thickness", 0.2)))
    rise = max(0.05, float(params.get("rise", 1.0)))
    cx, cy, cz = region.center
    sx, _sy, sz = region.size
    base_y = cy
    if preset == "flat_ceiling" or preset == "rock_ceiling":
        points = primitive_box((cx, base_y, cz), (sx, thickness, sz), spacing, layer_id, color, point_radius, "ceiling")
        return _roughen(points, max(spacing * 0.4, float(params.get("roughness", 0.16))), 0xCE111) if preset == "rock_ceiling" else points

    nx = max(2, int(math.ceil(sx / spacing)) + 1)
    nz = max(2, int(math.ceil(sz / spacing)) + 1)
    flag = SEMANTIC_FLAGS["ceiling"]
    points: list[PCPPoint] = []
    for ix in range(nx):
        x_norm = -1.0 + 2.0 * ix / max(1, nx - 1)
        x = cx + x_norm * sx * 0.5
        for iz in range(nz):
            z_norm = -1.0 + 2.0 * iz / max(1, nz - 1)
            z = cz + z_norm * sz * 0.5
            if preset == "vaulted_ceiling":
                lift = rise * (1.0 - abs(x_norm))
            elif preset == "rounded_ceiling":
                lift = rise * math.sqrt(max(0.0, 1.0 - x_norm * x_norm))
            else:
                lift = rise * math.sqrt(max(0.0, 1.0 - x_norm * x_norm - z_norm * z_norm))
            points.append(PCPPoint(x, base_y + lift, z, point_radius, *color, 0.0, -1.0, 0.0, 1.0, layer_id, flag, lift, 0.0))
    return points


def _fixture_geometry(
    preset: str,
    region: Region3D,
    params: dict[str, Any],
    layer_id: int,
    color: tuple[float, float, float, float],
    point_radius: float,
) -> list[PCPPoint]:
    spacing = max(0.05, float(params["spacing"]))
    cx, cy, cz = region.center
    if preset == "chandelier":
        radius = max(0.2, float(params.get("radius", 1.0)))
        chain = max(spacing * 3.0, float(params.get("chain_length", 1.5)))
        stages = max(1, min(8, int(round(float(params.get("stages", 3))))))
        points = primitive_line((cx, cy, cz), (cx, cy - chain, cz), spacing, layer_id, _vary_color(color, 0.7), point_radius, "light")
        for stage in range(stages):
            fraction = (stage + 1) / stages
            stage_y = cy - chain * fraction
            stage_radius = radius * (1.0 - 0.65 * fraction)
            points.extend(_ring_local("Top X/Z", (cx, stage_y, cz), stage_radius, stage_radius, spacing, spacing, layer_id, color, point_radius, "light"))
        points.extend(primitive_sphere((cx, cy - chain - radius * 0.15, cz), max(0.12, radius * 0.18), spacing, layer_id, _vary_color(color, 1.25), point_radius, "light"))
        return points
    if preset == "ceiling_light":
        width = max(0.4, float(params.get("width", max(region.size[0], 0.8))))
        depth = max(spacing * 3.0, float(params.get("depth", 0.3)))
        fixture_height = max(spacing * 2.0, float(params.get("fixture_height", 0.25)))
        points = primitive_box((cx, cy, cz), (width, fixture_height, max(region.size[2], depth)), spacing, layer_id, _vary_color(color, 0.8), point_radius, "light")
        points.extend(primitive_box((cx, cy - fixture_height * 0.55, cz), (width * 0.78, spacing, max(region.size[2], depth) * 0.78), spacing, layer_id, _vary_color(color, 1.3), point_radius, "light"))
        return points
    if preset == "wall_light":
        width = max(0.3, float(params.get("width", max(region.size[0], 0.6))))
        height = max(0.2, float(params.get("fixture_height", max(region.size[1], 0.35))))
        depth = max(spacing * 3.0, float(params.get("depth", 0.35)))
        points = _box_local(region.projection, region.center, (0.0, 0.0, 0.0), (width, height, depth), spacing, layer_id, _vary_color(color, 0.75), point_radius, "light")
        bulb_center = _local_to_world(region.projection, region.center, 0.0, 0.0, depth * 0.65)
        points.extend(primitive_sphere(bulb_center, min(width, height) * 0.3, spacing, layer_id, _vary_color(color, 1.35), point_radius, "light"))
        return points

    scale = max(spacing, float(params.get("scale", 0.2)))
    width, height, depth = 6.0 * scale, 5.0 * scale, 9.0 * scale
    points = _box_local(region.projection, region.center, (0.0, 0.0, 0.0), (width, height, depth), spacing, layer_id, _vary_color(color, 0.65), point_radius, "light")
    aperture_center = _local_to_world(region.projection, region.center, 0.0, 0.0, depth * 0.55)
    points.extend(_ring_local(region.projection, aperture_center, width * 0.18, width * 0.18, spacing, spacing, layer_id, (0.08, 0.08, 0.08, color[3]), point_radius, "light"))
    red_center = _local_to_world(region.projection, region.center, width * 0.32, height * 0.30, depth * 0.56)
    points.extend(primitive_sphere(red_center, max(spacing, scale * 0.32), spacing, layer_id, (1.0, 0.02, 0.02, 1.0), point_radius, "light"))
    for point in points:
        point.attribute0 = 0.02  # lowest practical authored light intensity
        point.attribute1 = 1.0 if (point.r > 0.8 and point.g < 0.2) else 0.0
    return points


def _opening_geometry(
    preset: str,
    region: Region3D,
    params: dict[str, Any],
    layer_id: int,
    color: tuple[float, float, float, float],
    point_radius: float,
) -> list[PCPPoint]:
    spacing = max(0.05, float(params["spacing"]))
    thickness = max(spacing * 2.0, float(params.get("frame_thickness", 0.2)))
    depth = max(spacing * 3.0, float(params.get("frame_depth", 0.3)))
    style = str(params.get("frame_style", "square"))
    width = max(spacing * 4.0, region.size[0] if region.projection != "Side Z/Y" else region.size[2])
    height = max(spacing * 4.0, region.size[1] if region.projection != "Top X/Z" else float(params.get("height", 2.2)))
    center = region.center
    if style == "office_slit_upward":
        width = min(width, max(thickness * 4.0, height * 0.28))
    elif style == "office_slit_sideways":
        height = min(height, max(thickness * 4.0, width * 0.28))

    if style in {"circle", "oval"}:
        points = _ring_local(region.projection, center, width * 0.5, (width * 0.5 if style == "circle" else height * 0.5), depth, spacing, layer_id, color, point_radius, "portal")
    else:
        points: list[PCPPoint] = []
        points.extend(_box_local(region.projection, center, (0.0, height * 0.5 - thickness * 0.5, 0.0), (width, thickness, depth), spacing, layer_id, color, point_radius, "portal"))
        points.extend(_box_local(region.projection, center, (0.0, -height * 0.5 + thickness * 0.5, 0.0), (width, thickness, depth), spacing, layer_id, color, point_radius, "portal"))
        points.extend(_box_local(region.projection, center, (-width * 0.5 + thickness * 0.5, 0.0, 0.0), (thickness, height, depth), spacing, layer_id, color, point_radius, "portal"))
        points.extend(_box_local(region.projection, center, (width * 0.5 - thickness * 0.5, 0.0, 0.0), (thickness, height, depth), spacing, layer_id, color, point_radius, "portal"))
        if style == "crossed":
            start_a = _local_to_world(region.projection, center, -width * 0.45, -height * 0.45, depth * 0.55)
            end_a = _local_to_world(region.projection, center, width * 0.45, height * 0.45, depth * 0.55)
            start_b = _local_to_world(region.projection, center, width * 0.45, -height * 0.45, depth * 0.55)
            end_b = _local_to_world(region.projection, center, -width * 0.45, height * 0.45, depth * 0.55)
            points.extend(primitive_line(start_a, end_a, spacing, layer_id, color, point_radius, "portal"))
            points.extend(primitive_line(start_b, end_b, spacing, layer_id, color, point_radius, "portal"))
        elif style == "barred":
            for fraction in (-0.25, 0.0, 0.25):
                start = _local_to_world(region.projection, center, width * fraction, -height * 0.45, depth * 0.55)
                end = _local_to_world(region.projection, center, width * fraction, height * 0.45, depth * 0.55)
                points.extend(primitive_line(start, end, spacing, layer_id, color, point_radius, "portal"))
    opening_code = {"window_frame": 1.0, "door_frame": 2.0, "portal_frame": 3.0}.get(preset, 0.0)
    style_code = float(FRAME_STYLES.index(style) + 1) if style in FRAME_STYLES else 1.0
    for point in points:
        point.attribute0 = opening_code
        point.attribute1 = style_code
    return points


def generate_preset(
    preset: str,
    region: Region3D,
    params: dict[str, Any],
    layer_id: int,
    color: tuple[float, float, float, float],
    point_radius: float,
) -> list[PCPPoint]:
    if preset.endswith("wall"):
        return _wall_geometry(preset, region, params, layer_id, color, point_radius)
    if preset.endswith("floor"):
        return _floor_geometry(preset, region, params, layer_id, color, point_radius)
    if preset.endswith("ceiling"):
        return _ceiling_geometry(preset, region, params, layer_id, color, point_radius)
    if preset in {"chandelier", "wall_light", "ceiling_light", "corner_camera"}:
        return _fixture_geometry(preset, region, params, layer_id, color, point_radius)
    if preset.endswith("frame"):
        return _opening_geometry(preset, region, params, layer_id, color, point_radius)
    return []


def estimate_preset_points(preset: str, region: Region3D, params: dict[str, Any]) -> int:
    spacing = max(0.05, float(params.get("spacing", 0.12)))
    sx, sy, sz = region.size
    if preset.endswith("wall"):
        height = max(sy, float(params.get("height", sy)))
        width = max(sx, sz)
        return max(32, int(4.0 * width * height / (spacing * spacing)))
    if preset.endswith("floor") or preset.endswith("ceiling"):
        return max(32, int(2.5 * max(sx, 1.0) * max(sz, 1.0) / (spacing * spacing)))
    if preset == "chandelier":
        radius = float(params.get("radius", 1.0))
        stages = int(params.get("stages", 3))
        return max(48, int(stages * math.tau * radius / spacing + float(params.get("chain_length", 1.5)) / spacing))
    if preset == "corner_camera":
        scale = float(params.get("scale", 0.2))
        return max(64, int((6 * 5 + 6 * 9 + 5 * 9) * scale * scale / (spacing * spacing) * 2.0))
    if preset.endswith("frame"):
        width = max(sx, sz)
        height = max(sy, 2.0)
        return max(48, int(5.0 * (width + height) / spacing))
    return 10_000


def room_shell_preview(region: Region3D, params: dict[str, Any], room_width: float, room_depth: float) -> list[tuple[float, float, float]]:
    center, size, _floor_y = room_shell_bounds(region, params, room_width, room_depth)
    return box_polyline(center, size)


def room_shell_bounds(
    region: Region3D,
    params: dict[str, Any],
    room_width: float,
    room_depth: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float], float]:
    floor_thickness = max(0.05, float(params.get("floor_thickness", 0.2)))
    wall_height = max(0.1, float(params.get("wall_height", 3.0)))
    if region.projection == "Top X/Z":
        width = max(0.2, region.size[0])
        depth = max(0.2, region.size[2])
        floor_y = region.center[1]
        center = (region.center[0], floor_y + floor_thickness + wall_height * 0.5, region.center[2])
    elif region.projection == "Front X/Y":
        width = max(0.2, region.size[0])
        depth = max(0.2, room_depth)
        floor_y = region.minimum[1]
        center = (region.center[0], floor_y + floor_thickness + wall_height * 0.5, region.center[2])
    elif region.projection == "Side Z/Y":
        width = max(0.2, room_width)
        depth = max(0.2, region.size[2])
        floor_y = region.minimum[1]
        center = (region.center[0], floor_y + floor_thickness + wall_height * 0.5, region.center[2])
    else:
        width = max(0.2, region.size[0])
        depth = max(0.2, region.size[2])
        floor_y = region.minimum[1]
        center = (region.center[0], floor_y + floor_thickness + wall_height * 0.5, region.center[2])
    return center, (width, wall_height, depth), floor_y


def generate_room_shell(
    region: Region3D,
    params: dict[str, Any],
    *,
    room_width: float,
    room_depth: float,
    layer_ids: dict[str, int],
    color: tuple[float, float, float, float],
    point_radius: float,
) -> dict[str, list[PCPPoint]]:
    spacing = max(0.05, float(params.get("spacing", 0.12)))
    wall_thickness = max(0.05, float(params.get("wall_thickness", 1.0)))
    floor_thickness = max(0.05, float(params.get("floor_thickness", max(0.15, spacing * 2.0))))
    ceiling_thickness = max(0.05, float(params.get("ceiling_thickness", max(0.15, spacing * 2.0))))
    wall_height = max(0.1, float(params.get("wall_height", 3.0)))
    top_gap = max(0.0, float(params.get("wall_top", 0.0)))
    bottom_gap = max(0.0, float(params.get("wall_bottom", 0.0)))
    center, size, floor_y = room_shell_bounds(region, params, room_width, room_depth)
    width, _height, depth = size
    effective_height = max(spacing * 2.0, wall_height - top_gap - bottom_gap)
    wall_center_y = floor_y + floor_thickness + bottom_gap + effective_height * 0.5
    floor_center_y = floor_y + floor_thickness * 0.5
    ceiling_center_y = floor_y + floor_thickness + wall_height + ceiling_thickness * 0.5

    result: dict[str, list[PCPPoint]] = {
        "floor": primitive_box((center[0], floor_center_y, center[2]), (width, floor_thickness, depth), spacing, layer_ids["floor"], color, point_radius, "floor"),
        "ceiling": primitive_box((center[0], ceiling_center_y, center[2]), (width, ceiling_thickness, depth), spacing, layer_ids["ceiling"], color, point_radius, "ceiling"),
        "walls": [],
    }
    wall_color = _vary_color(color, 0.92)
    result["walls"].extend(primitive_box((center[0], wall_center_y, center[2] - depth * 0.5 + wall_thickness * 0.5), (width, effective_height, wall_thickness), spacing, layer_ids["walls"], wall_color, point_radius, "wall"))
    result["walls"].extend(primitive_box((center[0], wall_center_y, center[2] + depth * 0.5 - wall_thickness * 0.5), (width, effective_height, wall_thickness), spacing, layer_ids["walls"], wall_color, point_radius, "wall"))
    result["walls"].extend(primitive_box((center[0] - width * 0.5 + wall_thickness * 0.5, wall_center_y, center[2]), (wall_thickness, effective_height, depth), spacing, layer_ids["walls"], wall_color, point_radius, "wall"))
    result["walls"].extend(primitive_box((center[0] + width * 0.5 - wall_thickness * 0.5, wall_center_y, center[2]), (wall_thickness, effective_height, depth), spacing, layer_ids["walls"], wall_color, point_radius, "wall"))
    return result
