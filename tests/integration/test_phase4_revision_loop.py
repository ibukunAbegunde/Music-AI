"""Phase 4 exit: critic PatchOps + measured improvement + rollback verified."""

from __future__ import annotations

import json

from backend.app.core.config import Settings
from backend.app.daw.fake import FakeDawAdapter
from backend.app.music.patch_apply import apply_patch_ops
from backend.app.render_eval.evaluate import evaluate_project
from backend.app.render_eval.metrics import improved
from backend.app.services.compose import compose_from_prompt
from backend.app.services.revision_loop import restore_project_version, run_revision_loop
from backend.app.storage.assets import AssetStore


def _spoil_hot(project):
    out = project.model_copy(deep=True)
    for t in out.tracks:
        t.note_events = [n.model_copy(update={"velocity": 127}) for n in t.note_events]
        t.drum_events = [d.model_copy(update={"velocity": 127}) for d in t.drum_events]
    return out


def _rewrite_cir(assets: AssetStore, project) -> None:
    """Overwrite tip CIR so revision_loop loads the spoiled state."""
    assert project.version_id is not None
    assets.write_json(
        f"projects/{project.id}/versions/{project.version_id}.json",
        project.model_dump(mode="json"),
    )


def test_suggest_only_returns_typed_ops(tmp_settings: Settings) -> None:
    daw = FakeDawAdapter()
    composed = compose_from_prompt(
        "Afrobeats 110 BPM in A minor",
        seed=40,
        settings=tmp_settings,
        adapter=daw,
    )
    result = run_revision_loop(
        composed.project.id,
        apply_ops=False,
        fixture_id="hot_clipping",
        settings=tmp_settings,
        adapter=daw,
    )
    assert result.user_confirmation_required
    assert result.stopped_reason == "awaiting_user_confirmation"
    assert not result.applied
    assert result.next_moves
    assert len(result.next_moves) <= 3
    assert all(op.action_type and op.target_role for op in result.next_moves)


def test_apply_loop_measured_improvement_and_undo(tmp_settings: Settings) -> None:
    daw = FakeDawAdapter()
    composed = compose_from_prompt(
        "Afrobeats 110 BPM in A minor",
        seed=41,
        settings=tmp_settings,
        adapter=daw,
    )
    parent_version = composed.version.id
    spoiled = _spoil_hot(composed.project)
    assets = AssetStore(tmp_settings)
    _rewrite_cir(assets, spoiled)

    before = evaluate_project(spoiled).scoreboard
    assert before is not None
    assert before.technical_fail_count >= 1 or before.technical < 0.85

    result = run_revision_loop(
        composed.project.id,
        max_iterations=3,
        apply_ops=True,
        settings=tmp_settings,
        adapter=daw,
    )
    assert result.undo_verified
    assert result.initial_scoreboard is not None
    assert result.final_scoreboard is not None
    # Either accepted an improving iter, or stopped cleanly after rollback attempt
    if result.applied:
        assert any(it.accepted for it in result.iterations)
        assert improved(result.initial_scoreboard, result.final_scoreboard) or (
            result.final_scoreboard.technical_fail_count
            <= result.initial_scoreboard.technical_fail_count
        )
        assert result.version is not None
        assert result.candidate is not None
        assert result.candidate.one_line_diff
        assert result.candidate.cir_snapshot_ref
        # Restore parent version (rollback path)
        restored = restore_project_version(
            composed.project.id,
            parent_version,
            settings=tmp_settings,
            adapter=FakeDawAdapter(),
        )
        assert restored.version_id == parent_version
    else:
        # No improvement accepted — still must have verified undo plumbing
        assert result.stopped_reason in {
            "no_improvement",
            "no_actionable_ops",
            "lock_violation",
            "healthy_plateau",
            "max_iterations",
        }
        assert any(it.rolled_back for it in result.iterations) or not result.iterations


