"""Musical diff + role-lock co-edit."""

from __future__ import annotations

from backend.app.music.coedit import (
    apply_role_locks,
    humanize_project,
    lock_bars,
    merge_preserving_locks,
)
from backend.app.music.diff import diff_projects
from backend.app.music.generators import generate_eight_bar_project


def test_diff_detects_bass_change() -> None:
    a = generate_eight_bar_project("Afrobeats 110 BPM", seed=10)
    b = generate_eight_bar_project("Afrobeats 110 BPM", seed=11)
    d = diff_projects(a, b)
    assert d.one_line_summary
    assert isinstance(d.roles_changed, list)


def test_diff_detects_pitch_only_change() -> None:
    a = generate_eight_bar_project("Afrobeats 110 BPM", seed=10)
    b = a.model_copy(deep=True)
    for t in b.tracks:
        if t.role.value == "bass":
            t.note_events = [n.model_copy(update={"pitch": n.pitch + 1}) for n in t.note_events]
    d = diff_projects(a, b)
    assert "bass" in d.roles_changed
    assert "No musical changes detected" not in d.one_line_summary


def test_merge_preserves_locked_drums() -> None:
    base = apply_role_locks(generate_eight_bar_project("trap", seed=1), ["drums"])
    regen = generate_eight_bar_project("trap", seed=99)
    merged = merge_preserving_locks(base, regen)
    drums_base = next(t for t in base.tracks if t.role.value == "drums")
    drums_merged = next(t for t in merged.tracks if t.role.value == "drums")
    assert [n.model_dump() for n in drums_base.note_events] == [
        n.model_dump() for n in drums_merged.note_events
    ]
    d = diff_projects(base, merged, expected_locked=["drums"])
    assert d.locked_roles_respected
    assert "drums" not in d.roles_changed or d.note_count_delta_by_role.get("drums", 0) == 0


def test_merge_honors_bar_locks() -> None:
    base = generate_eight_bar_project("trap", seed=1)
    idx = next(i for i, t in enumerate(base.tracks) if t.role.value == "bass")
    base.tracks[idx] = lock_bars(base.tracks[idx], 1, 4)
    regen = generate_eight_bar_project("trap", seed=99)
    merged = merge_preserving_locks(base, regen)
    bass_b = next(t for t in base.tracks if t.role.value == "bass")
    bass_m = next(t for t in merged.tracks if t.role.value == "bass")
    def _sig(notes):
        return sorted(
            (round(n.onset_beats, 3), n.pitch, n.velocity) for n in notes if n.onset_beats < 16.0
        )

    assert _sig(bass_b.note_events) == _sig(bass_m.note_events)
    # Unlocked bars (5–8) should come from regen, so overall track differs
    assert [n.model_dump() for n in bass_b.note_events] != [n.model_dump() for n in bass_m.note_events]


def test_humanize_skips_locked() -> None:
    p = apply_role_locks(generate_eight_bar_project("rnb", seed=3), ["bass"])
    h = humanize_project(p, seed=5)
    bass_p = next(t for t in p.tracks if t.role.value == "bass")
    bass_h = next(t for t in h.tracks if t.role.value == "bass")
    assert [n.model_dump() for n in bass_p.note_events] == [
        n.model_dump() for n in bass_h.note_events
    ]
