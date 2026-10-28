"""Pairwise comparison collection + listening journal persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import numpy as np

from backend.app.core.config import Settings, get_settings
from backend.app.models.schemas import (
    ListeningJournalEntry,
    PreferenceComparison,
    TasteProfileSummary,
    new_id,
    utcnow,
)
from backend.app.storage.assets import AssetStore

Choice = Literal["a", "b", "tie", "skip"]


def _taste_dir(assets: AssetStore) -> Path:
    path = assets.root / "taste"
    path.mkdir(parents=True, exist_ok=True)
    (path / "comparisons").mkdir(parents=True, exist_ok=True)
    (path / "journal").mkdir(parents=True, exist_ok=True)
    (path / "features").mkdir(parents=True, exist_ok=True)
    return path


def append_comparison(
    comparison: PreferenceComparison,
    *,
    settings: Settings | None = None,
    feature_a: list[float] | None = None,
    feature_b: list[float] | None = None,
) -> Path:
    """Persist a PreferenceComparison into the taste dataset index."""
    settings = settings or get_settings()
    assets = AssetStore(settings)
    root = _taste_dir(assets)

    if feature_a is not None:
        fa = root / "features" / f"{comparison.id}_a.json"
        fa.write_text(json.dumps(feature_a), encoding="utf-8")
        comparison.feature_a_ref = str(fa.relative_to(assets.root))
    if feature_b is not None:
        fb = root / "features" / f"{comparison.id}_b.json"
        fb.write_text(json.dumps(feature_b), encoding="utf-8")
        comparison.feature_b_ref = str(fb.relative_to(assets.root))

    path = root / "comparisons" / f"{comparison.id}.json"
    path.write_text(json.dumps(comparison.model_dump(mode="json"), indent=2), encoding="utf-8")

    index_path = root / "comparisons" / "index.json"
    index: list[str] = []
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    cid = str(comparison.id)
    if cid not in index:
        index.append(cid)
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return path


def list_comparisons(
    *,
    settings: Settings | None = None,
    decisive_only: bool = False,
) -> list[PreferenceComparison]:
    settings = settings or get_settings()
    assets = AssetStore(settings)
    root = _taste_dir(assets)
    index_path = root / "comparisons" / "index.json"
    if index_path.exists():
        ids = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        ids = [
            p.stem
            for p in sorted((root / "comparisons").glob("*.json"))
            if p.name != "index.json"
        ]
    out: list[PreferenceComparison] = []
    for cid in ids:
        path = root / "comparisons" / f"{cid}.json"
        if not path.exists():
            continue
        comp = PreferenceComparison.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if decisive_only and comp.user_choice not in ("a", "b"):
            continue
        out.append(comp)
    return out


def load_comparison_features(
    comparison: PreferenceComparison,
    *,
    settings: Settings | None = None,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    settings = settings or get_settings()
    assets = AssetStore(settings)

    def _load(ref: str | None) -> np.ndarray | None:
        if not ref:
            return None
        path = assets.root / ref
        if not path.exists():
            return None
        return np.asarray(json.loads(path.read_text(encoding="utf-8")), dtype=np.float32)

    return _load(comparison.feature_a_ref), _load(comparison.feature_b_ref)


def record_journal_entry(
    entry: ListeningJournalEntry,
    *,
    settings: Settings | None = None,
) -> Path:
    settings = settings or get_settings()
    assets = AssetStore(settings)
    root = _taste_dir(assets)
    path = root / "journal" / f"{entry.id}.json"
    path.write_text(json.dumps(entry.model_dump(mode="json"), indent=2), encoding="utf-8")
    index_path = root / "journal" / "index.json"
    index: list[str] = []
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    eid = str(entry.id)
    if eid not in index:
        index.append(eid)
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return path


def list_journal(*, settings: Settings | None = None) -> list[ListeningJournalEntry]:
    settings = settings or get_settings()
    assets = AssetStore(settings)
    root = _taste_dir(assets)
    index_path = root / "journal" / "index.json"
    if index_path.exists():
        ids = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        ids = [
            p.stem for p in sorted((root / "journal").glob("*.json")) if p.name != "index.json"
        ]
    out: list[ListeningJournalEntry] = []
    for eid in ids:
        path = root / "journal" / f"{eid}.json"
        if path.exists():
            out.append(
                ListeningJournalEntry.model_validate(json.loads(path.read_text(encoding="utf-8")))
            )
    return out


def taste_profile_summary(*, settings: Settings | None = None) -> TasteProfileSummary:
    settings = settings or get_settings()
    comps = list_comparisons(settings=settings)
    journal = list_journal(settings=settings)
    from backend.app.taste.registry import get_active_checkpoint
    from backend.app.taste.style_vectors import list_style_vectors

    tag_counts: dict[str, int] = {}
    genre_counts: dict[str, int] = {}
    decisive = 0
    for c in comps:
        if c.user_choice in ("a", "b"):
            decisive += 1
        for t in c.tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1
        genre = (c.context or {}).get("genre") or (c.context or {}).get("genre_template_id")
        if genre:
            genre_counts[str(genre)] = genre_counts.get(str(genre), 0) + 1

    active = get_active_checkpoint(settings=settings)
    vectors = list_style_vectors(settings=settings)
    limitations = [
        "Profile reflects recorded comparisons/journal only — no invented taste.",
        "Default encoder is simulation CIR projection (not CLAP/MERT).",
    ]
    if decisive < 20:
        limitations.append("Few decisive comparisons — do not over-trust ranking head.")
    return TasteProfileSummary(
        n_comparisons=len(comps),
        n_decisive=decisive,
        n_journal_entries=len(journal),
        n_style_vectors=len(vectors),
        preferred_tags=tag_counts,
        genre_counts=genre_counts,
        active_model_id=active.id if active else None,
        active_model_version=active.version if active else None,
        prediction_confidence=None if decisive < 10 else min(0.7, decisive / 100.0),
        limitations=limitations,
    )


def record_ab_preference(
    *,
    project_id: UUID,
    version_a_id: UUID,
    version_b_id: UUID,
    render_a_id: UUID,
    render_b_id: UUID,
    choice: Choice,
    reason: str | None = None,
    tags: list[str] | None = None,
    context: dict[str, Any] | None = None,
    feature_a: list[float] | None = None,
    feature_b: list[float] | None = None,
    settings: Settings | None = None,
    blind: bool = True,
) -> PreferenceComparison:
    """Create + persist a PreferenceComparison (Phase 5 collection entrypoint)."""
    comp = PreferenceComparison(
        id=new_id(),
        context=context or {},
        render_a_id=render_a_id,
        render_b_id=render_b_id,
        user_choice=choice,
        optional_reason=reason,
        tags=list(tags or []),
        timestamp=utcnow(),
        blind_status=blind,
        project_id=project_id,
        version_a_id=version_a_id,
        version_b_id=version_b_id,
    )
    append_comparison(comp, settings=settings, feature_a=feature_a, feature_b=feature_b)
    return comp
