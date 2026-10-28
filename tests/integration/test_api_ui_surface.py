"""Smoke tests for the local FastAPI UI surface."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core import config as config_mod
from backend.app.core.config import DawMode, Settings
from backend.app.main import app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    ws = tmp_path / "workspace"
    settings = Settings(
        app_env="test",
        workspace_dir=ws,
        database_url=f"sqlite:///{ws / 'test.db'}",
        daw_mode=DawMode.SIMULATION,
        log_level="WARNING",
        allow_cloud_audio=False,
        allow_cloud_llm=False,
    )
    settings.ensure_workspace()

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


def test_health_and_settings(client: TestClient) -> None:
    h = client.get("/api/health")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"
    s = client.get("/api/settings")
    assert s.status_code == 200
    assert s.json()["daw_mode"] == "simulation"


def test_compose_revise_versions_jobs(client: TestClient) -> None:
    r = client.post(
        "/api/compose",
        json={
            "prompt": "mellow Afrobeats 110 BPM in A minor",
            "seed": 42,
            "bars": 8,
            "locked_roles": ["drums"],
            "mode": "loop",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    project_id = body["project"]["id"]
    assert body["candidate"]["one_line_diff"]
    assert body["job_id"]
    assert any(t["locked"] for t in body["project"]["tracks"] if t["role"] == "drums")

    jobs = client.get("/api/jobs").json()
    assert any(j["id"] == body["job_id"] for j in jobs)

    rev = client.post(
        f"/api/projects/{project_id}/revise",
        json={"prompt": "keep the drums, soften bass", "seed": 43},
    )
    assert rev.status_code == 200, rev.text
    assert rev.json()["diff"]["one_line_summary"]

    versions = client.get(f"/api/projects/{project_id}/versions")
    assert versions.status_code == 200
    assert len(versions.json()) >= 2


def test_ref_compose_and_ab(client: TestClient) -> None:
    r = client.post(
        "/api/ref-compose",
        json={
            "prompt": "original mellow Afrobeats with bass bounce",
            "traits": ["bass_bounce", "percussion_texture"],
            "n": 2,
            "seed": 7,
            "bars": 8,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    project_id = body["project_id"]
    assert len(body["candidates"]) == 2

    ab = client.post(
        f"/api/projects/{project_id}/ab",
        json={"index_a": 0, "index_b": 1, "choice": "a", "reason": "test"},
    )
    assert ab.status_code == 200, ab.text
    assert ab.json()["musical_diff"]["one_line_summary"]
    assert ab.json()["preference"]["user_choice"] == "a"


def test_demo_reference_pipeline(client: TestClient) -> None:
    r = client.post("/api/references/demo-fixture")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["asset"]["id"]
    assert body["stems"]
    listed = client.get("/api/references")
    assert listed.status_code == 200
    assert any(x["asset"]["id"] == body["asset"]["id"] for x in listed.json())


def test_compose_full_mode(client: TestClient) -> None:
    """Full-length compose must accept bars≥32 (no 422 le=16 / 400 clash)."""
    r = client.post(
        "/api/compose",
        json={
            "prompt": "mellow Afrobeats full instrumental arrangement",
            "seed": 11,
            "bars": 32,
            "mode": "full",
            "scratch_or_release": "scratch",
            "autonomy_mode": "collaborative",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["project"]["length_bars"] >= 32
    assert body["arrangement"]["plan"]
    assert body["job_id"]
    # Scratch + collaborative → not gated for DAW write in simulation.
    assert body["arrangement"]["gated"] is False

    # Undersized bars with mode=full coerce to default 64 (not 422).
    coerced = client.post(
        "/api/compose",
        json={
            "prompt": "full length coerce bars",
            "seed": 12,
            "bars": 8,
            "mode": "full",
            "scratch_or_release": "scratch",
        },
    )
    assert coerced.status_code == 200, coerced.text
    assert coerced.json()["project"]["length_bars"] >= 32

    # Release + autonomous without force → gated (honest release gate).
    gated = client.post(
        "/api/compose",
        json={
            "prompt": "release gated full",
            "seed": 13,
            "bars": 32,
            "mode": "full",
            "scratch_or_release": "release",
            "autonomy_mode": "autonomous",
        },
    )
    assert gated.status_code == 200, gated.text
    assert gated.json()["arrangement"]["gated"] is True


def test_compose_with_borrow_traits(client: TestClient) -> None:
    """Workspace borrow chips must condition generation (not decorative)."""
    r = client.post(
        "/api/compose",
        json={
            "prompt": "original mellow Afrobeats with bass bounce",
            "seed": 21,
            "bars": 8,
            "mode": "loop",
            "traits": ["bass_bounce", "groove"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["traits"] == ["bass_bounce", "groove"]
    chip_traits = {c["trait"] for c in body["brief"]["borrow_chips"]}
    assert "bass_bounce" in chip_traits
    assert body["candidate"]["one_line_diff"]
