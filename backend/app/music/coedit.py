"""Co-edit helpers: role/bar locks and humanize (Phase 1)."""

from __future__ import annotations

from copy import deepcopy
from random import Random

from backend.app.models.schemas import BarRange, MusicProject, MusicTrack, TrackRole


def apply_role_locks(project: MusicProject, roles: list[str]) -> MusicProject:
    out = project.model_copy(deep=True)
    wanted = set(roles)
    for t in out.tracks:
        if t.role.value in wanted:
            t.locked = True
    return out


def lock_bars(track: MusicTrack, start_bar: int, end_bar: int) -> MusicTrack:
    t = track.model_copy(deep=True)
    t.locked_bar_ranges = list(t.locked_bar_ranges) + [BarRange(start_bar=start_bar, end_bar=end_bar)]
    return t


def _bar_of(onset_beats: float, bpb: int = 4) -> int:
    return int(onset_beats // bpb) + 1


def is_onset_locked(track: MusicTrack, onset_beats: float, bpb: int = 4) -> bool:
    if track.locked:
        return True
    bar = _bar_of(onset_beats, bpb)
    for r in track.locked_bar_ranges:
        if r.start_bar <= bar <= r.end_bar:
            return True
    return False


def humanize_track(
    track: MusicTrack,
    *,
    seed: int,
    timing_amount: float = 0.02,
    velocity_jitter: int = 6,
    bpb: int = 4,
) -> MusicTrack:
    """Humanize unlocked notes only."""
    if track.locked:
        return track.model_copy(deep=True)
    rng = Random(seed)
    out = track.model_copy(deep=True)
    new_notes = []
    for n in out.note_events:
        nn = n.model_copy()
        if not is_onset_locked(out, n.onset_beats, bpb):
            nn.onset_beats = max(0.0, n.onset_beats + rng.uniform(-timing_amount, timing_amount))
            nn.velocity = max(1, min(127, n.velocity + rng.randint(-velocity_jitter, velocity_jitter)))
        new_notes.append(nn)
    out.note_events = new_notes
    return out


def humanize_project(project: MusicProject, seed: int) -> MusicProject:
    out = project.model_copy(deep=True)
    out.tracks = [
        humanize_track(t, seed=seed + i) for i, t in enumerate(out.tracks)
    ]
    return out


def merge_preserving_locks(base: MusicProject, regenerated: MusicProject) -> MusicProject:
    """Keep locked tracks from base; take unlocked from regenerated."""
    out = base.model_copy(deep=True)
    regen_by_role = {t.role.value: t for t in regenerated.tracks}
    new_tracks = []
    for t in out.tracks:
        if t.locked:
            new_tracks.append(t)
        elif t.role.value in regen_by_role:
            rt = regen_by_role[t.role.value].model_copy(deep=True)
            rt.id = t.id
            rt.locked = t.locked
            rt.locked_bar_ranges = list(t.locked_bar_ranges)
            new_tracks.append(rt)
        else:
            new_tracks.append(t)
    # Add any new roles from regen that weren't in base
    base_roles = {t.role.value for t in out.tracks}
    for role, t in regen_by_role.items():
        if role not in base_roles:
            new_tracks.append(deepcopy(t))
    out.tracks = new_tracks
    out.track_ids = [t.id for t in new_tracks]
    out.bpm = regenerated.bpm
    out.key_estimate = regenerated.key_estimate
    out.seed = regenerated.seed
    return out


def parse_lock_roles_from_text(text: str) -> list[str]:
    lower = text.lower()
    locks: list[str] = []
    mapping = {
        "drums": ("drums", "drum", "percussion", "kick", "snare", "hat"),
        "bass": ("bass",),
        "chord": ("chord", "chords", "keys", "rhodes"),
    }
    # "keep X"
    for role, words in mapping.items():
        if any(f"keep {w}" in lower or f"keep the {w}" in lower for w in words):
            locks.append(role)
        if any(f"retain {w}" in lower or f"lock {w}" in lower for w in words):
            if role not in locks:
                locks.append(role)
    return locks
