"""Train a compact pairwise logistic ranking head on frozen embeddings."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.app.taste.encoder import FrozenEncoder, SimulationFrozenEncoder
from backend.app.taste.ranking import PairwiseRankingHead, _sigmoid


@dataclass
class TrainResult:
    head: PairwiseRankingHead
    train_metrics: dict[str, float]
    n_pairs: int


def _pair_accuracy(
    head: PairwiseRankingHead,
    emb_a: np.ndarray,
    emb_b: np.ndarray,
    labels: np.ndarray,
) -> float:
    """labels: 1 if B preferred, 0 if A preferred."""
    correct = 0
    for i in range(len(labels)):
        choice, _ = head.predict_pair(emb_a[i], emb_b[i])
        pred_b = 1 if choice == "b" else 0
        if pred_b == int(labels[i]):
            correct += 1
    return correct / max(len(labels), 1)


def train_ranking_head(
    emb_a: np.ndarray,
    emb_b: np.ndarray,
    labels: np.ndarray,
    *,
    encoder: FrozenEncoder | None = None,
    lr: float = 0.05,
    epochs: int = 200,
    l2: float = 1e-3,
    seed: int = 0,
) -> TrainResult:
    """SGD on logistic loss for P(B>A)=sigmoid(sB-sA).

    ``labels``: 1.0 when user chose B, 0.0 when user chose A.
    Embeddings are assumed already produced by a frozen encoder.
    """
    encoder = encoder or SimulationFrozenEncoder()
    ea = np.asarray(emb_a, dtype=np.float64)
    eb = np.asarray(emb_b, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64).reshape(-1)
    if ea.ndim != 2 or eb.ndim != 2 or ea.shape != eb.shape:
        raise ValueError("emb_a/emb_b must be (N, D) with matching shapes")
    if len(y) != ea.shape[0]:
        raise ValueError("label count mismatch")
    if len(y) == 0:
        raise ValueError("need at least one training pair")

    dim = ea.shape[1]
    rng = np.random.default_rng(seed)
    w = rng.normal(scale=0.01, size=dim)
    b = 0.0

    for _ in range(epochs):
        # shuffle
        order = rng.permutation(len(y))
        for i in order:
            delta = float(w @ eb[i] - w @ ea[i] + 0.0)  # bias cancels in pair
            # Actually bias cancels in pairwise delta — keep single bias for scoring only
            p = float(_sigmoid(delta))
            # grad of -[y log p + (1-y) log(1-p)] w.r.t. delta = p - y
            err = p - y[i]
            # d(delta)/dw = eb - ea
            w -= lr * (err * (eb[i] - ea[i]) + l2 * w)
        # bias unused in pairwise; leave at 0

    head = PairwiseRankingHead(
        weights=w.astype(np.float64),
        bias=float(b),
        encoder_name=encoder.name,
        encoder_version=encoder.version,
    )
    # train metrics
    probs = []
    for i in range(len(y)):
        _, p_b = head.predict_pair(ea[i], eb[i])
        probs.append(p_b)
    probs_a = np.asarray(probs)
    # clip for log loss
    eps = 1e-7
    probs_c = np.clip(probs_a, eps, 1 - eps)
    logloss = float(-np.mean(y * np.log(probs_c) + (1 - y) * np.log(1 - probs_c)))
    acc = _pair_accuracy(head, ea, eb, y)
    return TrainResult(
        head=head,
        train_metrics={"accuracy": acc, "logloss": logloss, "n_pairs": float(len(y))},
        n_pairs=len(y),
    )
