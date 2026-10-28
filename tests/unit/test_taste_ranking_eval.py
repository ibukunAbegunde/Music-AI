"""Unit: retrieval baseline, ranking head train/eval, registry rollback."""

from __future__ import annotations

import numpy as np

from backend.app.core.config import Settings
from backend.app.taste.evaluation import evaluate_ranking, project_holdout_split
from backend.app.taste.ranking import PairwiseRankingHead, predict_preference
from backend.app.taste.registry import (
    activate_checkpoint,
    get_active_checkpoint,
    list_checkpoints,
    rollback_checkpoint,
    save_checkpoint,
)
from backend.app.taste.retrieval import RetrievalBaseline
from backend.app.taste.simulate import build_simulated_dataset
from backend.app.taste.training import train_ranking_head


def test_project_holdout_keeps_variants_together() -> None:
    # 4 projects, 2 pairs each
    pids = ["p1", "p1", "p2", "p2", "p3", "p3", "p4", "p4"]
    split = project_holdout_split(pids, holdout_fraction=0.25, seed=0)
    hold_set = set(int(i) for i in split.holdout_idx)
    # whichever project is held out, both its pair indices must be in holdout
    for proj in ("p1", "p2", "p3", "p4"):
        idxs = [i for i, p in enumerate(pids) if p == proj]
        if idxs[0] in hold_set or idxs[1] in hold_set:
            assert idxs[0] in hold_set and idxs[1] in hold_set


def test_train_ranking_beats_random_on_simulated() -> None:
    pairs = build_simulated_dataset(
        n_projects=10, pairs_per_project=6, persist=False, seed=7
    )
    emb_a = np.stack([p.emb_a for p in pairs])
    emb_b = np.stack([p.emb_b for p in pairs])
    labels = np.asarray([p.label for p in pairs])
    project_ids = [p.project_id for p in pairs]

    split = project_holdout_split(project_ids, holdout_fraction=0.25, seed=1)
    tr = train_ranking_head(
        emb_a[split.train_idx],
        emb_b[split.train_idx],
        labels[split.train_idx],
        epochs=400,
        seed=1,
    )
    assert tr.train_metrics["accuracy"] >= 0.75

    report = evaluate_ranking(
        tr.head,
        emb_a,
        emb_b,
        labels,
        project_ids,
        holdout_fraction=0.25,
        seed=1,
        retrieval=RetrievalBaseline(),
    )
    assert report.n_holdout >= 1
    # Planted axis → holdout should clearly beat coin-flip; allow tiny float ties vs sampled random
    assert report.ranking["accuracy"] >= 0.7
    assert report.ranking["accuracy"] >= report.random["accuracy"] - 1e-9
    assert report.better_than_random or report.ranking["accuracy"] >= 0.7


def test_predict_preference_contract() -> None:
    head = PairwiseRankingHead(weights=np.ones(8), bias=0.0)
    a = np.zeros(8)
    b = np.ones(8)
    out = predict_preference(head, a, b)
    assert out["predicted_choice"] == "b"
    assert out["p_b_over_a"] > 0.5


def test_registry_activate_and_rollback(tmp_settings: Settings) -> None:
    tmp_settings.ensure_workspace()
    pairs = build_simulated_dataset(
        n_projects=4, pairs_per_project=3, settings=tmp_settings, persist=True, seed=3
    )
    emb_a = np.stack([p.emb_a for p in pairs])
    emb_b = np.stack([p.emb_b for p in pairs])
    labels = np.asarray([p.label for p in pairs])
    tr = train_ranking_head(emb_a, emb_b, labels, epochs=100, seed=0)

    ckpt1 = tr.head.to_checkpoint(
        version="0.1.0",
        train_metrics=tr.train_metrics,
        holdout_metrics={"accuracy": 0.8},
        better_than_baseline=True,
    )
    save_checkpoint(ckpt1, settings=tmp_settings, activate_if_better=True)
    assert get_active_checkpoint(settings=tmp_settings).id == ckpt1.id

    ckpt2 = tr.head.to_checkpoint(
        version="0.2.0",
        train_metrics=tr.train_metrics,
        holdout_metrics={"accuracy": 0.9},
        better_than_baseline=True,
        parent_checkpoint_id=ckpt1.id,
    )
    save_checkpoint(ckpt2, settings=tmp_settings, activate_if_better=True)
    assert get_active_checkpoint(settings=tmp_settings).id == ckpt2.id
    assert len(list_checkpoints(settings=tmp_settings)) == 2

    rolled = rollback_checkpoint(settings=tmp_settings)
    assert rolled is not None
    assert rolled.id == ckpt1.id
    assert get_active_checkpoint(settings=tmp_settings).id == ckpt1.id

    # re-activate v2 explicitly
    activate_checkpoint(ckpt2.id, settings=tmp_settings)
    assert get_active_checkpoint(settings=tmp_settings).id == ckpt2.id


def test_retrieval_baseline_predicts() -> None:
    rng = np.random.default_rng(0)
    winners = [rng.normal(size=16) for _ in range(5)]
    losers = [rng.normal(size=16) - 0.5 for _ in range(5)]
    base = RetrievalBaseline().fit(winners, losers)
    choice, p = base.predict_pair(losers[0], winners[0])
    assert choice in ("a", "b")
    assert 0.0 <= p <= 1.0
