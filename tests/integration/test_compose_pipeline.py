"""End-to-end Phase 0 compose pipeline in simulation mode."""

from __future__ import annotations

from backend.app.core.config import DawMode, Settings
from backend.app.daw.fake import FakeDawAdapter
from backend.app.daw.midi_fallback import MidiExportAdapter
from backend.app.models.db import init_db
from backend.app.music.midi import read_note_ons
from backend.app.services.compose import compose_from_prompt
from backend.app.storage.assets import AssetStore
from backend.app.storage.repository import ProjectRepository


def test_compose_simulation_persists_and_exports(tmp_settings: Settings) -> None:
    result = compose_from_prompt(
        "mellow Afrobeats groove 110 BPM in A minor with Rhodes chords",
        seed=2026,
        settings=tmp_settings,
        adapter=FakeDawAdapter(),
    )
    assert result.project.seed == 2026
    assert result.project.bpm == 110.0
    assert result.metadata_path.exists()
    for role in ("drums", "bass", "chord"):
        path = result.midi_paths[role]
        assert path.exists()
        assert len(read_note_ons(path)) > 0

    repo = ProjectRepository(init_db(tmp_settings))
    loaded = repo.get_project(result.project.id)
    assert loaded is not None
    assert loaded.generation_brief is not None
    versions = repo.list_versions(result.project.id)
    assert len(versions) == 1
    assert versions[0].exported_midi_paths


def test_compose_midi_export_adapter(tmp_settings: Settings) -> None:
    tmp_settings = Settings(
        app_env="test",
        log_level="WARNING",
        workspace_dir=tmp_settings.workspace_dir,
        database_url=tmp_settings.database_url,
        daw_mode=DawMode.MIDI_EXPORT,
    )
    assets = AssetStore(tmp_settings)
    adapter = MidiExportAdapter(assets)
    result = compose_from_prompt(
        "Amapiano 112 BPM",
        seed=11,
        settings=tmp_settings,
        adapter=adapter,
    )
    assert result.daw_result.succeeded
    assert result.daw_result.verified
    assert result.daw_result.user_action_required is not None
    verify = adapter.verify_postcondition({"roles": ["drums", "bass", "chord"], "min_files": 3})
    assert verify.succeeded


def test_same_prompt_same_seed_same_midi(tmp_settings: Settings) -> None:
    a = compose_from_prompt("trap 140 BPM", seed=42, settings=tmp_settings, adapter=FakeDawAdapter())
    # Fresh settings path but same logical seed — use sibling dir
    from pathlib import Path

    ws2 = Path(str(tmp_settings.workspace_dir) + "_b")
    settings_b = Settings(
        app_env="test",
        log_level="WARNING",
        workspace_dir=ws2,
        database_url=f"sqlite:///{ws2 / 'test.db'}",
        daw_mode=DawMode.SIMULATION,
    )
    b = compose_from_prompt("trap 140 BPM", seed=42, settings=settings_b, adapter=FakeDawAdapter())
    assert a.midi_paths["bass"].read_bytes() == b.midi_paths["bass"].read_bytes()
    assert a.midi_paths["chord"].read_bytes() == b.midi_paths["chord"].read_bytes()
