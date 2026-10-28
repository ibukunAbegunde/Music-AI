"""Unit: Phase 6 structure templates + arrangement engine."""

from __future__ import annotations

import pytest

from backend.app.music.arrangement import (
    MAX_FULL_BARS,
    MIN_FULL_BARS,
    apply_plan_to_brief,
    brief_for_full_compose,
    build_arrangement_plan,
    energy_curve_from_sections,
    generate_arranged_project,
)
from backend.app.music.brief import parse_brief
from backend.app.music.structure_templates import (
    get_structure_template,
    list_structure_templates,
    resolve_structure_id,
    validate_section_map,
)


def test_structure_templates_cover_genres() -> None:
    ids = {t.id for t in list_structure_templates()}
    assert "afrobeats_full" in ids
    assert "default_full" in ids
    for t in list_structure_templates():
        assert t.length_bars >= MIN_FULL_BARS
        validate_section_map(t.section_map, t.length_bars)
        assert t.instrument_palette


def test_resolve_structure_from_genre() -> None:
    assert resolve_structure_id("afrobeats") == "afrobeats_full"
    assert resolve_structure_id(None, "trap") == "trap_full"
    assert get_structure_template("amapiano").id == "amapiano_full"


def test_unknown_structure_hard_fails() -> None:
    with pytest.raises(ValueError, match="unknown structure"):
        resolve_structure_id("not_a_real_thing")
    with pytest.raises(ValueError, match="unknown structure"):
        get_structure_template("nope_full")
    with pytest.raises(ValueError, match="unknown structure"):
        brief_for_full_compose("trap banger", seed=1, structure_id="not_a_real_thing")


def test_section_names_unique_within_templates() -> None:
    for t in list_structure_templates():
        names = [s.name for s in t.section_map]
        assert len(names) == len(set(names)), f"duplicate section names in {t.id}: {names}"


def test_build_plan_and_energy_curve() -> None:
    brief = parse_brief("mellow Afrobeats 110 BPM in A minor", seed=1, bars=8)
    plan = build_arrangement_plan(brief)
    assert plan.length_bars == 64
    assert plan.structure_template_id == "afrobeats_full"
    assert len(plan.section_map) >= 4
    assert plan.section_map[0].name == "intro"
    curve = energy_curve_from_sections(plan.section_map)
    assert len(curve) == plan.length_bars
    assert curve[0].value == pytest.approx(plan.section_map[0].intensity_target)


def test_rescale_bars() -> None:
    brief = parse_brief("Afrobeats groove", seed=2)
    plan = build_arrangement_plan(brief, length_bars=48)
    assert plan.length_bars == 48
    assert plan.section_map[-1].end_bar == 48
    validate_section_map(plan.section_map, 48)


def test_bars_out_of_range() -> None:
    brief = parse_brief("pop song", seed=0)
    with pytest.raises(ValueError, match="bars"):
        build_arrangement_plan(brief, length_bars=MIN_FULL_BARS - 1)
    with pytest.raises(ValueError, match="bars"):
        build_arrangement_plan(brief, length_bars=MAX_FULL_BARS + 1)


def test_generate_arranged_multi_section() -> None:
    brief, plan = brief_for_full_compose(
        "Afrobeats 112 BPM in A minor", seed=42, structure_id="afrobeats_full"
    )
    project = generate_arranged_project(brief, plan)
    assert project.length_bars == 64
    assert len(project.sections) == len(plan.section_map)
    assert project.sections[0].name == "intro"
    assert project.schema_version == "0.3.0"
    # Events present across roles
    roles = {t.role.value for t in project.tracks}
    assert {"drums", "bass", "chord"} <= roles
    assert sum(len(t.note_events) + len(t.drum_events) for t in project.tracks) > 50


def test_release_plan_requires_approval() -> None:
    brief = parse_brief("trap banger", seed=3, scratch_or_release="release")
    plan = build_arrangement_plan(brief, structure_id="trap_full")
    assert "release_mode_daw_write" in plan.approvals_required
    applied = apply_plan_to_brief(brief, plan)
    assert applied.length_bars == plan.length_bars
    assert len(applied.section_map) == len(plan.section_map)
