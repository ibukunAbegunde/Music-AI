"""Unit: pairwise dataset + listening journal + style vectors."""

from __future__ import annotations

from uuid import uuid4

from backend.app.core.config import Settings
from backend.app.models.schemas import ListeningJournalEntry, new_id
from backend.app.music.recipes import recipe_from_project, save_recipe
from backend.app.services.compose import compose_from_prompt
from backend.app.daw.fake import FakeDawAdapter
from backend.app.taste.dataset import (
    append_comparison,
    list_comparisons,
    list_journal,
    record_ab_preference,
    record_journal_entry,
    taste_profile_summary,
)
from backend.app.taste.style_vectors import derive_style_vectors, list_style_vectors
from backend.app.storage.assets import AssetStore


def test_record_and_list_comparisons(tmp_settings: Settings) -> None:
    tmp_settings.ensure_workspace()
    pid = uuid4()
    comp = record_ab_preference(
        project_id=pid,
        version_a_id=uuid4(),
        version_b_id=uuid4(),
        render_a_id=uuid4(),
        render_b_id=uuid4(),
        choice="b",
        reason="bass",
        tags=["bass"],
        context={"genre": "afrobeats"},
        feature_a=[0.1] * 32,
        feature_b=[0.2] * 32,
        settings=tmp_settings,
    )
    listed = list_comparisons(settings=tmp_settings, decisive_only=True)
    assert len(listed) == 1
    assert listed[0].id == comp.id
    assert listed[0].feature_a_ref
    assert listed[0].project_id == pid


def test_listening_journal(tmp_settings: Settings) -> None:
    tmp_settings.ensure_workspace()
    entry = ListeningJournalEntry(
        project_id=uuid4(),
        notes="love the bounce",
        tags=["groove"],
        rating=4.5,
    )
    path = record_journal_entry(entry, settings=tmp_settings)
    assert path.exists()
    entries = list_journal(settings=tmp_settings)
    assert len(entries) == 1
    assert entries[0].notes == "love the bounce"


def test_taste_profile_no_invented_prefs(tmp_settings: Settings) -> None:
    tmp_settings.ensure_workspace()
    summary = taste_profile_summary(settings=tmp_settings)
    assert summary.n_comparisons == 0
    assert summary.n_journal_entries == 0
    assert summary.active_model_id is None
    assert any("no invented" in x.lower() or "recorded" in x.lower() for x in summary.limitations)


def test_style_vectors_only_from_approved(tmp_settings: Settings) -> None:
    tmp_settings.ensure_workspace()
    # no recipes → empty
    assert derive_style_vectors(settings=tmp_settings) == []

    result = compose_from_prompt(
        "Afrobeats 110 BPM in A minor",
        seed=11,
        settings=tmp_settings,
        adapter=FakeDawAdapter(),
    )
    recipe = recipe_from_project(result.project, name="winner", approved=False)
    assets = AssetStore(tmp_settings)
    save_recipe(recipe, assets)
    # unapproved → still empty when approved_only
    assert derive_style_vectors(settings=tmp_settings, approved_only=True) == []

    recipe.approved = True
    save_recipe(recipe, assets)
    derived = derive_style_vectors(settings=tmp_settings, approved_only=True)
    assert len(derived) >= 1
    assert derived[0].dim == 64
    assert derived[0].encoder_name == "simulation_cir_projection"
    assert len(list_style_vectors(settings=tmp_settings)) >= 1


def test_append_comparison_idempotent_index(tmp_settings: Settings) -> None:
    from backend.app.models.schemas import PreferenceComparison, utcnow

    tmp_settings.ensure_workspace()
    comp = PreferenceComparison(
        context={},
        render_a_id=new_id(),
        render_b_id=new_id(),
        user_choice="tie",
        timestamp=utcnow(),
    )
    append_comparison(comp, settings=tmp_settings)
    append_comparison(comp, settings=tmp_settings)
    assert len(list_comparisons(settings=tmp_settings)) == 1
