"""Borrow-trait conditioning: ReferenceProfile + chips → generator knobs.

Produces abstract feature targets — never copies reference MIDI/audio.
Novelty on the brief still drives how far phrasing drifts from the profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.models.schemas import (
    BorrowChip,
    BriefDocument,
    EnergyPoint,
    ReferenceProfile,
)
from backend.app.music.borrow import TRAIT_ALIASES, normalize_borrow_trait


@dataclass
class ConditioningPlan:
    """Resolved knobs applied by generators (simulation-friendly, deterministic)."""

    traits: list[str] = field(default_factory=list)
    bpm: float | None = None
    key: str | None = None
    swing: float = 0.0
    syncopation: float = 0.4
    bass_offbeat_bias: float = 0.35
    bass_density: float = 2.0
    drum_density_scale: float = 1.0
    chord_velocity_scale: float = 1.0
    soft_chords: bool = False
    energy_curve: list[float] = field(default_factory=list)
    genre_hint: str | None = None
    notes: list[str] = field(default_factory=list)
    profile_id: str | None = None
    novelty: float = 0.4

    def as_dict(self) -> dict[str, Any]:
        return {
            "traits": self.traits,
            "bpm": self.bpm,
            "key": self.key,
            "swing": self.swing,
            "syncopation": self.syncopation,
            "bass_offbeat_bias": self.bass_offbeat_bias,
            "bass_density": self.bass_density,
            "drum_density_scale": self.drum_density_scale,
            "chord_velocity_scale": self.chord_velocity_scale,
            "soft_chords": self.soft_chords,
            "energy_curve": self.energy_curve,
            "genre_hint": self.genre_hint,
            "notes": self.notes,
            "profile_id": self.profile_id,
            "novelty": self.novelty,
        }


# Synonym groups for conditioning knobs (canonical BorrowTrait + related traits).
# Aliases themselves are normalized via ``normalize_borrow_trait`` before lookup.
_TRAIT_GROUPS: dict[str, frozenset[str]] = {
    "bass_bounce": frozenset({"bass_bounce", "bass_rhythm"}),
    "drums": frozenset({"drums", "percussion_texture", "groove"}),
    "atmosphere": frozenset({"atmosphere"}),
    "chords": frozenset({"chords"}),
    "energy": frozenset({"energy", "arrangement"}),
}


def _expand(canonical: str) -> frozenset[str]:
    """Canonical + group siblings + any alias that maps onto them."""
    base = set(_TRAIT_GROUPS.get(canonical, frozenset({canonical})))
    base.add(canonical)
    for alias, target in TRAIT_ALIASES.items():
        if target in base or target == canonical:
            base.add(alias)
            base.add(target)
    return frozenset(base)


def _chip_weight(chips: list[BorrowChip], *traits: str) -> float:
    names: set[str] = set()
    for t in traits:
        names |= _expand(t)
        names.add(normalize_borrow_trait(t))
    return max(
        (c.weight for c in chips if normalize_borrow_trait(c.trait) in names or c.trait in names),
        default=0.0,
    )


def _has_trait(traits: list[str], *canonical: str) -> bool:
    names: set[str] = set()
    for t in canonical:
        names |= _expand(t)
        names.add(normalize_borrow_trait(t))
    return any(normalize_borrow_trait(t) in names or t in names for t in traits)


def build_conditioning_plan(
    brief: BriefDocument,
    profile: ReferenceProfile | None = None,
) -> ConditioningPlan:
    chips = [
        c if c.trait == normalize_borrow_trait(c.trait) else c.model_copy(update={"trait": normalize_borrow_trait(c.trait)})
        for c in brief.borrow_chips
    ]
    traits = [c.trait for c in chips]
    plan = ConditioningPlan(traits=traits, novelty=brief.novelty, profile_id=str(profile.id) if profile else None)

    if profile is None:
        plan.notes.append("no reference profile — genre template only")
        return plan

    # Objective estimates from profile (marked as estimates, not facts)
    if profile.bpm_estimate and (brief.bpm is None or _has_trait(traits, "energy", "arrangement")):
        plan.bpm = float(profile.bpm_estimate)
        plan.notes.append(f"bpm from profile estimate ({profile.bpm_confidence})")
    if profile.key_estimate and _has_trait(traits, "chords", "bass_bounce"):
        # Prefer brief key when user set one explicitly via free_text path — brief.key
        # is always set by parser; only override when chip weight is high and brief
        # still holds the template default "A minor" while profile differs.
        plan.key = profile.key_estimate
        plan.notes.append("key hypothesis from profile")

    gf = profile.groove_features
    plan.swing = float(gf.swing_estimate or 0.0)
    plan.syncopation = float(gf.syncopation or 0.4)

    w_bass = _chip_weight(chips, "bass_bounce")
    if w_bass > 0:
        bf = profile.bass_features or {}
        plan.bass_offbeat_bias = float(bf.get("offbeat_bias", 0.5)) * w_bass + 0.2 * (1 - w_bass)
        plan.bass_density = float(bf.get("note_density_per_bar", 2.0))
        # Novelty pulls phrasing away from the reference density
        plan.bass_density *= 0.7 + 0.6 * brief.novelty
        plan.notes.append(f"bass_bounce conditioned (w={w_bass:.2f})")

    w_perc = _chip_weight(chips, "drums", "percussion_texture", "groove")
    if w_perc > 0:
        plan.drum_density_scale = 0.85 + 0.5 * w_perc + 0.2 * plan.syncopation
        plan.swing = max(plan.swing, float(gf.swing_estimate or 0.0) * w_perc)
        plan.notes.append(f"percussion/groove conditioned (w={w_perc:.2f})")

    w_atm = _chip_weight(chips, "atmosphere")
    if w_atm > 0:
        plan.soft_chords = True
        plan.chord_velocity_scale = max(0.55, 1.0 - 0.35 * w_atm)
        plan.notes.append(f"atmosphere → softer pads/chords (w={w_atm:.2f})")

    w_chord = _chip_weight(chips, "chords")
    if w_chord > 0:
        plan.soft_chords = True
        plan.notes.append(f"chords borrowed abstractly (w={w_chord:.2f})")

    if _chip_weight(chips, "energy") > 0 and profile.energy_curve:
        plan.energy_curve = list(profile.energy_curve)
        plan.notes.append("energy curve from profile")

    if profile.genre_hypotheses:
        plan.genre_hint = profile.genre_hypotheses[0]
        plan.notes.append(f"genre hypothesis: {plan.genre_hint}")

    return plan


def apply_conditioning_to_brief(
    brief: BriefDocument,
    plan: ConditioningPlan,
    *,
    prefer_profile_bpm: bool = True,
) -> BriefDocument:
    """Mutate a copy of the brief with resolved BPM/key/energy from the plan."""
    out = brief.model_copy(deep=True)
    if prefer_profile_bpm and plan.bpm is not None:
        out.bpm = plan.bpm
    if plan.key is not None and _has_trait(plan.traits, "chords", "bass_bounce"):
        # Keep user's explicit key from free_text if parser found one — only fill
        # when chips ask for harmonic borrow and profile provided a key.
        out.key = plan.key
    if plan.energy_curve:
        out.energy_curve = [
            EnergyPoint(bar=i + 1, value=float(v))
            for i, v in enumerate(plan.energy_curve[: out.length_bars])
        ]
        # Pad if profile curve shorter than bars
        while len(out.energy_curve) < out.length_bars:
            last = out.energy_curve[-1].value if out.energy_curve else 0.55
            out.energy_curve.append(EnergyPoint(bar=len(out.energy_curve) + 1, value=last))
    if plan.genre_hint and (not out.genre_template_id or out.genre_template_id == "default"):
        from backend.app.music.templates import resolve_genre_id

        out.genre_template_id = resolve_genre_id(plan.genre_hint)
    return out
