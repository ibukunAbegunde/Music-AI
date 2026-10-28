"""Render / mix metrics contracts (fixture-friendly; no real audio required)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.models.schemas import Evaluation, new_id, utcnow


class RenderMetrics(BaseModel):
    """Measured or simulated bounce metrics.

    In simulation mode these are derived from CIR + optional fixture overlays.
    Dimensions stay separate — never collapse into a single 'quality' truth.
    """

    render_id: UUID = Field(default_factory=new_id)
    project_id: UUID | None = None
    version_id: UUID | None = None
    source: str = "simulation"  # simulation | fixture | live
    fixture_id: str | None = None
    sample_rate: int = 44100
    duration_sec: float = 0.0
    # Technical
    peak_dbfs: float = -6.0
    true_peak_dbfs: float | None = None
    measured_lufs: float = -14.0
    dynamic_range_db: float = 8.0
    clipping_ratio: float = 0.0  # fraction of frames near 0 dBFS
    silence_ratio: float = 0.0
    rms_dbfs: float = -18.0
    stereo_imbalance: float = 0.0  # 0 = centred, 1 = hard L/R skew
    excess_sub_energy: float = 0.0  # 0..1 heuristic
    # Musical (CIR-derived or annotated)
    note_density_per_bar: float = 0.0
    empty_role_count: int = 0
    kick_bass_overlap_ratio: float = 0.0
    groove_grid_error: float = 0.0  # mean |offset| in beats from 16th grid
    velocity_hot_ratio: float = 0.0  # notes with vel >= 120
    missing_end_fill: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())


class Scoreboard(BaseModel):
    """Separate technical / musical aggregates — not a universal quality score."""

    technical: float  # 0..1 higher = healthier mix
    musical: float  # 0..1 higher = more coherent CIR
    technical_fail_count: int = 0
    musical_fail_count: int = 0
    evaluations: list[Evaluation] = Field(default_factory=list)

    @property
    def any_fail(self) -> bool:
        return self.technical_fail_count > 0 or self.musical_fail_count > 0


def scoreboard_from_evaluations(evaluations: list[Evaluation]) -> Scoreboard:
    tech = [e for e in evaluations if e.metric_name.startswith("technical.")]
    musi = [e for e in evaluations if e.metric_name.startswith("musical.")]
    tech_vals = [e.value for e in tech if e.metric_name.endswith(".score")]
    musi_vals = [e.value for e in musi if e.metric_name.endswith(".score")]
    tech_fails = sum(1 for e in tech if e.metric_name.endswith(".fail") and e.value >= 0.5)
    musi_fails = sum(1 for e in musi if e.metric_name.endswith(".fail") and e.value >= 0.5)
    return Scoreboard(
        technical=sum(tech_vals) / len(tech_vals) if tech_vals else 0.5,
        musical=sum(musi_vals) / len(musi_vals) if musi_vals else 0.5,
        technical_fail_count=tech_fails,
        musical_fail_count=musi_fails,
        evaluations=evaluations,
    )


def improved(before: Scoreboard, after: Scoreboard, *, min_delta: float = 0.02) -> bool:
    """Measured improvement: fewer fails, or scores up without new fails."""
    if after.technical_fail_count + after.musical_fail_count < (
        before.technical_fail_count + before.musical_fail_count
    ):
        return True
    if after.any_fail and not before.any_fail:
        return False
    tech_up = after.technical - before.technical >= min_delta
    musi_up = after.musical - before.musical >= min_delta
    tech_down = before.technical - after.technical >= min_delta
    musi_down = before.musical - after.musical >= min_delta
    if tech_down or musi_down:
        return False
    return tech_up or musi_up
