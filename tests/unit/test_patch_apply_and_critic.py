"""Critic → typed PatchOps + CIR applicator."""

from __future__ import annotations

from backend.app.agents.critic import critique_project, propose_next_moves
from backend.app.music.coedit import apply_role_locks
from backend.app.music.generators import generate_eight_bar_project
from backend.app.music.patch_apply import apply_patch_ops
from backend.app.render_eval.evaluate import evaluate_project


def _spoil_hot(project):
    """Force hot velocities so technical checks fail on CIR simulation."""
    out = project.model_copy(deep=True)
    for t in out.tracks:
        t.note_events = [
            n.model_copy(update={"velocity": 127}) for n in t.note_events
        ]
        t.drum_events = [
            d.model_copy(update={"velocity": 127}) for d in t.drum_events
        ]
    return out


def test_critic_emits_typed_ops_only_from_fixture() -> None:
    p = generate_eight_bar_project("Afrobeats 110", seed=11)
    result = critique_project(p, fixture_id="hot_clipping", max_moves=3)
    assert result.next_moves
    assert len(result.next_moves) <= 3
    for op in result.next_moves:
        assert op.action_type
        assert op.target_role
        assert op.idempotency_key
        assert op.predicted_impact
    # Actionable artifact is ops — findings_summary is annotation only
    assert isinstance(result.findings_summary, list)
    assert any(o.action_type == "soften_velocity" for o in result.patch_ops)


def test_critic_skips_locked_roles() -> None:
    p = apply_role_locks(generate_eight_bar_project("Amapiano 112", seed=2), ["drums", "bass"])
    result = critique_project(p, fixture_id="muddy_sub", max_moves=3)
    assert all(m.target_role not in {"drums", "bass"} for m in result.next_moves)
    # Locked drums/bass must never be targeted; unlocked roles (e.g. chord) ok
    assert all(m.target_role != "drums" for m in result.next_moves)
    assert all(m.target_role != "bass" for m in result.next_moves)


def test_propose_next_moves_phase1_compat() -> None:
    p = apply_role_locks(generate_eight_bar_project("Afrobeats 110", seed=1), ["drums"])
    moves = propose_next_moves(p)
    assert moves
    assert all(m.target_role != "drums" for m in moves)
    assert len(moves) <= 3


def test_apply_soften_and_fill() -> None:
    p = _spoil_hot(generate_eight_bar_project("trap 140", seed=4))
    before = evaluate_project(p).scoreboard
    assert before is not None
    critic = critique_project(p, max_moves=3)
    assert critic.next_moves
    patched, applied = apply_patch_ops(p, critic.next_moves, seed=99)
    assert any(o.verification_status == "applied" for o in applied)
    after = evaluate_project(patched).scoreboard
    assert after is not None
    # Softening and/or end-fill should not worsen technical fail count unboundedly
    assert after.technical_fail_count <= before.technical_fail_count


def test_locked_role_rejected_by_applicator() -> None:
    p = apply_role_locks(generate_eight_bar_project("pop 120", seed=5), ["drums"])
    from backend.app.models.schemas import DawOperation

    op = DawOperation(
        action_type="add_fill",
        target_role="drums",
        parameters={"before_bar": 8},
        idempotency_key="fill-test",
    )
    _, applied = apply_patch_ops(p, [op])
    assert applied[0].verification_status == "rejected"
