"""Deterministic drum / bass / chord generators (Phase 1+3 conditioning)."""

from __future__ import annotations

from random import Random

from backend.app.models.schemas import (
    AutonomyPolicy,
    BriefDocument,
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
from backend.app.music.brief import parse_brief
from backend.app.music.coedit import apply_role_locks
from backend.app.music.conditioning import ConditioningPlan
from backend.app.music.templates import get_template
from backend.app.music.theory import PROGRESSIONS, beats_per_bar, parse_key, scale_pitch, triad

GM_DRUM = {
    "kick": 36,
    "snare": 38,
    "hat": 42,
    "hat_open": 46,
    "clap": 39,
    "perc": 54,
}


def _humanize(rng: Random, base: float, amount: float = 0.02) -> float:
    return max(0.0, base + rng.uniform(-amount, amount))


def _swing_offset(swing: float, sub: float) -> float:
    """Push off-beat 8ths later when swing > 0 (abstract groove borrow)."""
    if swing <= 0 or abs(sub - 0.5) > 0.01:
        return 0.0
    return min(0.12, swing * 0.25)


def generate_drums(
    brief: BriefDocument,
    rng: Random,
    bars: int,
    bpb: int,
    plan: ConditioningPlan | None = None,
) -> MusicTrack:
    tmpl = get_template(brief.genre_template_id or "default")
    genre = tmpl.id
    density = tmpl.groove_density * (0.7 + 0.6 * brief.novelty)
    if plan is not None:
        density *= plan.drum_density_scale
    swing = plan.swing if plan else 0.0
    events: list[DrumEvent] = []
    total = bars * bpb
    for beat in range(total):
        bar_pos = beat % bpb
        bar_idx = beat // bpb
        energy = 0.55
        if brief.energy_curve:
            ep = next((e for e in brief.energy_curve if e.bar == bar_idx + 1), None)
            if ep:
                energy = ep.value

        if bar_pos == 0 or (bar_pos == 2 and genre in ("default", "pop", "rnb", "trap", "drill")):
            events.append(
                DrumEvent(
                    instrument_role="kick",
                    onset_beats=_humanize(rng, float(beat), 0.01),
                    velocity=int(90 + 30 * energy),
                    duration_beats=0.25,
                    microtiming_ms=swing * 10.0,
                )
            )
        kick_prob = 0.45 + 0.2 * density
        if plan and plan.syncopation > 0.5:
            kick_prob += 0.1
        if genre in ("afrobeats", "amapiano") and bar_pos in (1, 2) and rng.random() < kick_prob:
            events.append(
                DrumEvent(
                    instrument_role="kick",
                    onset_beats=_humanize(rng, beat + 0.5 + _swing_offset(swing, 0.5), 0.015),
                    velocity=rng.randint(70, 95),
                    duration_beats=0.2,
                    microtiming_ms=swing * 12.0,
                )
            )
        if bar_pos in (1, 3):
            role = "clap" if genre in ("afrobeats", "amapiano") else "snare"
            events.append(
                DrumEvent(
                    instrument_role=role,
                    onset_beats=_humanize(rng, float(beat), 0.012),
                    velocity=rng.randint(95, 118),
                    duration_beats=0.25,
                )
            )
        # Hats — denser with novelty / trap / percussion borrow
        subs = [0.0, 0.5]
        if genre in ("trap", "drill") or brief.novelty > 0.6 or (plan and plan.drum_density_scale > 1.15):
            subs = [0.0, 0.25, 0.5, 0.75]
        for sub in subs:
            if rng.random() > density and sub not in (0.0, 0.5):
                continue
            events.append(
                DrumEvent(
                    instrument_role="hat",
                    onset_beats=_humanize(
                        rng, beat + sub + _swing_offset(swing, sub), 0.008
                    ),
                    velocity=rng.randint(40, 90),
                    duration_beats=0.12,
                    microtiming_ms=swing * 8.0 if abs(sub - 0.5) < 0.01 else 0.0,
                )
            )
        perc_prob = 0.45
        perc_traits = {"percussion_texture", "drums", "groove", "groove_swing"}
        if plan and perc_traits.intersection(plan.traits):
            perc_prob = 0.65
        if (genre == "amapiano" or (plan and perc_traits.intersection(plan.traits))) and bar_pos == 3 and rng.random() < perc_prob:
            events.append(
                DrumEvent(
                    instrument_role="perc",
                    onset_beats=_humanize(rng, beat + 0.75, 0.02),
                    velocity=rng.randint(60, 100),
                    duration_beats=0.2,
                )
            )
        # End-of-loop fill
        if bar_idx == bars - 1 and bar_pos == 3 and brief.novelty >= 0.3:
            events.append(
                DrumEvent(
                    instrument_role="hat_open",
                    onset_beats=_humanize(rng, beat + 0.5, 0.01),
                    velocity=rng.randint(80, 110),
                    duration_beats=0.4,
                )
            )

    notes = [
        NoteEvent(
            pitch=GM_DRUM.get(e.instrument_role, 37),
            onset_beats=e.onset_beats,
            duration_beats=e.duration_beats or 0.25,
            velocity=min(127, e.velocity),
            channel=9,
            source="generator:drums",
        )
        for e in events
    ]
    tags = [genre, "drums", "phase1"]
    if plan and plan.traits:
        tags.append("conditioned")
    return MusicTrack(
        role=TrackRole.DRUMS,
        drum_events=events,
        note_events=notes,
        tags=tags,
    )


def generate_bass(
    brief: BriefDocument,
    rng: Random,
    bars: int,
    bpb: int,
    plan: ConditioningPlan | None = None,
) -> MusicTrack:
    tmpl = get_template(brief.genre_template_id or "default")
    root_pc, mode = parse_key(brief.key or "A minor")
    prog = PROGRESSIONS.get(tmpl.progression_key, PROGRESSIONS["default"])
    notes: list[NoteEvent] = []
    offbeat = plan.bass_offbeat_bias if plan else 0.35
    density = plan.bass_density if plan else 2.0
    for bar in range(bars):
        degree = prog[bar % len(prog)]
        root = scale_pitch(root_pc, degree, octave=2, mode=mode)
        onset = float(bar * bpb)
        notes.append(
            NoteEvent(
                pitch=root,
                onset_beats=onset,
                duration_beats=1.5 if brief.novelty < 0.5 else 1.0,
                velocity=rng.randint(90, 110),
                channel=1,
                source="generator:bass",
            )
        )
        answer_deg = degree + (2 if rng.random() < 0.5 else 4)
        answer = scale_pitch(root_pc, answer_deg, octave=2, mode=mode)
        # Offbeat bias from borrowed bass_bounce (still novel pitch choices via seed)
        if tmpl.id in ("afrobeats", "amapiano") or offbeat > 0.4:
            off = 1.5 if rng.random() < offbeat else 2.0
        else:
            off = 2.0
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
        extra = density >= 2.2 or tmpl.id in ("afrobeats", "amapiano") or brief.novelty > 0.55
        if extra:
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
        if density >= 2.8 and rng.random() < 0.55:
            ghost = scale_pitch(root_pc, degree + 1, octave=2, mode=mode)
            notes.append(
                NoteEvent(
                    pitch=ghost,
                    onset_beats=onset + 0.75 + (0.25 if offbeat > 0.45 else 0.0),
                    duration_beats=0.25,
                    velocity=rng.randint(50, 70),
                    channel=1,
                    source="generator:bass",
                )
            )
        if tmpl.id in ("trap", "drill"):
            notes.append(
                NoteEvent(
                    pitch=min(127, root + 12),
                    onset_beats=onset + 0.05,
                    duration_beats=0.1,
                    velocity=rng.randint(40, 60),
                    channel=1,
                    source="generator:bass",
                )
            )
    tags = [tmpl.id, "bass", "phase1"]
    if plan and {"bass_bounce", "bass_rhythm"}.intersection(plan.traits):
        tags.append("conditioned")
    return MusicTrack(role=TrackRole.BASS, note_events=notes, tags=tags)


def generate_chords(
    brief: BriefDocument,
    rng: Random,
    bars: int,
    bpb: int,
    plan: ConditioningPlan | None = None,
) -> MusicTrack:
    tmpl = get_template(brief.genre_template_id or "default")
    root_pc, mode = parse_key(brief.key or "A minor")
    prog = PROGRESSIONS.get(tmpl.progression_key, PROGRESSIONS["default"])
    notes: list[NoteEvent] = []
    soft = (
        brief.novelty < 0.45
        or any(c.trait in {"chord_feel", "chords"} for c in brief.borrow_chips)
        or (plan is not None and plan.soft_chords)
    )
    vel_scale = plan.chord_velocity_scale if plan else 1.0
    for bar in range(bars):
        degree = prog[bar % len(prog)]
        pitches = triad(root_pc, degree, octave=4, mode=mode)
        if brief.novelty > 0.55 and rng.random() < 0.5:
            pitches.append(scale_pitch(root_pc, degree + 6, octave=4, mode=mode))
        onset = float(bar * bpb)
        for i, pitch in enumerate(pitches):
            base_lo, base_hi = (50, 75) if soft else (70, 95)
            vel = int(rng.randint(base_lo, base_hi) * vel_scale)
            notes.append(
                NoteEvent(
                    pitch=pitch,
                    onset_beats=onset + i * 0.02,
                    duration_beats=float(bpb) - 0.1,
                    velocity=max(1, min(127, vel)),
                    channel=2,
                    articulation="sustain",
                    source="generator:chords",
                )
            )
    tags = [tmpl.id, "chords", "keys", "phase1"]
    if plan and any(t in plan.traits for t in ("chord_feel", "chords", "atmosphere")):
        tags.append("conditioned")
    return MusicTrack(
        role=TrackRole.CHORD,
        note_events=notes,
        tags=tags,
    )


def generate_from_brief(
    brief: BriefDocument,
    *,
    name: str | None = None,
    plan: ConditioningPlan | None = None,
    reference_ids: list | None = None,
) -> MusicProject:
    bars = brief.length_bars
    seed = brief.seed if brief.seed is not None else 0
    rng = Random(seed)
    bpb = beats_per_bar(brief.meter)

    drums = generate_drums(brief, rng, bars, bpb, plan)
    bass = generate_bass(brief, Random(seed + 1), bars, bpb, plan)
    chords = generate_chords(brief, Random(seed + 2), bars, bpb, plan)
    tracks = [drums, bass, chords]
    section = Section(
        name="loop_a",
        start_bar=1,
        end_bar=bars,
        intensity_target=0.6,
        active_track_ids=[t.id for t in tracks],
    )
    tmpl = get_template(brief.genre_template_id or "default")
    project = MusicProject(
        id=new_id(),
        name=name or f"{tmpl.id}-{brief.bpm:g}bpm-{bars}bars",
        bpm=float(brief.bpm or tmpl.default_bpm),
        meter=brief.meter,
        key_estimate=brief.key,
        key_confidence=0.55,
        tonal_mode=parse_key(brief.key or "A minor")[1],
        length_bars=bars,
        tracks=tracks,
        track_ids=[t.id for t in tracks],
        sections=[section],
        section_ids=[section.id],
        generation_brief=brief.free_text,
        genre_template_id=tmpl.id,
        brief_id=brief.id,
        reference_ids=list(reference_ids or []),
        status=ProjectStatus.COMPOSING,
        seed=seed,
        recipe_id=brief.recipe_id,
        autonomy_policy=AutonomyPolicy(
            mode=brief.autonomy_mode,
            scratch_or_release=brief.scratch_or_release,
        ),
        schema_version="0.3.0",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    if brief.locked_roles:
        project = apply_role_locks(project, brief.locked_roles)
    return project


def generate_eight_bar_project(
    prompt: str,
    *,
    seed: int | None = None,
    bars: int = 8,
    name: str | None = None,
    locked_roles: list[str] | None = None,
) -> MusicProject:
    brief = parse_brief(prompt, seed=seed, bars=bars, locked_roles=locked_roles)
    return generate_from_brief(brief, name=name)


# Back-compat for Phase 0 tests
def parse_prompt(prompt: str, seed: int | None = None, bars: int = 8):
    from backend.app.music.generators import _PromptIntentCompat

    brief = parse_brief(prompt, seed=seed, bars=bars)
    return _PromptIntentCompat(
        genre=brief.genre_template_id or "default",
        bpm=float(brief.bpm or 110),
        key=brief.key or "A minor",
        bars=brief.length_bars,
        mood="mellow" if brief.novelty < 0.4 else "energetic",
        seed=brief.seed or 0,
        brief=brief.free_text,
    )


class _PromptIntentCompat:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def seed_from_prompt(prompt: str, explicit_seed: int | None = None) -> int:
    return parse_brief(prompt, seed=explicit_seed).seed or 0
