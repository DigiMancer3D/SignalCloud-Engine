from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from tools.pcp3.io import load_project

from .model import PhysicsProfile, ShowcaseAsset, VisualizationProfile


@dataclass(slots=True, frozen=True)
class CatalogEntry:
    asset_id: str
    display_name: str
    pack: str
    category: str
    directory: Path
    point_count: int
    physics_shape: str


def _entry(directory: Path, pack: str) -> CatalogEntry | None:
    asset_id = directory.name
    project = directory / f"{asset_id}.pcp3"
    physics = directory / f"{asset_id}.scphysics"
    if not project.is_file() or not physics.is_file():
        return None
    try:
        document = load_project(project)
        profile = PhysicsProfile.load(physics)
    except Exception:
        return None
    category = str(document.metadata.get("starter_catalog", "user" if pack == "user" else "uncategorized"))
    return CatalogEntry(
        asset_id=asset_id,
        display_name=document.display_name or asset_id.replace("_", " ").title(),
        pack=pack,
        category=category,
        directory=directory,
        point_count=len(document.points),
        physics_shape=profile.shape,
    )


def scan_catalog(project_root: Path) -> list[CatalogEntry]:
    root = Path(project_root).resolve()
    entries: list[CatalogEntry] = []
    for pack in ("starter", "user"):
        base = root / "content" / pack / "showcase"
        if not base.is_dir():
            continue
        for directory in sorted(path for path in base.iterdir() if path.is_dir()):
            item = _entry(directory, pack)
            if item is not None:
                entries.append(item)
    return sorted(entries, key=lambda item: (item.pack, item.category, item.display_name.casefold()))


def load_catalog_asset(entry: CatalogEntry) -> ShowcaseAsset:
    directory = entry.directory.resolve()
    project = directory / f"{entry.asset_id}.pcp3"
    physics = directory / f"{entry.asset_id}.scphysics"
    visualization = directory / f"{entry.asset_id}.scshowcase"
    provenance_path = directory / "provenance.json"
    document = load_project(project)
    profile = PhysicsProfile.load(physics)
    view = VisualizationProfile.load(visualization) if visualization.is_file() else VisualizationProfile()
    provenance: dict[str, object] = {}
    if provenance_path.is_file():
        payload = json.loads(provenance_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            provenance = payload
    source_name = str(provenance.get("source_name", project.name))
    source = directory / "source" / source_name
    if not source.is_file():
        source = project
    return ShowcaseAsset(source, f"managed-{entry.pack}", document, profile, provenance, [], view)
