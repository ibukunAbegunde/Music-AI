"""Stem separator adapter interface (spec §6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass
class StemAudio:
    stem_type: str
    samples: np.ndarray
    sample_rate: int
    confidence_flags: list[str] = field(default_factory=list)
    bleed_notes: str | None = None


@dataclass
class StemSet:
    stems: list[StemAudio]
    model: str
    version: str
    limitations: list[str] = field(default_factory=list)
    simulated: bool = True


@runtime_checkable
class StemSeparator(Protocol):
    name: str
    version: str
    simulated: bool

    def separate(
        self,
        samples: np.ndarray,
        sample_rate: int,
        *,
        target_stems: list[str] | None = None,
        output_dir: Path | None = None,
        options: dict | None = None,
    ) -> StemSet: ...
