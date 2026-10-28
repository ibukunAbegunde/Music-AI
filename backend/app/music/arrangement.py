"""Phase 6 arrangement: structure template → multi-section full instrumental CIR."""

from __future__ import annotations

from copy import deepcopy
from random import Random

from backend.app.models.schemas import (
    ArrangementPlan,
    BriefDocument,
    EnergyPoint,
    MusicProject,
    MusicTrack,
    Section,
    SectionDraft,
    TrackRole,
)
from backend.app.music.brief import parse_brief
from backend.app.music.coedit import add_end_fill
from backend.app.music.conditioning import ConditioningPlan
from backend.app.music.generators import generate_from_brief
from backend.app.music.structure_templates import (
    get_structure_template,
    resolve_structure_id,
    validate_section_map,
)
from backend.app.music.theory import beats_per_bar


MIN_FULL_BARS = 32
MAX_FULL_BARS = 256
DEFAULT_MOTIF_BARS = 8

# Section kinds that stay sparse (drop bass or thin drums)
_SPARSE_KINDS = {"intro", "outro", "break"}
_SOFT_KINDS = {"bridge", "prechorus", "verse_b"}


def energy_curve_from_sections(section_map: list[SectionDraft]) -> list[EnergyPoint]:
    points: list[EnergyPoint] = []
    for sec in section_map:
        for bar in range(sec.start_bar, sec.end_bar + 1):
            points.append(EnergyPoint(bar=bar, value=float(sec.intensity_target)))
    return points


def build_arrangement_plan(
    brief: BriefDocument,
    *,
    structure_id: str | None = None,
    length_bars: int | None = None,
) -> ArrangementPlan:
    """Resolve structure template onto the brief and return a concrete plan."""
    sid = resolve_structure_id(structure_id, brief.genre_template_id)
    tmpl = get_structure_template(sid)
    bars = int(length_bars or tmpl.length_bars)
    if bars < MIN_FULL_BARS or bars > MAX_FULL_BARS:
        raise ValueError(f"full-length bars must be {MIN_FULL_BARS}–{MAX_FULL_BARS}")

    section_map = list(tmpl.section_map)
    if bars != tmpl.length_bars:
        section_map = _rescale_section_map(section_map, tmpl.length_bars, bars)
    validate_section_map(section_map, bars)

    approvals: list[str] = []
    notes = [
        f"structure={tmpl.id}",
        f"length_bars={bars}",
        f"sections={len(section_map)}",
        "simulation/MIDI path — live FL Playlist placement is manual",
    ]
    if brief.scratch_or_release == "release":
        approvals.append("release_mode_daw_write")
        notes.append("Release mode: DAW writes require explicit approval / Scratch preferred")

    return ArrangementPlan(
        structure_template_id=tmpl.id,
        genre_template_id=tmpl.genre_template_id,
        length_bars=bars,
        section_map=section_map,
        instrument_palette=dict(tmpl.instrument_palette),
        energy_curve=energy_curve_from_sections(section_map),
        motif_bars=DEFAULT_MOTIF_BARS,
        scratch_or_release=brief.scratch_or_release,
        autonomy_mode=brief.autonomy_mode,
        approvals_required=approvals,
        notes=notes,
    )


def apply_plan_to_brief(brief: BriefDocument, plan: ArrangementPlan) -> BriefDocument:
    out = brief.model_copy(deep=True)
    out.length_bars = plan.length_bars
    out.section_map = list(plan.section_map)
    out.energy_curve = list(plan.energy_curve)
    if not out.genre_template_id:
        out.genre_template_id = plan.genre_template_id
    out.scratch_or_release = plan.scratch_or_release
    return out


def _rescale_section_map(
    section_map: list[SectionDraft], from_bars: int, to_bars: int
) -> list[SectionDraft]:
    """Proportionally stretch/shrink section boundaries to a new length."""
    if from_bars <= 0:
        raise ValueError("from_bars must be > 0")
    scale = to_bars / from_bars
    out: list[SectionDraft] = []
    cursor = 1
    for i, sec in enumerate(section_map):
        raw_len = sec.end_bar - sec.start_bar + 1
        new_len = max(1, int(round(raw_len * scale)))
        if i == len(section_map) - 1:
            end = to_bars
            start = min(cursor, to_bars)
        else:
            start = cursor
            end = min(to_bars, start + new_len - 1)
        if end < start:
            end = start
        out.append(
            SectionDraft(
                name=sec.name,
                start_bar=start,
                end_bar=end,
                intensity_target=sec.intensity_target,
            )
        )
        cursor = end + 1
        if cursor > to_bars:
            break
    if out and out[-1].end_bar != to_bars:
        out[-1].end_bar = to_bars
    return out


def _section_kind(name: str) -> str:
    return name.lower().split("_")[0].split("-")[0]


