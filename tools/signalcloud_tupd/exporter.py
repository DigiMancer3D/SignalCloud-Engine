from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

from tools.asset_doctor.content_abi import write_asset_envelope

from .codec import load_recipe, load_result_instance, save_recipe_atomic, save_result_instance_atomic
from .model import TupdInstanceTest, TupdPreview, TupdRecipe, TupdResultInstance


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-.")
    return slug[:80] or "tupd-recipe"


def export_managed_recipe(
    recipe: TupdRecipe,
    preview: TupdPreview,
    project_root: Path,
    instance: TupdResultInstance | None = None,
    tests: list[TupdInstanceTest] | None = None,
) -> Path:
    project_root = Path(project_root).resolve()
    slug = safe_slug(recipe.recipe_id)
    destination = project_root / "content" / "user" / "tupd" / slug
    destination.mkdir(parents=True, exist_ok=True)
    recipe_path = save_recipe_atomic(destination / f"{slug}.tupd", recipe)

    result_path = destination / f"{slug}.result.udata"
    result_path.write_text(
        "@udata 1\n\n[result]\n"
        f"recipe_id: {json.dumps(recipe.recipe_id)};\n"
        f"recipe_revision: {recipe.recipe_revision};\n"
        f"result_id: {json.dumps(recipe.result.result_id)};\n"
        f"result_name: {json.dumps(recipe.result.display_name)};\n"
        f"result_kind: {json.dumps(recipe.result.result_kind)};\n"
        f"interfaces: {json.dumps(recipe.result.interfaces)};\n"
        f"sockets: {json.dumps(recipe.result.sockets)};\n"
        f"tags: {json.dumps(recipe.result.tags)};\n"
        f"test_actions: {json.dumps(recipe.test_actions)};\n"
        f"point_budget: {recipe.result.point_budget};\n"
        f"preview_signature: {json.dumps(preview.signature)};\n"
        f"preview_valid: {json.dumps(preview.valid)};\n"
        f"stability_percent: {preview.stability_percent};\n"
        f"weight_before: {preview.weight_before};\n"
        f"weight_after: {preview.weight_after};\n",
        encoding="utf-8",
    )
    write_asset_envelope(
        project_root / "content",
        recipe_path,
        asset_id=f"user.tupd.{slug}",
        asset_type="tupd_recipe",
        family="items",
        pack="user",
        license_id="LicenseRef-UserAuthored",
        dependencies=[],
        hot_reload="authoring-only",
    )
    write_asset_envelope(
        project_root / "content",
        result_path,
        asset_id=f"user.tupd.{slug}.result",
        asset_type="udata",
        family="items",
        pack="user",
        license_id="LicenseRef-UserAuthored",
        dependencies=[f"user.tupd.{slug}"],
        hot_reload="disabled",
    )

    preview_receipt_path = destination / f"{slug}.preview_receipt.json"
    preview_receipt_path.write_text(json.dumps({
        "schema": "signalcloud.tupd-preview-receipt",
        "recipe_id": recipe.recipe_id,
        "recipe_revision": recipe.recipe_revision,
        "result_id": recipe.result.result_id,
        "valid": preview.valid,
        "forced": preview.forced,
        "condition_before": preview.condition_before,
        "condition_after": preview.condition_after,
        "weight_before": preview.weight_before,
        "weight_after": preview.weight_after,
        "stability_percent": preview.stability_percent,
        "point_budget": preview.point_budget,
        "signature": preview.signature,
        "normal_save_changed": False,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_asset_envelope(
        project_root / "content",
        preview_receipt_path,
        asset_id=f"user.tupd.{slug}.preview-receipt",
        asset_type="json",
        family="items",
        pack="user",
        license_id="LicenseRef-UserAuthored",
        dependencies=[f"user.tupd.{slug}"],
        hot_reload="disabled",
    )

    if instance is not None:
        instance_path = save_result_instance_atomic(destination / f"{slug}.tupdinstance", instance)
        write_asset_envelope(
            project_root / "content",
            instance_path,
            asset_id=f"user.tupd.{slug}.instance",
            asset_type="tupd_instance",
            family="items",
            pack="user",
            license_id="LicenseRef-UserAuthored",
            dependencies=[f"user.tupd.{slug}", f"user.tupd.{slug}.result"],
            hot_reload="authoring-only",
        )
        test_receipt_path = destination / f"{slug}.test_receipt.json"
        test_receipt_path.write_text(json.dumps({
            "schema": "signalcloud.tupd-test-receipt",
            "recipe_id": recipe.recipe_id,
            "instance_id": instance.instance_id,
            "result_state": instance.state,
            "test_count": instance.test_count,
            "tests": [asdict(test) for test in (tests or [])],
            "normal_save_changed": False,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_asset_envelope(
            project_root / "content",
            test_receipt_path,
            asset_id=f"user.tupd.{slug}.test-receipt",
            asset_type="json",
            family="items",
            pack="user",
            license_id="LicenseRef-UserAuthored",
            dependencies=[f"user.tupd.{slug}.instance"],
            hot_reload="disabled",
        )
        load_result_instance(instance_path)

    load_recipe(recipe_path)
    return destination


def recipe_digest(recipe_path: Path) -> str:
    return hashlib.sha256(Path(recipe_path).read_bytes()).hexdigest()
