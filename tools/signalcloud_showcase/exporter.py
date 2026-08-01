from __future__ import annotations

import json
import shutil
from pathlib import Path

from tools.asset_doctor.content_abi import repair_machine_paths, write_asset_envelope
from tools.pcp3.io import atomic_write_text, portable_metadata, save_project, slugify

from .model import ShowcaseAsset


def export_managed_asset(asset: ShowcaseAsset, project_root: Path, *, pack: str = "user") -> Path:
    root = Path(project_root).expanduser().resolve()
    if pack not in {"core", "starter", "mods", "user"}:
        raise ValueError("Showcase export pack must be core, starter, mods, or user")
    asset_id = slugify(asset.document.asset_id or asset.document.display_name)
    destination = root / "content" / pack / "showcase" / asset_id
    destination.mkdir(parents=True, exist_ok=True)
    source_dir = destination / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    asset.document.asset_id = asset_id
    project_path = destination / f"{asset_id}.pcp3"
    asset.document.metadata = portable_metadata(asset.document.metadata, root)
    asset.document.metadata.update({
        "showcase_managed_pack": pack,
        "showcase_source_path": f"source/{asset.source_path.name}",
        "physics_profile_file": f"{asset_id}.scphysics",
        "provenance_file": "provenance.json",
        "showcase_visualization_file": f"{asset_id}.scshowcase",
        "last_project_path": project_path.relative_to(root).as_posix(),
    })
    paths = save_project(asset.document, project_path, editor_name="SignalCloud Showcase A7a2r2")
    asset.document.metadata["last_project_path"] = project_path.relative_to(root).as_posix()
    physics_path = destination / f"{asset_id}.scphysics"
    asset.physics.profile_id = f"showcase.{asset_id}"
    asset.physics.auto_fit(asset.document.points).save(physics_path)
    visualization_path = destination / f"{asset_id}.scshowcase"
    asset.visualization.save(visualization_path)
    provenance = portable_metadata(dict(asset.provenance), root)
    provenance.update({
        "managed_pack": pack,
        "asset_id": asset_id,
        "pcp3_project": paths["project"].name,
        "pcp3_cloud": paths["cloud"].name,
        "physics_profile": physics_path.name,
        "showcase_visualization": visualization_path.name,
        "warnings": list(asset.warnings),
    })
    atomic_write_text(destination / "provenance.json", json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    source_copy = source_dir / asset.source_path.name
    if asset.source_path.resolve() != source_copy.resolve():
        shutil.copy2(asset.source_path, source_copy)

    license_id = "LicenseRef-SignalCloud-User-Authored" if pack == "user" else "CC0-1.0"
    write_asset_envelope(
        root / "content",
        paths["project"],
        asset_id=f"showcase.{pack}.{asset_id}",
        asset_type="pcp3_project",
        family="showcase",
        pack=pack,
        license_id=license_id,
        hot_reload="authoring-only",
    )
    write_asset_envelope(
        root / "content",
        physics_path,
        asset_id=f"showcase.physics.{pack}.{asset_id}",
        asset_type="physics_profile",
        family="physics",
        pack=pack,
        license_id=license_id,
        dependencies=[f"showcase.{pack}.{asset_id}"],
        hot_reload="authoring-only",
    )
    write_asset_envelope(
        root / "content",
        visualization_path,
        asset_id=f"showcase.visualization.{pack}.{asset_id}",
        asset_type="showcase_visualization",
        family="showcase",
        pack=pack,
        license_id=license_id,
        dependencies=[f"showcase.{pack}.{asset_id}", f"showcase.physics.{pack}.{asset_id}"],
        hot_reload="authoring-only",
    )
    companion_specs = (
        (paths["cloud"], f"showcase.cloud.{pack}.{asset_id}", "pcp3_cloud", "point_cloud"),
        (paths["cert"], f"showcase.certificate.{pack}.{asset_id}", "json_sidecar", "metadata"),
        (destination / "provenance.json", f"showcase.provenance.{pack}.{asset_id}", "json_sidecar", "metadata"),
        (source_copy, f"showcase.source.{pack}.{asset_id}", "udata" if source_copy.suffix.lower() == ".udata" else "source_data", "source"),
    )
    for companion, companion_id, companion_type, companion_family in companion_specs:
        write_asset_envelope(
            root / "content",
            companion,
            asset_id=companion_id,
            asset_type=companion_type,
            family=companion_family,
            pack=pack,
            license_id=license_id,
            dependencies=[f"showcase.{pack}.{asset_id}"],
            hot_reload="disabled",
        )
    atomic_write_text(
        destination / "VALIDATION_REPORT.md",
        "\n".join([
            f"# Showcase validation — {asset.document.display_name}",
            "",
            f"- Asset ID: `{asset_id}`",
            f"- Source kind: `{asset.source_kind}`",
            f"- Point count: `{len(asset.document.points)}`",
            f"- Physics shape: `{asset.physics.shape}`",
            f"- Collision half extents: `{asset.physics.collision_half_x:.3f}, {asset.physics.collision_half_y:.3f}, {asset.physics.collision_half_z:.3f}`",
            f"- Visualization: `{asset.visualization.view_mode}` at `{asset.visualization.lod_fraction:.3f}` LOD",
            "- Source execution: **blocked / data-only import**",
            "- Export path: project-relative and self-contained",
            "- Status: pending Asset Doctor confirmation",
            "",
        ]),
    )
    # Imported PCP3/UDATA metadata can carry its former working path. Repair
    # every managed text companion after copying, then refresh sidecar hashes.
    repair_machine_paths(root / "content")
    return destination
