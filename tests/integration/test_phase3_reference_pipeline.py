"""Phase 3 exit: reference → novel MIDI, A/B proxies, keep drums / replace bass."""

from __future__ import annotations

from backend.app.core.config import DawMode, Settings
from backend.app.daw.fake import FakeDawAdapter
from backend.app.daw.midi_fallback import MidiExportAdapter
from backend.app.models.db import init_db
from backend.app.music.midi import read_note_ons
from backend.app.music.recipes import apply_recipe, recipe_from_project, save_recipe
from backend.app.services.ab_compare import compare_session_pair
from backend.app.services.reference_compose import compose_from_reference
from backend.app.services.revise import revise_project
from backend.app.services.versions import list_version_timeline
from backend.app.storage.assets import AssetStore
from backend.app.storage.repository import ProjectRepository


def test_ref_compose_n_candidates_8_to_16_bars(tmp_settings: Settings) -> None:
    result = compose_from_reference(
        "original mellow Afrobeats groove, borrow bass bounce and percussion",
        traits=["bass_bounce", "percussion_texture"],
        fixture_genre="afrobeats",
        n=3,
        seed=42,
        bars=16,
        settings=tmp_settings,
        adapter=FakeDawAdapter(),
    )
    assert result.multi.baseline.project.length_bars == 16
    assert len(result.multi.candidates) == 3
    seeds = [c.seed for c in result.multi.candidates]
    assert seeds == [42, 43, 44]
    # Distinct MIDI across seeds
    bass_bytes = [
        c.midi_paths["bass"].read_bytes() for c in result.multi.candidates
    ]
    assert len({b for b in bass_bytes}) >= 2
    for c in result.multi.candidates:
        assert c.candidate.seed == c.seed
        assert c.candidate.cir_snapshot_ref
        assert c.candidate.loudness_notes.target_lufs == -14.0
        assert c.candidate.one_line_diff
        assert len(read_note_ons(c.midi_paths["combined"])) > 0
    # Conditioning recorded
    assert "bass_bounce" in result.multi.conditioning["traits"]
    assert result.analyzer == "FixtureReferenceAnalyzer"
    assert "Phase 2" in result.phase2_note


def test_ab_midi_proxy_and_musical_diff(tmp_settings: Settings) -> None:
    result = compose_from_reference(
        "Afrobeats 110 BPM novel groove",
        n=2,
        seed=7,
        bars=8,
        settings=tmp_settings,
        adapter=FakeDawAdapter(),
    )
    project_id = result.multi.baseline.project.id
    ab = compare_session_pair(
        project_id,
        index_a=0,
        index_b=1,
        choice="b",
        reason="prefer bass motion",
        settings=tmp_settings,
    )
    assert ab.path_mode == "midi_proxy"
    assert ab.side_a.midi_proxy_path and ab.side_a.midi_proxy_path.endswith("combined.mid")
    assert ab.side_b.midi_proxy_path and ab.side_b.midi_proxy_path.endswith("combined.mid")
    assert ab.musical_diff.one_line_summary
    assert ab.preference is not None
    assert ab.preference.user_choice == "b"
    assert ab.session_path.exists()


def test_keep_drums_replace_bass_revision(tmp_settings: Settings) -> None:
    result = compose_from_reference(
        "Afrobeats 110 BPM in A minor",
        traits=["bass_bounce"],
        n=2,
        seed=100,
        bars=8,
        settings=tmp_settings,
        adapter=FakeDawAdapter(),
    )
    project_id = result.multi.baseline.project.id
    # Tip is last candidate; revise keep drums / replace bass
    rev = revise_project(
        project_id,
        "keep the drums, replace bass",
        seed=200,
        settings=tmp_settings,
        adapter=FakeDawAdapter(),
    )
    assert rev.diff.locked_roles_respected
    assert "drums" not in rev.diff.roles_changed
    assert "bass" in rev.diff.roles_changed
    parent_drums = next(t for t in rev.parent.tracks if t.role.value == "drums")
    new_drums = next(t for t in rev.project.tracks if t.role.value == "drums")
    assert [n.model_dump() for n in parent_drums.note_events] == [
        n.model_dump() for n in new_drums.note_events
    ]
    parent_bass = next(t for t in rev.parent.tracks if t.role.value == "bass")
    new_bass = next(t for t in rev.project.tracks if t.role.value == "bass")
    assert [n.model_dump() for n in parent_bass.note_events] != [
        n.model_dump() for n in new_bass.note_events
    ]
    # Version timeline grew
    timeline = list_version_timeline(project_id, settings=tmp_settings)
    assert len(timeline) >= 3  # 2 candidates + revise
    assert any("bass" in (e.one_line_diff or "") for e in timeline)


def test_recipe_apply_respects_locks(tmp_settings: Settings) -> None:
    composed = compose_from_reference(
        "Amapiano 112 BPM",
        n=1,
        seed=5,
        bars=8,
        settings=tmp_settings,
        adapter=FakeDawAdapter(),
    )
    project_id = composed.multi.baseline.project.id
    # Lock drums on tip then save recipe
    locked = revise_project(
        project_id,
        "keep the drums, soften bass",
        seed=6,
        settings=tmp_settings,
        adapter=FakeDawAdapter(),
    )
    assets = AssetStore(tmp_settings)
    recipe = recipe_from_project(locked.project, name="amapiano-winner")
    assert "drums" in recipe.locked_roles
    save_recipe(recipe, assets)

    multi = apply_recipe(
        recipe.id,
        assets,
        prompt="Amapiano variation from recipe",
        seed=50,
        n=2,
        settings=tmp_settings,
        adapter=FakeDawAdapter(),
    )
    assert multi.brief.recipe_id == recipe.id
    assert "drums" in multi.brief.locked_roles
    for c in multi.candidates:
        drums = next(t for t in c.project.tracks if t.role.value == "drums")
        assert drums.locked


def test_ref_compose_midi_export_mode(tmp_settings: Settings) -> None:
    settings = Settings(
        app_env="test",
        log_level="WARNING",
        workspace_dir=tmp_settings.workspace_dir,
        database_url=tmp_settings.database_url,
        daw_mode=DawMode.MIDI_EXPORT,
    )
    assets = AssetStore(settings)
    result = compose_from_reference(
        "trap 140 BPM",
        fixture_genre="trap",
        traits=["bass_bounce"],
        n=2,
        seed=3,
        bars=12,
        settings=settings,
        adapter=MidiExportAdapter(assets),
    )
    assert result.multi.baseline.project.length_bars == 12
    assert result.multi.baseline.project.bpm == 140.0
    repo = ProjectRepository(init_db(settings))
    versions = repo.list_versions(result.multi.baseline.project.id)
    assert len(versions) == 2
