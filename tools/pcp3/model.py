from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable
import copy
import math
import uuid

ENVIRONMENT_TYPES = (
    "enemy",
    "boss",
    "mini_boss",
    "raid",
    "friendly",
    "environment_object",
    "environment_theme",
    "room",
    "liquid",
)

ENVIRONMENT_LABELS = {
    "enemy": "Enemy",
    "boss": "Boss",
    "mini_boss": "Mini-Boss",
    "raid": "Raid",
    "friendly": "User Friendly",
    "environment_object": "Environment Object",
    "environment_theme": "Environment Theme",
    "room": "Room",
    "liquid": "Liquid Maker",
}

MODE_DEFAULTS: dict[str, dict[str, Any]] = {
    "enemy": {"canvas_extent": [8.0, 6.0, 8.0], "point_budget": 120_000, "tool_profile": "formed_or_formless"},
    "boss": {"canvas_extent": [30.0, 24.0, 30.0], "point_budget": 1_500_000, "tool_profile": "multi_phase"},
    "mini_boss": {"canvas_extent": [16.0, 12.0, 16.0], "point_budget": 500_000, "tool_profile": "formed_or_formless"},
    "raid": {"canvas_extent": [140.0, 48.0, 140.0], "point_budget": 6_000_000, "tool_profile": "encounter_layout"},
    "friendly": {"canvas_extent": [8.0, 8.0, 8.0], "point_budget": 180_000, "tool_profile": "humanoid"},
    "environment_object": {"canvas_extent": [12.0, 12.0, 12.0], "point_budget": 250_000, "tool_profile": "object"},
    "environment_theme": {"canvas_extent": [40.0, 16.0, 40.0], "point_budget": 2_000_000, "tool_profile": "theme_set"},
    "room": {"canvas_extent": [36.0, 12.0, 48.0], "point_budget": 4_000_000, "tool_profile": "room_builder"},
    "liquid": {"canvas_extent": [30.0, 18.0, 30.0], "point_budget": 1_200_000, "tool_profile": "liquid_volume"},
}

SEMANTIC_FLAGS = {
    "generic": 0,
    "wall": 1,
    "floor": 2,
    "ceiling": 3,
    "dust": 4,
    "portal": 5,
    "water_surface": 6,
    "water_volume": 7,
    "light": 8,
    "enemy_body": 9,
    "friendly_body": 10,
    "weapon": 11,
    "pickup": 12,
    "trigger": 13,
    "bone": 14,
    "liquid_flow": 15,
}


@dataclass
class PCPPoint:
    x: float
    y: float
    z: float
    radius: float = 2.0
    r: float = 0.85
    g: float = 0.80
    b: float = 0.58
    a: float = 1.0
    nx: float = 0.0
    ny: float = 1.0
    nz: float = 0.0
    density: float = 1.0
    layer_id: int = 1
    flags: int = 0
    attribute0: float = 0.0
    attribute1: float = 0.0

    def distance_sq(self, x: float, y: float, z: float) -> float:
        return (self.x - x) ** 2 + (self.y - y) ** 2 + (self.z - z) ** 2


