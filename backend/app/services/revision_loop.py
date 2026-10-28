"""Bounded critic revision loop with measured improvement + rollback (Phase 4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from backend.app.agents.critic import CriticResult, critique_project
from backend.app.core.config import DawMode, Settings, get_settings
from backend.app.core.logging import log_event, setup_logging
from backend.app.daw.base import DawAdapter, DawResult
from backend.app.daw.fake import FakeDawAdapter
from backend.app.daw.midi_fallback import MidiExportAdapter
from backend.app.models.db import init_db
from backend.app.models.schemas import (
    CandidatePackage,
    DawOperation,
    LoudnessNotes,
    MusicProject,
    ProjectStatus,
    ProjectVersion,
    new_id,
    utcnow,
)
from backend.app.music.diff import diff_projects
from backend.app.music.midi import export_project_midi
from backend.app.music.patch_apply import apply_patch_ops
from backend.app.render_eval.evaluate import evaluate_project, persist_evaluation
from backend.app.render_eval.metrics import Scoreboard, improved
from backend.app.render_eval.simulate import seed_cir_defects_from_fixture
from backend.app.research.action_effect import (
    append_revision_outcome,
    outcomes_from_revision_iterations,
)
from backend.app.services.compose import select_adapter
from backend.app.services.revise import _load_cir
from backend.app.storage.assets import AssetStore
from backend.app.storage.repository import ProjectRepository


def _proposal_fixture_id(
    cir_board: Scoreboard | None, fixture_id: str | None
) -> str | None:
    """Drop fixture overlay once CIR fails are clear (avoid sticky proposals)."""
    if fixture_id is None or cir_board is None:
        return fixture_id
    if not cir_board.any_fail and cir_board.technical >= 0.85 and cir_board.musical >= 0.85:
        return None
    return fixture_id


@dataclass
class RevisionIteration:
    index: int
    before: Scoreboard
    after: Scoreboard | None
    ops: list[DawOperation]
    accepted: bool
    rolled_back: bool
    diff_summary: str | None = None
    reason: str = ""


@dataclass
class RevisionLoopResult:
    project: MusicProject
    parent: MusicProject
    version: ProjectVersion | None
    candidate: CandidatePackage | None
    iterations: list[RevisionIteration] = field(default_factory=list)
    final_scoreboard: Scoreboard | None = None
    initial_scoreboard: Scoreboard | None = None
    next_moves: list[DawOperation] = field(default_factory=list)
    critic: CriticResult | None = None
    snapshot_ref: str | None = None
    undo_verified: bool = False
    applied: bool = False
    stopped_reason: str = ""
    midi_paths: dict[str, Path] = field(default_factory=dict)
    daw_result: DawResult | None = None
    user_confirmation_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def _persist_version(
    *,
    project: MusicProject,
    parent: MusicProject,
    assets: AssetStore,
    repo: ProjectRepository,
    settings: Settings,
    instruction: str,
    ops: list[DawOperation],
    musical_diff,
) -> tuple[ProjectVersion, CandidatePackage, dict[str, Path]]:
    midi_paths = export_project_midi(project, assets.midi_dir(project.id))
    version = ProjectVersion(
        id=new_id(),
        parent_version_id=parent.version_id,
        canonical_project_snapshot=project.model_dump(mode="json"),
        exported_midi_paths=[str(p) for p in midi_paths.values()],
        operation_ids=[o.operation_id for o in ops],
        user_message=instruction,
        one_line_diff=musical_diff.one_line_summary,
        musical_diff=musical_diff,
        recipe_id=project.recipe_id,
        created_at=utcnow(),
        restorable=True,
    )
    project.version_id = version.id
    project.status = ProjectStatus.COMPLETED
    project.updated_at = utcnow()
    musical_diff.to_version_id = version.id
    repo.save_project(project)
    repo.save_version(version, project.id)
    cir_ref = f"projects/{project.id}/versions/{version.id}.json"
    assets.write_json(cir_ref, project.model_dump(mode="json"))
    assets.write_json(
        f"projects/{project.id}/diff_{version.id}.json",
        musical_diff.model_dump(mode="json"),
    )
    candidate = CandidatePackage(
        project_id=project.id,
        version_id=version.id,
        seed=int(project.seed or 0),
        cir_snapshot_ref=cir_ref,
        midi_paths=[str(p) for p in midi_paths.values()],
        loudness_notes=LoudnessNotes(
            target_lufs=-14.0,
            measured_lufs=None,
            normalization_status="n/a"
            if settings.daw_mode == DawMode.SIMULATION
            else "manual_required",
        ),
        one_line_diff=musical_diff.one_line_summary,
        musical_diff_id=musical_diff.id,
        parent_version_id=parent.version_id,
    )
    assets.write_json(
        f"projects/{project.id}/candidate_{candidate.id}.json",
        candidate.model_dump(mode="json"),
    )
    return version, candidate, midi_paths


def run_revision_loop(
    project_id: UUID,
    *,
    max_iterations: int = 3,
    apply_ops: bool = False,
    auto_approve_low_risk: bool = True,
    fixture_id: str | None = None,
    seed: int | None = None,
    settings: Settings | None = None,
    adapter: DawAdapter | None = None,
    parent_version_id: UUID | None = None,
    approved_operation_ids: list[UUID] | None = None,
) -> RevisionLoopResult:
    """Playback-centric loop: evaluate → ≤3 PatchOps → apply/measure → rollback if worse.

    Simulation mode uses CIR-derived / fixture metrics (no real audio bounce).
    Collaborative default: without apply_ops, returns typed next moves for confirmation.
    """
    settings = settings or get_settings()
    logger = setup_logging(settings.log_level)
    settings.ensure_workspace()
    session_factory = init_db(settings)
    repo = ProjectRepository(session_factory)
    assets = AssetStore(settings)

    stored = repo.get_project(project_id)
    if stored is None:
        raise ValueError(f"unknown project {project_id}")
    origin = _load_cir(assets, project_id, parent_version_id or stored.version_id) or stored
    current = origin.model_copy(deep=True)
    max_iterations = max(1, min(int(max_iterations), origin.autonomy_policy.max_generations or 3))

    # When applying with a fixture, seed matching CIR defects so scoreboard can move.
    # Diff baseline becomes the spoiled tip (still parent_version_id → origin).
    if apply_ops and fixture_id:
        current = seed_cir_defects_from_fixture(current, fixture_id)
    parent = current.model_copy(deep=True)
    parent.version_id = origin.version_id

    daw = adapter or select_adapter(settings, assets)
    daw.connect()
    snapshot_ref = None
    undo_verified = False
    if isinstance(daw, FakeDawAdapter):
        daw.create_or_update_notes(current)
        snap = daw.save_snapshot("pre-revision-loop")
        snapshot_ref = snap.observations.get("snapshot_ref")

    # Scoreboard always from CIR simulation so PatchOps can show measured deltas.
    # Optional fixture overlays drive *proposal* heuristics only (still typed ops),
    # and are dropped once CIR fails clear (no sticky fixture proposals).
    initial_bundle = evaluate_project(current)
    persist_evaluation(initial_bundle, assets)
    initial_board = initial_bundle.scoreboard
    assert initial_board is not None
    active_fixture = _proposal_fixture_id(initial_board, fixture_id)
    # Suggest-only path keeps the requested fixture so demos still surface it.
    suggest_fixture = fixture_id if not apply_ops else active_fixture
    proposal_bundle = (
        evaluate_project(current, fixture_id=suggest_fixture)
        if suggest_fixture
        else initial_bundle
    )

    # Suggest-only / collaborative without apply: return critic moves, no writes
    needs_confirm = (
        not apply_ops
        or current.autonomy_policy.mode == "suggest-only"
        or (
            current.autonomy_policy.mode == "collaborative"
            and current.autonomy_policy.require_approval_for_writes
            and not apply_ops
        )
    )

    critic = critique_project(
        current, fixture_id=suggest_fixture, bundle=proposal_bundle, max_moves=3
    )

    if needs_confirm and not apply_ops:
        log_event(
            logger,
            "revision_loop.awaiting_confirmation",
            project_id=str(project_id),
            moves=len(critic.next_moves),
        )
        return RevisionLoopResult(
            project=current,
            parent=parent,
            version=None,
            candidate=None,
            iterations=[],
            final_scoreboard=initial_board,
            initial_scoreboard=initial_board,
            next_moves=critic.next_moves,
            critic=critic,
            snapshot_ref=snapshot_ref,
            undo_verified=False,
            applied=False,
            stopped_reason="awaiting_user_confirmation",
            user_confirmation_required=True,
            metadata={
                "mode": settings.daw_mode.value,
                "fixture_id": fixture_id,
                "scoreboard": initial_board.model_dump(mode="json"),
            },
        )

    iterations: list[RevisionIteration] = []
    stopped = "max_iterations"
    loop_seed = seed if seed is not None else int(current.seed or 0) + 100
    approved_set = set(approved_operation_ids or [])

    for i in range(max_iterations):
        score_bundle = evaluate_project(current)
        before = score_bundle.scoreboard
        assert before is not None
        iter_fixture = _proposal_fixture_id(before, fixture_id)
        propose_bundle = (
            evaluate_project(current, fixture_id=iter_fixture)
            if iter_fixture
            else score_bundle
        )
        critic = critique_project(
            current, fixture_id=iter_fixture, bundle=propose_bundle, max_moves=3
        )

        ops = list(critic.next_moves)
        if approved_set:
            ops = [o for o in ops if o.operation_id in approved_set or not o.requires_approval]
        elif auto_approve_low_risk:
            ops = [
                o
                for o in ops
                if (not o.requires_approval) or o.risk_level == "low" or apply_ops
            ]
        else:
            ops = [o for o in ops if not o.requires_approval]

        if not ops:
            stopped = "no_actionable_ops"
            iterations.append(
                RevisionIteration(
                    index=i,
                    before=before,
                    after=before,
                    ops=[],
                    accepted=False,
                    rolled_back=False,
                    reason="no actionable PatchOps for unlocked roles",
                )
            )
            break

        # Snapshot for per-iteration rollback (CIR + FakeDaw)
        cir_before = current.model_copy(deep=True)
        iter_snap = None
        if isinstance(daw, FakeDawAdapter):
            daw.create_or_update_notes(cir_before)
            iter_snap = daw.save_snapshot(f"iter-{i}").observations.get("snapshot_ref")

        patched, applied_ops = apply_patch_ops(current, ops, seed=loop_seed + i)
        # Honor role-locks via diff check
        locks = [t.role.value for t in cir_before.tracks if t.locked]
        mdiff = diff_projects(
            cir_before,
            patched,
            from_version_id=cir_before.version_id,
            expected_locked=locks,
        )
        if not mdiff.locked_roles_respected:
            if iter_snap and isinstance(daw, FakeDawAdapter):
                daw.undo_or_restore(iter_snap)
            iterations.append(
                RevisionIteration(
                    index=i,
                    before=before,
                    after=before,
                    ops=applied_ops,
                    accepted=False,
                    rolled_back=True,
                    diff_summary=mdiff.one_line_summary,
                    reason="role-lock violation — rolled back",
                )
            )
            stopped = "lock_violation"
            break

        after_bundle = evaluate_project(patched)  # measured path: CIR simulation only
        after = after_bundle.scoreboard
        assert after is not None
        accept = improved(before, after)

        if accept:
            current = patched
            if isinstance(daw, FakeDawAdapter):
                daw.create_or_update_notes(current)
            iterations.append(
                RevisionIteration(
                    index=i,
                    before=before,
                    after=after,
                    ops=applied_ops,
                    accepted=True,
                    rolled_back=False,
                    diff_summary=mdiff.one_line_summary,
                    reason="measured improvement",
                )
            )
            persist_evaluation(after_bundle, assets)
            # Clear approved ids after one use so subsequent iters re-critique
            approved_set.clear()
        else:
            if iter_snap and isinstance(daw, FakeDawAdapter):
                restore = daw.undo_or_restore(iter_snap)
                undo_verified = bool(restore.verified and restore.succeeded)
            current = cir_before
            iterations.append(
                RevisionIteration(
                    index=i,
                    before=before,
                    after=after,
                    ops=applied_ops,
                    accepted=False,
                    rolled_back=True,
                    diff_summary=mdiff.one_line_summary,
                    reason="no measured improvement — rolled back",
                )
            )
            stopped = (
                "plateau_no_further_gain"
                if any(it.accepted for it in iterations)
                else "no_improvement"
            )
            break

        # Plateau: if scores already healthy and last iter tiny, stop
        if after.technical >= 0.9 and after.musical >= 0.9 and not after.any_fail:
            stopped = "healthy_plateau"
            break
    else:
        stopped = "max_iterations"

    # Verify top-level undo still works from pre-loop snapshot
    if snapshot_ref and isinstance(daw, FakeDawAdapter):
        # Don't actually leave restored — verify then re-apply current tip
        probe = FakeDawAdapter()
        probe.connect()
        probe.create_or_update_notes(parent)
        pre = probe.save_snapshot("undo-probe")
        pref = pre.observations["snapshot_ref"]
        probe.create_or_update_notes(current)
        restored = probe.undo_or_restore(pref)
        undo_verified = bool(restored.verified and restored.succeeded)
        # Ensure restore matched parent CIR tip roles/notes count
        if undo_verified and probe.project is not None:
            undo_verified = len(probe.project.tracks) == len(parent.tracks)

    final_bundle = evaluate_project(current)
    final_board = final_bundle.scoreboard
    final_fixture = _proposal_fixture_id(final_board, fixture_id)
    final_propose = (
        evaluate_project(current, fixture_id=final_fixture)
        if final_fixture
        else final_bundle
    )
    final_critic = critique_project(
        current, fixture_id=final_fixture, bundle=final_propose, max_moves=3
    )

    version = None
    candidate = None
    midi_paths: dict[str, Path] = {}
    daw_result = None
    accepted_ops = [o for it in iterations if it.accepted for o in it.ops]

    if any(it.accepted for it in iterations):
        musical_diff = diff_projects(
            parent,
            current,
            from_version_id=parent.version_id,
            expected_locked=[t.role.value for t in parent.tracks if t.locked],
        )
        current.generation_brief = (
            f"revision_loop:{stopped}"
            if not current.generation_brief
            else current.generation_brief
        )
        if isinstance(daw, FakeDawAdapter):
            daw_result = daw.create_or_update_notes(current)
            daw.verify_postcondition({"min_tracks": 1})
        elif isinstance(daw, MidiExportAdapter):
            daw_result = daw.create_or_update_notes(current)

        version, candidate, midi_paths = _persist_version(
            project=current,
            parent=parent,
            assets=assets,
            repo=repo,
            settings=settings,
            instruction=f"revision_loop apply ({stopped})",
            ops=accepted_ops,
            musical_diff=musical_diff,
        )
        if candidate and final_bundle.metrics:
            candidate.loudness_notes.measured_lufs = final_bundle.metrics.measured_lufs
            candidate.loudness_notes.normalization_status = "n/a"
            candidate.render_id = final_bundle.render.id

        meta = {
            "project_id": str(current.id),
            "version_id": str(version.id) if version else None,
            "parent_version_id": str(parent.version_id) if parent.version_id else None,
            "revision_loop": {
                "stopped_reason": stopped,
                "iterations": [
                    {
                        "index": it.index,
                        "accepted": it.accepted,
                        "rolled_back": it.rolled_back,
                        "reason": it.reason,
                        "diff": it.diff_summary,
                        "before": it.before.model_dump(mode="json"),
                        "after": it.after.model_dump(mode="json") if it.after else None,
                        "ops": [o.model_dump(mode="json") for o in it.ops],
                    }
                    for it in iterations
                ],
                "initial_scoreboard": initial_board.model_dump(mode="json"),
                "final_scoreboard": final_board.model_dump(mode="json") if final_board else None,
                "undo_verified": undo_verified,
                "fixture_id": fixture_id,
                "proposal_fixture_id": final_fixture,
                "proposal_source": "fixture" if final_fixture else "cir",
            },
            "candidate": candidate.model_dump(mode="json") if candidate else None,
            "next_moves": [o.model_dump(mode="json") for o in final_critic.next_moves],
            "snapshot_ref": snapshot_ref,
            "mode": settings.daw_mode.value,
            "schema_version": current.schema_version,
        }
        assets.write_json(f"projects/{current.id}/metadata.json", meta)
        assets.write_json(
            f"projects/{current.id}/revision_loop_{version.id}.json",
            meta["revision_loop"],
        )
    else:
        meta = {
            "project_id": str(current.id),
            "revision_loop": {
                "stopped_reason": stopped,
                "iterations": [
                    {
                        "index": it.index,
                        "accepted": it.accepted,
                        "rolled_back": it.rolled_back,
                        "reason": it.reason,
                        "ops": [o.model_dump(mode="json") for o in it.ops],
                    }
                    for it in iterations
                ],
                "initial_scoreboard": initial_board.model_dump(mode="json"),
                "final_scoreboard": final_board.model_dump(mode="json") if final_board else None,
                "undo_verified": undo_verified,
                "fixture_id": fixture_id,
                "proposal_fixture_id": final_fixture,
                "proposal_source": "fixture" if final_fixture else "cir",
            },
            "next_moves": [o.model_dump(mode="json") for o in final_critic.next_moves],
            "snapshot_ref": snapshot_ref,
            "mode": settings.daw_mode.value,
        }
        assets.write_json(f"projects/{current.id}/revision_loop_last.json", meta["revision_loop"])

    # Phase 7: persist revision outcomes for action-effect scaffolding.
    outcome_paths: list[str] = []
    for row in outcomes_from_revision_iterations(
        project_id=current.id,
        version_id=version.id if version else current.version_id,
        iterations=iterations,
        fixture_id=fixture_id,
    ):
        path = append_revision_outcome(row, settings=settings)
        outcome_paths.append(str(path))
    if isinstance(meta, dict):
        loop_meta = meta.setdefault("revision_loop", {})
        if isinstance(loop_meta, dict):
            loop_meta["action_effect_outcomes"] = outcome_paths
            # Refresh on-disk loop record so outcomes are discoverable from the project.
            if version is not None:
                assets.write_json(
                    f"projects/{current.id}/revision_loop_{version.id}.json",
                    loop_meta,
                )
            else:
                assets.write_json(
                    f"projects/{current.id}/revision_loop_last.json",
                    loop_meta,
                )

    log_event(
        logger,
        "revision_loop.done",
        project_id=str(project_id),
        stopped=stopped,
        accepted=sum(1 for it in iterations if it.accepted),
        undo_verified=undo_verified,
        action_effect_outcomes=len(outcome_paths),
    )

    return RevisionLoopResult(
        project=current,
        parent=parent,
        version=version,
        candidate=candidate,
        iterations=iterations,
        final_scoreboard=final_board,
        initial_scoreboard=initial_board,
        next_moves=final_critic.next_moves,
        critic=final_critic,
        snapshot_ref=snapshot_ref,
        undo_verified=undo_verified,
        applied=any(it.accepted for it in iterations),
        stopped_reason=stopped,
        midi_paths=midi_paths,
        daw_result=daw_result,
        user_confirmation_required=False,
        metadata=meta,
    )


def restore_project_version(
    project_id: UUID,
    version_id: UUID,
    *,
    settings: Settings | None = None,
    adapter: DawAdapter | None = None,
) -> MusicProject:
    """Restore CIR tip to a prior restorable ProjectVersion (undo path)."""
    settings = settings or get_settings()
    settings.ensure_workspace()
    session_factory = init_db(settings)
    repo = ProjectRepository(session_factory)
    assets = AssetStore(settings)
    project = _load_cir(assets, project_id, version_id)
    if project is None:
        raise ValueError(f"version {version_id} not found for project {project_id}")
    project.updated_at = utcnow()
    project.status = ProjectStatus.COMPLETED
    repo.save_project(project)
    # Write tip metadata pointer
    assets.write_json(
        f"projects/{project_id}/metadata.json",
        {
            "project_id": str(project_id),
            "version_id": str(version_id),
            "restored": True,
            "seed": project.seed,
            "bpm": project.bpm,
            "key": project.key_estimate,
            "bars": project.length_bars,
            "mode": settings.daw_mode.value,
            "schema_version": project.schema_version,
        },
    )
    daw = adapter or select_adapter(settings, assets)
    daw.connect()
    if isinstance(daw, FakeDawAdapter):
        daw.create_or_update_notes(project)
    return project
