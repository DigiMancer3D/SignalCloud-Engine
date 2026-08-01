from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json
import math

ALLOWED_SHAPES = ("box", "sphere", "capsule", "hull", "compound")
ALLOWED_SLEEP_POLICIES = ("allow", "never", "after_settle")
ALLOWED_VIEW_MODES = ("source", "density", "material", "light")
ALLOWED_LOD_FRACTIONS = (1.0, 0.5, 0.25, 0.125)


def _finite(value: float, default: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


@dataclass(slots=True)
class PhysicsProfile:
    schema: str = "signalcloud.physics-profile"
    schema_major: int = 1
    schema_minor: int = 1
    profile_id: str = "showcase.default"
    shape: str = "box"
    mass: float = 4.0
    friction: float = 0.55
    restitution: float = 0.28
    gravity_scale: float = 1.0
    drag: float = 0.04
    break_threshold: float = 18.0
    impact_multiplier: float = 1.0
    collision_half_x: float = 0.5
    collision_half_y: float = 0.5
    collision_half_z: float = 0.5
    collision_radius: float = 0.5
    sleep_policy: str = "after_settle"
    hold_points: list[list[float]] = field(default_factory=list)
    sockets: list[dict[str, Any]] = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)

    def normalize(self) -> "PhysicsProfile":
        if self.shape not in ALLOWED_SHAPES:
            self.shape = "box"
        if self.sleep_policy not in ALLOWED_SLEEP_POLICIES:
            self.sleep_policy = "after_settle"
        self.mass = min(100_000.0, max(0.001, _finite(self.mass, 4.0)))
        self.friction = min(4.0, max(0.0, _finite(self.friction, 0.55)))
        self.restitution = min(1.0, max(0.0, _finite(self.restitution, 0.28)))
        self.gravity_scale = min(8.0, max(-2.0, _finite(self.gravity_scale, 1.0)))
        self.drag = min(10.0, max(0.0, _finite(self.drag, 0.04)))
        self.break_threshold = min(1_000_000.0, max(0.0, _finite(self.break_threshold, 18.0)))
        self.impact_multiplier = min(100.0, max(0.0, _finite(self.impact_multiplier, 1.0)))
        self.collision_half_x = min(2000.0, max(0.02, _finite(self.collision_half_x, 0.5)))
        self.collision_half_y = min(2000.0, max(0.02, _finite(self.collision_half_y, 0.5)))
        self.collision_half_z = min(2000.0, max(0.02, _finite(self.collision_half_z, 0.5)))
        self.collision_radius = min(2000.0, max(0.02, _finite(self.collision_radius, 0.5)))
        clean_hold: list[list[float]] = []
        for point in self.hold_points[:32]:
            if isinstance(point, (list, tuple)) and len(point) >= 3:
                clean_hold.append([_finite(point[0], 0.0), _finite(point[1], 0.0), _finite(point[2], 0.0)])
        self.hold_points = clean_hold
        self.sockets = [dict(item) for item in self.sockets[:64] if isinstance(item, dict)]
        return self

    def auto_fit(self, points: list[Any]) -> "PhysicsProfile":
        finite: list[tuple[float, float, float]] = []
        for point in points:
            try:
                xyz = (float(point.x), float(point.y), float(point.z))
            except (AttributeError, TypeError, ValueError):
                continue
            if all(math.isfinite(value) for value in xyz):
                finite.append(xyz)
        if not finite:
            return self.normalize()
        xs, ys, zs = zip(*finite)
        self.collision_half_x = max(0.02, (max(xs) - min(xs)) * 0.5)
        self.collision_half_y = max(0.02, (max(ys) - min(ys)) * 0.5)
        self.collision_half_z = max(0.02, (max(zs) - min(zs)) * 0.5)
        self.collision_radius = max(0.02, math.sqrt(
            self.collision_half_x ** 2 + self.collision_half_y ** 2 + self.collision_half_z ** 2
        ))
        if self.shape == "sphere":
            self.collision_radius = max(self.collision_half_x, self.collision_half_y, self.collision_half_z)
        elif self.shape == "capsule":
            self.collision_radius = max(0.02, max(self.collision_half_x, self.collision_half_z))
            self.collision_half_y = max(0.02, self.collision_half_y - self.collision_radius)
        return self.normalize()

    def to_dict(self) -> dict[str, Any]:
        self.normalize()
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PhysicsProfile":
        known = {field_name for field_name in cls.__dataclass_fields__}
        values = {key: value for key, value in payload.items() if key in known}
        profile = cls(**values)
        unknown = {key: value for key, value in payload.items() if key not in known}
        if unknown:
            profile.extensions = {**profile.extensions, **unknown}
        return profile.normalize()

    @classmethod
    def load(cls, path: Path) -> "PhysicsProfile":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("SC physics profile must be a JSON object")
        if payload.get("schema") not in (None, "signalcloud.physics-profile"):
            raise ValueError("Unsupported SC physics profile schema")
        return cls.from_dict(payload)

    def save(self, path: Path) -> None:
        from tools.pcp3.io import atomic_write_text

        atomic_write_text(path, json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")


@dataclass(slots=True)
class VisualizationProfile:
    schema: str = "signalcloud.showcase-visualization"
    schema_major: int = 1
    schema_minor: int = 0
    view_mode: str = "source"
    lod_fraction: float = 1.0
    point_scale: float = 1.0
    collision_outline: bool = True
    actor_preview: bool = False
    animation_rate: float = 1.0
    playbook_id: str = ""
    snapshot_width: int = 1280
    snapshot_height: int = 720
    extensions: dict[str, Any] = field(default_factory=dict)

    def normalize(self) -> "VisualizationProfile":
        if self.view_mode not in ALLOWED_VIEW_MODES:
            self.view_mode = "source"
        lod = _finite(self.lod_fraction, 1.0)
        self.lod_fraction = min(ALLOWED_LOD_FRACTIONS, key=lambda candidate: abs(candidate - lod))
        self.point_scale = min(4.0, max(0.25, _finite(self.point_scale, 1.0)))
        self.animation_rate = min(4.0, max(0.1, _finite(self.animation_rate, 1.0)))
        self.snapshot_width = min(4096, max(320, int(self.snapshot_width)))
        self.snapshot_height = min(4096, max(240, int(self.snapshot_height)))
        self.playbook_id = str(self.playbook_id)[:160]
        self.collision_outline = bool(self.collision_outline)
        self.actor_preview = bool(self.actor_preview)
        return self

    def to_dict(self) -> dict[str, Any]:
        self.normalize()
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VisualizationProfile":
        known = {field_name for field_name in cls.__dataclass_fields__}
        values = {key: value for key, value in payload.items() if key in known}
        profile = cls(**values)
        unknown = {key: value for key, value in payload.items() if key not in known}
        if unknown:
            profile.extensions = {**profile.extensions, **unknown}
        return profile.normalize()

    @classmethod
    def load(cls, path: Path) -> "VisualizationProfile":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Showcase visualization profile must be a JSON object")
        if payload.get("schema") not in (None, "signalcloud.showcase-visualization"):
            raise ValueError("Unsupported Showcase visualization schema")
        return cls.from_dict(payload)

    def save(self, path: Path) -> None:
        from tools.pcp3.io import atomic_write_text

        atomic_write_text(path, json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")


@dataclass(slots=True)
class ShowcaseAsset:
    source_path: Path
    source_kind: str
    document: Any
    physics: PhysicsProfile
    provenance: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    visualization: VisualizationProfile = field(default_factory=VisualizationProfile)


@dataclass(slots=True)
class ShowcaseTestResult:
    test_name: str
    duration_seconds: float
    steps: int
    start_position: tuple[float, float, float]
    end_position: tuple[float, float, float]
    max_speed: float
    impact_speed: float
    bounce_count: int
    broken: bool
    settled: bool
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
