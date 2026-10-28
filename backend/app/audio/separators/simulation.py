"""Simulation stem separator — synthetic band/transient splits for CI.

Not a neural separator. Produces four broad stems (vocals/drums/bass/other)
via DSP heuristics so the pipeline and tests run without model downloads.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.audio.io import write_wav
from backend.app.audio.separators.base import StemAudio, StemSet

DEFAULT_STEMS = ["vocals", "drums", "bass", "other"]


def _butter_lowpass_fft(y: np.ndarray, sr: int, cutoff_hz: float) -> np.ndarray:
    n = len(y)
    spec = np.fft.rfft(y)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    mask = freqs <= cutoff_hz
    filtered = np.zeros_like(spec)
    filtered[mask] = spec[mask]
    return np.fft.irfft(filtered, n=n).astype(np.float32)


def _butter_highpass_fft(y: np.ndarray, sr: int, cutoff_hz: float) -> np.ndarray:
    n = len(y)
    spec = np.fft.rfft(y)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    mask = freqs >= cutoff_hz
    filtered = np.zeros_like(spec)
    filtered[mask] = spec[mask]
    return np.fft.irfft(filtered, n=n).astype(np.float32)


def _bandpass_fft(y: np.ndarray, sr: int, low: float, high: float) -> np.ndarray:
    n = len(y)
    spec = np.fft.rfft(y)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    mask = (freqs >= low) & (freqs <= high)
    filtered = np.zeros_like(spec)
    filtered[mask] = spec[mask]
    return np.fft.irfft(filtered, n=n).astype(np.float32)


def _transient_emphasize(y: np.ndarray, sr: int) -> np.ndarray:
    """High-pass + envelope follower residual as a drums proxy."""
    hp = _butter_highpass_fft(y, sr, 150.0)
    # Simple onset residual: y - heavily smoothed y
    win = max(1, int(0.05 * sr))
    kernel = np.ones(win, dtype=np.float64) / win
    smooth = np.convolve(np.abs(y), kernel, mode="same")
    env = smooth / (np.max(smooth) + 1e-9)
    transient = hp * env.astype(np.float32)
    return transient.astype(np.float32)


class SimulationStemSeparator:
    name = "simulation"
    version = "0.1.0"
    simulated = True

    def separate(
        self,
        samples: np.ndarray,
        sample_rate: int,
        *,
        target_stems: list[str] | None = None,
        output_dir: Path | None = None,
        options: dict | None = None,
    ) -> StemSet:
        y = np.asarray(samples, dtype=np.float32).reshape(-1)
        sr = int(sample_rate)
        targets = target_stems or list(DEFAULT_STEMS)

        bass = _butter_lowpass_fft(y, sr, 250.0)
        vocals = _bandpass_fft(y, sr, 300.0, 3500.0)
        drums = _transient_emphasize(y, sr)
        # other = residual after subtracting proxies (soft)
        other = (y - 0.5 * bass - 0.35 * vocals - 0.35 * drums).astype(np.float32)

        built: dict[str, np.ndarray] = {
            "bass": bass,
            "vocals": vocals,
            "drums": drums,
            "other": other,
        }

        bleed = (
            "Simulation stems are band/transient proxies — expect bleed and "
            "non-musical leakage. Not suitable for release sampling."
        )
        flags = ["simulated", "estimate", "bleed-expected"]

        stems: list[StemAudio] = []
        for stem_type in targets:
            audio = built.get(stem_type)
            if audio is None:
                audio = other
            if output_dir is not None:
                output_dir.mkdir(parents=True, exist_ok=True)
                write_wav(output_dir / f"{stem_type}.wav", audio, sr)
            stems.append(
                StemAudio(
                    stem_type=stem_type,
                    samples=audio,
                    sample_rate=sr,
                    confidence_flags=list(flags),
                    bleed_notes=bleed,
                )
            )

        return StemSet(
            stems=stems,
            model=self.name,
            version=self.version,
            limitations=[
                "Default Phase 2 separator is simulated (no Demucs weights).",
                "Enable real Demucs later via MUSIC_AI_SEPARATOR=demucs + optional extra "
                "`pip install -e '.[demucs]'` (large download; user-approved only).",
                bleed,
            ],
            simulated=True,
        )