def _apply_section_intensity(
    project: MusicProject,
    section_map: list[SectionDraft],
    *,
    seed: int,
) -> MusicProject:
    """Scale velocities / thin sparse sections; attach multi-section CIR metadata."""
    out = project.model_copy(deep=True)
    bpb = beats_per_bar(out.meter)
    rng = Random(seed + 17)

    # Build beat-range → intensity + kind
    bar_info: dict[int, tuple[float, str]] = {}
    for sec in section_map:
        kind = _section_kind(sec.name)
        for bar in range(sec.start_bar, sec.end_bar + 1):
            bar_info[bar] = (float(sec.intensity_target), kind)

    last_bar = max(bar_info) if bar_info else out.length_bars

    def scale_track(track: MusicTrack) -> MusicTrack:
        t = track.model_copy(deep=True)
        new_notes = []
        for n in t.note_events:
            bar = int(n.onset_beats // bpb) + 1
            intensity, kind = bar_info.get(bar, (0.55, "verse"))
            # Keep final bars intact so span asserts / MIDI playback remain honest.
            protect = bar >= last_bar - 1
            # Sparse intros/outros: drop some non-kick material
            if kind in _SPARSE_KINDS and not protect:
                if t.role == TrackRole.BASS and rng.random() > 0.45:
                    continue
                if t.role == TrackRole.CHORD and rng.random() > 0.55:
                    continue
            vel_scale = 0.55 + 0.7 * intensity
            if kind in _SOFT_KINDS:
                vel_scale *= 0.9
            nn = n.model_copy(deep=True)
            nn.velocity = max(1, min(127, int(nn.velocity * vel_scale)))
            new_notes.append(nn)
        if t.role == TrackRole.DRUMS:
            new_drums = []
            for d in t.drum_events:
                bar = int(d.onset_beats // bpb) + 1
                intensity, kind = bar_info.get(bar, (0.55, "verse"))
                protect = bar >= last_bar - 1
                if (
                    kind in _SPARSE_KINDS
                    and not protect
                    and d.instrument_role in ("hat", "hat_open", "perc")
                ):
                    if rng.random() > 0.4:
                        continue
                dd = d.model_copy(deep=True)
                dd.velocity = max(1, min(127, int(dd.velocity * (0.55 + 0.7 * intensity))))
                new_drums.append(dd)
            t.drum_events = new_drums
        t.note_events = new_notes
        return t

    out.tracks = [scale_track(t) for t in out.tracks]
    out.track_ids = [t.id for t in out.tracks]

    sections: list[Section] = []
    for sec in section_map:
        kind = _section_kind(sec.name)
        active = [t.id for t in out.tracks]
        # Intro/outro: still keep track ids but note sparsity in transition
        transition = None
        if kind in _SPARSE_KINDS:
            transition = "sparse palette — thinned bass/chords"
        elif kind == "chorus":
            transition = "full intensity"
        sections.append(
            Section(
                name=sec.name,
                start_bar=sec.start_bar,
                end_bar=sec.end_bar,
                intensity_target=sec.intensity_target,
                active_track_ids=active,
                transition_notes=transition,
            )
        )
    out.sections = sections
    out.section_ids = [s.id for s in sections]
    out.length_bars = section_map[-1].end_bar
    out.schema_version = "0.4.0"
    return out


def generate_arranged_project(
    brief: BriefDocument,
    plan: ArrangementPlan,
    *,
    name: str | None = None,
    plan_conditioning: ConditioningPlan | None = None,
    reference_ids: list | None = None,
) -> MusicProject:
    """Generate a full multi-section instrumental from an ArrangementPlan."""
    arranged_brief = apply_plan_to_brief(brief, plan)
    project = generate_from_brief(
        arranged_brief,
        name=name or f"{plan.genre_template_id}-full-{plan.length_bars}bars",
        plan=plan_conditioning,
        reference_ids=reference_ids,
    )
    project = _apply_section_intensity(
        project, plan.section_map, seed=int(arranged_brief.seed or 0)
    )
    # Boundary fill before final chorus / end
    last = plan.section_map[-1]
    if last.end_bar >= 8:
        project = add_end_fill(project, before_bar=last.end_bar)
    # Mid-song fill before last chorus if present
    choruses = [s for s in plan.section_map if _section_kind(s.name) == "chorus"]
    if len(choruses) >= 2:
        project = add_end_fill(project, before_bar=choruses[-1].start_bar)
    return project


def brief_for_full_compose(
    prompt: str,
    *,
    seed: int | None = None,
    structure_id: str | None = None,
    bars: int | None = None,
    scratch_or_release: str = "scratch",
    autonomy_mode: str = "collaborative",
    locked_roles: list[str] | None = None,
) -> tuple[BriefDocument, ArrangementPlan]:
    """Parse NL brief and bind a full-length arrangement plan."""
    # Parse at loop length first for genre/bpm/key, then expand via plan.
    brief = parse_brief(
        prompt,
        seed=seed,
        bars=8,
        locked_roles=locked_roles,
        scratch_or_release=scratch_or_release,
    )
    brief.autonomy_mode = autonomy_mode
    brief.scratch_or_release = scratch_or_release
    plan = build_arrangement_plan(brief, structure_id=structure_id, length_bars=bars)
    brief = apply_plan_to_brief(brief, plan)
    return brief, plan


def section_dicts_for_daw(project: MusicProject) -> list[dict]:
    """Serialize CIR sections for FakeDaw.arrange_section / manual Playlist docs."""
    return [
        {
            "name": s.name,
            "start_bar": s.start_bar,
            "end_bar": s.end_bar,
            "intensity_target": s.intensity_target,
            "transition_notes": s.transition_notes,
            "active_track_ids": [str(x) for x in s.active_track_ids],
        }
        for s in project.sections
    ]


def clone_brief_with_plan(brief: BriefDocument, plan: ArrangementPlan) -> BriefDocument:
    return apply_plan_to_brief(deepcopy(brief), plan)
