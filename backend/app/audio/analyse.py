"""Musical feature analysis — lightweight numpy DSP (estimates, not ground truth).

librosa is optional; when installed and ``prefer_librosa=True``, tempo/chroma
may use it. Default path stays dependency-light for CI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from backend.app.audio.io import load_audio, peak_normalize, rms
from backend.app.models.schemas import GrooveFeatures, ReferenceProfile, new_id

ANALYST_VERSION = "phase2-numpy-dsp-v1"

# Krumhansl-Kessler key profiles (major / minor)
_MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=np.float64,
)
_MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=np.float64,
)
_PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass
class AnalysisResult:
    profile: ReferenceProfile
    samples: np.ndarray
    sample_rate: int


def _frame_signal(y: np.ndarray, frame: int, hop: int) -> np.ndarray:
    if len(y) < frame:
        y = np.pad(y, (0, frame - len(y)))
    n_frames = 1 + (len(y) - frame) // hop
    out = np.empty((n_frames, frame), dtype=np.float64)
    for i in range(n_frames):
        start = i * hop
        out[i] = y[start : start + frame]
    return out


def _spectral_flux_onsets(y: np.ndarray, sr: int, hop: int = 512) -> tuple[np.ndarray, np.ndarray]:
    frame = 2048
    frames = _frame_signal(y, frame, hop)
    window = np.hanning(frame)
    mags = np.abs(np.fft.rfft(frames * window, axis=1))
    flux = np.maximum(0.0, np.diff(mags, axis=0, prepend=mags[:1]).sum(axis=1))
    # Normalize
    if flux.max() > 0:
        flux = flux / flux.max()
    times = np.arange(len(flux)) * hop / float(sr)
    return times.astype(np.float64), flux.astype(np.float64)


def _estimate_bpm(onset_env: np.ndarray, sr: int, hop: int = 512) -> tuple[float, float]:
    """Autocorrelation tempo estimate in a dance-music-friendly range."""
    if len(onset_env) < 8:
        return 110.0, 0.15
    # High-pass the envelope a bit
    env = onset_env - np.mean(onset_env)
    if np.max(np.abs(env)) < 1e-9:
        return 110.0, 0.1
    corr = np.correlate(env, env, mode="full")
    corr = corr[len(corr) // 2 :]
    # Lag range for 60–180 BPM
    min_bpm, max_bpm = 60.0, 180.0
    min_lag = int((60.0 / max_bpm) * sr / hop)
    max_lag = int((60.0 / min_bpm) * sr / hop)
    min_lag = max(1, min_lag)
    max_lag = min(len(corr) - 1, max(min_lag + 1, max_lag))
    segment = corr[min_lag:max_lag]
    if len(segment) == 0:
        return 110.0, 0.1
    peak_idx = int(np.argmax(segment)) + min_lag
    bpm = 60.0 * sr / (hop * peak_idx)
    # Confidence from peak prominence
    peak_val = float(corr[peak_idx])
    mean_val = float(np.mean(segment)) + 1e-9
    conf = float(np.clip((peak_val / mean_val - 1.0) / 5.0, 0.1, 0.95))
    # Prefer double/half if outside common loop tempos
    if bpm < 70:
        bpm *= 2
    if bpm > 160:
        bpm /= 2
    return float(np.clip(bpm, 60.0, 180.0)), conf


def _beat_grid(bpm: float, duration: float) -> list[float]:
    beat = 60.0 / bpm
    times = []
    t = 0.0
    while t < duration:
        times.append(round(t, 6))
        t += beat
    return times


def _chroma_vector(y: np.ndarray, sr: int) -> np.ndarray:
    frame = 4096
    hop = 2048
    frames = _frame_signal(y, frame, hop)
    window = np.hanning(frame)
    chroma = np.zeros(12, dtype=np.float64)
    freqs = np.fft.rfftfreq(frame, d=1.0 / sr)
    for fr in frames:
        mag = np.abs(np.fft.rfft(fr * window))
        for bin_i, f in enumerate(freqs):
            if f < 50 or f > 5000:
                continue
            # MIDI pitch class
            midi = 69 + 12 * np.log2(f / 440.0)
            pc = int(np.round(midi)) % 12
            chroma[pc] += mag[bin_i]
    if chroma.sum() > 0:
        chroma /= chroma.sum()
    return chroma


def _estimate_key(chroma: np.ndarray) -> tuple[str, float]:
    best_name = "C major"
    best_score = -1e9
    scores: list[float] = []
    for shift in range(12):
        rolled = np.roll(chroma, -shift)
        maj = float(np.dot(rolled, _MAJOR_PROFILE / _MAJOR_PROFILE.sum()))
        minor = float(np.dot(rolled, _MINOR_PROFILE / _MINOR_PROFILE.sum()))
        scores.extend([maj, minor])
        if maj > best_score:
            best_score = maj
            best_name = f"{_PITCH_NAMES[shift]} major"
        if minor > best_score:
            best_score = minor
            best_name = f"{_PITCH_NAMES[shift]} minor"
    # Softmax-ish confidence
    arr = np.array(scores, dtype=np.float64)
    arr = arr - arr.max()
    ex = np.exp(arr * 8)
    conf = float(ex.max() / (ex.sum() + 1e-9))
    conf = float(np.clip(conf, 0.15, 0.9))
    return best_name, conf


def _energy_curve(y: np.ndarray, sr: int, n_points: int = 32) -> list[float]:
    if len(y) == 0:
        return [0.0] * n_points
    hop = max(1, len(y) // n_points)
    vals = []
    for i in range(n_points):
        chunk = y[i * hop : (i + 1) * hop]
        vals.append(float(np.sqrt(np.mean(chunk**2))) if len(chunk) else 0.0)
    mx = max(vals) or 1.0
    return [round(v / mx, 4) for v in vals]


def _groove_from_onsets(
    times: np.ndarray, flux: np.ndarray, bpm: float
) -> GrooveFeatures:
    beat = 60.0 / bpm
    # Peak pick
    thr = float(np.mean(flux) + 0.5 * np.std(flux))
    peaks = []
    for i in range(1, len(flux) - 1):
        if flux[i] >= thr and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1]:
            peaks.append(float(times[i]))
    # Microtiming vs nearest 16th
    grid = beat / 4.0
    offsets = []
    for p in peaks:
        nearest = round(p / grid) * grid
        offsets.append(round((p - nearest) * 1000.0, 3))  # ms
    # Swing proxy: mean absolute offset of off-8th positions
    swing = None
    if offsets:
        swing = float(np.clip(np.mean(np.abs(offsets)) / 50.0, 0.0, 1.0))
    sync = None
    if peaks and beat > 0:
        # Fraction of onsets not near downbeats
        off = 0
        for p in peaks:
            rem = (p % beat) / beat
            if 0.15 < rem < 0.85:
                off += 1
        sync = off / len(peaks)
    density = len(peaks) / max(times[-1], 1e-6) if len(times) else 0.0
    return GrooveFeatures(
        onset_grid=[round(p, 4) for p in peaks[:128]],
        microtiming_offsets=offsets[:128],
        syncopation=round(sync, 4) if sync is not None else None,
        swing_estimate=round(swing, 4) if swing is not None else None,
        onset_density=round(density, 4),
        beat_strength=round(float(np.mean(flux)), 4) if len(flux) else None,
    )


def _try_librosa_tempo(y: np.ndarray, sr: int) -> tuple[float, float] | None:
    try:
        import librosa  # type: ignore
    except ImportError:
        return None
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])
    return bpm, 0.7


def analyse_audio(
    path: Path | np.ndarray,
    *,
    sample_rate: int | None = None,
    reference_id=None,
    prefer_librosa: bool = False,
) -> AnalysisResult:
    """Analyse audio file or samples → ReferenceProfile (all fields marked estimates)."""
    limitations = [
        "BPM/key/groove are heuristic estimates — verify by ear.",
        "Time signature assumed 4/4 unless overridden.",
        "No neural embeddings computed in default Phase 2 path.",
    ]
    analyst: dict[str, str] = {"dsp": ANALYST_VERSION}

    if isinstance(path, np.ndarray):
        y = peak_normalize(np.asarray(path, dtype=np.float32))
        sr = int(sample_rate or 22050)
    else:
        y, sr, _ = load_audio(Path(path), target_sr=22050)
        y = peak_normalize(y)

    hop = 512
    times, flux = _spectral_flux_onsets(y, sr, hop=hop)
    bpm, bpm_conf = _estimate_bpm(flux, sr, hop=hop)
    if prefer_librosa:
        lib = _try_librosa_tempo(y, sr)
        if lib is not None:
            bpm, bpm_conf = lib
            analyst["tempo"] = "librosa.beat.beat_track"
            limitations.append("Tempo used optional librosa path.")

    duration = len(y) / float(sr)
    beat_times = _beat_grid(bpm, duration)
    chroma = _chroma_vector(y, sr)
    key, key_conf = _estimate_key(chroma)
    groove = _groove_from_onsets(times, flux, bpm)
    energy = _energy_curve(y, sr)

    # Crude bass register energy
    frame = 2048
    window = np.hanning(frame)
    spec = np.abs(np.fft.rfft(y[:frame] * window)) if len(y) >= frame else np.abs(np.fft.rfft(y))
    freqs = np.fft.rfftfreq(min(frame, len(y)), d=1.0 / sr)
    bass_mask = (freqs >= 40) & (freqs <= 250)
    mid_mask = (freqs > 250) & (freqs <= 2000)
    high_mask = freqs > 2000
    total = float(spec.sum()) + 1e-9
    bass_ratio = float(spec[bass_mask].sum() / total) if bass_mask.any() else 0.0
    mix = {
        "rms": round(rms(y), 5),
        "peak": round(float(np.max(np.abs(y))), 5),
        "bass_energy_ratio": round(bass_ratio, 4),
        "mid_energy_ratio": round(float(spec[mid_mask].sum() / total), 4) if mid_mask.any() else 0.0,
        "high_energy_ratio": round(float(spec[high_mask].sum() / total), 4) if high_mask.any() else 0.0,
    }

    profile = ReferenceProfile(
        id=new_id(),
        reference_id=reference_id,
        bpm_estimate=round(bpm, 2),
        bpm_confidence=round(bpm_conf, 3),
        meter="4/4",
        beat_times=beat_times[:256],
        key_estimate=key,
        key_confidence=round(key_conf, 3),
        energy_curve=energy,
        timbre_tags=_timbre_tags(mix),
        genre_hypotheses=[],
        instrumentation_hypotheses=_instrument_guess(mix, groove),
        groove_features=groove,
        bass_features={
            "energy_ratio": mix["bass_energy_ratio"],
            "bounce_proxy": groove.swing_estimate,
            "onset_density": groove.onset_density,
        },
        mix_metrics=mix,
        analyst_versions=analyst,
        available_borrow_traits=[
            "bass_bounce",
            "drums",
            "percussion_texture",
            "atmosphere",
            "chords",
            "arrangement",
            "bass_rhythm",
            "groove",
            "energy",
        ],
        limitations=limitations,
        is_estimate=True,
    )
    return AnalysisResult(profile=profile, samples=y, sample_rate=sr)


def _timbre_tags(mix: dict[str, Any]) -> list[str]:
    tags = []
    if mix["bass_energy_ratio"] > 0.35:
        tags.append("bass-heavy")
    if mix["high_energy_ratio"] > 0.25:
        tags.append("bright")
    if mix["rms"] < 0.05:
        tags.append("quiet")
    if mix["peak"] > 0.9:
        tags.append("hot-peaks")
    return tags or ["balanced"]


def _instrument_guess(mix: dict[str, Any], groove: GrooveFeatures) -> list[str]:
    guesses = []
    if mix["bass_energy_ratio"] > 0.25:
        guesses.append("bass")
    if (groove.onset_density or 0) > 2.0:
        guesses.append("percussion")
    if mix["high_energy_ratio"] > 0.2:
        guesses.append("hats_or_noise")
    guesses.append("mixed")
    return guesses
