"""Deterministic CIR → feature vector for taste ranking (no audio model).

Features are transparent musical/production proxies derived from MIDI/CIR.
They are *not* pretrained audio embeddings — those plug in via the encoder
adapter when an optional model is installed and approved.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from backend.app.models.schemas import MusicProject, TrackRole

FEATURE_DIM = 32
FEATURE_NAMES: list[str] = [
    "bpm_norm",
    "bars_norm",
    "n_tracks",
    "n_locked",
    "density_kick",
    "density_snare",
    "density_hat",
    "density_perc",
    "density_bass",
    "density_chord",
    "density_lead",
    "density_pad",
    "mean_vel_drums",
    "mean_vel_bass",
    "mean_vel_harmony",
    "pitch_mean_bass",
    "pitch_span_bass",
    "pitch_mean_chord",
    "pitch_span_harmony",
    "syncopation_proxy",
    "swing_proxy",
    "fill_end_proxy",
    "kick_bass_overlap",
    "novelty_proxy",
    "genre_afrobeats",
    "genre_amapiano",
    "genre_rnb",
    "genre_trap",
    "genre_drill",
    "key_brightness",
    "meter_is_44",
    "seed_parity",
]

_ROLE_DENSITY = {
    TrackRole.KICK: "density_kick",
    TrackRole.SNARE: "density_snare",
    TrackRole.HAT: "density_hat",
    TrackRole.PERCUSSION: "density_perc",
    TrackRole.DRUMS: "density_kick",  # fold into kick bucket as coarse proxy
    TrackRole.BASS: "density_bass",
    TrackRole.CHORD: "density_chord",
    TrackRole.LEAD: "density_lead",
    TrackRole.PAD: "density_pad",
}

_GENRE_FLAGS = {
    "afrobeats": "genre_afrobeats",
    "amapiano": "genre_amapiano",
    "rnb": "genre_rnb",
    "r&b": "genre_rnb",
    "trap": "genre_trap",
    "drill": "genre_drill",
}

_KEY_BRIGHT = {
    "C": 0.5,
    "G": 0.7,
    "D": 0.75,
    "A": 0.8,
    "E": 0.85,
    "B": 0.9,
    "F#": 0.95,
    "F": 0.4,
    "Bb": 0.35,
    "Eb": 0.3,
    "Ab": 0.25,
    "Db": 0.2,
}


def _note_density(n_events: int, bars: int) -> float:
    denom = max(bars, 1) * 4.0  # 16th-grid slots per bar rough
    return float(min(1.0, n_events / max(denom, 1.0)))


def _mean_vel(events: list[Any]) -> float:
    if not events:
        return 0.0
    return float(np.mean([getattr(e, "velocity", 64) for e in events]) / 127.0)


def _pitches(notes: list[Any]) -> list[int]:
    return [int(n.pitch) for n in notes]


def extract_cir_features(project: MusicProject) -> np.ndarray:
    """Return a length-FEATURE_DIM float32 vector from a MusicProject CIR."""
    vec = {name: 0.0 for name in FEATURE_NAMES}
    bars = max(int(project.length_bars), 1)
    vec["bpm_norm"] = float(np.clip((project.bpm - 60.0) / 120.0, 0.0, 1.0))
    vec["bars_norm"] = float(np.clip(bars / 32.0, 0.0, 1.0))
    vec["n_tracks"] = float(min(1.0, len(project.tracks) / 12.0))
    vec["n_locked"] = float(min(1.0, sum(1 for t in project.tracks if t.locked) / 8.0))
    vec["meter_is_44"] = 1.0 if project.meter.startswith("4") else 0.0
    vec["seed_parity"] = 1.0 if (project.seed or 0) % 2 == 0 else 0.0
    vec["novelty_proxy"] = 0.4

    drum_events: list[Any] = []
    bass_notes: list[Any] = []
    harm_notes: list[Any] = []
    kick_onsets: list[float] = []
    bass_onsets: list[float] = []

    for track in project.tracks:
        role = track.role
        n_notes = len(track.note_events)
        n_drums = len(track.drum_events)
        key = _ROLE_DENSITY.get(role)
        if key:
            vec[key] = max(vec[key], _note_density(n_notes + n_drums, bars))

        if role in (TrackRole.KICK, TrackRole.SNARE, TrackRole.HAT, TrackRole.PERCUSSION, TrackRole.DRUMS):
            drum_events.extend(track.drum_events or track.note_events)
            if role in (TrackRole.KICK, TrackRole.DRUMS):
                for e in track.drum_events:
                    kick_onsets.append(float(e.onset_beats))
                for e in track.note_events:
                    kick_onsets.append(float(e.onset_beats))
        elif role == TrackRole.BASS:
            bass_notes.extend(track.note_events)
            for e in track.note_events:
                bass_onsets.append(float(e.onset_beats))
        elif role in (TrackRole.CHORD, TrackRole.LEAD, TrackRole.PAD):
            harm_notes.extend(track.note_events)

    vec["mean_vel_drums"] = _mean_vel(drum_events)
    vec["mean_vel_bass"] = _mean_vel(bass_notes)
    vec["mean_vel_harmony"] = _mean_vel(harm_notes)

    bp = _pitches(bass_notes)
    if bp:
        vec["pitch_mean_bass"] = float(np.clip(np.mean(bp) / 127.0, 0.0, 1.0))
        vec["pitch_span_bass"] = float(np.clip((max(bp) - min(bp)) / 24.0, 0.0, 1.0))
    hp = _pitches(harm_notes)
    if hp:
        vec["pitch_mean_chord"] = float(np.clip(np.mean(hp) / 127.0, 0.0, 1.0))
        vec["pitch_span_harmony"] = float(np.clip((max(hp) - min(hp)) / 36.0, 0.0, 1.0))

    # Syncopation / swing proxies from onset fractional beats
    all_onsets = kick_onsets + bass_onsets
    if all_onsets:
        frac = np.array([o % 1.0 for o in all_onsets], dtype=np.float64)
        offbeat = np.mean((frac > 0.2) & (frac < 0.8))
        vec["syncopation_proxy"] = float(offbeat)
        # swing: bias toward late 8ths (~0.66)
        late = np.mean(np.abs(frac - 0.66) < 0.12)
        vec["swing_proxy"] = float(late)

    # End-of-loop fill proxy: density in last bar
    last_bar_start = float((bars - 1) * 4)
    end_hits = sum(1 for o in all_onsets if o >= last_bar_start)
    vec["fill_end_proxy"] = float(min(1.0, end_hits / 8.0))

    # Kick/bass overlap within 50ms of a 16th (~0.06 beats at 4/4)
    overlap = 0
    for bo in bass_onsets:
        if any(abs(bo - ko) < 0.08 for ko in kick_onsets):
            overlap += 1
    vec["kick_bass_overlap"] = float(min(1.0, overlap / max(len(bass_onsets), 1)))

    genre = (project.genre_template_id or "").lower()
    for key, flag in _GENRE_FLAGS.items():
        if key in genre:
            vec[flag] = 1.0

    if project.key_estimate:
        root = project.key_estimate.split()[0].replace("minor", "").replace("major", "").strip()
        # normalize flats
        root = root.replace("♭", "b").replace("♯", "#")
        for k, bright in _KEY_BRIGHT.items():
            if root.upper().startswith(k.upper()) or root == k:
                vec["key_brightness"] = bright
                break

    out = np.array([vec[n] for n in FEATURE_NAMES], dtype=np.float32)
    assert out.shape == (FEATURE_DIM,)
    return out


def feature_dict(project: MusicProject) -> dict[str, float]:
    arr = extract_cir_features(project)
    return {n: float(v) for n, v in zip(FEATURE_NAMES, arr, strict=True)}
