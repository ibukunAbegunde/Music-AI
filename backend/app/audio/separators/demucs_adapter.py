"""Optional Demucs adapter — not used by default.

Install (manual, large download — user approval required):
  pip install -e '.[demucs]'
  # then first run may download model weights

Enable:
  MUSIC_AI_SEPARATOR=demucs
  # or music-ai separate <id> --separator demucs
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.audio.separators.base import StemSet


class DemucsNotAvailable(RuntimeError):
    pass


class DemucsStemSeparator:
    name = "demucs"
    version = "optional-uninstalled"
    simulated = False

    def separate(
        self,
        samples: np.ndarray,
        sample_rate: int,
        *,
        target_stems: list[str] | None = None,
        output_dir: Path | None = None,
        options: dict | None = None,
    ) -> StemSet:
        try:
            import demucs  # type: ignore  # noqa: F401
        except ImportError as exc:
            raise DemucsNotAvailable(
                "Demucs is not installed. Default separator is 'simulation'. "
                "To enable later (large download, user-approved): "
                "pip install -e '.[demucs]' then re-run with --separator demucs. "
                "See docs/audio-models.md."
            ) from exc

        # Real inference path intentionally not auto-wired without weights.
        # Keep interface honest rather than silently falling back.
        raise DemucsNotAvailable(
            "Demucs package is importable but Music-AI will not auto-download "
            "weights. Point DEMUCS_MODEL_PATH at a local checkpoint or follow "
            "docs/audio-models.md, then extend this adapter."
        )
