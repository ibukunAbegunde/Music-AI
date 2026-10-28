"""Frozen-encoder pairwise ranking head.

P(B > A) = sigmoid(s(B) - s(A)) where s(x) = w·embed(x) + b.
Head is compact (embed_dim params); encoder stays frozen.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.app.models.schemas import TasteModelCheckpoint


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    x = np.asarray(x, dtype=np.float64)
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


@dataclass
class PairwiseRankingHead:
    weights: np.ndarray
    bias: float = 0.0
    encoder_name: str = "simulation_cir_projection"
    encoder_version: str = "0.1.0"
    version: str = "0.1.0"
    name: str = "pairwise_logistic"

    @property
    def feature_dim(self) -> int:
        return int(self.weights.shape[0])

    def score(self, emb: np.ndarray) -> float:
        e = np.asarray(emb, dtype=np.float64).reshape(-1)
        if e.shape[0] != self.feature_dim:
            raise ValueError(f"emb dim {e.shape[0]} != head dim {self.feature_dim}")
        return float(self.weights @ e + self.bias)

    def predict_pair(self, emb_a: np.ndarray, emb_b: np.ndarray) -> tuple[str, float]:
        """Return (predicted_winner 'a'|'b', P(B>A))."""
        delta = self.score(emb_b) - self.score(emb_a)
        p_b = float(_sigmoid(delta))
        choice = "b" if p_b >= 0.5 else "a"
        return choice, p_b

    def to_checkpoint(
        self,
        *,
        version: str,
        train_metrics: dict | None = None,
        holdout_metrics: dict | None = None,
        baseline_metrics: dict | None = None,
        better_than_baseline: bool = False,
        notes: str | None = None,
        parent_checkpoint_id=None,
        active: bool = False,
    ) -> TasteModelCheckpoint:
        return TasteModelCheckpoint(
            name=self.name,
            version=version,
            encoder_name=self.encoder_name,
            encoder_version=self.encoder_version,
            head_kind="pairwise_logistic",
            feature_dim=self.feature_dim,
            weights=[float(w) for w in self.weights.tolist()],
            bias=float(self.bias),
            train_metrics=train_metrics or {},
            holdout_metrics=holdout_metrics or {},
            baseline_metrics=baseline_metrics or {},
            better_than_baseline=better_than_baseline,
            active=active,
            notes=notes,
            parent_checkpoint_id=parent_checkpoint_id,
        )

    @classmethod
    def from_checkpoint(cls, ckpt: TasteModelCheckpoint) -> PairwiseRankingHead:
        return cls(
            weights=np.asarray(ckpt.weights, dtype=np.float64),
            bias=float(ckpt.bias),
            encoder_name=ckpt.encoder_name,
            encoder_version=ckpt.encoder_version,
            version=ckpt.version,
            name=ckpt.name,
        )


def predict_preference(
    head: PairwiseRankingHead,
    emb_a: np.ndarray,
    emb_b: np.ndarray,
) -> dict[str, float | str]:
    choice, p_b = head.predict_pair(emb_a, emb_b)
    return {
        "predicted_choice": choice,
        "p_b_over_a": p_b,
        "score_a": head.score(emb_a),
        "score_b": head.score(emb_b),
    }
