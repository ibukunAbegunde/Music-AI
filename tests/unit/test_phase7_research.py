"""Phase 7 research stubs — interfaces, heuristics, multi-DAW registry."""

from __future__ import annotations

from uuid import uuid4

import pytest

from backend.app.core.config import Settings
from backend.app.daw.registry import get_daw_adapter, list_daw_adapters
from backend.app.daw.stubs import AbletonStubAdapter, LogicStubAdapter
from backend.app.models.schemas import DawOperation, MusicProject, ProjectStatus, TrackRole
from backend.app.music.brief import parse_brief
from backend.app.research.action_effect import (
    HeuristicActionEffectPredictor,
    RevisionOutcome,
    append_revision_outcome,
    list_revision_outcomes,
    predict_effect,
)
from backend.app.research.dual_path import assert_cir_editable_for_role_edit, dual_path_policy
from backend.app.research.eval_harness import BlindListeningHarness, run_phase7_baseline_eval
from backend.app.research.midi_specialist import (
    DeterministicMidiSpecialist,
    MidiSpecialistRequest,
    get_midi_specialist,
)
from backend.app.research.mix_heuristics import run_advanced_mix_heuristics
from backend.app.research.registry import research_status
from backend.app.research.vocal import StubVocalWorkflow, get_vocal_workflow


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        workspace_dir=tmp_path / "ws",
        database_url=f"sqlite:///{tmp_path / 'ws' / 'music_ai.db'}",
    )


def test_deterministic_specialist_composes(settings: Settings) -> None:
    from backend.app.research.midi_specialist import compose_cir_from_brief

    brief = parse_brief("mellow Afrobeats 110 BPM in A minor", seed=42, bars=8)
    result = DeterministicMidiSpecialist().compose(
        MidiSpecialistRequest(brief=brief, name="t")
    )
    assert result.mode == "deterministic"
    assert result.cir_is_system_of_record is True
    assert len(result.project.tracks) >= 3
    assert get_midi_specialist(settings).name == "deterministic_generators"
    shared = compose_cir_from_brief(brief, settings=settings, name="shared")
    assert shared.specialist_name == "deterministic_generators"
    assert shared.mode == "deterministic"


def test_optional_specialist_refuses_without_flag(settings: Settings) -> None:
    settings.midi_specialist = "optional"
    settings.music_ai_allow_specialist_download = False
    with pytest.raises(RuntimeError, match="MUSIC_AI_ALLOW_SPECIALIST_DOWNLOAD"):
        get_midi_specialist(settings)


def test_action_effect_outcome_roundtrip(settings: Settings) -> None:
    settings.ensure_workspace()
    outcome = RevisionOutcome(
        project_id=uuid4(),
        iteration_index=0,
        ops=[
            DawOperation(
                action_type="soften_velocity",
                target_role="bass",
                idempotency_key="k1",
            )
        ],
        before_technical=0.5,
        before_musical=0.6,
        after_technical=0.7,
        after_musical=0.75,
        accepted=True,
    )
    append_revision_outcome(outcome, settings=settings)
    rows = list_revision_outcomes(settings=settings, accepted_only=True)
    assert len(rows) == 1
    assert rows[0].delta_technical == pytest.approx(0.2)
    pred = HeuristicActionEffectPredictor(rows).predict(
        outcome.ops, before_technical=0.5, before_musical=0.6
    )
    assert pred.evidence_n == 1
    assert pred.predicted_delta_technical == pytest.approx(0.2)
    # Empty log → weak prior still returns a prediction
    empty = HeuristicActionEffectPredictor([]).predict(
        outcome.ops, before_technical=0.5, before_musical=0.6
    )
    assert empty.evidence_n == 0
    assert empty.predictor_name == "heuristic_action_effect"
    # Wired helper reads persisted outcomes
    wired = predict_effect(outcome.ops, settings=settings)
    assert wired.evidence_n >= 1


def test_advanced_mix_heuristics(settings: Settings) -> None:
    brief = parse_brief("trap 140 BPM", seed=7, bars=8)
    project = DeterministicMidiSpecialist().compose(
        MidiSpecialistRequest(brief=brief)
    ).project
    report = run_advanced_mix_heuristics(project)
    assert report.heuristics
    ids = {h.id for h in report.heuristics}
    assert "sidechain_proxy" in ids
    assert "master_bus_headroom" in ids
    assert 0.0 <= report.overall_mix_score <= 1.0


