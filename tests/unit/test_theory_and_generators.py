"""Theory + generator unit tests."""

from __future__ import annotations

from backend.app.music.generators import generate_eight_bar_project, parse_prompt, seed_from_prompt
from backend.app.music.theory import parse_key, scale_pitch, triad


def test_parse_key_major_minor() -> None:
    assert parse_key("C")[0] == 0
    assert parse_key("A minor")[1] == "minor"
    assert parse_key("F# major")[0] == 6


def test_scale_and_triad_in_range() -> None:
    pitches = triad(0, 1, 4, "major")  # C major
    assert pitches == [48, 52, 55] or all(0 <= p <= 127 for p in pitches)
    assert 0 <= scale_pitch(0, 1, 3, "minor") <= 127


def test_prompt_parsing_afrobeats() -> None:
    intent = parse_prompt("Make a mellow Afrobeats groove at 110 BPM in A minor")
    assert intent.genre == "afrobeats"
    assert intent.bpm == 110.0
    assert "A" in intent.key
    assert intent.mood == "mellow"


def test_seed_reproducibility() -> None:
    prompt = "atmospheric Amapiano 112 BPM"
    a = generate_eight_bar_project(prompt, seed=42)
    b = generate_eight_bar_project(prompt, seed=42)
    assert a.seed == b.seed == 42
    assert [n.model_dump() for n in a.tracks[0].note_events] == [
        n.model_dump() for n in b.tracks[0].note_events
    ]
    assert [n.model_dump() for n in a.tracks[1].note_events] == [
        n.model_dump() for n in b.tracks[1].note_events
    ]


def test_different_seeds_diverge() -> None:
    a = generate_eight_bar_project("trap beat", seed=1)
    b = generate_eight_bar_project("trap beat", seed=2)
    assert a.tracks[0].note_events != b.tracks[0].note_events


def test_prompt_hash_seed_stable() -> None:
    assert seed_from_prompt("hello") == seed_from_prompt("hello")
    assert seed_from_prompt("hello") != seed_from_prompt("hello!")


def test_eight_bar_structure() -> None:
    p = generate_eight_bar_project("R&B keys and bass", seed=7, bars=8)
    assert p.length_bars == 8
    roles = {t.role.value for t in p.tracks}
    assert roles == {"drums", "bass", "chord"}
    assert all(len(t.note_events) > 0 for t in p.tracks)
