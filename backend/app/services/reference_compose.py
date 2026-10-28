"""Reference → novel 8–16 bar composition (Phase 3 exit path).

Uses FixtureReferenceAnalyzer when Phase 2 APIs are absent; swaps to real
analyzer once Phase 2 types land on main.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from backend.app.audio.reference import (
    FixtureReferenceAnalyzer,
    bind_borrow_chips,
    load_fixture_profile,
)
from backend.app.core.config import Settings, get_settings
from backend.app.models.schemas import (
    BriefDocument,
    LicenseClass,
    ReferenceAsset,
    ReferenceProfile,
)
from backend.app.music.brief import parse_brief
from backend.app.services.candidates import MultiCandidateResult, generate_candidates


@dataclass
class ReferenceComposeResult:
    asset: ReferenceAsset | None
    profile: ReferenceProfile
    traits: list[str]
    multi: MultiCandidateResult
    analyzer: str
    phase2_note: str


DEFAULT_TRAITS = ("bass_bounce", "percussion_texture")


def compose_from_reference(
    prompt: str,
    *,
    traits: Sequence[str] | None = None,
    fixture_genre: str = "afrobeats",
    n: int = 2,
    seed: int | None = None,
    bars: int = 8,
    settings: Settings | None = None,
    adapter=None,
    analyzer: FixtureReferenceAnalyzer | None = None,
    profile: ReferenceProfile | None = None,
    asset: ReferenceAsset | None = None,
    locked_roles: list[str] | None = None,
    recipe_id: UUID | None = None,
) -> ReferenceComposeResult:
    """Brief + borrow chips from a (fixture or real) ReferenceProfile → N candidates."""
    if bars < 8 or bars > 16:
        raise ValueError("bars must be in 8..16 for Phase 3")

    settings = settings or get_settings()
    selected = list(traits) if traits else list(DEFAULT_TRAITS)

    used_analyzer = "provided_profile"
    ref_asset = asset
    if profile is None:
        az = analyzer or FixtureReferenceAnalyzer()
        ref_asset, profile = az.register_fixture(
            name=f"{fixture_genre}-ref.wav",
            genre=fixture_genre,
            license_class=LicenseClass.OWNED,
        )
        used_analyzer = "FixtureReferenceAnalyzer"

    brief: BriefDocument = parse_brief(
        prompt,
        seed=seed,
        bars=bars,
        locked_roles=locked_roles,
    )
    chips = bind_borrow_chips(profile, selected, reference_id=ref_asset.id if ref_asset else None)
    # Merge with any chips the NL parser already found
    existing = {c.trait for c in brief.borrow_chips}
    for c in chips:
        if c.trait not in existing:
            brief.borrow_chips.append(c)
    if recipe_id is not None:
        brief.recipe_id = recipe_id

    # Prefer profile BPM when prompt didn't set one explicitly
    from backend.app.music.brief import explicit_bpm_from_text

    if explicit_bpm_from_text(prompt) is None and profile.bpm_estimate:
        brief.bpm = float(profile.bpm_estimate)

    ref_ids = [ref_asset.id] if ref_asset else []
    multi = generate_candidates(
        brief,
        n=n,
        base_seed=seed if seed is not None else brief.seed,
        settings=settings,
        adapter=adapter,
        profile=profile,
        reference_ids=ref_ids,
    )
    return ReferenceComposeResult(
        asset=ref_asset,
        profile=profile,
        traits=selected,
        multi=multi,
        analyzer=used_analyzer,
        phase2_note=(
            "Phase 2 reference/stem APIs not on main — composed against "
            "FixtureReferenceAnalyzer + ReferenceProfile schema. Rebase onto "
            "Phase 2 PR when available to wire real analyse/separate paths."
        ),
    )


def profile_from_fixture_name(name: str) -> ReferenceProfile:
    return load_fixture_profile(name)
