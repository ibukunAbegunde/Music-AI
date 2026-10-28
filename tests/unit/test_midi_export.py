"""MIDI export verification."""

from __future__ import annotations

from pathlib import Path

from backend.app.music.generators import generate_eight_bar_project
from backend.app.music.midi import export_project_midi, read_note_ons


def test_export_writes_parseable_midi(tmp_path: Path) -> None:
    project = generate_eight_bar_project("Afrobeats 110 BPM", seed=99)
    paths = export_project_midi(project, tmp_path / "midi")
    assert set(paths) >= {"drums", "bass", "chord", "combined"}
    for role in ("drums", "bass", "chord"):
        ons = read_note_ons(paths[role])
        assert len(ons) > 0, f"{role} has no note_ons"
        for _tick, pitch, vel in ons:
            assert 0 <= pitch <= 127
            assert 1 <= vel <= 127
    combined = read_note_ons(paths["combined"])
    assert len(combined) >= len(read_note_ons(paths["bass"]))


def test_reproducible_midi_bytes(tmp_path: Path) -> None:
    p1 = generate_eight_bar_project("same prompt", seed=123)
    p2 = generate_eight_bar_project("same prompt", seed=123)
    d1 = tmp_path / "a"
    d2 = tmp_path / "b"
    paths1 = export_project_midi(p1, d1)
    paths2 = export_project_midi(p2, d2)
    for role in ("drums", "bass", "chord"):
        assert paths1[role].read_bytes() == paths2[role].read_bytes()
