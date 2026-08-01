from __future__ import annotations

from pathlib import Path
import math

from tools.pcp3.io import slugify
from tools.pcp3.model import PCPDocument, PCPPoint

from .exporter import export_managed_asset
from .model import PhysicsProfile, ShowcaseAsset, VisualizationProfile


def _box_points(
    width: float,
    height: float,
    depth: float,
    color: tuple[float, float, float],
    spacing: float = 0.14,
    center: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> list[PCPPoint]:
    points: list[PCPPoint] = []
    nx = max(2, round(width / spacing))
    ny = max(2, round(height / spacing))
    nz = max(2, round(depth / spacing))
    cx, cy, cz = center
    for ix in range(nx + 1):
        x = cx - width / 2 + width * ix / nx
        for iy in range(ny + 1):
            y = cy - height / 2 + height * iy / ny
            for z in (cz - depth / 2, cz + depth / 2):
                points.append(PCPPoint(x, y, z, 1.7, *color, 1.0))
    for iz in range(nz + 1):
        z = cz - depth / 2 + depth * iz / nz
        for iy in range(ny + 1):
            y = cy - height / 2 + height * iy / ny
            for x in (cx - width / 2, cx + width / 2):
                points.append(PCPPoint(x, y, z, 1.7, *color, 1.0))
    for ix in range(nx + 1):
        x = cx - width / 2 + width * ix / nx
        for iz in range(nz + 1):
            z = cz - depth / 2 + depth * iz / nz
            for y in (cy - height / 2, cy + height / 2):
                points.append(PCPPoint(x, y, z, 1.7, *color, 1.0))
    return points


def _cylinder_points(
    radius: float,
    height: float,
    color: tuple[float, float, float],
    *,
    center: tuple[float, float, float] = (0.0, 0.0, 0.0),
    radial_samples: int = 52,
    height_samples: int = 16,
) -> list[PCPPoint]:
    cx, cy, cz = center
    points: list[PCPPoint] = []
    for iy in range(height_samples + 1):
        y = cy - height / 2 + height * iy / height_samples
        for index in range(radial_samples):
            angle = math.tau * index / radial_samples
            points.append(PCPPoint(
                cx + math.cos(angle) * radius,
                y,
                cz + math.sin(angle) * radius,
                1.65, *color, 1.0,
                math.cos(angle), 0.0, math.sin(angle), 1.0,
            ))
    for ring_radius in (radius * 0.35, radius * 0.68, radius):
        for index in range(radial_samples):
            angle = math.tau * index / radial_samples
            for y in (cy - height / 2, cy + height / 2):
                points.append(PCPPoint(
                    cx + math.cos(angle) * ring_radius,
                    y,
                    cz + math.sin(angle) * ring_radius,
                    1.55, *color, 1.0,
                ))
    return points


def _asset(
    project_root: Path,
    asset_id: str,
    display_name: str,
    points: list[PCPPoint],
    profile: PhysicsProfile,
    tags: list[str],
    *,
    actor_preview: bool = False,
    view_mode: str = "material",
) -> ShowcaseAsset:
    doc = PCPDocument.new("environment_object")
    doc.asset_id = slugify(asset_id)
    doc.display_name = display_name
    doc.points = points
    doc.author.creator_name = "DigiMancer3D / SignalCloud Engine"
    doc.author.title = display_name
    doc.author.description = "Original procedural SignalCloud starter asset generated for the public Alpha Showcase."
    doc.author.tags = ["starter", "showcase", *tags]
    doc.metadata.update({
        "showcase_source_kind": "procedural-signalcloud",
        "showcase_import_policy": "original_generated_data",
        "license_id": "CC0-1.0",
        "provenance": "SignalCloud A7a2 procedural generator",
        "starter_catalog": "architecture" if "architecture" in tags else "systems",
    })
    source_path = Path(project_root) / "examples" / "showcase" / f"{asset_id}.source.udata"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        "@udata 1\n\n[source]\n"
        f"asset_id: {{\"value\":\"{asset_id}\"}};\n"
        "generator: {\"value\":\"SignalCloud Showcase A7a2 procedural generator\"};\n"
        "license_id: {\"value\":\"CC0-1.0\"};\n",
        encoding="utf-8",
    )
    provenance = {
        "schema": "signalcloud.showcase-provenance",
        "schema_major": 1,
        "source_name": source_path.name,
        "source_kind": "procedural-signalcloud",
        "source_sha256": "generated-at-export",
        "importer": "SignalCloud Showcase A7a2 starter generator",
        "execution_policy": "no_external_source",
        "point_count": len(points),
        "license_id": "CC0-1.0",
    }
    profile.auto_fit(points)
    visualization = VisualizationProfile(
        view_mode=view_mode,
        lod_fraction=1.0,
        point_scale=1.05,
        collision_outline=True,
        actor_preview=actor_preview,
        playbook_id="starter.actor.motion" if actor_preview else "",
    )
    return ShowcaseAsset(source_path, "procedural-signalcloud", doc, profile, provenance, [], visualization)


