"""Recipe save/load — groove + palette + locks + CIR locked-track replay."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from backend.app.models.schemas import BriefDocument, MusicProject, Recipe, SectionDraft, utcnow
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
        "genre_template_id": project.genre_template_id,
    }
    return Recipe(
        name=name or f"{project.name}-recipe",
        genre_tags=[tag for t in project.tracks for tag in t.tags if tag not in ("phase1",)],
        groove_fingerprint=groove,
        arrangement_skeleton=skeleton,
        locked_roles=locked,
        brief_snapshot={
            "generation_brief": project.generation_brief,
            "seed": project.seed,
            "genre_template_id": project.genre_template_id,
        },
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


def load_recipe_cir(recipe: Recipe, assets: AssetStore) -> MusicProject | None:
    """Load the CIR snapshot referenced by a recipe (locked-track source of truth).

    Falls back to the source project's tip metadata when ``cir_snapshot_ref``
    is missing or stale. Returns None only when no CIR can be recovered —
    callers then generate fresh locked material (documented stub path).
    """
    if recipe.cir_snapshot_ref:
        path = assets.root / recipe.cir_snapshot_ref
        if path.exists():
            return MusicProject.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if recipe.source_project_id is not None:
        meta_path = assets.root / "projects" / str(recipe.source_project_id) / "metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            vid = meta.get("version_id")
            if vid:
                cir_path = (
                    assets.root
                    / "projects"
                    / str(recipe.source_project_id)
                    / "versions"
                    / f"{vid}.json"
                )
                if cir_path.exists():
                    return MusicProject.model_validate(
                        json.loads(cir_path.read_text(encoding="utf-8"))
                    )
    return None


def brief_from_recipe(
    recipe: Recipe,
    *,
    prompt: str | None = None,
    seed: int | None = None,
    bars: int | None = None,
    novelty: float | None = None,
) -> BriefDocument:
    """Seed a BriefDocument from a saved recipe (locks + groove + skeleton)."""
    from backend.app.models.schemas import EnergyPoint
    from backend.app.music.brief import parse_brief

    fp = recipe.groove_fingerprint or {}
    text = prompt or recipe.brief_snapshot.get("generation_brief") or recipe.name
    length = bars or int(fp.get("length_bars") or 8)
    brief = parse_brief(
        str(text),
        seed=seed if seed is not None else recipe.brief_snapshot.get("seed"),
        bars=length,
        locked_roles=list(recipe.locked_roles),
    )
    # Prefer persisted genre from recipe over brief-text re-parse
    genre = (
        recipe.brief_snapshot.get("genre_template_id")
        or fp.get("genre_template_id")
    )
    if genre:
        brief.genre_template_id = str(genre)
    if fp.get("bpm"):
        brief.bpm = float(fp["bpm"])
    if fp.get("key"):
        brief.key = str(fp["key"])
    if fp.get("meter"):
        brief.meter = str(fp["meter"])
    if recipe.arrangement_skeleton:
        brief.section_map = list(recipe.arrangement_skeleton)
    if novelty is not None:
        brief.novelty = novelty
    brief.recipe_id = recipe.id
    brief.locked_roles = sorted(set(brief.locked_roles) | set(recipe.locked_roles))
    if not brief.energy_curve:
        brief.energy_curve = [
            EnergyPoint(bar=i + 1, value=0.55) for i in range(brief.length_bars)
        ]
    brief.updated_at = utcnow()
    return brief


def apply_recipe(
    recipe_id: UUID,
    assets: AssetStore,
    *,
    prompt: str | None = None,
    seed: int | None = None,
    bars: int | None = None,
    n: int = 2,
    settings=None,
    adapter=None,
    profile=None,
):
    """Load recipe → brief → N candidates, replaying locked CIR MIDI when available.

    Locked roles are restored from ``recipe.cir_snapshot_ref`` (or source tip)
    via ``generate_candidates(baseline_project=…)``. If no CIR can be loaded,
    candidates still share freshly generated locked material (stub path).
    """
    from backend.app.services.candidates import generate_candidates

    recipe = load_recipe(recipe_id, assets)
    if recipe is None:
        raise ValueError(f"unknown recipe {recipe_id}")
    brief = brief_from_recipe(recipe, prompt=prompt, seed=seed, bars=bars)
    recipe_cir = load_recipe_cir(recipe, assets)
    return generate_candidates(
        brief,
        n=n,
        base_seed=seed if seed is not None else brief.seed,
        settings=settings,
        adapter=adapter,
        profile=profile,
        baseline_project=recipe_cir,
    )