def test_vocal_stub_guide_melody(settings: Settings) -> None:
    brief = parse_brief("rnb 90 BPM", seed=3, bars=8)
    project = DeterministicMidiSpecialist().compose(
        MidiSpecialistRequest(brief=brief)
    ).project
    wf = get_vocal_workflow(settings)
    plan = wf.plan_vocals(project, lyric_hint="la la")
    assert plan.mode == "stub"
    updated = wf.apply_guide_melody(project, plan)
    assert any(t.role == TrackRole.VOCAL for t in updated.tracks)
    settings.vocal_workflow = "optional"
    with pytest.raises(RuntimeError, match="VOCAL_MODEL"):
        get_vocal_workflow(settings)


def test_multi_daw_registry_and_stubs() -> None:
    ids = {a["id"] for a in list_daw_adapters()}
    assert "fake" in ids
    assert "midi_export" in ids
    assert "ableton" in ids
    assert "logic" in ids
    assert "reaper" in ids
    assert "postfader" in ids
    ableton = get_daw_adapter("ableton")
    assert isinstance(ableton, AbletonStubAdapter)
    refused = ableton.create_or_update_notes(
        MusicProject(
            name="x",
            bpm=120,
            length_bars=8,
            status=ProjectStatus.CREATED,
        )
    )
    assert refused.supported is False
    assert refused.succeeded is False
    probe = LogicStubAdapter().probe_capabilities()
    assert probe.observations["capabilities"]["stub"] is True


def test_postfader_compose_fails_honestly(settings: Settings, tmp_path) -> None:
    """DAW_MODE=postfader must not return OK with buried daw.succeeded=False."""
    from backend.app.core.config import DawMode
    from backend.app.daw.base import DawWriteError
    from backend.app.daw.registry import adapter_for_settings
    from backend.app.daw.stubs import PostFaderStubAdapter
    from backend.app.services.compose import compose_from_prompt, select_adapter

    settings.daw_mode = DawMode.POSTFADER
    settings.workspace_dir = tmp_path / "ws_post"
    settings.database_url = f"sqlite:///{tmp_path / 'ws_post' / 'music_ai.db'}"
    settings.ensure_workspace()

    adapter = adapter_for_settings(settings)
    assert isinstance(adapter, PostFaderStubAdapter)
    assert isinstance(select_adapter(settings, None), PostFaderStubAdapter)  # type: ignore[arg-type]

    with pytest.raises(DawWriteError, match="postfader|stub|DAW write failed"):
        compose_from_prompt("trap 140 BPM", seed=9, settings=settings)


def test_dual_path_policy() -> None:
    policy = dual_path_policy()
    assert policy.cir_is_system_of_record is True
    assert policy.black_box_audio_only_forbidden is True
    brief = parse_brief("afrobeats", seed=1, bars=8)
    project = DeterministicMidiSpecialist().compose(
        MidiSpecialistRequest(brief=brief)
    ).project
    guard = assert_cir_editable_for_role_edit(project)
    assert guard["ok"] is True


def test_research_eval_harness(settings: Settings) -> None:
    result = run_phase7_baseline_eval(
        "mellow Afrobeats 110 BPM", seed=42, bars=8, settings=settings
    )
    assert result.simulation is True
    assert result.blind_listening_status == "not_run"
    assert result.preference_proxy in ("baseline", "candidate", "tie")
    # Default specialist == deterministic → expect tie
    assert result.preference_proxy == "tie"

    harness = BlindListeningHarness()
    harness.add_pair(baseline_project_id="a", candidate_project_id="b")
    harness.record_choice(0, "candidate", reason="prefer bounce")
    assert harness.preference_rate(prefer="candidate") == 1.0


def test_research_status_lists_capabilities(settings: Settings) -> None:
    status = research_status(settings)
    assert status["phase"] == 7
    caps = {c["id"] for c in status["capabilities"]}
    assert "midi_specialist" in caps
    assert "action_effect" in caps
    assert "multi_daw" in caps
    assert status["daw_adapters"]
