"""Critic stub — emits typed PatchOps only (Phase 1 scaffold; Phase 4 fills heuristics)."""

from __future__ import annotations

from uuid import uuid4

from backend.app.models.schemas import DawOperation, MusicProject, MusicalDiff


def propose_next_moves(
    project: MusicProject,
    *,
    diff: MusicalDiff | None = None,
    max_moves: int = 3,
) -> list[DawOperation]:
    """Return up to max_moves typed patch ops (heuristic stubs)."""
    ops: list[DawOperation] = []
    unlocked = [t for t in project.tracks if not t.locked]
    if any(t.role.value == "drums" and not t.locked for t in project.tracks):
        ops.append(
            DawOperation(
                action_type="humanize_role",
                target_role="drums",
                parameters={"timing_amount": 0.015, "velocity_jitter": 5},
                idempotency_key=f"humanize-drums-{uuid4().hex[:8]}",
                predicted_impact="Slightly looser drum feel",
                explanation="Humanize unlocked drums",
                risk_level="low",
                requires_approval=project.autonomy_policy.scratch_or_release == "release",
            )
        )
    if any(t.role.value == "bass" and not t.locked for t in project.tracks):
        ops.append(
            DawOperation(
                action_type="regenerate_role",
                target_role="bass",
                parameters={"variation": "softer"},
                idempotency_key=f"regen-bass-{uuid4().hex[:8]}",
                predicted_impact="New bass variation; drums preserved if locked",
                explanation="Regenerate bass line",
                risk_level="medium",
                requires_approval=True,
            )
        )
    ops.append(
        DawOperation(
            action_type="add_fill",
            target_role="drums",
            parameters={"before_bar": project.length_bars},
            idempotency_key=f"fill-{uuid4().hex[:8]}",
            predicted_impact=f"Add fill before bar {project.length_bars}",
            explanation="End-of-loop drum fill",
            risk_level="low",
            requires_approval=project.autonomy_policy.mode != "autonomous",
        )
    )
    # Prefer ops targeting unlocked roles when possible
    if unlocked:
        unlocked_roles = {t.role.value for t in unlocked}
        ops = [o for o in ops if o.target_role in unlocked_roles or o.action_type == "add_fill"] or ops
    return ops[:max_moves]
