"""Transcription adapter interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from backend.app.models.schemas import NoteEvent


@dataclass
class TranscriptionResult:
    notes: list[NoteEvent]
    model: str
    version: str
    simulated: bool
    limitations: list[str] = field(default_factory=list)
    midi_path: Path | None = None
    confidence_mean: float | None = None


@runtime_checkable
class Transcriber(Protocol):
    name: str
    version: str
    simulated: bool

    def transcribe(
        self,
        samples: np.ndarray,
        sample_rate: int,
        *,
        bpm: float | None = None,
        output_midi: Path | None = None,
        options: dict | None = None,
    ) -> TranscriptionResult: ...
