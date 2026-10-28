"""Frozen encoder interface + simulation projection (no large downloads).

Real pretrained audio encoders (CLAP/MERT/…) must be opt-in via
``MUSIC_AI_ALLOW_ENCODER_DOWNLOAD=true`` and an installed optional extra.
Until then we project CIR features through a fixed seeded matrix — this is
an honest stub that preserves the ranking-head training interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from backend.app.core.config import Settings, get_settings
from backend.app.models.schemas import MusicProject
from backend.app.taste.features import FEATURE_DIM, extract_cir_features

DEFAULT_EMBED_DIM = 64
SIM_ENCODER_NAME = "simulation_cir_projection"
SIM_ENCODER_VERSION = "0.1.0"


class FrozenEncoder(Protocol):
    name: str
    version: str
    embed_dim: int

    def encode_project(self, project: MusicProject) -> np.ndarray:
        """Return L2-normalized embedding for a CIR project."""
        ...

    def encode_features(self, features: np.ndarray) -> np.ndarray:
        """Project a FEATURE_DIM vector (or already-encoded vector) to embed_dim."""
        ...


@dataclass
class SimulationFrozenEncoder:
    """Deterministic frozen projection of CIR features — no weights downloaded."""

    name: str = SIM_ENCODER_NAME
    version: str = SIM_ENCODER_VERSION
    embed_dim: int = DEFAULT_EMBED_DIM
    seed: int = 20261028

    def __post_init__(self) -> None:
        rng = np.random.default_rng(self.seed)
        # Fixed Gaussian projection FEATURE_DIM → embed_dim (frozen; no training).
        # Scaled so typical unit-ish features yield stable norms before L2.
        self._proj = (
            rng.normal(size=(FEATURE_DIM, self.embed_dim)) / np.sqrt(FEATURE_DIM)
        ).astype(np.float64)

    def encode_features(self, features: np.ndarray) -> np.ndarray:
        x = np.asarray(features, dtype=np.float64).reshape(-1)
        if x.shape[0] != FEATURE_DIM:
            raise ValueError(f"expected {FEATURE_DIM}-d features, got {x.shape[0]}")
        emb = x @ self._proj
        norm = np.linalg.norm(emb) + 1e-9
        return (emb / norm).astype(np.float32)

    def encode_project(self, project: MusicProject) -> np.ndarray:
        return self.encode_features(extract_cir_features(project))


class OptionalAudioEncoderStub:
    """Honest refusal for heavy pretrained encoders until explicitly enabled."""

    name = "optional_audio_encoder"
    version = "stub-0"
    embed_dim = DEFAULT_EMBED_DIM

    def encode_project(self, project: MusicProject) -> np.ndarray:
        raise RuntimeError(
            "Optional audio encoder (CLAP/MERT) is not installed. "
            "Default taste path uses SimulationFrozenEncoder. "
            "Set MUSIC_AI_ALLOW_ENCODER_DOWNLOAD=true and install optional "
            "weights only after explicit approval — see docs/audio-models.md."
        )

    def encode_features(self, features: np.ndarray) -> np.ndarray:
        raise RuntimeError(
            "Optional audio encoder refused — use SimulationFrozenEncoder "
            "or enable MUSIC_AI_ALLOW_ENCODER_DOWNLOAD after approval."
        )


def get_frozen_encoder(
    settings: Settings | None = None,
    *,
    prefer_optional: bool = False,
) -> FrozenEncoder:
    """Return the frozen encoder for taste ranking.

    Default: SimulationFrozenEncoder (always available, no download).
    If prefer_optional and allow flag is set but no model installed → clear error.
    """
    settings = settings or get_settings()
    allow = bool(
        getattr(settings, "music_ai_allow_encoder_download", False)
        or getattr(settings, "allow_encoder_download", False)
    )
    if prefer_optional or getattr(settings, "taste_encoder", "simulation") == "optional":
        if not allow:
            raise RuntimeError(
                "taste_encoder=optional requires MUSIC_AI_ALLOW_ENCODER_DOWNLOAD=true "
                "(no large model downloads without explicit approval)."
            )
        # Future: load real encoder here. For Phase 5 we still refuse honestly.
        raise RuntimeError(
            "Optional pretrained audio encoder is approved via flag but not "
            "bundled in this build. Use simulation encoder or install a "
            "compatible adapter when available."
        )
    return SimulationFrozenEncoder()
