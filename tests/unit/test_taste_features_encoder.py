"""Unit: CIR features + simulation frozen encoder (no downloads)."""

from __future__ import annotations

import numpy as np
import pytest

from backend.app.core.config import Settings
from backend.app.models.schemas import DrumEvent, MusicProject, MusicTrack, NoteEvent, TrackRole
from backend.app.taste.encoder import (
    OptionalAudioEncoderStub,
    SimulationFrozenEncoder,
    get_frozen_encoder,
)
from backend.app.taste.features import FEATURE_DIM, extract_cir_features, feature_dict


def _mini_project(**kwargs) -> MusicProject:
    tracks = [
        MusicTrack(
            role=TrackRole.KICK,
            drum_events=[
                DrumEvent(instrument_role="kick", onset_beats=0.0, velocity=100),
                DrumEvent(instrument_role="kick", onset_beats=2.0, velocity=100),
            ],
        ),
        MusicTrack(
            role=TrackRole.BASS,
            note_events=[
                NoteEvent(pitch=36, onset_beats=0.0, duration_beats=0.5, velocity=90),
                NoteEvent(pitch=38, onset_beats=1.5, duration_beats=0.5, velocity=88),
            ],
        ),
    ]
    return MusicProject(
        name="feat-test",
        bpm=110,
        length_bars=8,
        genre_template_id="afrobeats",
        key_estimate="A minor",
        tracks=tracks,
        seed=1,
        **kwargs,
    )


def test_feature_dim_and_names() -> None:
    proj = _mini_project()
    vec = extract_cir_features(proj)
    assert vec.shape == (FEATURE_DIM,)
    assert vec.dtype == np.float32
    d = feature_dict(proj)
    assert d["genre_afrobeats"] == 1.0
    assert d["density_bass"] > 0
    assert 0.0 <= d["bpm_norm"] <= 1.0


def test_simulation_encoder_deterministic() -> None:
    proj = _mini_project()
    enc = SimulationFrozenEncoder(seed=20261028)
    a = enc.encode_project(proj)
    b = enc.encode_project(proj)
    assert a.shape == (64,)
    assert np.allclose(a, b)
    assert abs(float(np.linalg.norm(a)) - 1.0) < 1e-5


def test_optional_encoder_refuses_without_flag(tmp_settings: Settings) -> None:
    stub = OptionalAudioEncoderStub()
    with pytest.raises(RuntimeError, match="not installed"):
        stub.encode_project(_mini_project())
    tmp_settings.music_ai_allow_encoder_download = False
    tmp_settings.taste_encoder = "optional"
    with pytest.raises(RuntimeError, match="MUSIC_AI_ALLOW_ENCODER_DOWNLOAD"):
        get_frozen_encoder(tmp_settings, prefer_optional=True)


def test_music_ai_allow_encoder_download_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Documented MUSIC_AI_* env name must flip the setting (not only bare ALLOW_*)."""
    monkeypatch.delenv("ALLOW_ENCODER_DOWNLOAD", raising=False)
    monkeypatch.setenv("MUSIC_AI_ALLOW_ENCODER_DOWNLOAD", "true")
    s = Settings(_env_file=None)
    assert s.music_ai_allow_encoder_download is True
    assert s.allow_encoder_download is True
    monkeypatch.setenv("MUSIC_AI_ALLOW_ENCODER_DOWNLOAD", "false")
    s2 = Settings(_env_file=None)
    assert s2.music_ai_allow_encoder_download is False


def test_default_encoder_is_simulation(tmp_settings: Settings) -> None:
    enc = get_frozen_encoder(tmp_settings)
    assert enc.name == "simulation_cir_projection"
    emb = enc.encode_project(_mini_project())
    assert emb.shape[0] == 64
