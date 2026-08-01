from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
from typing import Iterable

from .model import PhysicsProfile, VisualizationProfile


@dataclass(slots=True)
class ProjectedPoint:
    x: float
    y: float
    depth: float
    radius: float
    color: str


@dataclass(slots=True)
class PreviewSourcePoint:
    x: float
    y: float
    z: float
    radius: float = 1.2
    r: float = 0.25
    g: float = 0.94
    b: float = 0.84
    a: float = 1.0
    density: float = 4.1


def _rgb(point: object, mode: str, depth: float, time_seconds: float) -> tuple[int, int, int]:
    r = min(1.0, max(0.0, float(getattr(point, "r", 0.8))))
    g = min(1.0, max(0.0, float(getattr(point, "g", 0.8))))
    b = min(1.0, max(0.0, float(getattr(point, "b", 0.8))))
    if mode == "density":
        value = min(1.0, max(0.0, (float(getattr(point, "density", 1.0)) + 1.0) / 5.0))
        r, g, b = 0.16 + 0.84 * value, 0.92 - 0.58 * value, 0.96 - 0.74 * value
    elif mode == "material":
        grain = 0.5 + 0.5 * math.sin(
            float(point.x) * 2.19 + float(point.y) * 1.37 + float(point.z) * 1.71 + time_seconds * 0.35
        )
        r, g, b = (
            r * (0.74 + 0.30 * grain) + 0.04,
            g * (0.70 + 0.22 * grain) + 0.07,
            b * (0.68 + 0.38 * grain) + 0.11,
        )
    elif mode == "light":
        amount = min(1.0, max(0.18, 1.15 - abs(depth) * 0.13))
        r, g, b = r * (0.32 + amount), g * (0.28 + amount * 0.90), b * (0.36 + amount * 1.08)
    return tuple(min(255, max(0, round(value * 255))) for value in (r, g, b))


def _rotate_y(x: float, z: float, yaw: float) -> tuple[float, float]:
    c, s = math.cos(yaw), math.sin(yaw)
    return x * c - z * s, x * s + z * c


def _source_bounds(points: Iterable[object]) -> tuple[float, float, float, float, float, float]:
    points = list(points)
    xs = [float(point.x) for point in points]
    ys = [float(point.y) for point in points]
    zs = [float(point.z) for point in points]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def _actor_deform(
    x: float,
    y: float,
    z: float,
    *,
    half_x: float,
    half_y: float,
    half_z: float,
    time_seconds: float,
) -> tuple[float, float, float]:
    height = max(0.001, half_y * 2.0)
    vertical = min(1.0, max(0.0, (y + half_y) / height))
    planted_t = min(1.0, max(0.0, (vertical - 0.02) / 0.23))
    planted = planted_t * planted_t * (3.0 - 2.0 * planted_t)
    phase = time_seconds * 2.35
    x += math.sin(phase + vertical * 2.8) * max(0.25, half_x) * 0.22 * planted
    z += math.cos(phase * 0.77 + vertical * 3.6) * max(0.20, half_z) * 0.18 * planted
    y += math.sin(phase * 1.35 + vertical * 5.0) * height * 0.035 * planted
    twist = math.sin(phase * 0.82) * 0.42 * vertical
    x, z = _rotate_y(x, z, twist)
    return x, y, z


