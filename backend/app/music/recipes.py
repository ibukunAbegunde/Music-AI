"""Recipe save/load stubs (Phase 1) — groove + palette + locks session memory."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from backend.app.models.schemas import MusicProject, Recipe, SectionDraft, utcnow
from backend.app.storage.assets import AssetStore


def recipe_from_project(
    project: MusicProject,
    *,
    name: str | None = None,
    approved: bool = False,
) -> Recipe:
    locked = [t.role.value for t in project.tracks if t.locked]
    skeleton = [
        SectionDraft(
            name=s.name,
            start_bar=s.start_bar,
            end_bar=s.end_bar,
            intensity_target=s.intensity_target,
        )
        for s in project.sections
    ]
    groove = {
        "bpm": project.bpm,
        "key": project.key_estimate,
        "meter": project.meter,
        "length_bars": project.length_bars,
        "role_note_counts": {t.role.value: len(t.note_events) for t in project.tracks},
    }
    return Recipe(
        name=name or f"{project.name}-recipe",
        genre_tags=[tag for t in project.tracks for tag in t.tags if tag not in ("phase1",)],
        groove_fingerprint=groove,
        arrangement_skeleton=skeleton,
        locked_roles=locked,
        brief_snapshot={"generation_brief": project.generation_brief, "seed": project.seed},
        cir_snapshot_ref=f"projects/{project.id}/versions/{project.version_id}.json"
        if project.version_id
        else None,
        source_project_id=project.id,
        approved=approved,
        created_at=utcnow(),
    )


def _recipes_dir(assets: AssetStore) -> Path:
    path = assets.root / "recipes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_recipe(recipe: Recipe, assets: AssetStore) -> Path:
    """Persist a recipe JSON under workspace/recipes/."""
    path = _recipes_dir(assets) / f"{recipe.id}.json"
    path.write_text(json.dumps(recipe.model_dump(mode="json"), indent=2), encoding="utf-8")
    # Index stub for list_recipes
    index_path = _recipes_dir(assets) / "index.json"
    index: list[str] = []
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    rid = str(recipe.id)
    if rid not in index:
        index.append(rid)
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return path


def load_recipe(recipe_id: UUID, assets: AssetStore) -> Recipe | None:
    path = _recipes_dir(assets) / f"{recipe_id}.json"
    if not path.exists():
        return None
    return Recipe.model_validate(json.loads(path.read_text(encoding="utf-8")))


def list_recipes(assets: AssetStore) -> list[Recipe]:
    index_path = _recipes_dir(assets) / "index.json"
    if not index_path.exists():
        # Fallback: scan directory
        recipes = []
        for p in sorted(_recipes_dir(assets).glob("*.json")):
            if p.name == "index.json":
                continue
            recipes.append(Recipe.model_validate(json.loads(p.read_text(encoding="utf-8"))))
        return recipes
    out: list[Recipe] = []
    for rid in json.loads(index_path.read_text(encoding="utf-8")):
        r = load_recipe(UUID(rid), assets)
        if r is not None:
            out.append(r)
    return out
