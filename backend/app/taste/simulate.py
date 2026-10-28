"""Synthetic pairwise preference dataset for CI / simulation demos.

Builds a latent preference direction over CIR features so the ranking head
can beat random + retrieval on held-out projects without real listening data.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import numpy as np

from backend.app.core.config import Settings
from backend.app.models.schemas import (
    DrumEvent,
    MusicProject,
    MusicTrack,
    NoteEvent,
    PreferenceComparison,
    TrackRole,
    new_id,
    utcnow,
)
from backend.app.taste.dataset import append_comparison
from backend.app.taste.encoder import SimulationFrozenEncoder
from backend.app.taste.features import extract_cir_features


@dataclass
class SimulatedPair:
    project_id: UUID
    project_a: MusicProject
    project_b: MusicProject
    choice: str  # a | b
    comparison: PreferenceComparison
    emb_a: np.ndarray
    emb_b: np.ndarray
    label: float  # 1 if B preferred


def _synth_project(
    *,
    project_id: UUID,
    seed: int,
    bpm: float,
    genre: str,
    bass_density: float,
    drum_vel: int,
    syncopation: float,
) -> MusicProject:
    rng = np.random.default_rng(seed)
    bars = 8
    tracks: list[MusicTrack] = []

    # kick on quarters
    kicks = [
        DrumEvent(instrument_role="kick", onset_beats=float(b * 4 + i), velocity=drum_vel)
        for b in range(bars)
        for i in (0, 2)
    ]
    tracks.append(MusicTrack(role=TrackRole.KICK, drum_events=kicks))

    snares = [
        DrumEvent(instrument_role="snare", onset_beats=float(b * 4 + 1), velocity=drum_vel - 5)
        for b in range(bars)
    ]
    tracks.append(MusicTrack(role=TrackRole.SNARE, drum_events=snares))

    hats = []
    for b in range(bars):
        for step in range(8):
            onset = b * 4 + step * 0.5
            if syncopation > 0.3 and step % 2 == 1:
                onset += 0.08 * syncopation
            hats.append(
                DrumEvent(
                    instrument_role="hat",
                    onset_beats=float(onset),
                    velocity=max(40, drum_vel - 20),
                )
            )
    tracks.append(MusicTrack(role=TrackRole.HAT, drum_events=hats))

    n_bass = max(4, int(bass_density * 24))
    bass_notes = []
    for i in range(n_bass):
        onset = float((i * (bars * 4) / n_bass) + (0.25 if syncopation > 0.4 else 0.0))
        pitch = int(36 + (i % 5) * 2 + int(rng.integers(0, 2)))
        bass_notes.append(
            NoteEvent(
                pitch=pitch,
                onset_beats=onset % (bars * 4),
                duration_beats=0.5,
                velocity=int(np.clip(drum_vel - 10 + rng.integers(-5, 6), 40, 120)),
            )
        )
    tracks.append(MusicTrack(role=TrackRole.BASS, note_events=bass_notes))

    chord_notes = [
        NoteEvent(pitch=60 + (i % 3) * 4, onset_beats=float(b * 4), duration_beats=2.0, velocity=70)
        for b in range(bars)
        for i in range(3)
    ]
    tracks.append(MusicTrack(role=TrackRole.CHORD, note_events=chord_notes))

    return MusicProject(
        id=project_id,
        name=f"sim-{genre}-{seed}",
        bpm=bpm,
        length_bars=bars,
        genre_template_id=genre,
        key_estimate="A minor",
        tracks=tracks,
        seed=seed,
        version_id=new_id(),
        schema_version="0.3.0",
    )


def _latent_score(features: np.ndarray, direction: np.ndarray) -> float:
    return float(features @ direction)


def build_simulated_dataset(
    *,
    n_projects: int = 8,
    pairs_per_project: int = 4,
    settings: Settings | None = None,
    seed: int = 42,
    persist: bool = True,
) -> list[SimulatedPair]:
    """Generate synthetic A/B pairs with a planted preference direction."""
    rng = np.random.default_rng(seed)
    encoder = SimulationFrozenEncoder(seed=20261028)
    # Prefer higher bass density, moderate syncopation, mid BPM afrobeats-ish
    direction = np.zeros(32, dtype=np.float64)
    # indices from FEATURE_NAMES
    direction[8] = 1.2  # density_bass
    direction[19] = 0.8  # syncopation_proxy
    direction[12] = 0.4  # mean_vel_drums
    direction[24] = 0.5  # genre_afrobeats
    direction = direction / (np.linalg.norm(direction) + 1e-9)

    genres = ["afrobeats", "amapiano", "rnb", "trap"]
    pairs: list[SimulatedPair] = []

    for p in range(n_projects):
        project_id = uuid4()
        genre = genres[p % len(genres)]
        bpm = float(100 + (p % 4) * 5)
        for k in range(pairs_per_project):
            seed_a = seed + p * 100 + k * 2
            seed_b = seed_a + 1
            # Push A/B to opposite sides of the planted preference axis
            low = float(rng.uniform(0.15, 0.35))
            high = float(rng.uniform(0.65, 0.95))
            if rng.random() < 0.5:
                dens_a, dens_b = low, high
                sync_a, sync_b = low, high
                vel_a, vel_b = 75, 105
            else:
                dens_a, dens_b = high, low
                sync_a, sync_b = high, low
                vel_a, vel_b = 105, 75
            a = _synth_project(
                project_id=project_id,
                seed=seed_a,
                bpm=bpm + rng.uniform(-2, 2),
                genre=genre,
                bass_density=dens_a,
                drum_vel=vel_a,
                syncopation=sync_a,
            )
            b = _synth_project(
                project_id=project_id,
                seed=seed_b,
                bpm=bpm + rng.uniform(-2, 2),
                genre=genre,
                bass_density=dens_b,
                drum_vel=vel_b,
                syncopation=sync_b,
            )
            # ensure distinct version ids
            a.version_id = new_id()
            b.version_id = new_id()
            fa = extract_cir_features(a)
            fb = extract_cir_features(b)
            sa = _latent_score(fa, direction)
            sb = _latent_score(fb, direction)
            # tiny noise — keep label aligned with planted axis
            sa += float(rng.normal(0, 0.005))
            sb += float(rng.normal(0, 0.005))
            choice = "b" if sb >= sa else "a"
            label = 1.0 if choice == "b" else 0.0
            emb_a = encoder.encode_features(fa)
            emb_b = encoder.encode_features(fb)
            comp = PreferenceComparison(
                context={
                    "project_id": str(project_id),
                    "genre": genre,
                    "genre_template_id": genre,
                    "task": "simulated_taste",
                    "simulated": True,
                },
                render_a_id=new_id(),
                render_b_id=new_id(),
                user_choice=choice,
                optional_reason="simulated latent preference",
                tags=["simulated", "bass" if abs(fa[8] - fb[8]) > 0.05 else "groove"],
                timestamp=utcnow(),
                blind_status=True,
                project_id=project_id,
                version_a_id=a.version_id,
                version_b_id=b.version_id,
            )
            if persist and settings is not None:
                append_comparison(
                    comp,
                    settings=settings,
                    feature_a=fa.tolist(),
                    feature_b=fb.tolist(),
                )
            pairs.append(
                SimulatedPair(
                    project_id=project_id,
                    project_a=a,
                    project_b=b,
                    choice=choice,
                    comparison=comp,
                    emb_a=emb_a,
                    emb_b=emb_b,
                    label=label,
                )
            )
    return pairs
