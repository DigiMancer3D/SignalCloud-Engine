from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from .model import PCPPoint


@dataclass(frozen=True)
class Pane:
    name: str
    projection: str
    x: float
    y: float
    width: float
    height: float

    def contains(self, sx: float, sy: float) -> bool:
        return self.x <= sx <= self.x + self.width and self.y <= sy <= self.y + self.height


def _rotate_x(x: float, y: float, z: float, radians: float) -> tuple[float, float, float]:
    c, s = math.cos(radians), math.sin(radians)
    return x, y * c - z * s, y * s + z * c


def _rotate_y(x: float, y: float, z: float, radians: float) -> tuple[float, float, float]:
    c, s = math.cos(radians), math.sin(radians)
    return x * c + z * s, y, -x * s + z * c


def _rotate_z(x: float, y: float, z: float, radians: float) -> tuple[float, float, float]:
    c, s = math.cos(radians), math.sin(radians)
    return x * c - y * s, x * s + y * c, z


def rotate_xyz(point: tuple[float, float, float], x_degrees: float, y_degrees: float, z_degrees: float) -> tuple[float, float, float]:
    x, y, z = point
    x, y, z = _rotate_x(x, y, z, math.radians(x_degrees))
    x, y, z = _rotate_y(x, y, z, math.radians(y_degrees))
    return _rotate_z(x, y, z, math.radians(z_degrees))


def inverse_rotate_xyz(point: tuple[float, float, float], x_degrees: float, y_degrees: float, z_degrees: float) -> tuple[float, float, float]:
    x, y, z = point
    x, y, z = _rotate_z(x, y, z, math.radians(-z_degrees))
    x, y, z = _rotate_y(x, y, z, math.radians(-y_degrees))
    return _rotate_x(x, y, z, math.radians(-x_degrees))


def normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(value * value for value in vector))
    if length <= 1e-9:
        return 0.0, 0.0, -1.0
    return tuple(value / length for value in vector)  # type: ignore[return-value]


def cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def mul(a: tuple[float, float, float], scalar: float) -> tuple[float, float, float]:
    return a[0] * scalar, a[1] * scalar, a[2] * scalar


def dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def camera_basis(yaw_degrees: float, pitch_degrees: float, roll_degrees: float = 0.0) -> tuple[
    tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]
]:
    yaw = math.radians(yaw_degrees)
    pitch = math.radians(pitch_degrees)
    forward = normalize((math.cos(pitch) * math.cos(yaw), math.sin(pitch), math.cos(pitch) * math.sin(yaw)))
    right = normalize(cross(forward, (0.0, 1.0, 0.0)))
    up = normalize(cross(right, forward))
    if abs(roll_degrees) > 1e-9:
        roll = math.radians(roll_degrees)
        c, s = math.cos(roll), math.sin(roll)
        old_right, old_up = right, up
        right = add(mul(old_right, c), mul(old_up, s))
        up = add(mul(old_up, c), mul(old_right, -s))
    return forward, right, up


def perspective_project(
    point: tuple[float, float, float], pane: Pane, target: tuple[float, float, float],
    yaw_degrees: float, pitch_degrees: float, roll_degrees: float, distance: float,
    fov_degrees: float = 58.0,
) -> tuple[float, float, float] | None:
    forward, right, up = camera_basis(yaw_degrees, pitch_degrees, roll_degrees)
    eye = sub(target, mul(forward, max(0.1, distance)))
    relative = sub(point, eye)
    depth = dot(relative, forward)
    if depth <= 0.01:
        return None
    aspect = max(0.01, pane.width / max(1.0, pane.height))
    tan_half = math.tan(math.radians(fov_degrees) * 0.5)
    nx = dot(relative, right) / (depth * tan_half * aspect)
    ny = dot(relative, up) / (depth * tan_half)
    sx = pane.x + pane.width * (0.5 + nx * 0.5)
    sy = pane.y + pane.height * (0.5 - ny * 0.5)
    return sx, sy, depth


def perspective_ray_to_target_plane(
    sx: float, sy: float, pane: Pane, target: tuple[float, float, float],
    yaw_degrees: float, pitch_degrees: float, roll_degrees: float, distance: float,
    fov_degrees: float = 58.0,
) -> tuple[float, float, float]:
    forward, right, up = camera_basis(yaw_degrees, pitch_degrees, roll_degrees)
    eye = sub(target, mul(forward, max(0.1, distance)))
    aspect = max(0.01, pane.width / max(1.0, pane.height))
    nx = ((sx - pane.x) / max(1.0, pane.width) - 0.5) * 2.0
    ny = (0.5 - (sy - pane.y) / max(1.0, pane.height)) * 2.0
    tan_half = math.tan(math.radians(fov_degrees) * 0.5)
    direction = normalize(add(forward, add(mul(right, nx * tan_half * aspect), mul(up, ny * tan_half))))
    denominator = dot(direction, forward)
    if abs(denominator) < 1e-8:
        return target
    t = dot(sub(target, eye), forward) / denominator
    return add(eye, mul(direction, max(0.0, t)))


def catmull_rom_points(anchors: Sequence[tuple[float, float, float]], samples_per_segment: int = 18) -> list[tuple[float, float, float]]:
    if len(anchors) < 2:
        return list(anchors)
    if len(anchors) == 2:
        start, end = anchors
        return [
            tuple(start[axis] + (end[axis] - start[axis]) * index / samples_per_segment for axis in range(3))
            for index in range(samples_per_segment + 1)
        ]
    padded = [anchors[0], *anchors, anchors[-1]]
    output: list[tuple[float, float, float]] = []
    for segment in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[segment - 1], padded[segment], padded[segment + 1], padded[segment + 2]
        for sample in range(samples_per_segment):
            t = sample / samples_per_segment
            t2, t3 = t * t, t * t * t
            values = []
            for axis in range(3):
                value = 0.5 * (
                    2.0 * p1[axis]
                    + (-p0[axis] + p2[axis]) * t
                    + (2.0 * p0[axis] - 5.0 * p1[axis] + 4.0 * p2[axis] - p3[axis]) * t2
                    + (-p0[axis] + 3.0 * p1[axis] - 3.0 * p2[axis] + p3[axis]) * t3
                )
                values.append(value)
            output.append(tuple(values))
    output.append(anchors[-1])
    return output


def resample_polyline(points: Sequence[tuple[float, float, float]], spacing: float) -> list[tuple[float, float, float]]:
    if len(points) < 2:
        return list(points)
    spacing = max(0.01, spacing)
    output = [points[0]]
    carry = 0.0
    previous = points[0]
    for current in points[1:]:
        delta = sub(current, previous)
        length = math.sqrt(dot(delta, delta))
        if length <= 1e-9:
            continue
        direction = mul(delta, 1.0 / length)
        distance = spacing - carry
        while distance <= length + 1e-9:
            output.append(add(previous, mul(direction, distance)))
            distance += spacing
        carry = max(0.0, length - (distance - spacing))
        previous = current
    if output[-1] != points[-1]:
        output.append(points[-1])
    return output


def region_indices(
    points: Iterable[tuple[int, PCPPoint]], projector, x1: float, y1: float, x2: float, y2: float,
) -> set[int]:
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    selected: set[int] = set()
    for index, point in points:
        projected = projector(point)
        if projected is None:
            continue
        sx, sy = projected[:2]
        if left <= sx <= right and top <= sy <= bottom:
            selected.add(index)
    return selected
