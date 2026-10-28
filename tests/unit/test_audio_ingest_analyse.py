"""Unit tests: ingest hashing + analyse estimates."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from backend.app.audio.analyse import analyse_audio
from backend.app.audio.ingest import import_reference, sha256_file
from backend.app.audio.io import AudioLoadError, write_wav
from backend.app.models.schemas import LicenseClass
from tests.fixtures.audio import make_groove_wav


def test_sha256_stable(tmp_path: Path) -> None:
    p = tmp_path / "a.wav"
    write_wav(p, np.zeros(1000, dtype=np.float32), 22050)
    assert sha256_file(p) == sha256_file(p)
    assert len(sha256_file(p)) == 64


def test_import_rejects_unsupported(tmp_settings, tmp_path: Path) -> None:
    bad = tmp_path / "x.txt"
    bad.write_text("nope")
    with pytest.raises(AudioLoadError):
        import_reference(bad, settings=tmp_settings)


def test_import_immutable_store(tmp_settings, tmp_path: Path) -> None:
    src = make_groove_wav(tmp_path / "groove.wav", bpm=112.0)
    asset = import_reference(
        src,
        settings=tmp_settings,
        license_class=LicenseClass.OWNED,
        permission_notes="personal library",
    )
    assert asset.immutable_sha256 == sha256_file(src)
    stored = Path(asset.source_uri_or_local_path)
    assert stored.exists()
    assert sha256_file(stored) == asset.immutable_sha256
    assert Path(asset.analysis_wav_path).exists()
    assert asset.duration_sec and asset.duration_sec > 1.0
    assert "bass_bounce" in asset.available_borrow_traits
    # Original must not be mutated — rewrite source and confirm store unchanged
    original_hash = asset.immutable_sha256
    src.write_bytes(b"corrupt")
    assert sha256_file(stored) == original_hash


def test_analyse_returns_estimates(tmp_path: Path) -> None:
    wav = make_groove_wav(tmp_path / "g.wav", bpm=110.0, duration_sec=6.0)
    result = analyse_audio(wav)
    p = result.profile
    assert p.is_estimate is True
    assert p.bpm_estimate is not None
    assert 60 <= p.bpm_estimate <= 180
    assert p.bpm_confidence is not None and 0 < p.bpm_confidence <= 1
    assert p.key_estimate
    assert p.key_confidence is not None
    assert len(p.beat_times) > 4
    assert len(p.energy_curve) > 0
    assert p.groove_features.onset_density is not None
    assert p.limitations
