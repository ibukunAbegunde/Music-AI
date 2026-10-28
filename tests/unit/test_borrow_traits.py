"""Canonical BorrowTrait vocabulary + alias normalization."""

from __future__ import annotations

from backend.app.models.schemas import BorrowTrait
from backend.app.music.borrow import (
    KNOWN_BORROW_TRAITS,
    normalize_borrow_trait,
    normalize_borrow_traits,
)


def test_known_traits_match_enum() -> None:
    assert KNOWN_BORROW_TRAITS == frozenset(t.value for t in BorrowTrait)


def test_alias_normalization() -> None:
    assert normalize_borrow_trait("chord_feel") == "chords"
    assert normalize_borrow_trait("groove_swing") == "groove"
    assert normalize_borrow_trait("energy_curve") == "energy"
    assert normalize_borrow_trait("bass") == "bass_bounce"
    assert normalize_borrow_trait("percussion") == "percussion_texture"
    assert normalize_borrow_trait("Bass Bounce") == "bass_bounce"


def test_normalize_dedupes() -> None:
    assert normalize_borrow_traits(["bass", "bass_bounce", "groove_swing", "groove"]) == [
        "bass_bounce",
        "groove",
    ]
