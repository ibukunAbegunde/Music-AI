"""Heuristic / fixture transcription — no Basic Pitch download required.

Produces editable MIDI candidate notes from onset+pitch proxies on pitched stems
(especially bass). Marked simulated/estimate.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.models.schemas import MusicTrack, NoteEvent, TrackRole
from backend.app.music.midi import track_to_midifile
from backend.app.transcription.base import TranscriptionResult


def _hz_to_midi(hz: float) -> int:
    if hz <= 0:
        return 36
    return int(np.clip(round(69 + 12 * np.log2(hz / 440.0)), 24, 72))


def _estimate_f0_acf(frame: np.ndarray, sr: int, fmin: float = 40.0, fmax: float = 400.0) -> float | None:
    if len(frame) < 32:
        return None
    x = frame - np.mean(frame)
    if np.max(np.abs(x)) < 1e-6:
        return None
    corr = np.correlate(x, x, mode="full")
    corr = corr[len(corr) // 2 :]
    min_lag = max(1, int(sr / fmax))
    max_lag = min(len(corr) - 1, int(sr / fmin))
    if max_lag <= min_lag:
        return None
    seg = corr[min_lag:max_lag]
    lag = int(np.argmax(seg)) + min_lag
    if corr[lag] <= 0:
        return None
    return float(sr / lag)


class StubTranscriber:
    name = "stub"
    version = "0.1.0"
    simulated = True

    def transcribe(
        self,
        samples: np.ndarray,
        sample_rate: int,
        *,
        bpm: float | None = None,
        output_midi: Path | None = None,
        options: dict | None = None,
    ) -> TranscriptionResult:
        y = np.asarray(samples, dtype=np.float32).reshape(-1)
        sr = int(sample_rate)
        bpm = float(bpm or 110.0)
        options = options or {}
        max_notes = int(options.get("max_notes", 64))

        hop = int(0.05 * sr)  # 50 ms
        frame = int(0.1 * sr)
        beat = 60.0 / bpm
        notes: list[NoteEvent] = []

        i = 0
        while i + frame < len(y) and len(notes) < max_notes:
            chunk = y[i : i + frame]
            energy = float(np.sqrt(np.mean(chunk**2)))
            if energy < 0.02:
                i += hop
                continue
            f0 = _estimate_f0_acf(chunk, sr)
            if f0 is None:
                i += hop
                continue
            onset_sec = i / float(sr)
            onset_beats = onset_sec / beat * 4.0 / 4.0  # seconds → beats
            onset_beats = onset_sec * (bpm / 60.0)
            # Quantize lightly to 16ths but keep groove (partial)
            grid = 0.25
            q = round(onset_beats / grid) * grid
            # Prefer original microtiming slightly
            onset = 0.7 * onset_beats + 0.3 * q
            pitch = _hz_to_midi(f0)
            conf = float(np.clip(energy * 4.0, 0.2, 0.85))
            # Skip near-duplicates
            if notes and abs(notes[-1].onset_beats - onset) < 0.12 and notes[-1].pitch == pitch:
                i += hop
                continue
            notes.append(
                NoteEvent(
                    pitch=pitch,
                    onset_beats=round(max(0.0, onset), 4),
                    duration_beats=0.4,
                    velocity=int(np.clip(40 + energy * 200, 40, 110)),
                    channel=0,
                    confidence=round(conf, 3),
                    source="stub-transcriber",
                )
            )
            i += max(hop, int(0.15 * sr))

        # Ensure at least a small editable candidate when energy exists
        if not notes and float(np.max(np.abs(y))) > 1e-4:
            notes.append(
                NoteEvent(
                    pitch=36,
                    onset_beats=0.0,
                    duration_beats=0.5,
                    velocity=80,
                    confidence=0.25,
                    source="stub-fallback",
                )
            )
            notes.append(
                NoteEvent(
                    pitch=43,
                    onset_beats=1.0,
                    duration_beats=0.5,
                    velocity=75,
                    confidence=0.25,
                    source="stub-fallback",
                )
            )

        midi_path = None
        if output_midi is not None:
            track = MusicTrack(role=TrackRole.BASS, note_events=notes)
            mid = track_to_midifile(track, bpm=bpm)
            output_midi = Path(output_midi)
            output_midi.parent.mkdir(parents=True, exist_ok=True)
            mid.save(str(output_midi))
            midi_path = output_midi

        mean_conf = (
            float(np.mean([n.confidence or 0.0 for n in notes])) if notes else None
        )
        return TranscriptionResult(
            notes=notes,
            model=self.name,
            version=self.version,
            simulated=True,
            limitations=[
                "Stub heuristic transcription — not Basic Pitch.",
                "Best treated as an editable MIDI candidate; correct by ear.",
                ("Enable Basic Pitch later: pip install -e '.[basic-pitch]' "
                "then --transcriber basic_pitch (see docs/audio-models.md)."),
            ],
            midi_path=midi_path,
            confidence_mean=round(mean_conf, 3) if mean_conf is not None else None,
        )
