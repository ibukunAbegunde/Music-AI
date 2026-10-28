"""Critic — emits typed PatchOps only (Phase 4). No essay-only actionable path."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from backend.app.models.schemas import DawOperation, Evaluation, MusicalDiff, MusicProject
from backend.app.render_eval.evaluate import CritiqueBundle, evaluate_project
from backend.app.render_eval.metrics import RenderMetrics, Scoreboard


@dataclass
class CriticResult:
    """Actionable critic output: validated PatchOps (+ optional annotations on ops)."""

    patch_ops: list[DawOperation] = field(default_factory=list)
    next_moves: list[DawOperation] = field(default_factory=list)
    evaluations: list[Evaluation] = field(default_factory=list)
    scoreboard: Scoreboard | None = None
    metrics: RenderMetrics | None = None
    findings_summary: list[str] = field(default_factory=list)  # annotations only — not the deliverable

    def model_dump(self) -> dict:
        return {
            "patch_ops": [o.model_dump(mode="json") for o in self.patch_ops],
            "next_moves": [o.model_dump(mode="json") for o in self.next_moves],
            "evaluations": [e.model_dump(mode="json") for e in self.evaluations],
            "scoreboard": self.scoreboard.model_dump(mode="json") if self.scoreboard else None,
            "metrics": self.metrics.model_dump(mode="json") if self.metrics else None,
            "findings_summary": self.findings_summary,
        }


def _needs_approval(project: MusicProject, risk: str) -> bool:
    policy = project.autonomy_policy
    if policy.mode == "autonomous" and policy.scratch_or_release == "scratch":
        return risk == "high"
    if policy.mode == "suggest-only":
        return True
    # collaborative default
    if policy.scratch_or_release == "release":
        return True
    return risk != "low"


def _op(
    *,
    action_type: str,
    target_role: str,
    parameters: dict,
    impact: str,
    explanation: str,
    risk: str,
    project: MusicProject,
    idem: str,
) -> DawOperation:
    return DawOperation(
        action_type=action_type,
        target_role=target_role,
        parameters=parameters,
        idempotency_key=f"{idem}-{uuid4().hex[:8]}",
        predicted_impact=impact,
        explanation=explanation,
        risk_level=risk,
        requires_approval=_needs_approval(project, risk),
        expected_postcondition={"role_changed": target_role},
    )


def _fail_map(evaluations: list[Evaluation]) -> dict[str, Evaluation]:
    return {
        e.metric_name: e
        for e in evaluations
        if e.metric_name.endswith(".fail") and e.value >= 0.5
    }


def propose_patch_ops_from_evaluations(
    project: MusicProject,
    evaluations: list[Evaluation],
    metrics: RenderMetrics | None = None,
    *,
    diff: MusicalDiff | None = None,
    max_ops: int = 8,
) -> list[DawOperation]:
    """Map measured findings → typed PatchOps. Locked roles never targeted."""
    unlocked = {t.role.value for t in project.tracks if not t.locked}
    fails = _fail_map(evaluations)
    ops: list[DawOperation] = []

    def can(role: str) -> bool:
        return role in unlocked

    # Technical: clipping / hot velocity → soften loudest unlocked role
    if "technical.clipping.fail" in fails or "technical.hot_velocity.fail" in fails:
        # Prefer drums if unlocked (often peaky), else bass, else first unlocked
        target = next((r for r in ("drums", "bass", "chord") if can(r)), None)
        if target:
            ops.append(
                _op(
                    action_type="soften_velocity",
                    target_role=target,
                    parameters={"factor": 0.72},
                    impact=f"Lower {target} velocity to reduce peaks/clipping risk",
                    explanation="technical: hot peaks / clipping",
                    risk="low",
                    project=project,
                    idem=f"soften-{target}",
                )
            )

    if "technical.loudness.fail" in fails and metrics is not None:
        # Too quiet → scale up; too loud → scale down
        factor = 0.8 if metrics.measured_lufs > -10 else 1.15
        target = next((r for r in ("drums", "bass", "chord") if can(r)), None)
        if target:
            ops.append(
                _op(
                    action_type="scale_velocity",
                    target_role=target,
                    parameters={"factor": factor},
                    impact=f"Scale {target} velocity toward target loudness",
                    explanation="technical: loudness off target",
                    risk="low",
                    project=project,
                    idem=f"lufs-{target}",
                )
            )

    if "technical.excess_sub.fail" in fails and can("bass"):
        ops.append(
            _op(
                action_type="soften_velocity",
                target_role="bass",
                parameters={"factor": 0.65},
                impact="Soften bass to reduce excess low-end energy",
                explanation="technical: excess sub",
                risk="low",
                project=project,
                idem="sub-bass",
            )
        )
        if can("bass"):
            ops.append(
                _op(
                    action_type="nudge_bass_off_kick",
                    target_role="bass",
                    parameters={"amount_beats": 0.06},
                    impact="Micro-shift bass off kick to unmask low end",
                    explanation="technical/musical: kick-bass stacking",
                    risk="low",
                    project=project,
                    idem="nudge-bass",
                )
            )

    if "musical.kick_bass.fail" in fails and can("bass"):
        ops.append(
            _op(
                action_type="nudge_bass_off_kick",
                target_role="bass",
                parameters={"amount_beats": 0.08},
                impact="Offset bass from kick onsets",
                explanation="musical: kick/bass overlap",
                risk="low",
                project=project,
                idem="kick-bass",
            )
        )

    if "musical.density.fail" in fails:
        target = next((r for r in ("chord", "drums", "bass") if can(r)), None)
        if target and metrics and metrics.note_density_per_bar > 28:
            ops.append(
                _op(
                    action_type="reduce_density",
                    target_role=target,
                    parameters={"keep_ratio": 0.7},
                    impact=f"Thin {target} events to lower density",
                    explanation="musical: density too high",
                    risk="medium",
                    project=project,
                    idem=f"thin-{target}",
                )
            )
        elif target and metrics and metrics.note_density_per_bar < 2 and can(target):
            ops.append(
                _op(
                    action_type="regenerate_role",
                    target_role=target,
                    parameters={"variation": "fill"},
                    impact=f"Regenerate sparse {target}",
                    explanation="musical: density too low",
                    risk="medium",
                    project=project,
                    idem=f"regen-{target}",
                )
            )

    if "musical.empty_roles.fail" in fails:
        for t in project.tracks:
            if t.enabled and not t.locked and not t.note_events and not t.drum_events:
                ops.append(
                    _op(
                        action_type="regenerate_role",
                        target_role=t.role.value,
                        parameters={"variation": "repair"},
                        impact=f"Regenerate empty {t.role.value} track",
                        explanation="musical: empty role",
                        risk="medium",
                        project=project,
                        idem=f"empty-{t.role.value}",
                    )
                )

    if "musical.grid.fail" in fails and can("drums"):
        ops.append(
            _op(
                action_type="quantize_role",
                target_role="drums",
                parameters={"grid": 0.25},
                impact="Snap unlocked drums to 16th grid to reduce timing drift",
                explanation="musical: groove grid error",
                risk="low",
                project=project,
                idem="grid-drums",
            )
        )

    if "musical.end_fill.fail" in fails and can("drums"):
        ops.append(
            _op(
                action_type="add_fill",
                target_role="drums",
                parameters={"before_bar": project.length_bars},
                impact=f"Add drum fill before bar {project.length_bars}",
                explanation="musical: missing end fill",
                risk="low",
                project=project,
                idem="end-fill",
            )
        )

    # Deduplicate by (action_type, target_role), preserve order
    seen: set[tuple[str, str | None]] = set()
    unique: list[DawOperation] = []
    for op in ops:
        key = (op.action_type, op.target_role)
        if key in seen:
            continue
        if op.target_role and op.target_role not in unlocked:
            continue
        seen.add(key)
        unique.append(op)

    # Diff-aware hint: if bass already changed a lot, prefer softer follow-ups
    if diff and "bass" in diff.roles_changed and can("chord"):
        if not any(o.action_type == "humanize_role" and o.target_role == "chord" for o in unique):
            unique.append(
                _op(
                    action_type="humanize_role",
                    target_role="chord",
                    parameters={"timing_amount": 0.012, "velocity_jitter": 4},
                    impact="Humanize chords after bass revision",
                    explanation="diff-aware follow-up",
                    risk="low",
                    project=project,
                    idem="post-bass-chord",
                )
            )

    return unique[:max_ops]


def propose_next_moves(
    project: MusicProject,
    *,
    diff: MusicalDiff | None = None,
    max_moves: int = 3,
    evaluations: list[Evaluation] | None = None,
    metrics: RenderMetrics | None = None,
) -> list[DawOperation]:
    """Return up to max_moves typed patch ops (≤3 for playback-centric loop).

    Phase 1 compatibility: if no evaluations provided, falls back to lock-aware
    heuristic stubs, then prefers evaluation-driven ops when available.
    """
    if evaluations is not None:
        ops = propose_patch_ops_from_evaluations(
            project, evaluations, metrics, diff=diff, max_ops=max_moves * 2
        )
        if ops:
            return ops[:max_moves]

    # Fallback heuristic stubs (unlocked only) — still typed PatchOps, never essays
    ops: list[DawOperation] = []
    unlocked_roles = {t.role.value for t in project.tracks if not t.locked}

    if "drums" in unlocked_roles:
        ops.append(
            _op(
                action_type="humanize_role",
                target_role="drums",
                parameters={"timing_amount": 0.015, "velocity_jitter": 5},
                impact="Slightly looser drum feel",
                explanation="Humanize unlocked drums",
                risk="low",
                project=project,
                idem="humanize-drums",
            )
        )
        ops.append(
            _op(
                action_type="add_fill",
                target_role="drums",
                parameters={"before_bar": project.length_bars},
                impact=f"Add fill before bar {project.length_bars}",
                explanation="End-of-loop drum fill",
                risk="low",
                project=project,
                idem="fill",
            )
        )
    if "bass" in unlocked_roles:
        ops.append(
            _op(
                action_type="regenerate_role",
                target_role="bass",
                parameters={"variation": "softer"},
                impact="New bass variation; drums preserved if locked",
                explanation="Regenerate bass line",
                risk="medium",
                project=project,
                idem="regen-bass",
            )
        )
    if "chord" in unlocked_roles:
        ops.append(
            _op(
                action_type="regenerate_role",
                target_role="chord",
                parameters={"variation": "voicing"},
                impact="New chord voicings",
                explanation="Regenerate chords",
                risk="medium",
                project=project,
                idem="regen-chord",
            )
        )

    ops = [o for o in ops if o.target_role in unlocked_roles]
    if not ops and unlocked_roles:
        role = next(iter(unlocked_roles))
        ops.append(
            _op(
                action_type="humanize_role",
                target_role=role,
                parameters={"timing_amount": 0.01, "velocity_jitter": 4},
                impact=f"Humanize unlocked {role}",
                explanation=f"Humanize {role}",
                risk="low",
                project=project,
                idem=f"humanize-{role}",
            )
        )
    return ops[:max_moves]


def critique_project(
    project: MusicProject,
    *,
    fixture_id: str | None = None,
    metrics: RenderMetrics | None = None,
    diff: MusicalDiff | None = None,
    max_moves: int = 3,
    bundle: CritiqueBundle | None = None,
) -> CriticResult:
    """Full Phase 4 critic: evaluate → typed PatchOps → ≤3 next moves."""
    b = bundle or evaluate_project(project, fixture_id=fixture_id, metrics=metrics)
    patch_ops = propose_patch_ops_from_evaluations(
        project,
        b.evaluations,
        b.metrics,
        diff=diff,
        max_ops=8,
    )
    next_moves = patch_ops[:max_moves]
    findings = [
        e.explanation or e.metric_name
        for e in b.evaluations
        if e.metric_name.endswith(".fail") and e.value >= 0.5
    ]
    return CriticResult(
        patch_ops=patch_ops,
        next_moves=next_moves,
        evaluations=b.evaluations,
        scoreboard=b.scoreboard,
        metrics=b.metrics,
        findings_summary=findings,
    )
