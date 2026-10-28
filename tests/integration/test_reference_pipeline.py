"""Integration: import → analyse → separate → transcribe → profile (+ borrow chips)."""

from __future__ import annotations

from pathlib import Path

from backend.app.models.schemas import BorrowTrait
from backend.app.music.brief import parse_brief
from backend.app.services.reference import (
    bind_borrow_chips,
    load_profile,
    run_pipeline,
    stem_to_music_track,
)
from tests.fixtures.audio import make_groove_wav


def test_full_reference_pipeline(tmp_settings, tmp_path: Path) -> None:
    wav = make_groove_wav(tmp_path / "ref.wav", bpm=110.0, duration_sec=5.0)
    result = run_pipeline(
        wav,
        settings=tmp_settings,
        license_class="owned",
        use_mode="analysis",
        borrow_traits=["bass_bounce", "drums"],
        lock_bass=True,
        prompt_for_brief="mellow Afrobeats with this bass bounce",
    )
    assert result.asset.analysis_status == "transcribed"
    assert result.asset.immutable_sha256
    assert result.profile.bpm_estimate is not None
    assert result.profile.is_estimate is True
    assert len(result.stems) == 4
    assert result.transcription_midi is not None
    assert result.transcription_midi.exists()
    assert len(result.transcription_notes) >= 1
    assert result.simulated["separator"] is True
    assert result.simulated["transcriber"] is True

    # Stem → role mappings present; bass locked
    roles = {m.stem_type: m for m in result.asset.stem_role_mappings}
    assert "bass" in roles
    assert roles["bass"].locked is True
    assert roles["bass"].role.value == "bass"

    # Borrow chips bound to brief
    assert result.brief_with_borrows is not None
    traits = {c.trait for c in result.brief_with_borrows.borrow_chips}
    assert "bass_bounce" in traits
    assert "drums" in traits
    bound = [c for c in result.brief_with_borrows.borrow_chips if c.trait in ("bass_bounce", "drums")]
    assert bound
    assert all(c.reference_id == result.asset.id for c in bound)

    # Profile reload
    prof = load_profile(result.asset.id, tmp_settings)
    assert prof.transcription_summary.get("stem_type") == "bass"
    assert any("estimate" in lim.lower() or "heuristic" in lim.lower() or "Simulat" in lim
               or "simulation" in lim.lower() or "Stub" in lim for lim in prof.limitations)

    # CIR track from transcribed bass stem
    bass = next(s for s in result.stems if s.stem_type == "bass")
    assert bass.role_locked is True
    assert len(bass.note_events) >= 1
    track = stem_to_music_track(bass)
    assert track.locked is True
    assert track.role.value == "bass"
    assert len(track.note_events) >= 1


def test_bind_borrow_chips_idempotent_add() -> None:
    brief = parse_brief("Amapiano 112 BPM")
    from uuid import uuid4

    rid = uuid4()
    brief = bind_borrow_chips(brief, rid, [BorrowTrait.BASS_BOUNCE.value, "groove"])
    assert len(brief.borrow_chips) == 2
    brief = bind_borrow_chips(brief, rid, ["energy"])
    assert len(brief.borrow_chips) == 3
