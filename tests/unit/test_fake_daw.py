"""FakeDawAdapter state machine tests."""

from __future__ import annotations

from backend.app.daw.fake import FakeDawAdapter
from backend.app.music.generators import generate_eight_bar_project


def test_fake_daw_create_verify_restore() -> None:
    daw = FakeDawAdapter()
    assert daw.connect().succeeded
    caps = daw.probe_capabilities()
    assert caps.observations["capabilities"]["create_or_update_notes"] is True
    assert caps.observations["capabilities"]["live_fl_studio"] is False

    project = generate_eight_bar_project("test groove", seed=5)
    snap = daw.save_snapshot("before").observations["snapshot_ref"]
    applied = daw.create_or_update_notes(project)
    assert applied.succeeded and applied.verified
    daw.set_tempo(118)
    verify = daw.verify_postcondition({"bpm": 118, "min_tracks": 3, "min_notes": 8})
    assert verify.succeeded

    tracks = daw.read_tracks()
    assert len(tracks.observations["tracks"]) == 3

    restored = daw.undo_or_restore(snap)
    assert restored.succeeded
    assert daw.bpm == 120.0 or daw.project is None


def test_fake_export_requires_user_action() -> None:
    daw = FakeDawAdapter()
    daw.connect()
    result = daw.export_audio_or_request_manual_bounce("/tmp/out.wav")
    assert result.succeeded is False
    assert result.user_action_required is not None
