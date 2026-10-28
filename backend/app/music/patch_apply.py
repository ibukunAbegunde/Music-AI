"""Apply typed PatchOps / DawOperations to CIR (simulation-safe)."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from random import Random

from backend.app.models.schemas import DawOperation, MusicProject, TrackRole
from backend.app.music.brief import explicit_genre_from_text, parse_brief
from backend.app.music.coedit import (
    add_end_fill,
    humanize_track,
    is_onset_locked,
    merge_preserving_locks,
)
from backend.app.music.generators import generate_from_brief
from backend.app.music.templates import get_template

SUPPORTED_ACTIONS = frozenset(
    {
        "humanize_role",
        "quantize_role",
        "regenerate_role",
        "add_fill",
        "soften_velocity",
        "scale_velocity",
        "reduce_density",
        "nudge_bass_off_kick",
    }
)


class PatchApplyError(ValueError):
    pass


def _track_for_role(project: MusicProject, role: str | None):
    if role is None:
        return None
    return next((t for t in project.tracks if t.role.value == role), None)


def apply_patch_ops(
    project: MusicProject,
    ops: Iterable[DawOperation],
    *,
    seed: int | None = None,
) -> tuple[MusicProject, list[DawOperation]]:
    """Apply ops sequentially. Locked roles are skipped and marked rejected."""
    out = project.model_copy(deep=True)
    applied: list[DawOperation] = []
    rng_seed = seed if seed is not None else int(out.seed or 0)

    for raw in ops:
        op = raw.model_copy(deep=True)
        role = op.target_role
        track = _track_for_role(out, role)

        if role and track is None:
            op.verification_status = "rejected"
            op.observed_result = {"error": f"no track for role {role}"}
            applied.append(op)
            continue
        if track is not None and track.locked:
            op.verification_status = "rejected"
            op.observed_result = {"error": f"role {role} is locked"}
            applied.append(op)
            continue
        if op.action_type not in SUPPORTED_ACTIONS:
            op.verification_status = "rejected"
            op.observed_result = {"error": f"unsupported action {op.action_type}"}
            applied.append(op)
            continue

        try:
            out = _apply_one(out, op, seed=rng_seed)
            op.verification_status = "applied"
            op.observed_result = {"ok": True, "action": op.action_type, "role": role}
        except Exception as exc:  # noqa: BLE001 — surface to observed_result
            op.verification_status = "failed"
            op.observed_result = {"error": str(exc)}
        applied.append(op)

    return out, applied


def _apply_one(project: MusicProject, op: DawOperation, *, seed: int) -> MusicProject:
    action = op.action_type
    params = op.parameters or {}
    role = op.target_role

    if action == "humanize_role":
        out = project.model_copy(deep=True)
        for i, t in enumerate(out.tracks):
            if t.role.value == role:
                out.tracks[i] = humanize_track(
                    t,
                    seed=seed + i,
                    timing_amount=float(params.get("timing_amount", 0.015)),
                    velocity_jitter=int(params.get("velocity_jitter", 5)),
                )
        return out

    if action == "quantize_role":
        grid = float(params.get("grid", 0.25))
        return _quantize_role(project, role, grid=grid)

    if action == "add_fill":
        before = int(params.get("before_bar", project.length_bars))
        return add_end_fill(project, before_bar=before)

    if action in ("soften_velocity", "scale_velocity"):
        factor = float(params.get("factor", 0.7 if action == "soften_velocity" else 1.0))
        if "factor" not in params and action == "scale_velocity":
            factor = float(params.get("scale", 0.85))
        return _scale_velocity(project, role, factor)

    if action == "reduce_density":
        keep = float(params.get("keep_ratio", 0.75))
        return _thin_role(project, role, keep_ratio=keep, seed=seed)

    if action == "nudge_bass_off_kick":
        amount = float(params.get("amount_beats", 0.06))
        return _nudge_bass_off_kick(project, amount=amount)

    if action == "regenerate_role":
        return _regenerate_role(project, role, seed=seed, variation=str(params.get("variation", "")))

    raise PatchApplyError(f"unsupported action {action}")


def _quantize_role(project: MusicProject, role: str | None, *, grid: float) -> MusicProject:
    out = project.model_copy(deep=True)
    grid = max(1e-6, grid)
    for t in out.tracks:
        if role and t.role.value != role:
            continue
        if t.locked:
            continue
        t.note_events = [
            n
            if is_onset_locked(t, n.onset_beats)
            else n.model_copy(update={"onset_beats": round(n.onset_beats / grid) * grid})
            for n in t.note_events
        ]
        t.drum_events = [
            d
            if is_onset_locked(t, d.onset_beats)
            else d.model_copy(update={"onset_beats": round(d.onset_beats / grid) * grid})
            for d in t.drum_events
        ]
    return out


def _scale_velocity(project: MusicProject, role: str | None, factor: float) -> MusicProject:
    out = project.model_copy(deep=True)
    for t in out.tracks:
        if role and t.role.value != role:
            continue
        if t.locked:
            continue
        t.note_events = [
            n.model_copy(update={"velocity": max(1, min(127, int(n.velocity * factor)))})
            if not is_onset_locked(t, n.onset_beats)
            else n
            for n in t.note_events
        ]
        t.drum_events = [
            d.model_copy(update={"velocity": max(1, min(127, int(d.velocity * factor)))})
            if not is_onset_locked(t, d.onset_beats)
            else d
            for d in t.drum_events
        ]
    return out


def _thin_role(
    project: MusicProject, role: str | None, *, keep_ratio: float, seed: int
) -> MusicProject:
    out = project.model_copy(deep=True)
    rng = Random(seed)
    keep_ratio = max(0.2, min(1.0, keep_ratio))
    for t in out.tracks:
        if role and t.role.value != role:
            continue
        if t.locked:
            continue
        notes = []
        for n in t.note_events:
            if is_onset_locked(t, n.onset_beats) or rng.random() < keep_ratio:
                notes.append(n)
        # Always keep at least one note if we had any
        if t.note_events and not notes:
            notes = [t.note_events[0]]
        t.note_events = notes
        if t.drum_events:
            drums = []
            for d in t.drum_events:
                if is_onset_locked(t, d.onset_beats) or rng.random() < keep_ratio:
                    drums.append(d)
            t.drum_events = drums or t.drum_events[:1]
    return out


def _nudge_bass_off_kick(project: MusicProject, *, amount: float) -> MusicProject:
    kicks: list[float] = []
    for t in project.tracks:
        if t.role == TrackRole.DRUMS:
            kicks.extend(d.onset_beats for d in t.drum_events if d.instrument_role == "kick")
            kicks.extend(n.onset_beats for n in t.note_events if n.pitch == 36)
    out = project.model_copy(deep=True)
    for t in out.tracks:
        if t.role != TrackRole.BASS or t.locked:
            continue
        new_notes = []
        for n in t.note_events:
            if is_onset_locked(t, n.onset_beats):
                new_notes.append(n)
                continue
            if any(abs(n.onset_beats - k) <= 0.05 for k in kicks):
                new_notes.append(n.model_copy(update={"onset_beats": n.onset_beats + amount}))
            else:
                new_notes.append(n)
        t.note_events = new_notes
    return out


def _regenerate_role(
    project: MusicProject, role: str | None, *, seed: int, variation: str
) -> MusicProject:
    if role is None:
        raise PatchApplyError("regenerate_role requires target_role")
    # Preserve locks: regenerate full project then merge so locked tracks stay.
    locked = [t.role.value for t in project.tracks if t.locked]
    if role in locked:
        raise PatchApplyError(f"cannot regenerate locked role {role}")
    # Prefer persisted genre_template_id — generation_brief may be revise text
    brief_text = project.generation_brief or (
        f"{project.key_estimate or ''} {project.bpm:g} BPM"
    )
    brief = parse_brief(
        brief_text,
        seed=seed + 17,
        bars=project.length_bars,
        locked_roles=locked,
    )
    brief.bpm = project.bpm
    brief.key = project.key_estimate
    parent_genre = project.genre_template_id or explicit_genre_from_text(
        project.generation_brief or ""
    )
    if parent_genre:
        brief.genre_template_id = parent_genre
        tmpl = get_template(parent_genre)
        brief.title = f"{tmpl.name} patch"
    # Soften / voicing cues via seed offset
    if variation == "softer":
        brief.novelty = max(0.0, (brief.novelty or 0.4) - 0.1)
    regenerated = generate_from_brief(brief, name=project.name + "-patch")
    # Only take the target role from regen; keep others from project
    partial = project.model_copy(deep=True)
    regen_track = next((t for t in regenerated.tracks if t.role.value == role), None)
    if regen_track is None:
        raise PatchApplyError(f"generator produced no {role}")
    new_tracks = []
    for t in partial.tracks:
        if t.role.value == role:
            rt = deepcopy(regen_track)
            rt.id = t.id
            rt.locked = False
            rt.locked_bar_ranges = list(t.locked_bar_ranges)
            if variation == "softer" and rt.note_events:
                rt.note_events = [
                    n.model_copy(update={"velocity": max(1, int(n.velocity * 0.7))})
                    for n in rt.note_events
                ]
            new_tracks.append(rt)
        else:
            new_tracks.append(t)
    partial.tracks = new_tracks
    # Re-merge against locked parent for bar-locks
    parent_locked = project.model_copy(deep=True)
    for t in parent_locked.tracks:
        if t.role.value in locked:
            t.locked = True
    return merge_preserving_locks(parent_locked, partial)
