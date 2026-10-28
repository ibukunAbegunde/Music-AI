"""Musical consistency heuristics on CIR (+ metrics annotations)."""

from __future__ import annotations

from backend.app.models.schemas import Evaluation, MusicProject, TrackRole
from backend.app.render_eval.metrics import RenderMetrics

EVALUATOR = "musical_heuristics"
VERSION = "0.4.0"


def _eval(render_id, name: str, value: float, *, explanation: str, evidence: list[str] | None = None) -> Evaluation:
    return Evaluation(
        render_id=render_id,
        metric_name=name,
        value=value,
        evaluator_name=EVALUATOR,
        evaluator_version=VERSION,
        explanation=explanation,
        evidence_refs=evidence or [],
    )


def _role_event_count(project: MusicProject, role: str) -> int:
    for t in project.tracks:
        if t.role.value == role:
            return len(t.note_events) + len(t.drum_events)
    return 0


def kick_bass_overlap(project: MusicProject, *, window_beats: float = 0.08) -> float:
    """Fraction of bass onsets that sit nearly on a kick onset."""
    kicks: list[float] = []
    bass: list[float] = []
    for t in project.tracks:
        if t.role == TrackRole.DRUMS:
            for d in t.drum_events:
                if d.instrument_role == "kick":
                    kicks.append(d.onset_beats)
            for n in t.note_events:
                if n.pitch == 36:  # GM kick
                    kicks.append(n.onset_beats)
        if t.role == TrackRole.BASS:
            bass.extend(n.onset_beats for n in t.note_events)
    if not bass or not kicks:
        return 0.0
    hits = 0
    for b in bass:
        if any(abs(b - k) <= window_beats for k in kicks):
            hits += 1
    return hits / len(bass)


def groove_grid_error(project: MusicProject, *, grid: float = 0.25) -> float:
    """Mean absolute offset from a 16th-note grid across all onsets."""
    onsets: list[float] = []
    for t in project.tracks:
        onsets.extend(n.onset_beats for n in t.note_events)
        onsets.extend(d.onset_beats for d in t.drum_events)
    if not onsets:
        return 0.0
    errs = [abs(o - round(o / grid) * grid) for o in onsets]
    return sum(errs) / len(errs)


def run_musical_checks(project: MusicProject, metrics: RenderMetrics) -> list[Evaluation]:
    rid = metrics.render_id
    out: list[Evaluation] = []
    penalties = 0.0
    fails = 0

    empty = sum(1 for t in project.tracks if t.enabled and not t.note_events and not t.drum_events)
    empty_fail = empty > 0
    out.append(
        _eval(
            rid,
            "musical.empty_roles.fail",
            1.0 if empty_fail else 0.0,
            explanation=f"empty_enabled_roles={empty}",
            evidence=["empty_role_count"],
        )
    )
    if empty_fail:
        penalties += 0.2
        fails += 1

    density = metrics.note_density_per_bar
    density_fail = density > 40 or density < 2
    out.append(
        _eval(
            rid,
            "musical.density.fail",
            1.0 if density_fail else 0.0,
            explanation=f"note_density_per_bar={density:.2f}",
            evidence=["note_density_per_bar"],
        )
    )
    if density_fail:
        penalties += 0.15
        fails += 1
    elif density > 28:
        penalties += 0.06

    overlap = metrics.kick_bass_overlap_ratio
    # Mild overlap is musical (kick+bass lock); heavy stacking can muddy low end
    overlap_fail = overlap > 0.85 and metrics.excess_sub_energy > 0.45
    out.append(
        _eval(
            rid,
            "musical.kick_bass.fail",
            1.0 if overlap_fail else 0.0,
            explanation=f"kick_bass_overlap={overlap:.3f}",
            evidence=["kick_bass_overlap_ratio"],
        )
    )
    if overlap_fail:
        penalties += 0.12
        fails += 1

    grid_err = metrics.groove_grid_error
    grid_fail = grid_err > 0.08
    out.append(
        _eval(
            rid,
            "musical.grid.fail",
            1.0 if grid_fail else 0.0,
            explanation=f"groove_grid_error={grid_err:.4f} beats",
            evidence=["groove_grid_error"],
        )
    )
    if grid_fail:
        penalties += 0.1
        fails += 1
    elif grid_err > 0.04:
        penalties += 0.04

    # Arrangement contrast: expect some density toward the end for loops with fills
    if metrics.missing_end_fill and project.length_bars >= 8:
        out.append(
            _eval(
                rid,
                "musical.end_fill.fail",
                1.0,
                explanation="No drum fill near end of loop",
                evidence=["missing_end_fill"],
            )
        )
        penalties += 0.08
        fails += 1
    else:
        out.append(
            _eval(
                rid,
                "musical.end_fill.fail",
                0.0,
                explanation="End fill present or not required",
                evidence=["missing_end_fill"],
            )
        )

    # Bass / drums presence
    if _role_event_count(project, "drums") == 0:
        penalties += 0.15
        fails += 1
    if _role_event_count(project, "bass") == 0:
        penalties += 0.1
        fails += 1

    score = max(0.0, min(1.0, 1.0 - penalties))
    out.append(
        _eval(
            rid,
            "musical.score",
            score,
            explanation=f"aggregate musical coherence; fails={fails}",
            evidence=[f"fail_count={fails}"],
        )
    )
    return out
