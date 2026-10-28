"""Brief parser + genre templates."""

from __future__ import annotations

from backend.app.music.brief import explicit_key_from_text, parse_brief
from backend.app.music.templates import get_template, list_templates, resolve_genre_id


def test_templates_cover_core_genres() -> None:
    ids = {t.id for t in list_templates()}
    assert {"afrobeats", "amapiano", "rnb", "trap", "drill", "pop", "default"} <= ids


def test_parse_brief_afrobeats() -> None:
    b = parse_brief("mellow Afrobeats groove 110 BPM in A minor with Rhodes chords", seed=1)
    assert b.genre_template_id == "afrobeats"
    assert b.bpm == 110.0
    assert "A" in (b.key or "")
    assert b.autonomy_mode == "collaborative"
    assert b.scratch_or_release == "scratch"
    assert any(c.trait == "chord_feel" for c in b.borrow_chips)
    assert len(b.energy_curve) == 8


def test_parse_brief_locks() -> None:
    b = parse_brief("keep the drums, change bass", seed=2)
    assert "drums" in b.locked_roles


def test_resolve_alias() -> None:
    assert resolve_genre_id("r&b") == "rnb"
    assert get_template("amapiano").default_bpm == 112


def test_explicit_key_ignores_bass_letter() -> None:
    assert explicit_key_from_text("keep the drums, soften bass") is None
    assert explicit_key_from_text("trap 140 BPM in C major") == "C major"
    assert explicit_key_from_text("mellow Afrobeats 110 BPM in A minor") == "A minor"
