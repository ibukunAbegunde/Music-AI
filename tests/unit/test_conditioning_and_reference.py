"""Phase 3: ReferenceProfile fixtures, borrow chips, conditioning plan."""

from __future__ import annotations

from backend.app.audio.reference import (
    FixtureReferenceAnalyzer,
    bind_borrow_chips,
    load_fixture_profile,
)
from backend.app.music.brief import parse_brief
from backend.app.music.conditioning import apply_conditioning_to_brief, build_conditioning_plan
from backend.app.music.generators import generate_from_brief


def test_fixture_profile_afrobeats() -> None:
    profile = load_fixture_profile("afrobeats")
    assert profile.bpm_estimate == 110.0
    assert profile.groove_features.swing_estimate is not None
    assert "offbeat_bias" in (profile.bass_features or {})


def test_fixture_analyzer_ingest_analyse() -> None:
    az = FixtureReferenceAnalyzer()
    asset, profile = az.register_fixture(genre="trap")
    assert asset.analysis_status == "fixture_complete"
    assert profile.bpm_estimate == 140.0
    assert az.get_profile(asset.id) is profile or az.get_profile(asset.id) is not None


def test_bind_borrow_chips_aliases() -> None:
    profile = load_fixture_profile("afrobeats")
    chips = bind_borrow_chips(profile, ["bass", "percussion", "rhodes", "groove_swing", "energy_curve"])
    traits = {c.trait for c in chips}
    # Normalized onto Phase 2 BorrowTrait values
    assert "bass_bounce" in traits
    assert "percussion_texture" in traits
    assert "chords" in traits
    assert "groove" in traits
    assert "energy" in traits
    assert all(c.reference_id == profile.id for c in chips)


def test_conditioning_accepts_phase2_borrow_trait_chips() -> None:
    """Phase 2 chips (chords/groove/energy/drums) must condition generators."""
    profile = load_fixture_profile("afrobeats")
    brief = parse_brief("Afrobeats borrow", seed=2, bars=8)
    brief.borrow_chips = bind_borrow_chips(profile, ["drums", "groove", "chords", "energy"])
    plan = build_conditioning_plan(brief, profile)
    assert plan.drum_density_scale > 1.0
    assert plan.soft_chords is True
    assert plan.energy_curve
    assert plan.bpm == 110.0


def test_conditioning_plan_bass_and_perc() -> None:
    profile = load_fixture_profile("afrobeats")
    brief = parse_brief("mellow Afrobeats with bass bounce and percussion", seed=1, bars=8)
    brief.borrow_chips = bind_borrow_chips(profile, ["bass_bounce", "percussion_texture"])
    plan = build_conditioning_plan(brief, profile)
    assert "bass_bounce" in plan.traits
    assert plan.bass_offbeat_bias > 0.3
    assert plan.drum_density_scale > 1.0
    conditioned = apply_conditioning_to_brief(brief, plan)
    assert conditioned.bpm == 110.0


def test_conditioned_generation_differs_from_unconditioned() -> None:
    profile = load_fixture_profile("afrobeats")
    brief = parse_brief("Afrobeats 110 BPM in A minor", seed=99, bars=8)
    plain = generate_from_brief(brief)
    brief2 = brief.model_copy(deep=True)
    brief2.borrow_chips = bind_borrow_chips(profile, ["bass_bounce", "percussion_texture"])
    plan = build_conditioning_plan(brief2, profile)
    conditioned = generate_from_brief(brief2, plan=plan)
    plain_bass = next(t for t in plain.tracks if t.role.value == "bass")
    cond_bass = next(t for t in conditioned.tracks if t.role.value == "bass")
    # Same seed + conditioning should alter bass density/phrasing vs plain
    assert len(cond_bass.note_events) >= len(plain_bass.note_events)
    assert "conditioned" in cond_bass.tags
