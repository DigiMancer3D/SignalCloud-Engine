from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .codec import load_recipe, load_result_instance
from .model import TupdRecipe, TupdResultInstance


@dataclass(slots=True, frozen=True)
class TupdCatalogEntry:
    key: str
    label: str
    pack: str
    path: Path
    mode: str


@dataclass(slots=True, frozen=True)
class TupdInstanceCatalogEntry:
    key: str
    label: str
    pack: str
    path: Path
    state: str


def scan_catalog(project_root: Path) -> list[TupdCatalogEntry]:
    project_root = Path(project_root).resolve()
    roots = (
        ("Core Recipes", project_root / "content" / "core" / "tupd"),
        ("Starter Recipes", project_root / "content" / "starter" / "tupd"),
        ("User Recipes", project_root / "content" / "user" / "tupd"),
    )
    entries: list[TupdCatalogEntry] = []
    for pack, root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.tupd")):
            try:
                recipe = load_recipe(path)
            except (OSError, ValueError):
                continue
            entries.append(TupdCatalogEntry(
                key=recipe.recipe_id,
                label=recipe.label,
                pack=pack,
                path=path,
                mode=recipe.mode,
            ))
    return entries


def scan_result_instances(project_root: Path) -> list[TupdInstanceCatalogEntry]:
    project_root = Path(project_root).resolve()
    roots = (
        ("Core Results", project_root / "content" / "core" / "tupd"),
        ("Starter Results", project_root / "content" / "starter" / "tupd"),
        ("User Results", project_root / "content" / "user" / "tupd"),
    )
    entries: list[TupdInstanceCatalogEntry] = []
    for pack, root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.tupdinstance")):
            try:
                instance = load_result_instance(path)
            except (OSError, ValueError):
                continue
            entries.append(TupdInstanceCatalogEntry(
                key=instance.instance_id,
                label=instance.display_name or instance.result_id,
                pack=pack,
                path=path,
                state=instance.state,
            ))
    return entries


def load_catalog_recipe(entry: TupdCatalogEntry) -> TupdRecipe:
    return load_recipe(entry.path)


def load_catalog_instance(entry: TupdInstanceCatalogEntry) -> TupdResultInstance:
    return load_result_instance(entry.path)
