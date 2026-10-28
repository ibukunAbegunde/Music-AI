"""Phase 6 exit: brief/reference → full instrumental + MIDI + versioned project."""

from __future__ import annotations

from pathlib import Path

from backend.app.core.config import DawMode, Settings
from backend.app.daw.fake import FakeDawAdapter
from backend.app.daw.midi_fallback import MidiExportAdapter
from backend.app.services.full_compose import (
    full_compose_from_prompt,
    full_compose_from_reference,
    load_arrangement_plan,
)
from backend.app.services.versions import list_version_timeline, load_version_project
from backend.app.storage.assets import AssetStore


def test_full_compose_brief_to_versioned_midi(tmp_settings: Settings) -> None:
    tmp_settings.ensure_workspace()
    adapter = FakeDawAdapter()
    result = full_compose_from_prompt(
        "mellow Afrobeats 110 BPM in A minor",
        seed=42,
        structure_id="afrobeats_full",
        scratch_or_release="scratch",
        settings=tmp_settings,
        adapter=adapter,
    )
    assert result.project.length_bars == 64
    assert len(result.project.sections) >= 4
    assert result.project.sections[0].name == "intro"
    assert result.version.id == result.project.version_id
    assert result.candidate is not None
    assert result.gated is False
    assert result.daw_result.succeeded
    assert len(result.arrange_results) == len(result.project.sections)
    assert len(adapter.sections) == len(result.project.sections)

    # Playable MIDI export path
    for role in ("drums", "bass", "chord", "combined"):
        assert role in result.midi_paths
        assert result.midi_paths[role].exists()
        assert result.midi_paths[role].stat().st_size > 0

    # Versioned editable CIR
    assets = AssetStore(tmp_settings)
    cir = assets.root / "projects" / str(result.project.id) / "versions" / f"{result.version.id}.json"
    assert cir.exists()
    plan_disk = load_arrangement_plan(result.project.id, settings=tmp_settings)
    assert plan_disk["structure_template_id"] == "afrobeats_full"
    assert plan_disk["length_bars"] == 64

    timeline = list_version_timeline(result.project.id, settings=tmp_settings)
    assert len(timeline) >= 1
    loaded = load_version_project(result.project.id, result.version.id, settings=tmp_settings)
    assert loaded is not None
    assert loaded.length_bars == 64
    assert len(loaded.sections) == len(result.project.sections)

    # Manual FL steps documented on disk
    steps_path = (
        tmp_settings.workspace_dir
        / "projects"
        / str(result.project.id)
        / "manual_fl_steps.json"
    )
    assert steps_path.exists()
    assert any("Playlist" in s or "playlist" in s.lower() for s in result.manual_steps)


def test_full_compose_release_gates_daw_write(tmp_settings: Settings) -> None:
    tmp_settings.ensure_workspace()
    adapter = FakeDawAdapter()
    result = full_compose_from_prompt(
        "trap 140 BPM",
        seed=7,
        structure_id="trap_full",
        scratch_or_release="release",
        autonomy_mode="collaborative",
        settings=tmp_settings,
        adapter=adapter,
    )
    assert result.gated is True
    assert result.daw_result.attempted is False
    assert adapter.project is None  # no write
    # MIDI still exported for review
    assert result.midi_paths["combined"].exists()
    assert "release_mode_daw_write" in result.plan.approvals_required


def test_full_compose_from_reference_fixture(tmp_settings: Settings) -> None:
    tmp_settings.ensure_workspace()
    result = full_compose_from_reference(
        "original mellow Afrobeats with this bass bounce",
        traits=["bass_bounce", "percussion_texture"],
        fixture="afrobeats",
        seed=11,
        bars=48,
        settings=tmp_settings,
        adapter=FakeDawAdapter(),
    )
    assert result.project.length_bars == 48
    assert result.project.reference_ids
    assert any(c.trait == "bass_bounce" for c in result.brief.borrow_chips)
    assert result.midi_paths["drums"].exists()


def test_full_compose_midi_export_mode(tmp_settings: Settings) -> None:
    tmp_settings.daw_mode = DawMode.MIDI_EXPORT
    tmp_settings.ensure_workspace()
    assets = AssetStore(tmp_settings)
    result = full_compose_from_prompt(
        "R&B 90 BPM chill",
        seed=5,
        structure_id="rnb_full",
        settings=tmp_settings,
        adapter=MidiExportAdapter(assets),
    )
    assert result.project.length_bars == 64
    assert result.arrangement_plan_path is not None
    assert Path(result.arrangement_plan_path).exists()
    # MidiExport arrange_section returns user_action_required (manual Playlist)
    assert result.arrange_results
    assert any(r.user_action_required for r in result.arrange_results)
