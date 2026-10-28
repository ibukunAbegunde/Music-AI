"""Phase 7 integration — revision outcomes + research API + MIDI audition."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core import config as config_mod
from backend.app.core.config import DawMode, Settings
from backend.app.main import app
from backend.app.research.action_effect import list_revision_outcomes
from backend.app.services.compose import compose_from_prompt
from backend.app.services.revision_loop import run_revision_loop


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    ws = tmp_path / "ws"
    s = Settings(
        app_env="test",
        workspace_dir=ws,
        database_url=f"sqlite:///{ws / 'music_ai.db'}",
        daw_mode=DawMode.SIMULATION,
        log_level="WARNING",
    )
    s.ensure_workspace()
    return s


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    def _settings() -> Settings:
        return settings

    config_mod.get_settings.cache_clear()
    monkeypatch.setattr(config_mod, "get_settings", _settings)

    import backend.app.main as main_mod
    from backend.app.api import deps

    monkeypatch.setattr(main_mod, "get_settings", _settings)
    deps._session_factory.cache_clear()
    monkeypatch.setattr(deps, "get_settings", _settings)
    monkeypatch.setattr(
        deps,
        "_session_factory",
        lambda: __import__("backend.app.models.db", fromlist=["init_db"]).init_db(settings),
    )

    with TestClient(app) as c:
        yield c


def test_revision_loop_logs_action_effect_outcomes(settings: Settings) -> None:
    composed = compose_from_prompt(
        "mellow Afrobeats 110 BPM in A minor", seed=42, settings=settings
    )
    result = run_revision_loop(
        composed.project.id,
        settings=settings,
        apply_ops=True,
        max_iterations=2,
        fixture_id="muddy_sub",
    )
    assert result.iterations
    outcomes = list_revision_outcomes(settings=settings, project_id=composed.project.id)
    assert len(outcomes) == len(result.iterations)
    loop_meta = result.metadata.get("revision_loop") or {}
    assert "action_effect_outcomes" in loop_meta
    assert len(loop_meta["action_effect_outcomes"]) == len(outcomes)


def test_compose_uses_specialist_hook(settings: Settings) -> None:
    from backend.app.services.compose import load_project_metadata
    from backend.app.services.full_compose import full_compose_from_prompt

    result = compose_from_prompt("trap 140 BPM", seed=11, settings=settings)
    assert result.project.seed == 11
    assert len(result.midi_paths) >= 1
    assert result.specialist_name == "deterministic_generators"
    assert result.specialist_mode == "deterministic"
    meta = load_project_metadata(result.project.id, settings=settings)
    assert meta["specialist_name"] == "deterministic_generators"
    assert meta["specialist_mode"] == "deterministic"

    full = full_compose_from_prompt(
        "mellow Afrobeats 110 BPM", seed=3, bars=48, settings=settings
    )
    assert full.specialist_name == "deterministic_generators"
    assert full.specialist_mode == "deterministic"
    full_meta = load_project_metadata(full.project.id, settings=settings)
    assert full_meta["specialist_name"] == "deterministic_generators"
    assert full_meta["specialist_mode"] == "deterministic"


def test_research_api_and_midi_audition(client: TestClient, settings: Settings) -> None:
    composed = compose_from_prompt(
        "mellow Afrobeats 110 BPM", seed=5, settings=settings
    )
    status = client.get("/api/research/status")
    assert status.status_code == 200
    body = status.json()
    assert body["phase"] == 7
    assert any(c["id"] == "midi_specialist" for c in body["capabilities"])

    eval_res = client.post("/api/research/eval", params={"prompt": "afrobeats", "seed": 1})
    assert eval_res.status_code == 200
    assert eval_res.json()["simulation"] is True

    audition = client.get(f"/api/projects/{composed.project.id}/midi-audition")
    assert audition.status_code == 200
    data = audition.json()
    assert data["normalization_status"] == "midi_proxy"
    assert data["playable_in_ui"] is False
    assert data["midi_paths"]

    job = client.post("/api/jobs", json={"kind": "compose", "detail": {}}).json()
    cancelled = client.post(f"/api/jobs/{job['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["cancel_stub"] is True
