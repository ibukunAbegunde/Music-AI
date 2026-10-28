"""Held-out pairwise evaluation — split by project/song, never by near-dupe variants."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import numpy as np

from backend.app.taste.ranking import PairwiseRankingHead, _sigmoid
from backend.app.taste.retrieval import RetrievalBaseline


@dataclass
class EvalSplit:
    train_idx: np.ndarray
    holdout_idx: np.ndarray
    holdout_project_ids: list[str]


@dataclass
class EvalReport:
    ranking: dict[str, float]
    retrieval: dict[str, float]
    random: dict[str, float]
    better_than_retrieval: bool
    better_than_random: bool
    n_holdout: int
    n_train: int
    holdout_projects: list[str]
    calibration_bins: list[dict[str, float]]
    notes: list[str]


def project_holdout_split(
    project_ids: list[UUID | str | None],
    *,
    holdout_fraction: float = 0.25,
    seed: int = 0,
    min_holdout_projects: int = 1,
) -> EvalSplit:
    """Hold out entire projects so variants of the same song stay together."""
    keyed: dict[str, list[int]] = {}
    for i, pid in enumerate(project_ids):
        key = str(pid) if pid is not None else f"__none_{i}"
        keyed.setdefault(key, []).append(i)
    projects = sorted(keyed.keys())
    rng = np.random.default_rng(seed)
    rng.shuffle(projects)
    n_hold = max(min_holdout_projects, int(round(len(projects) * holdout_fraction)))
    n_hold = min(n_hold, max(1, len(projects) - 1)) if len(projects) > 1 else 0
    hold_projects = set(projects[:n_hold]) if n_hold else set()
    train_idx: list[int] = []
    hold_idx: list[int] = []
    for p, idxs in keyed.items():
        if p in hold_projects:
            hold_idx.extend(idxs)
        else:
            train_idx.extend(idxs)
    if not hold_idx and train_idx:
        # single-project fallback: hold out last 25% of pairs (documented limitation)
        cut = max(1, len(train_idx) // 4)
        hold_idx = train_idx[-cut:]
        train_idx = train_idx[:-cut]
        hold_projects = {"__pair_fraction_fallback__"}
    return EvalSplit(
        train_idx=np.asarray(train_idx, dtype=int),
        holdout_idx=np.asarray(hold_idx, dtype=int),
        holdout_project_ids=sorted(hold_projects),
    )


def _metrics(
    preds_b: np.ndarray,
    labels: np.ndarray,
) -> dict[str, float]:
    """preds_b = P(B>A); labels 1 if B won."""
    eps = 1e-7
    p = np.clip(np.asarray(preds_b, dtype=np.float64), eps, 1 - eps)
    y = np.asarray(labels, dtype=np.float64)
    pred_choice = (p >= 0.5).astype(np.float64)
    acc = float(np.mean(pred_choice == y)) if len(y) else 0.0
    logloss = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))) if len(y) else 0.0
    # Brier
    brier = float(np.mean((p - y) ** 2)) if len(y) else 0.0
    return {"accuracy": acc, "logloss": logloss, "brier": brier, "n": float(len(y))}


def _calibration_bins(
    preds_b: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 5,
) -> list[dict[str, float]]:
    p = np.asarray(preds_b, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    if len(p) == 0:
        return []
    edges = np.linspace(0, 1, n_bins + 1)
    bins: list[dict[str, float]] = []
    for i in range(n_bins):
        mask = (p >= edges[i]) & (p < edges[i + 1] if i < n_bins - 1 else p <= edges[i + 1])
        if not np.any(mask):
            continue
        bins.append(
            {
                "bin_lo": float(edges[i]),
                "bin_hi": float(edges[i + 1]),
                "mean_pred": float(np.mean(p[mask])),
                "mean_label": float(np.mean(y[mask])),
                "n": float(np.sum(mask)),
            }
        )
    return bins


def evaluate_ranking(
    head: PairwiseRankingHead,
    emb_a: np.ndarray,
    emb_b: np.ndarray,
    labels: np.ndarray,
    project_ids: list[UUID | str | None],
    *,
    holdout_fraction: float = 0.25,
    seed: int = 0,
    retrieval: RetrievalBaseline | None = None,
) -> EvalReport:
    """Compare ranking head vs retrieval baseline vs random on project-held-out pairs."""
    split = project_holdout_split(project_ids, holdout_fraction=holdout_fraction, seed=seed)
    ea = np.asarray(emb_a, dtype=np.float64)
    eb = np.asarray(emb_b, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)

    # Fit retrieval on train winners only
    if retrieval is None:
        retrieval = RetrievalBaseline()
    winners = []
    losers = []
    for i in split.train_idx:
        if y[i] >= 0.5:
            winners.append(eb[i])
            losers.append(ea[i])
        else:
            winners.append(ea[i])
            losers.append(eb[i])
    retrieval.fit(winners, losers)

    def _rank_preds(idxs: np.ndarray) -> np.ndarray:
        out = []
        for i in idxs:
            _, p_b = head.predict_pair(ea[i], eb[i])
            out.append(p_b)
        return np.asarray(out, dtype=np.float64)

    def _ret_preds(idxs: np.ndarray) -> np.ndarray:
        out = []
        for i in idxs:
            _, p_b = retrieval.predict_pair(ea[i], eb[i])
            out.append(p_b)
        return np.asarray(out, dtype=np.float64)

    hold = split.holdout_idx
    rank_m = _metrics(_rank_preds(hold), y[hold])
    ret_m = _metrics(_ret_preds(hold), y[hold])
    rng = np.random.default_rng(seed + 7)
    random_preds = rng.random(len(hold))
    rand_m = _metrics(random_preds, y[hold])

    notes = [
        "Holdout is by project_id (variants of one song stay together).",
        "Deploy ranking head only if better_than_retrieval on holdout.",
        "Accuracy targets are exploratory — do not claim >70% without evidence.",
    ]
    if "__pair_fraction_fallback__" in split.holdout_project_ids:
        notes.append(
            "Only one project in dataset — fell back to pair-fraction holdout "
            "(weaker than project holdout)."
        )

    return EvalReport(
        ranking=rank_m,
        retrieval=ret_m,
        random=rand_m,
        better_than_retrieval=rank_m["accuracy"] > ret_m["accuracy"]
        or (
            abs(rank_m["accuracy"] - ret_m["accuracy"]) < 1e-9
            and rank_m["logloss"] < ret_m["logloss"]
        ),
        better_than_random=rank_m["accuracy"] > rand_m["accuracy"],
        n_holdout=int(len(hold)),
        n_train=int(len(split.train_idx)),
        holdout_projects=list(split.holdout_project_ids),
        calibration_bins=_calibration_bins(_rank_preds(hold), y[hold]),
        notes=notes,
    )


def score_candidates(
    head: PairwiseRankingHead,
    embeddings: list[np.ndarray],
) -> list[float]:
    """Score a list of candidate embeddings (higher = preferred)."""
    return [head.score(e) for e in embeddings]