def project_points(
    points: list[object],
    width: int,
    height: int,
    view: VisualizationProfile,
    *,
    yaw_degrees: float = -38.0,
    pitch_degrees: float = 24.0,
    zoom: float = 0.84,
    maximum_points: int = 6000,
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    object_yaw: float = 0.0,
    time_seconds: float = 0.0,
    scene_center: tuple[float, float, float] | None = None,
    scene_extent: float | None = None,
) -> list[ProjectedPoint]:
    if not points or width <= 10 or height <= 10:
        return []
    count = max(1, min(len(points), round(len(points) * view.lod_fraction), maximum_points))
    stride = len(points) / count
    sampled = [points[min(len(points) - 1, int(index * stride))] for index in range(count)]
    min_x, max_x, min_y, max_y, min_z, max_z = _source_bounds(sampled)
    source_center = ((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, (min_z + max_z) * 0.5)
    half_x = max(0.025, (max_x - min_x) * 0.5)
    half_y = max(0.025, (max_y - min_y) * 0.5)
    half_z = max(0.025, (max_z - min_z) * 0.5)

    transformed: list[tuple[object, float, float, float]] = []
    for point in sampled:
        x = float(point.x) - source_center[0]
        y = float(point.y) - source_center[1]
        z = float(point.z) - source_center[2]
        if view.actor_preview:
            x, y, z = _actor_deform(
                x, y, z, half_x=half_x, half_y=half_y, half_z=half_z, time_seconds=time_seconds
            )
        x, z = _rotate_y(x, z, object_yaw)
        transformed.append((point, x + translation[0], y + translation[1], z + translation[2]))

    if scene_center is None:
        tx = [item[1] for item in transformed]
        ty = [item[2] for item in transformed]
        tz = [item[3] for item in transformed]
        cx, cy, cz = (min(tx) + max(tx)) * 0.5, (min(ty) + max(ty)) * 0.5, (min(tz) + max(tz)) * 0.5
    else:
        cx, cy, cz = scene_center
    if scene_extent is None:
        tx = [item[1] for item in transformed]
        ty = [item[2] for item in transformed]
        tz = [item[3] for item in transformed]
        extent = max(max(tx) - min(tx), max(ty) - min(ty), max(tz) - min(tz), 0.05)
    else:
        extent = max(0.05, float(scene_extent))

    yaw = math.radians(yaw_degrees)
    pitch = math.radians(pitch_degrees)
    sy, cyaw = math.sin(yaw), math.cos(yaw)
    sp, cp = math.sin(pitch), math.cos(pitch)
    scale = min(width, height) * 0.72 * zoom / extent
    projected: list[ProjectedPoint] = []
    for point, world_x, world_y, world_z in transformed:
        x, y, z = world_x - cx, world_y - cy, world_z - cz
        rx = x * cyaw - z * sy
        rz = x * sy + z * cyaw
        ry = y * cp - rz * sp
        depth = y * sp + rz * cp
        sxp = width * 0.5 + rx * scale
        syp = height * 0.53 - ry * scale
        radius = max(0.65, min(3.4, float(getattr(point, "radius", 1.5)) * 0.72 * view.point_scale))
        rgb = _rgb(point, view.view_mode, depth, time_seconds)
        projected.append(ProjectedPoint(sxp, syp, depth, radius, f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"))
    projected.sort(key=lambda item: item.depth)
    return projected


def _line_points(a: tuple[float, float, float], b: tuple[float, float, float], *, spacing: float = 0.08) -> list[PreviewSourcePoint]:
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
    steps = max(2, math.ceil(distance / max(0.01, spacing)))
    return [
        PreviewSourcePoint(a[0] + dx * i / steps, a[1] + dy * i / steps, a[2] + dz * i / steps)
        for i in range(steps + 1)
    ]


def collision_wire_points(
    profile: PhysicsProfile,
    *,
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    object_yaw: float = 0.0,
) -> list[PreviewSourcePoint]:
    profile = PhysicsProfile.from_dict(profile.to_dict())
    cx, cy, cz = translation
    points: list[PreviewSourcePoint] = []

    def world(local: tuple[float, float, float]) -> tuple[float, float, float]:
        x, z = _rotate_y(local[0], local[2], object_yaw)
        return cx + x, cy + local[1], cz + z

    if profile.shape == "sphere":
        for axis in range(3):
            previous: tuple[float, float, float] | None = None
            first: tuple[float, float, float] | None = None
            for index in range(65):
                angle = math.tau * index / 64
                c, s = math.cos(angle) * profile.collision_radius, math.sin(angle) * profile.collision_radius
                local = (0.0, c, s) if axis == 0 else ((c, 0.0, s) if axis == 1 else (c, s, 0.0))
                current = world(local)
                if previous is not None:
                    points.extend(_line_points(previous, current))
                first = first or current
                previous = current
        return points

    if profile.shape == "capsule":
        radius = profile.collision_radius
        half = profile.collision_half_y
        for sx in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                points.extend(_line_points(world((sx * radius, -half, sz * radius)), world((sx * radius, half, sz * radius))))
        for y in (-half, half):
            previous = None
            for index in range(65):
                angle = math.tau * index / 64
                current = world((math.cos(angle) * radius, y, math.sin(angle) * radius))
                if previous is not None:
                    points.extend(_line_points(previous, current))
                previous = current
        return points

    hx, hy, hz = profile.collision_half_x, profile.collision_half_y, profile.collision_half_z
    corners = [
        (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
        (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz),
    ]
    edges = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7))
    world_corners = [world(item) for item in corners]
    for left, right in edges:
        points.extend(_line_points(world_corners[left], world_corners[right]))
    return points


def write_snapshot_ppm(
    path: Path,
    points: list[object],
    profile: PhysicsProfile,
    view: VisualizationProfile,
    *,
    width: int | None = None,
    height: int | None = None,
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    object_yaw: float = 0.0,
    time_seconds: float = 0.0,
    scene_center: tuple[float, float, float] | None = None,
    scene_extent: float | None = None,
) -> Path:
    width = width or view.snapshot_width
    height = height or view.snapshot_height
    width = min(4096, max(320, int(width)))
    height = min(4096, max(240, int(height)))
    background = (8, 13, 18)
    pixels = bytearray(background * (width * height))
    projected = project_points(
        points, width, height, view, maximum_points=50_000,
        translation=translation, object_yaw=object_yaw, time_seconds=time_seconds,
        scene_center=scene_center, scene_extent=scene_extent,
    )
    if view.collision_outline:
        collision_view = VisualizationProfile.from_dict(view.to_dict())
        collision_view.view_mode = "source"
        collision_view.lod_fraction = 1.0
        projected += project_points(
            collision_wire_points(profile, translation=translation, object_yaw=object_yaw),
            width, height, collision_view, maximum_points=20_000,
            scene_center=scene_center, scene_extent=scene_extent,
        )
    for point in sorted(projected, key=lambda item: item.depth):
        color = tuple(int(point.color[index:index + 2], 16) for index in (1, 3, 5))
        radius = max(1, round(point.radius))
        for yy in range(max(0, round(point.y) - radius), min(height, round(point.y) + radius + 1)):
            for xx in range(max(0, round(point.x) - radius), min(width, round(point.x) + radius + 1)):
                offset = (yy * width + xx) * 3
                pixels[offset:offset + 3] = bytes(color)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + pixels)
    return target