def build_starter_assets(project_root: Path) -> list[ShowcaseAsset]:
    root = Path(project_root).resolve()
    assets: list[ShowcaseAsset] = []

    assets.append(_asset(
        root, "office_shipping_crate", "Office Shipping Crate",
        _box_points(2.0, 1.4, 1.5, (0.56, 0.43, 0.26)),
        PhysicsProfile(
            profile_id="showcase.office_shipping_crate", shape="box", mass=18.0,
            friction=0.72, restitution=0.16, break_threshold=145.0,
            hold_points=[[-0.8, 0.0, 0.0], [0.8, 0.0, 0.0]],
            sockets=[{"id": "top_mount", "position": [0.0, 0.72, 0.0], "kind": "flat"}],
        ),
        ["architecture", "office", "backrooms", "crate"],
    ))

    wall = _box_points(4.4, 2.8, 0.22, (0.68, 0.65, 0.48), 0.16)
    wall += _box_points(0.10, 2.45, 0.30, (0.36, 0.34, 0.29), 0.10, (-1.45, 0.0, 0.0))
    wall += _box_points(0.10, 2.45, 0.30, (0.36, 0.34, 0.29), 0.10, (1.45, 0.0, 0.0))
    assets.append(_asset(
        root, "modular_office_wall_panel", "Modular Office Wall Panel", wall,
        PhysicsProfile(profile_id="showcase.modular_office_wall_panel", shape="box", mass=48.0,
                       friction=0.88, restitution=0.05, break_threshold=410.0,
                       sockets=[{"id": "wall_left", "position": [-2.2, 0.0, 0.0], "kind": "architecture"},
                                {"id": "wall_right", "position": [2.2, 0.0, 0.0], "kind": "architecture"}]),
        ["architecture", "office", "wall", "modular"],
    ))

    frame = _box_points(0.28, 3.0, 0.38, (0.27, 0.31, 0.34), 0.10, (-1.2, 0.0, 0.0))
    frame += _box_points(0.28, 3.0, 0.38, (0.27, 0.31, 0.34), 0.10, (1.2, 0.0, 0.0))
    frame += _box_points(2.68, 0.30, 0.38, (0.27, 0.31, 0.34), 0.10, (0.0, 1.35, 0.0))
    assets.append(_asset(
        root, "signal_door_frame", "Signal Door Frame", frame,
        PhysicsProfile(profile_id="showcase.signal_door_frame", shape="compound", mass=36.0,
                       friction=0.80, restitution=0.08, break_threshold=320.0,
                       sockets=[{"id": "door_hinge", "position": [-1.0, 0.0, 0.0], "kind": "hinge"},
                                {"id": "header_signal", "position": [0.0, 1.5, 0.0], "kind": "signal"}]),
        ["architecture", "doorway", "threshold", "modular"],
    ))

    cabinet = _box_points(1.25, 2.0, 0.72, (0.38, 0.43, 0.46), 0.11)
    for y in (-0.52, 0.0, 0.52):
        cabinet += _box_points(0.72, 0.07, 0.05, (0.12, 0.15, 0.17), 0.05, (0.0, y, -0.39))
    assets.append(_asset(
        root, "rolling_file_cabinet", "Rolling File Cabinet", cabinet,
        PhysicsProfile(profile_id="showcase.rolling_file_cabinet", shape="box", mass=27.0,
                       friction=0.34, restitution=0.10, break_threshold=230.0,
                       hold_points=[[0.0, 0.65, -0.36]],
                       sockets=[{"id": "drawer_lock", "position": [0.0, 0.88, -0.38], "kind": "interaction"}]),
        ["architecture", "office", "cabinet", "furniture"],
    ))

    cart = _box_points(2.2, 0.16, 1.0, (0.42, 0.48, 0.50), 0.10, (0.0, 0.25, 0.0))
    cart += _box_points(0.12, 1.5, 0.12, (0.30, 0.34, 0.36), 0.08, (-0.95, 0.95, 0.0))
    cart += _box_points(0.12, 1.5, 0.12, (0.30, 0.34, 0.36), 0.08, (0.95, 0.95, 0.0))
    for x in (-0.82, 0.82):
        for z in (-0.34, 0.34):
            cart += _cylinder_points(0.16, 0.12, (0.12, 0.14, 0.16), center=(x, 0.08, z), radial_samples=28, height_samples=4)
    assets.append(_asset(
        root, "utility_cart", "Office Utility Cart", cart,
        PhysicsProfile(profile_id="showcase.utility_cart", shape="compound", mass=23.0,
                       friction=0.24, restitution=0.12, break_threshold=180.0,
                       hold_points=[[-0.95, 1.35, 0.0], [0.95, 1.35, 0.0]],
                       sockets=[{"id": "cargo_top", "position": [0.0, 0.38, 0.0], "kind": "flat"}]),
        ["architecture", "office", "cart", "furniture"],
    ))

    beacon_points = _box_points(0.8, 1.6, 0.8, (0.18, 0.52, 0.64), 0.10)
    for ring in range(48):
        angle = math.tau * ring / 48
        beacon_points.append(PCPPoint(math.cos(angle) * 0.62, 0.55, math.sin(angle) * 0.62, 2.1, 0.24, 0.92, 0.98, 1.0))
    assets.append(_asset(
        root, "portable_signal_beacon", "Portable Signal Beacon", beacon_points,
        PhysicsProfile(profile_id="showcase.portable_signal_beacon", shape="compound", mass=6.5,
                       friction=0.61, restitution=0.24, break_threshold=88.0,
                       hold_points=[[0.0, 0.25, 0.0]],
                       sockets=[{"id": "signal_socket", "position": [0.0, 0.82, 0.0], "kind": "signal"}]),
        ["systems", "gameplay", "beacon", "tupd-compatible"], view_mode="light",
    ))

    pipe = _cylinder_points(0.30, 2.7, (0.35, 0.58, 0.62), center=(0.0, 0.0, 0.0))
    pipe += _cylinder_points(0.42, 0.18, (0.22, 0.34, 0.38), center=(0.0, -1.2, 0.0), radial_samples=44, height_samples=4)
    pipe += _cylinder_points(0.42, 0.18, (0.22, 0.34, 0.38), center=(0.0, 1.2, 0.0), radial_samples=44, height_samples=4)
    assets.append(_asset(
        root, "signal_conduit_section", "Signal Conduit Section", pipe,
        PhysicsProfile(profile_id="showcase.signal_conduit_section", shape="capsule", mass=9.0,
                       friction=0.48, restitution=0.18, break_threshold=125.0,
                       hold_points=[[0.0, -0.65, 0.0], [0.0, 0.65, 0.0]],
                       sockets=[{"id": "conduit_a", "position": [0.0, -1.35, 0.0], "kind": "conduit"},
                                {"id": "conduit_b", "position": [0.0, 1.35, 0.0], "kind": "conduit"}]),
        ["systems", "conduit", "modular", "tupd-compatible"],
    ))

    bracket = _box_points(1.8, 0.20, 0.70, (0.50, 0.52, 0.55), 0.08)
    bracket += _box_points(0.20, 1.25, 0.70, (0.50, 0.52, 0.55), 0.08, (-0.8, 0.52, 0.0))
    bracket += _box_points(0.20, 1.25, 0.70, (0.50, 0.52, 0.55), 0.08, (0.8, 0.52, 0.0))
    assets.append(_asset(
        root, "universal_mount_bracket", "Universal Mount Bracket", bracket,
        PhysicsProfile(profile_id="showcase.universal_mount_bracket", shape="compound", mass=4.2,
                       friction=0.67, restitution=0.16, break_threshold=96.0,
                       sockets=[{"id": "mount_left", "position": [-0.72, 0.58, 0.0], "kind": "mount"},
                                {"id": "mount_right", "position": [0.72, 0.58, 0.0], "kind": "mount"},
                                {"id": "mount_base", "position": [0.0, -0.12, 0.0], "kind": "flat"}]),
        ["systems", "mount", "bracket", "tupd-compatible"],
    ))

    actor = _box_points(0.92, 1.25, 0.48, (0.31, 0.68, 0.77), 0.10, (0.0, 0.55, 0.0))
    actor += _cylinder_points(0.34, 0.48, (0.48, 0.82, 0.88), center=(0.0, 1.42, 0.0), radial_samples=40, height_samples=8)
    actor += _box_points(0.25, 1.15, 0.25, (0.22, 0.52, 0.62), 0.08, (-0.62, 0.52, 0.0))
    actor += _box_points(0.25, 1.15, 0.25, (0.22, 0.52, 0.62), 0.08, (0.62, 0.52, 0.0))
    actor += _box_points(0.30, 1.15, 0.34, (0.18, 0.40, 0.48), 0.08, (-0.24, -0.65, 0.0))
    actor += _box_points(0.30, 1.15, 0.34, (0.18, 0.40, 0.48), 0.08, (0.24, -0.65, 0.0))
    assets.append(_asset(
        root, "training_actor_block", "Training Actor Block", actor,
        PhysicsProfile(profile_id="showcase.training_actor_block", shape="capsule", mass=72.0,
                       friction=0.78, restitution=0.05, break_threshold=540.0,
                       sockets=[{"id": "hand_left", "position": [-0.72, 0.45, 0.0], "kind": "hand"},
                                {"id": "hand_right", "position": [0.72, 0.45, 0.0], "kind": "hand"},
                                {"id": "head", "position": [0.0, 1.65, 0.0], "kind": "actor"}]),
        ["systems", "actor", "animation", "playbook"], actor_preview=True, view_mode="light",
    ))

    tool = _box_points(2.5, 0.38, 0.45, (0.56, 0.30, 0.22), 0.08)
    tool += _box_points(0.44, 1.35, 0.40, (0.24, 0.27, 0.29), 0.08, (-0.82, -0.67, 0.0))
    tool += _cylinder_points(0.22, 0.52, (0.20, 0.78, 0.88), center=(1.25, 0.0, 0.0), radial_samples=32, height_samples=6)
    assets.append(_asset(
        root, "tupd_tool_body", "Tupd Tool Body", tool,
        PhysicsProfile(profile_id="showcase.tupd_tool_body", shape="compound", mass=5.8,
                       friction=0.64, restitution=0.13, break_threshold=118.0,
                       hold_points=[[-0.82, -0.58, 0.0]],
                       sockets=[{"id": "tool_front", "position": [1.48, 0.0, 0.0], "kind": "tool-head"},
                                {"id": "tool_top", "position": [0.0, 0.24, 0.0], "kind": "accessory"},
                                {"id": "tool_power", "position": [-1.18, 0.0, 0.0], "kind": "power"}]),
        ["systems", "tool", "weapon-body", "tupd-compatible"], view_mode="material",
    ))

    return assets


def install_starter_assets(project_root: Path) -> list[Path]:
    root = Path(project_root).resolve()
    return [export_managed_asset(asset, root, pack="starter") for asset in build_starter_assets(root)]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    for path in install_starter_assets(args.root):
        print(path)
