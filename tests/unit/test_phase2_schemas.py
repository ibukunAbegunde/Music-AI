"""Phase 2 schema additions: borrow traits, stem→role."""

from __future__ import annotations

from uuid import uuid4

from backend.app.models.schemas import (
    STEM_TYPE_TO_ROLE,
    BorrowChip,
    BorrowTrait,
    ReferenceAsset,
    ReferenceProfile,
    StemAsset,
    StemRoleMapping,
    TrackRole,
)


def test_borrow_trait_enum_and_chip() -> None:
    assert BorrowTrait.BASS_BOUNCE.value == "bass_bounce"
    chip = BorrowChip(reference_id=uuid4(), trait=BorrowTrait.DRUMS.value, weight=0.8)
    assert chip.weight == 0.8


def test_stem_role_mapping_defaults() -> None:
    assert STEM_TYPE_TO_ROLE["bass"] == TrackRole.BASS
    assert STEM_TYPE_TO_ROLE["drums"] == TrackRole.DRUMS
    m = StemRoleMapping(
        stem_id=uuid4(),
        stem_type="bass",
        role=TrackRole.BASS,
        locked=True,
        lock_reason="keep bass",
    )
    assert m.locked is True


def test_reference_profile_estimate_flag() -> None:
    p = ReferenceProfile(is_estimate=True, bpm_estimate=110.0, bpm_confidence=0.5)
    assert p.is_estimate is True
    assert "bass_bounce" in p.available_borrow_traits or p.available_borrow_traits == []


def test_stem_asset_transcription_fields() -> None:
    s = StemAsset(
        reference_id=uuid4(),
        stem_type="bass",
        file_path="/tmp/bass.wav",
        mapped_role=TrackRole.BASS,
        role_locked=False,
    )
    assert s.note_events == []


def test_reference_asset_phase2_fields() -> None:
    a = ReferenceAsset(
        original_filename="x.wav",
        immutable_sha256="a" * 64,
        source_uri_or_local_path="/tmp/x.wav",
    )
    assert a.schema_version == "0.3.0"
    assert a.stem_role_mappings == []
