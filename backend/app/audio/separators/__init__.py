"""Stem separation adapters."""

from __future__ import annotations

from backend.app.audio.separators.base import StemSeparator, StemSet
from backend.app.audio.separators.simulation import SimulationStemSeparator


def get_separator(name: str | None = None) -> StemSeparator:
    """Factory: default ``simulation``. Optional ``demucs`` if installed + approved."""
    key = (name or "simulation").lower().strip()
    if key in ("simulation", "fake", "stub", "sim"):
        return SimulationStemSeparator()
    if key == "demucs":
        from backend.app.audio.separators.demucs_adapter import DemucsStemSeparator

        return DemucsStemSeparator()
    raise ValueError(f"unknown separator {name!r}; use 'simulation' or 'demucs'")


__all__ = ["SimulationStemSeparator", "StemSeparator", "StemSet", "get_separator"]
