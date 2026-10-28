"""Audio → MIDI transcription adapters (Phase 2)."""

from backend.app.transcription.base import TranscriptionResult, Transcriber
from backend.app.transcription.stub import StubTranscriber


def get_transcriber(name: str | None = None) -> Transcriber:
    key = (name or "stub").lower().strip()
    if key in ("stub", "simulation", "fake", "heuristic"):
        return StubTranscriber()
    if key in ("basic_pitch", "basic-pitch"):
        from backend.app.transcription.basic_pitch_adapter import BasicPitchTranscriber

        return BasicPitchTranscriber()
    raise ValueError(f"unknown transcriber {name!r}; use 'stub' or 'basic_pitch'")


__all__ = ["TranscriptionResult", "Transcriber", "StubTranscriber", "get_transcriber"]
