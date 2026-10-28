"""Canonical BorrowTrait vocabulary + NL/legacy aliases (Phases 2–3).

Single source of truth: ``BorrowTrait`` in schemas. Aliases normalize onto
those values before chips hit conditioning / CLI / recipes.
"""

from __future__ import annotations

from backend.app.models.schemas import BorrowTrait

# Canonical set — always derived from the enum (never a parallel hard-coded list).
KNOWN_BORROW_TRAITS: frozenset[str] = frozenset(t.value for t in BorrowTrait)

# Map free-form / legacy Phase 3 chip names → BorrowTrait values.
TRAIT_ALIASES: dict[str, str] = {
    "bass": "bass_bounce",
    "bass_feel": "bass_bounce",
    "percussion": "percussion_texture",
    "perc": "percussion_texture",
    "pads": "atmosphere",
    "space": "atmosphere",
    "pad": "atmosphere",
    "chord_feel": "chords",
    "harmony": "chords",
    "rhodes": "chords",
    "keys": "chords",
    "groove_swing": "groove",
    "swing": "groove",
    "energy_curve": "energy",
}


def normalize_borrow_trait(trait: str) -> str:
    """Normalize a free-form trait string onto a BorrowTrait value when known."""
    t = trait.strip().lower().replace(" ", "_").replace("-", "_")
    t = TRAIT_ALIASES.get(t, t)
    return t


def normalize_borrow_traits(traits: list[str]) -> list[str]:
    """Normalize a list, preserving order and de-duplicating."""
    out: list[str] = []
    seen: set[str] = set()
    for trait in traits:
        n = normalize_borrow_trait(trait)
        if n not in seen:
            out.append(n)
            seen.add(n)
    return out
