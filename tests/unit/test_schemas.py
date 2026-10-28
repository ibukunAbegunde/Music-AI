"""Domain schema validation tests."""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.models.schemas import (
    DrumEvent,
    LicenseClass,
    MusicProject,
    MusicTrack,
    NoteEvent,
    ReferenceAsset,
    TrackRole,
    UseMode,
)


def test_note_event_bounds() -> None:
    n = NoteEvent(pitch=60, onset_beats=0, duration_beats=1, velocity=100)
    assert n.pitch == 60
    with pytest.raises(ValidationError):
        NoteEvent(pitch=128, onset_beats=0, duration_beats=1, velocity=100)
    with pytest.raises(ValidationError):
        NoteEvent(pitch=60, onset_beats=0, duration_beats=0, velocity=100)
    with pytest.raises(ValidationError):
        NoteEvent(pitch=60, onset_beats=0, duration_beats=1, velocity=0)


def test_music_project_defaults() -> None:
    p = MusicProject(name="demo")
    assert isinstance(p.id, UUID)
    assert p.length_bars == 8
    assert p.status.value == "CREATED"
    assert p.rights_policy.allow_direct_sample is False


def test_reference_unknown_license_default() -> None:
    r = ReferenceAsset(
        original_filename="x.wav",
        immutable_sha256="abc",
        source_uri_or_local_path="/tmp/x.wav",
    )
    assert r.license_class == LicenseClass.UNKNOWN
    assert r.use_mode == UseMode.ANALYSIS


def test_track_roles() -> None:
    t = MusicTrack(role=TrackRole.BASS, note_events=[], drum_events=[])
    assert t.enabled is True
    d = DrumEvent(instrument_role="kick", onset_beats=0, velocity=100)
    assert d.duration_beats == 0.25
