"""Optional Spotify Basic Pitch adapter — not used by default.

Install (manual):
  pip install -e '.[basic-pitch]'

Enable:
  music-ai transcribe <stem-id> --transcriber basic_pitch
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.transcription.base import TranscriptionResult


class BasicPitchNotAvailable(RuntimeError):
    pass


class BasicPitchTranscriber:
    name = "basic_pitch"
    version = "optional-uninstalled"
    simulated = False

    def transcribe(
        self,
        samples: np.ndarray,
        sample_rate: int,
        *,
        bpm: float | None = None,
        output_midi: Path | None = None,
        options: dict | None = None,
    ) -> TranscriptionResult:
        try:
            import basic_pitch  # type: ignore  # noqa: F401
        except ImportError as exc:
            raise BasicPitchNotAvailable(
                "basic-pitch is not installed. Default transcriber is 'stub'. "
                "To enable later: pip install -e '.[basic-pitch]' "
                "(may pull TensorFlow/ONNX — user-approved). See docs/audio-models.md."
            ) from exc

        raise BasicPitchNotAvailable(
            "basic-pitch is importable but Music-AI does not auto-download model "
            "weights in CI. Follow docs/audio-models.md to wire predict() locally."
        )
