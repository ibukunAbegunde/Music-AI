"""Action-effect / revision-outcome scaffolding (Phase 7).

Logs PatchOp outcomes from the revision loop so a future action-effect model
can train on (state, action) → measured delta. Default predictor is a
transparent heuristic over logged outcomes — not a trained model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.core.config import Settings, get_settings
from backend.app.models.schemas import DawOperation, new_id, utcnow
from backend.app.storage.assets import AssetStore


class RevisionOutcome(BaseModel):
    """One measured revision iteration — training row for a future action-effect model."""

    id: UUID = Field(default_factory=new_id)
    project_id: UUID
    version_id: UUID | None = None
    iteration_index: int = 0
    ops: list[DawOperation] = Field(default_factory=list)
    before_technical: float
    before_musical: float
    after_technical: float | None = None
    after_musical: float | None = None
    accepted: bool = False
    rolled_back: bool = False
    reason: str = ""
    delta_technical: float | None = None
    delta_musical: float | None = None
    fixture_id: str | None = None
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())
    schema_version: str = "0.7.0"


class ActionEffectPrediction(BaseModel):
    """Predicted scoreboard deltas for a candidate PatchOp list."""

    predicted_delta_technical: float
    predicted_delta_musical: float
    confidence: float
    predictor_name: str
    predictor_version: str
    explanation: str
    evidence_n: int = 0
    cir_is_system_of_record: bool = True


def _outcomes_dir(assets: AssetStore) -> Path:
    path = assets.root / "research" / "action_effect" / "outcomes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_revision_outcome(
    outcome: RevisionOutcome,
    *,
    settings: Settings | None = None,
) -> Path:
    """Persist a revision outcome for later action-effect training."""
    settings = settings or get_settings()
    assets = AssetStore(settings)
    root = _outcomes_dir(assets)
    if outcome.after_technical is not None:
        outcome.delta_technical = outcome.after_technical - outcome.before_technical
    if outcome.after_musical is not None:
        outcome.delta_musical = outcome.after_musical - outcome.before_musical
    path = root / f"{outcome.id}.json"
    path.write_text(json.dumps(outcome.model_dump(mode="json"), indent=2), encoding="utf-8")
    index_path = root / "index.json"
    index: list[str] = []
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    oid = str(outcome.id)
    if oid not in index:
        index.append(oid)
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return path


def list_revision_outcomes(
    *,
    settings: Settings | None = None,
    project_id: UUID | None = None,
    accepted_only: bool = False,
) -> list[RevisionOutcome]:
    settings = settings or get_settings()
    assets = AssetStore(settings)
    root = _outcomes_dir(assets)
    index_path = root / "index.json"
    if not index_path.exists():
        return []
    ids = json.loads(index_path.read_text(encoding="utf-8"))
    out: list[RevisionOutcome] = []
    for oid in ids:
        path = root / f"{oid}.json"
        if not path.exists():
            continue
        row = RevisionOutcome.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if project_id is not None and row.project_id != project_id:
            continue
        if accepted_only and not row.accepted:
            continue
        out.append(row)
    return out


def outcomes_from_revision_iterations(
    *,
    project_id: UUID,
    version_id: UUID | None,
    iterations: list[Any],
    fixture_id: str | None = None,
) -> list[RevisionOutcome]:
    """Convert RevisionIteration dataclasses into RevisionOutcome rows."""
    rows: list[RevisionOutcome] = []
    for it in iterations:
        before = it.before
        after = it.after
        rows.append(
            RevisionOutcome(
                project_id=project_id,
                version_id=version_id,
                iteration_index=it.index,
                ops=list(it.ops),
                before_technical=float(before.technical),
                before_musical=float(before.musical),
                after_technical=float(after.technical) if after is not None else None,
                after_musical=float(after.musical) if after is not None else None,
                accepted=bool(it.accepted),
                rolled_back=bool(it.rolled_back),
                reason=str(it.reason or ""),
                fixture_id=fixture_id,
            )
        )
    return rows


class ActionEffectPredictor(Protocol):
    name: str
    version: str

    def predict(
        self,
        ops: list[DawOperation],
        *,
        before_technical: float,
        before_musical: float,
    ) -> ActionEffectPrediction: ...


class HeuristicActionEffectPredictor:
    """Mean historical delta by action_type — transparent stub, not a trained model."""

    name = "heuristic_action_effect"
    version = "0.7.0"

    def __init__(self, outcomes: list[RevisionOutcome] | None = None) -> None:
        self._outcomes = outcomes or []

    def predict(
        self,
        ops: list[DawOperation],
        *,
        before_technical: float,
        before_musical: float,
    ) -> ActionEffectPrediction:
        del before_technical, before_musical  # reserved for future conditioned models
        if not ops:
            return ActionEffectPrediction(
                predicted_delta_technical=0.0,
                predicted_delta_musical=0.0,
                confidence=0.0,
                predictor_name=self.name,
                predictor_version=self.version,
                explanation="No ops — zero delta.",
                evidence_n=0,
            )
        action_types = {o.action_type for o in ops}
        matched = [
            o
            for o in self._outcomes
            if o.accepted
            and o.delta_technical is not None
            and o.delta_musical is not None
            and any(op.action_type in action_types for op in o.ops)
        ]
        if not matched:
            # Mild optimistic prior for soften/nudge family; zero otherwise.
            soft = any(
                a.startswith(("soften", "nudge")) or a == "add_fill" for a in action_types
            )
            dt = 0.03 if soft else 0.0
            dm = 0.02 if soft else 0.0
            return ActionEffectPrediction(
                predicted_delta_technical=dt,
                predicted_delta_musical=dm,
                confidence=0.15,
                predictor_name=self.name,
                predictor_version=self.version,
                explanation=(
                    "No matching logged outcomes; weak prior from action_type family. "
                    "Not a trained action-effect model."
                ),
                evidence_n=0,
            )
        dt = sum(o.delta_technical or 0.0 for o in matched) / len(matched)
        dm = sum(o.delta_musical or 0.0 for o in matched) / len(matched)
        conf = min(0.85, 0.25 + 0.1 * len(matched))
        return ActionEffectPrediction(
            predicted_delta_technical=float(dt),
            predicted_delta_musical=float(dm),
            confidence=float(conf),
            predictor_name=self.name,
            predictor_version=self.version,
            explanation=(
                f"Mean delta over {len(matched)} accepted outcomes matching "
                f"action_types={sorted(action_types)}. Honest heuristic — not trained."
            ),
            evidence_n=len(matched),
        )


def predict_effect(
    ops: list[DawOperation],
    *,
    before_technical: float = 0.5,
    before_musical: float = 0.5,
    settings: Settings | None = None,
) -> ActionEffectPrediction:
    outcomes = list_revision_outcomes(settings=settings)
    return HeuristicActionEffectPredictor(outcomes).predict(
        ops,
        before_technical=before_technical,
        before_musical=before_musical,
    )
