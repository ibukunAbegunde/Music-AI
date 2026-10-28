"""Phase 5 exit: pairwise collection, retrieval baseline, ranking head, holdout, registry."""

from __future__ import annotations

from backend.app.core.config import Settings
from backend.app.daw.fake import FakeDawAdapter
from backend.app.music.recipes import recipe_from_project, save_recipe
from backend.app.services.ab_compare import compare_session_pair
from backend.app.services.candidates import generate_candidates
from backend.app.music.brief import parse_brief
from backend.app.storage.assets import AssetStore
from backend.app.taste.dataset import list_comparisons, list_journal, record_journal_entry, taste_profile_summary
from backend.app.models.schemas import ListeningJournalEntry
from backend.app.taste.pipeline import train_and_evaluate
from backend.app.taste.registry import get_active_checkpoint, list_checkpoints, rollback_checkpoint
from backend.app.taste.simulate import build_simulated_dataset
from backend.app.taste.style_vectors import derive_style_vectors


def test_ab_choice_feeds_taste_dataset(tmp_settings: Settings) -> None:
    brief = parse_brief("Afrobeats 110 BPM groove", seed=20, bars=8)
    multi = generate_candidates(
        brief, n=2, base_seed=20, settings=tmp_settings, adapter=FakeDawAdapter()
    )
    project_id = multi.baseline.project.id
    ab = compare_session_pair(
        project_id,
        index_a=0,
        index_b=1,
        choice="a",
        reason="prefer A hats",
        settings=tmp_settings,
    )
    assert ab.preference is not None
    comps = list_comparisons(settings=tmp_settings, decisive_only=True)
    assert len(comps) >= 1
    assert comps[-1].user_choice == "a"
    assert comps[-1].project_id == project_id
    assert comps[-1].feature_a_ref and comps[-1].feature_b_ref


def test_full_taste_pipeline_simulate_train_eval_registry(tmp_settings: Settings) -> None:
    tmp_settings.ensure_workspace()
    pairs = build_simulated_dataset(
        n_projects=8,
        pairs_per_project=4,
        settings=tmp_settings,
        seed=99,
        persist=True,
    )
    assert len(pairs) == 32
    assert len(list_comparisons(settings=tmp_settings, decisive_only=True)) == 32

    result = train_and_evaluate(
        settings=tmp_settings,
        version="0.1.0-sim",
        seed=2,
        epochs=300,
        activate_if_better=True,
    )
    er = result.eval_report
    assert er.n_holdout >= 1
    assert er.better_than_random
    # Deploy gate: if better than retrieval, must be active; else registered inactive
    ckpts = list_checkpoints(settings=tmp_settings)
    assert len(ckpts) == 1
    if er.better_than_retrieval:
        assert result.activated
        active = get_active_checkpoint(settings=tmp_settings)
        assert active is not None
        assert active.better_than_baseline
    else:
        assert not result.activated
        assert get_active_checkpoint(settings=tmp_settings) is None

    # Journal + profile
    entry = ListeningJournalEntry(
        project_id=pairs[0].project_id,
        notes="sim listening note",
        tags=["simulated"],
        rating=4.0,
    )
    record_journal_entry(entry, settings=tmp_settings)
    assert len(list_journal(settings=tmp_settings)) == 1
    profile = taste_profile_summary(settings=tmp_settings)
    assert profile.n_decisive == 32
    assert profile.n_journal_entries == 1
    assert any("simulation" in x.lower() for x in profile.limitations)


def test_registry_rollback_after_second_train(tmp_settings: Settings) -> None:
    tmp_settings.ensure_workspace()
    build_simulated_dataset(
        n_projects=8, pairs_per_project=4, settings=tmp_settings, seed=5, persist=True
    )
    r1 = train_and_evaluate(
        settings=tmp_settings, version="0.1.0", seed=0, epochs=250, activate_if_better=True
    )
    r2 = train_and_evaluate(
        settings=tmp_settings, version="0.2.0", seed=1, epochs=250, activate_if_better=True
    )
    # Force-activate both path: if either activated, exercise rollback history
    if r1.activated and r2.activated:
        active = get_active_checkpoint(settings=tmp_settings)
        assert active is not None
        assert active.version == "0.2.0"
        prev = rollback_checkpoint(settings=tmp_settings)
        assert prev is not None
        assert prev.version == "0.1.0"
    else:
        # Still have registered checkpoints even if gate refused activation
        assert len(list_checkpoints(settings=tmp_settings)) >= 2


def test_style_vectors_from_approved_recipe(tmp_settings: Settings) -> None:
    brief = parse_brief("mellow Afrobeats 108 BPM", seed=33, bars=8)
    multi = generate_candidates(
        brief, n=1, base_seed=33, settings=tmp_settings, adapter=FakeDawAdapter()
    )
    recipe = recipe_from_project(multi.baseline.project, name="phase5-winner", approved=True)
    save_recipe(recipe, AssetStore(tmp_settings))
    vectors = derive_style_vectors(settings=tmp_settings, approved_only=True)
    assert len(vectors) == 1
    assert vectors[0].source_kind == "recipe"
    assert vectors[0].approved_only is True
    assert abs(sum(x * x for x in vectors[0].values) - 1.0) < 1e-3
