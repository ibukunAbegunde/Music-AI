"""Unit tests: simulation separator + stub transcription."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from backend.app.audio.io import read_wav
from backend.app.audio.separators import get_separator
from backend.app.audio.separators.demucs_adapter import DemucsNotAvailable, DemucsStemSeparator
from backend.app.transcription import get_transcriber
from backend.app.transcription.basic_pitch_adapter import (
    BasicPitchNotAvailable,
    BasicPitchTranscriber,
)
from tests.fixtures.audio import make_groove_wav


def test_simulation_separator_writes_four_stems(tmp_path: Path) -> None:
    wav = make_groove_wav(tmp_path / "mix.wav", duration_sec=3.0)
    y, sr = read_wav(wav)
    sep = get_separator("simulation")
    out = tmp_path / "stems"
    result = sep.separate(y, sr, output_dir=out)
    assert result.simulated is True
    assert {s.stem_type for s in result.stems} == {"vocals", "drums", "bass", "other"}
    for s in result.stems:
        assert (out / f"{s.stem_type}.wav").exists()
        assert "simulated" in s.confidence_flags


def test_demucs_adapter_refuses_without_install() -> None:
    sep = DemucsStemSeparator()
    with pytest.raises(DemucsNotAvailable):
        sep.separate(np.zeros(1000, dtype=np.float32), 22050)


def test_stub_transcriber_emits_midi(tmp_path: Path) -> None:
    wav = make_groove_wav(tmp_path / "mix.wav", bpm=110.0, duration_sec=4.0)
    y, sr = read_wav(wav)
    # Prefer bass-ish signal
    from backend.app.audio.separators import SimulationStemSeparator

    stems = SimulationStemSeparator().separate(y, sr)
    bass = next(s for s in stems.stems if s.stem_type == "bass")
    tr = get_transcriber("stub")
    midi = tmp_path / "bass.mid"
    result = tr.transcribe(bass.samples, bass.sample_rate, bpm=110.0, output_midi=midi)
    assert result.simulated is True
    assert len(result.notes) >= 1
    assert midi.exists()
    assert all(0 <= n.pitch <= 127 for n in result.notes)


def test_basic_pitch_adapter_refuses_without_install() -> None:
    tr = BasicPitchTranscriber()
    with pytest.raises(BasicPitchNotAvailable):
        tr.transcribe(np.zeros(1000, dtype=np.float32), 22050)


def test_unknown_separator() -> None:
    with pytest.raises(ValueError):
        get_separator("nope")
