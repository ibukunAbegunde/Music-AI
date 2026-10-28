"""Deterministic 8-bar drum / bass / chord generators (Phase 0)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from random import Random

from backend.app.models.schemas import (
    DrumEvent,
    MusicProject,
    MusicTrack,
    NoteEvent,
    ProjectStatus,
    Section,
    TrackRole,
    new_id,
    utcnow,
)
from backend.app.music.theory import PROGRESSIONS, beats_per_bar, parse_key, scale_pitch, triad

# General MIDI drum map (channel 9 / 10)
GM_DRUM = {
    "kick": 36,
    "snare": 38,
    "hat": 42,
    "hat_open": 46,
    "clap": 39,
    "perc": 54,
}


@dataclass(frozen=True)
class PromptIntent:
    genre: str
    bpm: float
    key: str
    bars: int
    mood: str
    seed: int
    brief: str


def seed_from_prompt(prompt: str, explicit_seed: int | None = None) -> int:
    if explicit_seed is not None:
        return explicit_seed
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def parse_prompt(prompt: str, seed: int | None = None, bars: int = 8) -> PromptIntent:
    """Lightweight intent extraction from a creative brief (no LLM in Phase 0)."""
    lower = prompt.lower()
    genre = "default"
    for g in ("amapiano", "afrobeats", "afrobeat", "rnb", "r&b", "trap", "drill", "pop"):
        if g in lower:
            genre = "afrobeats" if g.startswith("afro") else ("rnb" if g in ("rnb", "r&b") else g)
            break

    bpm = 110.0
    bpm_match = re.search(r"(\d{2,3})\s*bpm", lower)
    if bpm_match:
        bpm = float(bpm_match.group(1))
    elif genre == "trap":
        bpm = 140.0
    elif genre == "amapiano":
        bpm = 112.0
    elif genre == "afrobeats":
        bpm = 110.0
    elif genre == "rnb":
        bpm = 90.0

    key = "A minor"
    key_match = re.search(
        r"\b([A-Ga-g](?:#|b)?)\s*(major|minor|maj|min|m)?\b",
        prompt,
    )
    if key_match:
        root = key_match.group(1).upper() if len(key_match.group(1)) == 1 else (
            key_match.group(1)[0].upper() + key_match.group(1)[1:]
        )
        mode_tok = (key_match.group(2) or "").lower()
        if mode_tok in ("m", "min", "minor") or "minor" in lower:
            key = f"{root} minor"
        elif mode_tok in ("maj", "major"):
            key = f"{root} major"
        else:
            key = f"{root} minor" if "minor" in lower else f"{root} major"

    mood = "mellow" if any(w in lower for w in ("mellow", "chill", "soft", "warm")) else "energetic"
    if any(w in lower for w in ("dark", "moody", "atmospheric")):
        mood = "atmospheric"

    return PromptIntent(
        genre=genre,
        bpm=bpm,
        key=key,
        bars=bars,
        mood=mood,
        seed=seed_from_prompt(prompt, seed),
        brief=prompt.strip(),
    )


def _humanize(rng: Random, base: float, amount: float = 0.02) -> float:
    return max(0.0, base + rng.uniform(-amount, amount))


def generate_drums(intent: PromptIntent, rng: Random, bars: int, bpb: int) -> MusicTrack:
    events: list[DrumEvent] = []
    total = bars * bpb
    for beat in range(total):
        bar_pos = beat % bpb
        # Kick on 1 and often 3; Afrobeats/Amapiano add syncopation
        if bar_pos == 0 or (bar_pos == 2 and intent.genre in ("default", "pop", "rnb", "trap")):
            events.append(
                DrumEvent(
                    instrument_role="kick",
                    onset_beats=_humanize(rng, float(beat), 0.01),
                    velocity=rng.randint(100, 120),
                    duration_beats=0.25,
                )
            )
        if intent.genre in ("afrobeats", "amapiano") and bar_pos in (1, 2) and rng.random() < 0.55:
            events.append(
                DrumEvent(
                    instrument_role="kick",
                    onset_beats=_humanize(rng, beat + 0.5, 0.015),
                    velocity=rng.randint(70, 95),
                    duration_beats=0.2,
                )
            )
        # Snare / clap on 2 and 4
        if bar_pos in (1, 3):
            role = "clap" if intent.genre in ("afrobeats", "amapiano") else "snare"
            events.append(
                DrumEvent(
                    instrument_role=role,
                    onset_beats=_humanize(rng, float(beat), 0.012),
                    velocity=rng.randint(95, 118),
                    duration_beats=0.25,
                )
            )
        # Hats every 8th; open hat occasional
        for sub in (0.0, 0.5):
            events.append(
                DrumEvent(
                    instrument_role="hat",
                    onset_beats=_humanize(rng, beat + sub, 0.008),
                    velocity=rng.randint(55, 90) if sub == 0 else rng.randint(40, 70),
                    duration_beats=0.15,
                )
            )
        if intent.genre == "amapiano" and bar_pos == 3 and rng.random() < 0.4:
            events.append(
                DrumEvent(
                    instrument_role="perc",
                    onset_beats=_humanize(rng, beat + 0.75, 0.02),
                    velocity=rng.randint(60, 100),
                    duration_beats=0.2,
                )
            )

    # Also encode as NoteEvents on GM drum channel for MIDI export convenience
    notes: list[NoteEvent] = []
    for e in events:
        pitch = GM_DRUM.get(e.instrument_role, 37)
        notes.append(
            NoteEvent(
                pitch=pitch,
                onset_beats=e.onset_beats,
                duration_beats=e.duration_beats or 0.25,
                velocity=e.velocity,
                channel=9,
                source="generator:drums",
            )
        )

    return MusicTrack(
        role=TrackRole.DRUMS,
        drum_events=events,
        note_events=notes,
        tags=[intent.genre, "drums", "phase0"],
    )


def generate_bass(intent: PromptIntent, rng: Random, bars: int, bpb: int) -> MusicTrack:
    root_pc, mode = parse_key(intent.key)
    prog = PROGRESSIONS.get(intent.genre, PROGRESSIONS["default"])
    notes: list[NoteEvent] = []
    for bar in range(bars):
        degree = prog[bar % len(prog)]
        root = scale_pitch(root_pc, degree, octave=2, mode=mode)
        onset = float(bar * bpb)
        # Root on downbeat
        notes.append(
            NoteEvent(
                pitch=root,
                onset_beats=onset,
                duration_beats=1.5 if intent.mood == "mellow" else 1.0,
                velocity=rng.randint(90, 110),
                channel=1,
                source="generator:bass",
            )
        )
        # Syncopated answer
        answer_deg = degree + (2 if rng.random() < 0.5 else 4)
        answer = scale_pitch(root_pc, answer_deg, octave=2, mode=mode)
        off = 2.0 if intent.genre not in ("afrobeats", "amapiano") else 1.5
        notes.append(
            NoteEvent(
                pitch=answer,
                onset_beats=onset + off + rng.choice([0.0, 0.5]),
                duration_beats=0.75,
                velocity=rng.randint(70, 95),
                channel=1,
                source="generator:bass",
            )
        )
        if intent.genre in ("afrobeats", "amapiano"):
            notes.append(
                NoteEvent(
                    pitch=root,
                    onset_beats=onset + 3.0,
                    duration_beats=0.5,
                    velocity=rng.randint(65, 85),
                    channel=1,
                    source="generator:bass",
                )
            )
    return MusicTrack(role=TrackRole.BASS, note_events=notes, tags=[intent.genre, "bass", "phase0"])


def generate_chords(intent: PromptIntent, rng: Random, bars: int, bpb: int) -> MusicTrack:
    root_pc, mode = parse_key(intent.key)
    prog = PROGRESSIONS.get(intent.genre, PROGRESSIONS["default"])
    notes: list[NoteEvent] = []
    for bar in range(bars):
        degree = prog[bar % len(prog)]
        pitches = triad(root_pc, degree, octave=4, mode=mode)
        onset = float(bar * bpb)
        # Rhodes-like sustained pads with slight stagger
        for i, pitch in enumerate(pitches):
            notes.append(
                NoteEvent(
                    pitch=pitch,
                    onset_beats=onset + i * 0.02,
                    duration_beats=float(bpb) - 0.1,
                    velocity=rng.randint(55, 80) if intent.mood in ("mellow", "atmospheric") else rng.randint(70, 95),
                    channel=2,
                    articulation="sustain",
                    source="generator:chords",
                )
            )
    return MusicTrack(
        role=TrackRole.CHORD,
        note_events=notes,
        tags=[intent.genre, "chords", "keys", "phase0"],
    )


def generate_eight_bar_project(
    prompt: str,
    *,
    seed: int | None = None,
    bars: int = 8,
    name: str | None = None,
) -> MusicProject:
    """Build a reproducible MusicProject with drums, bass, and chords."""
    intent = parse_prompt(prompt, seed=seed, bars=bars)
    rng = Random(intent.seed)
    bpb = beats_per_bar("4/4")

    drums = generate_drums(intent, rng, bars, bpb)
    bass = generate_bass(intent, Random(intent.seed + 1), bars, bpb)
    chords = generate_chords(intent, Random(intent.seed + 2), bars, bpb)
    tracks = [drums, bass, chords]
    section = Section(
        name="loop_a",
        start_bar=1,
        end_bar=bars,
        intensity_target=0.6,
        active_track_ids=[t.id for t in tracks],
    )

    project = MusicProject(
        id=new_id(),
        name=name or f"{intent.genre}-{intent.bpm:g}bpm-{bars}bars",
        bpm=intent.bpm,
        meter="4/4",
        key_estimate=intent.key,
        key_confidence=0.55,
        tonal_mode=parse_key(intent.key)[1],
        length_bars=bars,
        tracks=tracks,
        track_ids=[t.id for t in tracks],
        sections=[section],
        section_ids=[section.id],
        generation_brief=intent.brief,
        status=ProjectStatus.COMPOSING,
        seed=intent.seed,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    return project
