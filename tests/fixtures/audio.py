"""Synthetic audio fixtures for Phase 2 tests (no copyrighted material)."""

from __future__ import annotations

from pathlib import Path

from backend.app.audio.io import synth_tone_wav


def make_groove_wav(dest: Path, *, bpm: float = 110.0, duration_sec: float = 4.0) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    return synth_tone_wav(dest, duration_sec=duration_sec, bpm=bpm, root_hz=110.0)
