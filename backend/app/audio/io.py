"""Lightweight audio I/O — stdlib wave + optional ffmpeg decode.

Avoids large model / codec wheels in CI. WAV is first-class; MP3/FLAC/M4A
decode via ffmpeg when present, else clear error.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aiff", ".aif"}
NATIVE_WAV = {".wav"}


class AudioLoadError(ValueError):
    """Raised when an audio file cannot be loaded."""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> Path:
    """Write mono or stereo float32 [-1, 1] samples as 16-bit PCM WAV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(samples, dtype=np.float64)
    if arr.ndim == 1:
        channels = 1
        frames = arr
    elif arr.ndim == 2:
        channels = min(arr.shape[0], arr.shape[1])
        # Prefer (n_samples, n_channels)
        if arr.shape[0] < arr.shape[1] and arr.shape[0] <= 8:
            arr = arr.T
        channels = arr.shape[1]
        frames = arr
    else:
        raise AudioLoadError(f"unsupported sample shape {arr.shape}")

    clipped = np.clip(frames, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        if channels == 1:
            wf.writeframes(pcm.tobytes())
        else:
            interleaved = pcm.reshape(-1, channels)
            wf.writeframes(interleaved.astype("<i2").tobytes())
    return path


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """Read a WAV file → (mono float32 samples, sample_rate)."""
    path = Path(path)
    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sampwidth == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sampwidth == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise AudioLoadError(f"unsupported sample width {sampwidth}")

    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1)
    return data.astype(np.float32), int(sample_rate)


def _ffmpeg_decode_to_wav(src: Path, dest: Path, sample_rate: int = 22050) -> Path:
    if not ffmpeg_available():
        raise AudioLoadError(
            f"cannot decode {src.suffix}: ffmpeg not found. "
            "Install ffmpeg or supply a WAV/PCM file."
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-sample_fmt",
        "s16",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not dest.exists():
        raise AudioLoadError(
            f"ffmpeg failed to decode {src.name}: {proc.stderr[-400:] if proc.stderr else 'unknown'}"
        )
    return dest


def load_audio(
    path: Path,
    *,
    target_sr: int | None = 22050,
    analysis_wav_out: Path | None = None,
) -> tuple[np.ndarray, int, Path | None]:
    """Load audio to mono float32.

    Returns (samples, sample_rate, analysis_wav_path_or_none).
    Non-WAV inputs are decoded via ffmpeg into an analysis WAV derivative.
    """
    path = Path(path)
    if not path.exists():
        raise AudioLoadError(f"file not found: {path}")
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise AudioLoadError(
            f"unsupported format {ext}; accepted: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    analysis_path: Path | None = None
    if ext in NATIVE_WAV:
        samples, sr = read_wav(path)
        if target_sr and sr != target_sr:
            samples = resample_linear(samples, sr, target_sr)
            sr = target_sr
            if analysis_wav_out is not None:
                write_wav(analysis_wav_out, samples, sr)
                analysis_path = analysis_wav_out
        elif analysis_wav_out is not None:
            # Keep a PCM analysis copy (immutable original stays separate)
            write_wav(analysis_wav_out, samples, sr)
            analysis_path = analysis_wav_out
        return samples, sr, analysis_path

    out = analysis_wav_out
    if out is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        out = Path(tmp.name)
    _ffmpeg_decode_to_wav(path, out, sample_rate=target_sr or 22050)
    samples, sr = read_wav(out)
    return samples, sr, out


def resample_linear(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return samples.astype(np.float32)
    duration = len(samples) / float(orig_sr)
    n_out = max(1, int(round(duration * target_sr)))
    x_old = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, samples).astype(np.float32)


def peak_normalize(samples: np.ndarray, peak: float = 0.95) -> np.ndarray:
    mx = float(np.max(np.abs(samples))) if len(samples) else 0.0
    if mx < 1e-12:
        return samples.astype(np.float32)
    return (samples * (peak / mx)).astype(np.float32)


def rms(samples: np.ndarray) -> float:
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))


def estimate_file_duration_sec(path: Path) -> float | None:
    path = Path(path)
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    # Rough probe via ffmpeg
    if not ffmpeg_available():
        return None
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


def wav_header_info(path: Path) -> dict:
    with wave.open(str(path), "rb") as wf:
        return {
            "channels": wf.getnchannels(),
            "sample_rate": wf.getframerate(),
            "sampwidth": wf.getsampwidth(),
            "n_frames": wf.getnframes(),
            "duration_sec": wf.getnframes() / float(wf.getframerate()),
        }


def synth_tone_wav(
    path: Path,
    *,
    duration_sec: float = 2.0,
    sample_rate: int = 22050,
    bpm: float = 110.0,
    root_hz: float = 110.0,
) -> Path:
    """Deterministic synthetic groove fixture (kick + bass + hat-ish)."""
    n = int(duration_sec * sample_rate)
    t = np.arange(n, dtype=np.float64) / sample_rate
    beat = 60.0 / bpm
    samples = np.zeros(n, dtype=np.float64)

    # Kick clicks on beats
    for i in range(int(duration_sec / beat) + 1):
        start = int(i * beat * sample_rate)
        length = int(0.08 * sample_rate)
        if start >= n:
            break
        env = np.linspace(1.0, 0.0, min(length, n - start))
        kick_t = np.arange(len(env)) / sample_rate
        samples[start : start + len(env)] += 0.7 * env * np.sin(2 * np.pi * 60 * kick_t)

    # Bass notes on off-beats (bounce)
    for i in range(int(duration_sec / (beat / 2)) + 1):
        if i % 2 == 0:
            continue
        start = int(i * (beat / 2) * sample_rate)
        length = int(0.2 * sample_rate)
        if start >= n:
            break
        env = np.linspace(1.0, 0.15, min(length, n - start))
        bass_t = np.arange(len(env)) / sample_rate
        samples[start : start + len(env)] += 0.45 * env * np.sin(2 * np.pi * root_hz * bass_t)

    # High noise hats on 8ths
    rng = np.random.default_rng(42)
    for i in range(int(duration_sec / (beat / 2)) + 1):
        start = int(i * (beat / 2) * sample_rate)
        length = int(0.02 * sample_rate)
        if start >= n:
            break
        noise = rng.standard_normal(min(length, n - start))
        env = np.linspace(0.25, 0.0, len(noise))
        samples[start : start + len(noise)] += 0.15 * env * noise

    # Soft pad tone for "other/atmosphere"
    samples += 0.08 * np.sin(2 * np.pi * root_hz * 2 * t) * np.sin(2 * np.pi * 0.5 * t)

    samples = peak_normalize(samples.astype(np.float32), 0.9)
    return write_wav(path, samples, sample_rate)
