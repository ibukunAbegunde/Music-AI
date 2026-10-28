"""Retrieval-based preference baseline (nearest-neighbour / similarity heuristic).

v0 taste: transparent preference via similarity to previously preferred examples.
No trained weights — used as the deploy gate baseline for the ranking head.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class RetrievalBaseline:
    """Score candidates by cosine similarity to preferred embeddings."""

    preferred: list[np.ndarray] = field(default_factory=list)
    rejected: list[np.ndarray] = field(default_factory=list)
    name: str = "retrieval_nn"
    version: str = "0.1.0"

    def fit(
        self,
        winner_embs: list[np.ndarray],
        loser_embs: list[np.ndarray] | None = None,
    ) -> RetrievalBaseline:
        self.preferred = [np.asarray(e, dtype=np.float64) for e in winner_embs]
        self.rejected = [np.asarray(e, dtype=np.float64) for e in (loser_embs or [])]
        return self

    def score(self, emb: np.ndarray) -> float:
        """Higher = closer to preferred, farther from rejected."""
        e = np.asarray(emb, dtype=np.float64)
        e = e / (np.linalg.norm(e) + 1e-9)
        if not self.preferred:
            return 0.0
        pref = np.stack([p / (np.linalg.norm(p) + 1e-9) for p in self.preferred])
        sim_pref = float(np.mean(pref @ e))
        sim_rej = 0.0
        if self.rejected:
            rej = np.stack([p / (np.linalg.norm(p) + 1e-9) for p in self.rejected])
            sim_rej = float(np.mean(rej @ e))
        return sim_pref - 0.5 * sim_rej

    def predict_pair(self, emb_a: np.ndarray, emb_b: np.ndarray) -> tuple[str, float]:
        """Return ('a'|'b', P(B>A)-style probability centered on sigmoid of score delta)."""
        sa = self.score(emb_a)
        sb = self.score(emb_b)
        delta = sb - sa
        p_b = float(1.0 / (1.0 + np.exp(-delta * 4.0)))
        choice = "b" if sb >= sa else "a"
        return choice, p_b
