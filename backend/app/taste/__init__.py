"""Personal taste / preference ranking (Phase 5).

Simulation-first: frozen encoder is a deterministic CIR feature projection
(no CLAP/MERT download). Optional real encoders refuse unless explicitly enabled.
"""

from backend.app.taste.dataset import (
    append_comparison,
    list_comparisons,
    list_journal,
    record_journal_entry,
    taste_profile_summary,
)
from backend.app.taste.encoder import get_frozen_encoder
from backend.app.taste.evaluation import evaluate_ranking
from backend.app.taste.ranking import PairwiseRankingHead, predict_preference
from backend.app.taste.registry import (
    activate_checkpoint,
    get_active_checkpoint,
    list_checkpoints,
    rollback_checkpoint,
    save_checkpoint,
)
from backend.app.taste.retrieval import RetrievalBaseline
from backend.app.taste.style_vectors import derive_style_vectors, list_style_vectors
from backend.app.taste.training import train_ranking_head

__all__ = [
    "PairwiseRankingHead",
    "RetrievalBaseline",
    "activate_checkpoint",
    "append_comparison",
    "derive_style_vectors",
    "evaluate_ranking",
    "get_active_checkpoint",
    "get_frozen_encoder",
    "list_checkpoints",
    "list_comparisons",
    "list_journal",
    "list_style_vectors",
    "predict_preference",
    "record_journal_entry",
    "rollback_checkpoint",
    "save_checkpoint",
    "taste_profile_summary",
    "train_ranking_head",
]