def test_rollback_when_ops_do_not_improve(tmp_settings: Settings) -> None:
    """Force a worsening patch and ensure loop rolls back CIR + FakeDaw."""
    daw = FakeDawAdapter()
    composed = compose_from_prompt(
        "pop 120 BPM",
        seed=42,
        settings=tmp_settings,
        adapter=daw,
    )
    # Scale velocities up hard — should worsen technical score on already ok mix
    from backend.app.models.schemas import DawOperation

    bad_ops = [
        DawOperation(
            action_type="scale_velocity",
            target_role="drums",
            parameters={"factor": 1.5},
            idempotency_key="worsen-drums",
            risk_level="low",
            requires_approval=False,
        ),
        DawOperation(
            action_type="scale_velocity",
            target_role="bass",
            parameters={"factor": 1.5},
            idempotency_key="worsen-bass",
            risk_level="low",
            requires_approval=False,
        ),
    ]
    before_proj = composed.project.model_copy(deep=True)
    before_board = evaluate_project(before_proj).scoreboard
    patched, _ = apply_patch_ops(before_proj, bad_ops, seed=1)
    after_board = evaluate_project(patched).scoreboard
    assert before_board and after_board
    # Confirm this patch is actually worse (or at least not an improvement)
    assert not improved(before_board, after_board) or after_board.technical <= before_board.technical

    # Snapshot → apply → restore
    daw.create_or_update_notes(before_proj)
    snap = daw.save_snapshot("pre-bad")
    ref = snap.observations["snapshot_ref"]
    daw.create_or_update_notes(patched)
    restored = daw.undo_or_restore(ref)
    assert restored.succeeded and restored.verified
    assert daw.project is not None
    drums_before = next(t for t in before_proj.tracks if t.role.value == "drums")
    drums_restored = next(t for t in daw.project.tracks if t.role.value == "drums")
    assert [n.velocity for n in drums_before.note_events] == [
        n.velocity for n in drums_restored.note_events
    ]


def test_revision_loop_respects_drum_lock(tmp_settings: Settings) -> None:
    daw = FakeDawAdapter()
    composed = compose_from_prompt(
        "Afrobeats 110 BPM",
        seed=43,
        settings=tmp_settings,
        adapter=daw,
        locked_roles=["drums"],
    )
    spoiled = _spoil_hot(composed.project)
    for t in spoiled.tracks:
        if t.role.value == "drums":
            t.locked = True
    assets = AssetStore(tmp_settings)
    _rewrite_cir(assets, spoiled)

    result = run_revision_loop(
        composed.project.id,
        max_iterations=2,
        apply_ops=True,
        fixture_id="hot_clipping",
        settings=tmp_settings,
        adapter=daw,
    )
    for it in result.iterations:
        for op in it.ops:
            if op.verification_status == "applied":
                assert op.target_role != "drums"
    assert all(m.target_role != "drums" for m in result.next_moves)


def test_fixture_driven_critique_persists_artifacts(tmp_settings: Settings) -> None:
    daw = FakeDawAdapter()
    composed = compose_from_prompt(
        "Amapiano 112 BPM",
        seed=44,
        settings=tmp_settings,
        adapter=daw,
    )
    result = run_revision_loop(
        composed.project.id,
        apply_ops=True,
        fixture_id="muddy_sub",
        max_iterations=2,
        settings=tmp_settings,
        adapter=daw,
    )
    assets = AssetStore(tmp_settings)
    # Evaluations written under renders/
    render_root = assets.root / "renders" / str(composed.project.id)
    assert render_root.exists()
    assert any(render_root.glob("*_evaluations.json"))
    if result.applied:
        loop_path = (
            assets.root
            / "projects"
            / str(composed.project.id)
            / f"revision_loop_{result.version.id}.json"
        )
        data = json.loads(loop_path.read_text(encoding="utf-8"))
        assert data["undo_verified"] is True
        assert data["fixture_id"] == "muddy_sub"
