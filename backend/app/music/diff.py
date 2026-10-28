"""CIR musical diff between MusicProject versions."""

from __future__ import annotations

from backend.app.models.schemas import MusicalDiff, MusicProject, NoteEvent, new_id


def _note_signature(n: NoteEvent) -> tuple:
    return (
        n.pitch,
        round(n.onset_beats, 3),
        round(n.duration_beats, 3),
        n.velocity,
        n.channel,
    )


def _role_note_counts(project: MusicProject) -> dict[str, int]:
    return {t.role.value: len(t.note_events) for t in project.tracks}


def _role_note_sigs(project: MusicProject) -> dict[str, list[tuple]]:
    return {
        t.role.value: sorted(_note_signature(n) for n in t.note_events)
        for t in project.tracks
    }


def _avg_velocity(project: MusicProject, role: str) -> float | None:
    for t in project.tracks:
        if t.role.value == role and t.note_events:
            return sum(n.velocity for n in t.note_events) / len(t.note_events)
    return None


def _pitch_set(project: MusicProject, role: str) -> set[int]:
    for t in project.tracks:
        if t.role.value == role:
            return {n.pitch for n in t.note_events}
    return set()


def diff_projects(
    before: MusicProject,
    after: MusicProject,
    *,
    from_version_id=None,
    to_version_id=None,
    expected_locked: list[str] | None = None,
) -> MusicalDiff:
    before_counts = _role_note_counts(before)
    after_counts = _role_note_counts(after)
    before_sigs = _role_note_sigs(before)
    after_sigs = _role_note_sigs(after)
    roles = sorted(set(before_counts) | set(after_counts) | set(before_sigs) | set(after_sigs))
    deltas: dict[str, int] = {}
    changed: list[str] = []
    details: list[str] = []
    for role in roles:
        d = after_counts.get(role, 0) - before_counts.get(role, 0)
        deltas[role] = d
        content_changed = before_sigs.get(role, []) != after_sigs.get(role, [])
        if d != 0:
            changed.append(role)
            details.append(
                f"{role}: note count {before_counts.get(role, 0)} → {after_counts.get(role, 0)}"
            )
        elif content_changed:
            changed.append(role)
            bp = _pitch_set(before, role)
            ap = _pitch_set(after, role)
            if bp != ap:
                details.append(f"{role}: pitch content changed ({sorted(bp)} → {sorted(ap)})")
            else:
                details.append(f"{role}: note timing/velocity content changed")
        bv = _avg_velocity(before, role)
        av = _avg_velocity(after, role)
        if bv is not None and av is not None and abs(av - bv) >= 3:
            if role not in changed:
                changed.append(role)
            details.append(f"{role}: avg velocity {bv:.0f} → {av:.0f}")

    # Harmony / groove heuristics
    harmony: list[str] = []
    groove: list[str] = []
    if before.key_estimate != after.key_estimate:
        harmony.append(f"key {before.key_estimate} → {after.key_estimate}")
        details.append(f"key {before.key_estimate} → {after.key_estimate}")
    if abs((before.bpm or 0) - (after.bpm or 0)) > 0.01:
        details.append(f"bpm {before.bpm} → {after.bpm}")
    if "drums" in changed:
        groove.append("drum pattern altered")
    if "bass" in changed:
        harmony.append("bass line altered")
    if "chord" in changed:
        harmony.append("chord voicings altered")

    density_before = sum(before_counts.values()) / max(before.length_bars, 1)
    density_after = sum(after_counts.values()) / max(after.length_bars, 1)
    density_delta = density_after - density_before

    locked_ok = True
    expected = expected_locked or [t.role.value for t in before.tracks if t.locked]
    for role in expected:
        bt = next((t for t in before.tracks if t.role.value == role), None)
        at = next((t for t in after.tracks if t.role.value == role), None)
        if bt and at:
            if [n.model_dump() for n in bt.note_events] != [n.model_dump() for n in at.note_events]:
                locked_ok = False
                details.append(f"LOCK VIOLATION on {role}")
            elif [d.model_dump() for d in bt.drum_events] != [
                d.model_dump() for d in at.drum_events
            ]:
                locked_ok = False
                details.append(f"LOCK VIOLATION on {role} (drum_events)")

    if not changed and locked_ok and before.key_estimate == after.key_estimate:
        summary = "No musical changes detected"
    elif not changed:
        summary = "Metadata-only change"
        if before.key_estimate != after.key_estimate:
            summary = f"key {before.key_estimate} → {after.key_estimate}"
            if "key" not in "".join(changed):
                pass
    else:
        parts = []
        for role in changed:
            d = deltas.get(role, 0)
            if d != 0:
                parts.append(f"{role} {'+' if d >= 0 else ''}{d} notes")
            else:
                parts.append(f"{role} content tweaked")
        summary = "; ".join(parts)
        if expected:
            summary += "; locks respected" if locked_ok else "; LOCK BROKEN"

    return MusicalDiff(
        id=new_id(),
        from_version_id=from_version_id,
        to_version_id=to_version_id,
        roles_changed=changed,
        note_count_delta_by_role=deltas,
        density_delta=density_delta,
        harmony_delta_notes=harmony,
        groove_delta_notes=groove,
        locked_roles_respected=locked_ok,
        one_line_summary=summary,
        details=details,
    )


def baseline_diff_summary(project: MusicProject) -> str:
    roles = ", ".join(sorted({t.role.value for t in project.tracks}))
    return (
        f"Initial {project.length_bars}-bar {project.key_estimate or 'key?'} "
        f"@ {project.bpm:g} BPM with {roles}"
    )