@dataclass
class Layer:
    id: int
    name: str
    group: str = "Geometry"
    visible: bool = True
    locked: bool = False
    opacity: float = 1.0
    blend_mode: str = "normal"
    semantic: str = "generic"
    tags: list[str] = field(default_factory=list)
    future_attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthorForm:
    creator_name: str = ""
    title: str = ""
    asset_type: str = "environment_object"
    description: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class DocumentSettings:
    width: float = 12.0
    height: float = 12.0
    depth: float = 12.0
    background: list[float] = field(default_factory=lambda: [0.025, 0.03, 0.04, 1.0])
    ambient_light: float = 0.35
    point_scale: float = 1.0
    density_scale: float = 1.0
    grid_spacing: float = 0.5
    units: str = "metres"
    origin_mode: str = "center"
    future_attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class PCPDocument:
    schema: str = "pcp3_project_v0"
    project_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str = "untitled_asset"
    display_name: str = "Untitled Asset"
    environment_type: str = "environment_object"
    settings: DocumentSettings = field(default_factory=DocumentSettings)
    author: AuthorForm = field(default_factory=AuthorForm)
    layers: list[Layer] = field(default_factory=lambda: [Layer(1, "Base Points")])
    points: list[PCPPoint] = field(default_factory=list)
    selected_indices: set[int] = field(default_factory=set)
    active_layer_id: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=lambda: {
        "enabled": True,
        "auto_preview_in_game": False,
        "preview_zone": "Reception Tape",
        "preview_position": [2.0, 1.0, -3.0],
        "preview_scale": 1.0,
        "stress_spawn_policy": "pcp3_asset_showcase",
    })
    dirty: bool = False

    @classmethod
    def new(cls, environment_type: str = "environment_object") -> "PCPDocument":
        if environment_type not in ENVIRONMENT_TYPES:
            environment_type = "environment_object"
        defaults = MODE_DEFAULTS[environment_type]
        extent = defaults["canvas_extent"]
        doc = cls(environment_type=environment_type)
        doc.settings.width = float(extent[0])
        doc.settings.height = float(extent[1])
        doc.settings.depth = float(extent[2])
        doc.author.asset_type = environment_type
        doc.metadata = {
            "tool_profile": defaults["tool_profile"],
            "recommended_point_budget": defaults["point_budget"],
            "editor_branch": "ISL_plus_branch2",
            "preserve_unknown_fields": True,
        }
        return doc

    def active_layer(self) -> Layer:
        for layer in self.layers:
            if layer.id == self.active_layer_id:
                return layer
        if not self.layers:
            self.layers.append(Layer(1, "Base Points"))
        self.active_layer_id = self.layers[0].id
        return self.layers[0]

    def add_layer(self, name: str | None = None, semantic: str = "generic") -> Layer:
        next_id = max((layer.id for layer in self.layers), default=0) + 1
        layer = Layer(next_id, name or f"Layer {next_id}", semantic=semantic)
        self.layers.append(layer)
        self.active_layer_id = layer.id
        self.dirty = True
        return layer

    def remove_layer(self, layer_id: int) -> None:
        if len(self.layers) <= 1:
            return
        self.layers = [layer for layer in self.layers if layer.id != layer_id]
        self.points = [point for point in self.points if point.layer_id != layer_id]
        self.selected_indices.clear()
        if self.active_layer_id == layer_id:
            self.active_layer_id = self.layers[0].id
        self.dirty = True

    def visible_points(self) -> Iterable[tuple[int, PCPPoint]]:
        layer_map = {layer.id: layer for layer in self.layers}
        for index, point in enumerate(self.points):
            layer = layer_map.get(point.layer_id)
            if layer is not None and layer.visible:
                yield index, point

    def layer_points(self, layer_id: int) -> Iterable[tuple[int, PCPPoint]]:
        for index, point in enumerate(self.points):
            if point.layer_id == layer_id:
                yield index, point

    def add_point(self, point: PCPPoint) -> int:
        if point.layer_id == 0:
            point.layer_id = self.active_layer_id
        self.points.append(point)
        self.dirty = True
        return len(self.points) - 1

    def add_points(self, points: Iterable[PCPPoint]) -> int:
        count = 0
        for point in points:
            if point.layer_id == 0:
                point.layer_id = self.active_layer_id
            self.points.append(point)
            count += 1
        if count:
            self.dirty = True
        return count

    def erase_sphere(self, x: float, y: float, z: float, radius: float, active_layer_only: bool = False) -> int:
        radius_sq = radius * radius
        before = len(self.points)
        layer_id = self.active_layer_id
        self.points = [
            point for point in self.points
            if (active_layer_only and point.layer_id != layer_id) or point.distance_sq(x, y, z) > radius_sq
        ]
        removed = before - len(self.points)
        if removed:
            self.selected_indices.clear()
            self.dirty = True
        return removed

    def recolor_sphere(self, x: float, y: float, z: float, radius: float, rgba: tuple[float, float, float, float]) -> int:
        radius_sq = radius * radius
        changed = 0
        layer = self.active_layer()
        if layer.locked:
            return 0
        for point in self.points:
            if point.layer_id == layer.id and point.distance_sq(x, y, z) <= radius_sq:
                point.r, point.g, point.b, point.a = rgba
                changed += 1
        if changed:
            self.dirty = True
        return changed

    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        if not self.points:
            half = (self.settings.width / 2.0, self.settings.height / 2.0, self.settings.depth / 2.0)
            return ((-half[0], -half[1], -half[2]), half)
        return (
            (min(p.x for p in self.points), min(p.y for p in self.points), min(p.z for p in self.points)),
            (max(p.x for p in self.points), max(p.y for p in self.points), max(p.z for p in self.points)),
        )

    def snapshot(self) -> dict[str, Any]:
        data = self.to_dict(include_points=True)
        data["selected_indices"] = sorted(self.selected_indices)
        return data

    def restore(self, snapshot: dict[str, Any]) -> None:
        restored = PCPDocument.from_dict(copy.deepcopy(snapshot))
        self.__dict__.update(restored.__dict__)
        self.selected_indices = set(snapshot.get("selected_indices", []))
        self.dirty = True

    def to_dict(self, include_points: bool = False) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "project_id": self.project_id,
            "asset_id": self.asset_id,
            "display_name": self.display_name,
            "environment_type": self.environment_type,
            "settings": asdict(self.settings),
            "author": asdict(self.author),
            "layers": [asdict(layer) for layer in self.layers],
            "active_layer_id": self.active_layer_id,
            "metadata": copy.deepcopy(self.metadata),
            "runtime": copy.deepcopy(self.runtime),
            "point_count": len(self.points),
        }
        if include_points:
            payload["points"] = [asdict(point) for point in self.points]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PCPDocument":
        document = cls()
        document.schema = str(payload.get("schema", "pcp3_project_v0"))
        document.project_id = str(payload.get("project_id", uuid.uuid4()))
        document.asset_id = str(payload.get("asset_id", "untitled_asset"))
        document.display_name = str(payload.get("display_name", "Untitled Asset"))
        environment = str(payload.get("environment_type", "environment_object"))
        document.environment_type = environment if environment in ENVIRONMENT_TYPES else "environment_object"
        settings = payload.get("settings", {})
        known_settings = {field_name for field_name in DocumentSettings.__dataclass_fields__}
        settings_known = {key: value for key, value in settings.items() if key in known_settings}
        document.settings = DocumentSettings(**settings_known)
        unknown_settings = {key: value for key, value in settings.items() if key not in known_settings}
        if unknown_settings:
            document.settings.future_attributes.update(unknown_settings)
        author = payload.get("author", {})
        document.author = AuthorForm(
            creator_name=str(author.get("creator_name", "")),
            title=str(author.get("title", "")),
            asset_type=str(author.get("asset_type", document.environment_type)),
            description=str(author.get("description", "")),
            tags=list(author.get("tags", [])),
        )
        document.layers = []
        layer_fields = set(Layer.__dataclass_fields__)
        for layer_payload in payload.get("layers", []):
            if not isinstance(layer_payload, dict):
                continue
            known_layer = {key: value for key, value in layer_payload.items() if key in layer_fields}
            unknown_layer = {key: value for key, value in layer_payload.items() if key not in layer_fields}
            layer = Layer(**known_layer)
            if unknown_layer:
                layer.future_attributes.update(unknown_layer)
            document.layers.append(layer)
        if not document.layers:
            document.layers = [Layer(1, "Base Points")]
        document.active_layer_id = int(payload.get("active_layer_id", document.layers[0].id))
        document.metadata = copy.deepcopy(payload.get("metadata", {}))
        document.runtime = copy.deepcopy(payload.get("runtime", document.runtime))
        document.points = [PCPPoint(**point) for point in payload.get("points", []) if isinstance(point, dict)]
        document.dirty = False
        return document


