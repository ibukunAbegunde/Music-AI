"""Style vectors from approved projects/recipes (Phase 5 / product-upgrades §10).

Only derived when approved data exists. Hold out by project — do not train
generative models on tiny sets; these vectors are for retrieval/conditioning.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from backend.app.core.config import Settings, get_settings
from backend.app.models.schemas import MusicProject, Recipe, StyleVector
from backend.app.music.recipes import list_recipes, load_recipe_cir
from backend.app.storage.assets import AssetStore
from backend.app.taste.encoder import FrozenEncoder, get_frozen_encoder


def _vectors_dir(assets: AssetStore) -> Path:
    path = assets.root / "taste" / "style_vectors"
    path.mkdir(parents=True, exist_ok=True)
    return path


def derive_style_vector(
    *,
    source_kind: str,
    source_id: UUID,
    project: MusicProject,
    encoder: FrozenEncoder,
    genre_tags: list[str] | None = None,
    approved_only: bool = True,
) -> StyleVector:
    emb = encoder.encode_project(project)
    return StyleVector(
        source_kind=source_kind,
        source_id=source_id,
        project_id=project.id,
        genre_tags=list(genre_tags or []),
        dim=int(emb.shape[0]),
        values=[float(x) for x in emb.tolist()],
        encoder_name=encoder.name,
        encoder_version=encoder.version,
        approved_only=approved_only,
    )


def save_style_vector(vector: StyleVector, *, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    assets = AssetStore(settings)
    root = _vectors_dir(assets)
    path = root / f"{vector.id}.json"
    path.write_text(json.dumps(vector.model_dump(mode="json"), indent=2), encoding="utf-8")
    index_path = root / "index.json"
    index: list[str] = []
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    vid = str(vector.id)
    if vid not in index:
        index.append(vid)
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return path


def list_style_vectors(*, settings: Settings | None = None) -> list[StyleVector]:
    settings = settings or get_settings()
    assets = AssetStore(settings)
    root = _vectors_dir(assets)
    index_path = root / "index.json"
    if index_path.exists():
        ids = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        ids = [p.stem for p in sorted(root.glob("*.json")) if p.name != "index.json"]
    out: list[StyleVector] = []
    for vid in ids:
        path = root / f"{vid}.json"
        if path.exists():
            out.append(StyleVector.model_validate(json.loads(path.read_text(encoding="utf-8"))))
    return out


def derive_style_vectors(
    *,
    settings: Settings | None = None,
    approved_only: bool = True,
    min_approved: int = 1,
) -> list[StyleVector]:
    """Derive + persist style vectors from approved recipes with recoverable CIR.

    Returns empty list (and does not invent vectors) when insufficient approved data.
    """
    settings = settings or get_settings()
    assets = AssetStore(settings)
    encoder = get_frozen_encoder(settings)
    recipes = list_recipes(assets)
    if approved_only:
        recipes = [r for r in recipes if r.approved]
    if len(recipes) < min_approved:
        return []

    derived: list[StyleVector] = []
    for recipe in recipes:
        cir = load_recipe_cir(recipe, assets)
        if cir is None:
            continue
        vec = derive_style_vector(
            source_kind="recipe",
            source_id=recipe.id,
            project=cir,
            encoder=encoder,
            genre_tags=list(recipe.genre_tags),
            approved_only=approved_only,
        )
        save_style_vector(vec, settings=settings)
        derived.append(vec)
    return derived


def nearest_style(
    query: MusicProject,
    *,
    settings: Settings | None = None,
    top_k: int = 3,
) -> list[tuple[StyleVector, float]]:
    """Cosine nearest approved style vectors for conditioning/retrieval."""
    import numpy as np

    settings = settings or get_settings()
    encoder = get_frozen_encoder(settings)
    q = encoder.encode_project(query)
    qn = q / (np.linalg.norm(q) + 1e-9)
    scored: list[tuple[StyleVector, float]] = []
    for v in list_style_vectors(settings=settings):
        e = np.asarray(v.values, dtype=np.float32)
        en = e / (np.linalg.norm(e) + 1e-9)
        scored.append((v, float(qn @ en)))
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:top_k]
