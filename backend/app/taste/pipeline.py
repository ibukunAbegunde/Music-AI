"""Phase 5 orchestration: collect → encode → train → eval → registry gate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import numpy as np

from backend.app.core.config import Settings, get_settings
from backend.app.models.schemas import TasteModelCheckpoint
from backend.app.storage.assets import AssetStore
from backend.app.taste.dataset import list_comparisons, load_comparison_features
from backend.app.taste.encoder import FrozenEncoder, get_frozen_encoder
from backend.app.taste.evaluation import EvalReport, evaluate_ranking, project_holdout_split
from backend.app.taste.ranking import PairwiseRankingHead
from backend.app.taste.registry import get_active_checkpoint, save_checkpoint
from backend.app.taste.retrieval import RetrievalBaseline
from backend.app.taste.training import train_ranking_head


@dataclass
class TasteTrainEvalResult:
    checkpoint: TasteModelCheckpoint
    checkpoint_path: Path
    eval_report: EvalReport
    activated: bool
    n_decisive: int
    encoder_name: str
    notes: list[str]


def _load_pair_matrices(
    settings: Settings,
    encoder: FrozenEncoder,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[UUID | None]]:
    comps = list_comparisons(settings=settings, decisive_only=True)
    emb_a_list: list[np.ndarray] = []
    emb_b_list: list[np.ndarray] = []
    labels: list[float] = []
    project_ids: list[UUID | None] = []

    for c in comps:
        fa, fb = load_comparison_features(c, settings=settings)
        if fa is None or fb is None:
            # Skip pairs without stored features (cannot recover CIR here)
            continue
        emb_a_list.append(encoder.encode_features(fa))
        emb_b_list.append(encoder.encode_features(fb))
        labels.append(1.0 if c.user_choice == "b" else 0.0)
        project_ids.append(c.project_id)

    if not emb_a_list:
        raise ValueError(
            "No decisive pairwise examples with stored features. "
            "Record A/B choices (music-ai ab … --choice) or run music-ai taste-simulate."
        )
    return (
        np.stack(emb_a_list),
        np.stack(emb_b_list),
        np.asarray(labels, dtype=np.float64),
        project_ids,
    )


def train_and_evaluate(
    *,
    settings: Settings | None = None,
    version: str = "0.1.0",
    holdout_fraction: float = 0.25,
    seed: int = 0,
    epochs: int = 250,
    activate_if_better: bool = True,
) -> TasteTrainEvalResult:
    """Train ranking head, evaluate vs retrieval/random, register; activate only if better."""
    settings = settings or get_settings()
    encoder = get_frozen_encoder(settings)
    emb_a, emb_b, labels, project_ids = _load_pair_matrices(settings, encoder)

    split = project_holdout_split(project_ids, holdout_fraction=holdout_fraction, seed=seed)
    train_a, train_b, train_y = emb_a[split.train_idx], emb_b[split.train_idx], labels[split.train_idx]
    if len(train_y) < 2:
        raise ValueError("Need ≥2 train pairs after project holdout split")

    result = train_ranking_head(
        train_a,
        train_b,
        train_y,
        encoder=encoder,
        epochs=epochs,
        seed=seed,
    )
    report = evaluate_ranking(
        result.head,
        emb_a,
        emb_b,
        labels,
        project_ids,
        holdout_fraction=holdout_fraction,
        seed=seed,
        retrieval=RetrievalBaseline(),
    )

    parent = get_active_checkpoint(settings=settings)
    notes = list(report.notes)
    if not report.better_than_retrieval:
        notes.append(
            "NOT activated: holdout ranking did not beat retrieval baseline "
            "(honest deploy gate)."
        )
    else:
        notes.append("Holdout beat retrieval — eligible for activation.")

    ckpt = result.head.to_checkpoint(
        version=version,
        train_metrics=result.train_metrics,
        holdout_metrics=report.ranking,
        baseline_metrics={"retrieval": report.retrieval, "random": report.random},
        better_than_baseline=report.better_than_retrieval,
        notes="; ".join(notes),
        parent_checkpoint_id=parent.id if parent else None,
        active=False,
    )
    should_activate = bool(activate_if_better and report.better_than_retrieval)
    path = save_checkpoint(ckpt, settings=settings, activate_if_better=should_activate)

    # Persist eval report alongside
    assets = AssetStore(settings)
    assets.write_json(
        f"models/taste/eval_{ckpt.id}.json",
        {
            "checkpoint_id": str(ckpt.id),
            "ranking": report.ranking,
            "retrieval": report.retrieval,
            "random": report.random,
            "better_than_retrieval": report.better_than_retrieval,
            "better_than_random": report.better_than_random,
            "n_holdout": report.n_holdout,
            "n_train": report.n_train,
            "holdout_projects": report.holdout_projects,
            "calibration_bins": report.calibration_bins,
            "notes": report.notes,
        },
    )

    return TasteTrainEvalResult(
        checkpoint=ckpt if not should_activate else (get_active_checkpoint(settings=settings) or ckpt),
        checkpoint_path=path,
        eval_report=report,
        activated=should_activate,
        n_decisive=int(len(labels)),
        encoder_name=encoder.name,
        notes=notes,
    )


def rank_embeddings(
    embeddings: list[np.ndarray],
    *,
    settings: Settings | None = None,
    head: PairwiseRankingHead | None = None,
) -> list[float]:
    settings = settings or get_settings()
    if head is None:
        ckpt = get_active_checkpoint(settings=settings)
        if ckpt is None:
            raise RuntimeError("No active taste model — train + activate first")
        head = PairwiseRankingHead.from_checkpoint(ckpt)
    return [head.score(e) for e in embeddings]