def primitive_box(center: tuple[float, float, float], size: tuple[float, float, float], spacing: float,
                  layer_id: int, color: tuple[float, float, float, float], radius: float,
                  semantic: str = "generic") -> list[PCPPoint]:
    cx, cy, cz = center
    sx, sy, sz = (max(0.01, value) for value in size)
    spacing = max(0.05, spacing)
    nx = max(2, int(math.ceil(sx / spacing)) + 1)
    ny = max(2, int(math.ceil(sy / spacing)) + 1)
    nz = max(2, int(math.ceil(sz / spacing)) + 1)
    flag = SEMANTIC_FLAGS.get(semantic, 0)
    points: list[PCPPoint] = []
    for ix in range(nx):
        x = cx - sx / 2 + sx * ix / (nx - 1)
        for iy in range(ny):
            y = cy - sy / 2 + sy * iy / (ny - 1)
            for z, normal in ((cz - sz / 2, (0, 0, -1)), (cz + sz / 2, (0, 0, 1))):
                points.append(PCPPoint(x, y, z, radius, *color, *normal, 1.0, layer_id, flag))
    for ix in range(nx):
        x = cx - sx / 2 + sx * ix / (nx - 1)
        for iz in range(nz):
            z = cz - sz / 2 + sz * iz / (nz - 1)
            for y, normal in ((cy - sy / 2, (0, -1, 0)), (cy + sy / 2, (0, 1, 0))):
                points.append(PCPPoint(x, y, z, radius, *color, *normal, 1.0, layer_id, flag))
    for iy in range(ny):
        y = cy - sy / 2 + sy * iy / (ny - 1)
        for iz in range(nz):
            z = cz - sz / 2 + sz * iz / (nz - 1)
            for x, normal in ((cx - sx / 2, (-1, 0, 0)), (cx + sx / 2, (1, 0, 0))):
                points.append(PCPPoint(x, y, z, radius, *color, *normal, 1.0, layer_id, flag))
    return points


