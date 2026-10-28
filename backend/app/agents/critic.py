"""Critic stub — emits typed PatchOps only (Phase 1 scaffold; Phase 4 fills heuristics)."""

from __future__ import annotations

from uuid import uuid4

from backend.app.models.schemas import DawOperation, MusicalDiff, MusicProject


def propose_next_moves(
    project: MusicProject,
    *,
    diff: MusicalDiff | None = None,
    max_moves: int = 3,
) -> list[DawOperation]:
    """Return up to max_moves typed patch ops targeting unlocked roles only."""
    ops: list[DawOperation] = []
    unlocked = [t for t in project.tracks if not t.locked]
    unlocked_roles = {t.role.value for t in unlocked}

    if "drums" in unlocked_roles:
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
    if "bass" in unlocked_roles:
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
    if "chord" in unlocked_roles:
        ops.append(
            DawOperation(
                action_type="regenerate_role",
                target_role="chord",
                parameters={"variation": "voicing"},
                idempotency_key=f"regen-chord-{uuid4().hex[:8]}",
                predicted_impact="New chord voicings",
                explanation="Regenerate chords",
                risk_level="medium",
                requires_approval=True,
            )
        )

    # Never propose ops against locked roles
    ops = [o for o in ops if o.target_role in unlocked_roles]
    if not ops and unlocked_roles:
        # Fallback: generic humanize on first unlocked role
        role = next(iter(unlocked_roles))
        ops.append(
            DawOperation(
                action_type="humanize_role",
                target_role=role,
                parameters={"timing_amount": 0.01, "velocity_jitter": 4},
                idempotency_key=f"humanize-{role}-{uuid4().hex[:8]}",
                predicted_impact=f"Humanize unlocked {role}",
                explanation=f"Humanize {role}",
                risk_level="low",
                requires_approval=True,
            )
        )
    return ops[:max_moves]
