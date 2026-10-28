"""Phase 1 revise + candidate packaging integration."""

from __future__ import annotations

from backend.app.core.config import DawMode, Settings
from backend.app.daw.fake import FakeDawAdapter
from backend.app.daw.midi_fallback import MidiExportAdapter
from backend.app.services.compose import compose_from_prompt
from backend.app.services.revise import revise_project
from backend.app.storage.assets import AssetStore


def test_compose_candidate_package(tmp_settings: Settings) -> None:
    result = compose_from_prompt(
        "mellow Afrobeats 110 BPM in A minor",
        seed=2026,
        settings=tmp_settings,
        adapter=FakeDawAdapter(),
    )
    c = result.candidate
    assert c.seed == 2026
    assert c.cir_snapshot_ref
    assert c.one_line_diff
    assert c.loudness_notes.target_lufs == -14.0
    assert result.brief.genre_template_id == "afrobeats"
    assert len(result.next_moves) <= 3
    assert all(m.action_type for m in result.next_moves)


def test_revise_keeps_drums(tmp_settings: Settings) -> None:
    daw = FakeDawAdapter()
    composed = compose_from_prompt(
        "Afrobeats 110 BPM",
        seed=42,
        settings=tmp_settings,
        adapter=daw,
    )
    revised = revise_project(
        composed.project.id,
        "keep the drums, soften bass",
        seed=43,
        settings=tmp_settings,
        adapter=daw,
    )
    assert revised.diff.locked_roles_respected
    assert "drums" not in revised.diff.roles_changed or revised.diff.note_count_delta_by_role.get(
        "drums", 0
    ) == 0
    drums_before = next(t for t in revised.parent.tracks if t.role.value == "drums")
    drums_after = next(t for t in revised.project.tracks if t.role.value == "drums")
    assert [n.model_dump() for n in drums_before.note_events] == [
        n.model_dump() for n in drums_after.note_events
    ]
    # Soften bass should reduce velocities
    bass_before = next(t for t in revised.parent.tracks if t.role.value == "bass")
    bass_after = next(t for t in revised.project.tracks if t.role.value == "bass")
    assert sum(n.velocity for n in bass_after.note_events) < sum(
        n.velocity for n in bass_before.note_events
    )
    assert revised.candidate.one_line_diff
    assert revised.undo_available
    assert revised.snapshot_ref


def test_midi_export_revise_path(tmp_settings: Settings) -> None:
    settings = Settings(
        app_env="test",
        log_level="WARNING",
        workspace_dir=tmp_settings.workspace_dir,
        database_url=tmp_settings.database_url,
        daw_mode=DawMode.MIDI_EXPORT,
    )
    assets = AssetStore(settings)
    composed = compose_from_prompt(
        "Amapiano 112 BPM",
        seed=7,
        settings=settings,
        adapter=MidiExportAdapter(assets),
    )
    revised = revise_project(
        composed.project.id,
        "keep the drums, change bass",
        seed=8,
        settings=settings,
        adapter=MidiExportAdapter(assets),
    )
    assert revised.diff.locked_roles_respected
    assert revised.midi_paths["bass"].exists()