def primitive_sphere(center: tuple[float, float, float], sphere_radius: float, spacing: float,
                     layer_id: int, color: tuple[float, float, float, float], point_radius: float,
                     semantic: str = "generic") -> list[PCPPoint]:
    cx, cy, cz = center
    sphere_radius = max(0.05, sphere_radius)
    spacing = max(0.05, spacing)
    area = 4.0 * math.pi * sphere_radius * sphere_radius
    count = max(24, int(area / (spacing * spacing)))
    flag = SEMANTIC_FLAGS.get(semantic, 0)
    golden = math.pi * (3.0 - math.sqrt(5.0))
    points: list[PCPPoint] = []
    for index in range(count):
        y_norm = 1.0 - 2.0 * (index + 0.5) / count
        ring = math.sqrt(max(0.0, 1.0 - y_norm * y_norm))
        angle = golden * index
        nx = math.cos(angle) * ring
        ny = y_norm
        nz = math.sin(angle) * ring
        points.append(PCPPoint(
            cx + nx * sphere_radius,
            cy + ny * sphere_radius,
            cz + nz * sphere_radius,
            point_radius, *color, nx, ny, nz, 1.0, layer_id, flag,
        ))
    return points


def primitive_cylinder(center: tuple[float, float, float], cylinder_radius: float, height: float, spacing: float,
                       layer_id: int, color: tuple[float, float, float, float], point_radius: float,
                       semantic: str = "generic") -> list[PCPPoint]:
    cx, cy, cz = center
    cylinder_radius = max(0.05, cylinder_radius)
    height = max(0.05, height)
    spacing = max(0.05, spacing)
    ring_count = max(12, int(math.ceil(2.0 * math.pi * cylinder_radius / spacing)))
    vertical_count = max(2, int(math.ceil(height / spacing)) + 1)
    radial_count = max(2, int(math.ceil(cylinder_radius / spacing)) + 1)
    flag = SEMANTIC_FLAGS.get(semantic, 0)
    points: list[PCPPoint] = []
    for iy in range(vertical_count):
        y = cy - height / 2.0 + height * iy / (vertical_count - 1)
        for ia in range(ring_count):
            angle = 2.0 * math.pi * ia / ring_count
            nx = math.cos(angle)
            nz = math.sin(angle)
            points.append(PCPPoint(cx + nx * cylinder_radius, y, cz + nz * cylinder_radius,
                                   point_radius, *color, nx, 0.0, nz, 1.0, layer_id, flag))
    for side, ny in ((-1.0, -1.0), (1.0, 1.0)):
        y = cy + side * height / 2.0
        for ir in range(radial_count):
            radius = cylinder_radius * ir / (radial_count - 1)
            ring = 1 if ir == 0 else max(8, int(math.ceil(2.0 * math.pi * radius / spacing)))
            for ia in range(ring):
                angle = 2.0 * math.pi * ia / ring
                points.append(PCPPoint(cx + math.cos(angle) * radius, y, cz + math.sin(angle) * radius,
                                       point_radius, *color, 0.0, ny, 0.0, 1.0, layer_id, flag))
    return points


def primitive_line(start: tuple[float, float, float], end: tuple[float, float, float], spacing: float,
                   layer_id: int, color: tuple[float, float, float, float], point_radius: float,
                   semantic: str = "generic") -> list[PCPPoint]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dz = end[2] - start[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    count = max(2, int(math.ceil(length / max(0.05, spacing))) + 1)
    normal = (0.0, 1.0, 0.0)
    flag = SEMANTIC_FLAGS.get(semantic, 0)
    return [
        PCPPoint(
            start[0] + dx * index / (count - 1),
            start[1] + dy * index / (count - 1),
            start[2] + dz * index / (count - 1),
            point_radius, *color, *normal, 1.0, layer_id, flag,
        )
        for index in range(count)
    ]
