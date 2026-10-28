"""Derive RenderMetrics from CIR (simulation) and optional fixture overlays."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from backend.app.models.schemas import MusicProject, new_id
from backend.app.render_eval.metrics import RenderMetrics
from backend.app.render_eval.musical import groove_grid_error, kick_bass_overlap

# Packaged fixtures live beside tests; also allow workspace overrides.
_PACKAGE_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "renders"


def _has_end_fill(project: MusicProject) -> bool:
    bpb = 4
    start = (project.length_bars - 1) * bpb
    for t in project.tracks:
        if t.role.value != "drums":
            continue
        for d in t.drum_events:
            if d.onset_beats >= start + 2.0 and d.instrument_role in ("hat_open", "snare", "tom"):
                return True
        for n in t.note_events:
            if n.onset_beats >= start + 2.0 and n.source and "fill" in n.source:
                return True
    return False


def simulate_render_metrics(
    project: MusicProject,
    *,
    fixture_id: str | None = None,
    fixture_dir: Path | None = None,
    render_id: UUID | None = None,
) -> RenderMetrics:
    """Build metrics from CIR; overlay a named fixture JSON when provided."""
    notes = [n for t in project.tracks for n in t.note_events]
    drums = [d for t in project.tracks for d in t.drum_events]
    all_vel = [n.velocity for n in notes] + [d.velocity for d in drums]
    n_events = len(notes) + len(drums)
    density = n_events / max(project.length_bars, 1)
    hot = sum(1 for v in all_vel if v >= 120) / max(len(all_vel), 1)
    avg_vel = (sum(all_vel) / len(all_vel)) if all_vel else 80.0
    # Map velocity → crude loudness / peak proxies (deterministic, no audio).
    peak_dbfs = -0.1 if hot > 0.3 else (-1.0 if hot > 0.12 else -6.0 + (avg_vel - 90) * 0.05)
    clipping = max(0.0, (hot - 0.15) * 0.4)
    measured_lufs = -23.0 + (avg_vel / 127.0) * 16.0  # ~-23..-7
    empty = sum(1 for t in project.tracks if t.enabled and not t.note_events and not t.drum_events)
    overlap = kick_bass_overlap(project)
    grid = groove_grid_error(project)
    # Excess sub proxy: dense bass + high kick/bass lock
    bass_notes = sum(len(t.note_events) for t in project.tracks if t.role.value == "bass")
    excess_sub = min(1.0, (bass_notes / max(project.length_bars * 4, 1)) * 0.35 + overlap * 0.5)
    silence = 0.0 if n_events > 4 else 0.5
    bars_sec = project.length_bars * (60.0 / max(project.bpm, 1.0)) * 4.0

    metrics = RenderMetrics(
        render_id=render_id or new_id(),
        project_id=project.id,
        version_id=project.version_id,
        source="simulation",
        duration_sec=bars_sec,
        peak_dbfs=peak_dbfs,
        true_peak_dbfs=peak_dbfs + 0.2,
        measured_lufs=measured_lufs,
        dynamic_range_db=max(3.0, 12.0 - hot * 10),
        clipping_ratio=clipping,
        silence_ratio=silence,
        rms_dbfs=measured_lufs + 4.0,
        stereo_imbalance=0.05,
        excess_sub_energy=excess_sub,
        note_density_per_bar=density,
        empty_role_count=empty,
        kick_bass_overlap_ratio=overlap,
        groove_grid_error=grid,
        velocity_hot_ratio=hot,
        missing_end_fill=not _has_end_fill(project),
    )

    if fixture_id:
        overlay = load_fixture(fixture_id, fixture_dir=fixture_dir)
        data = metrics.model_dump()
        for k, v in overlay.items():
            if k in ("id", "fixture_id", "description"):
                continue
            if k in data:
                data[k] = v
        data["source"] = "fixture"
        data["fixture_id"] = fixture_id
        data["project_id"] = project.id
        data["version_id"] = project.version_id
        data["render_id"] = metrics.render_id
        metrics = RenderMetrics.model_validate(data)
    return metrics


def load_fixture(fixture_id: str, *, fixture_dir: Path | None = None) -> dict:
    dirs = [d for d in (fixture_dir, _PACKAGE_FIXTURES) if d is not None]
    for d in dirs:
        path = d / f"{fixture_id}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"render fixture not found: {fixture_id} (searched {[str(x) for x in dirs]})")


def list_fixtures(*, fixture_dir: Path | None = None) -> list[str]:
    names: set[str] = set()
    for d in (fixture_dir, _PACKAGE_FIXTURES):
        if d is None or not d.exists():
            continue
        for p in d.glob("*.json"):
            names.add(p.stem)
    return sorted(names)


def seed_cir_defects_from_fixture(project: MusicProject, fixture_id: str) -> MusicProject:
    """Mirror fixture intent onto CIR so measured improvement is falsifiable in sim.

    Fixtures still drive critic proposals via metric overlay; this seeds matching
    CIR defects so PatchOps can change the CIR-derived scoreboard.
    """
    out = project.model_copy(deep=True)
    if fixture_id == "hot_clipping":
        for t in out.tracks:
            if t.locked:
                continue
            t.note_events = [n.model_copy(update={"velocity": 127}) for n in t.note_events]
            t.drum_events = [d.model_copy(update={"velocity": 127}) for d in t.drum_events]
    elif fixture_id == "muddy_sub":
        for t in out.tracks:
            if t.role.value == "bass" and not t.locked:
                t.note_events = [
                    n.model_copy(update={"velocity": min(127, max(n.velocity, 118))})
                    for n in t.note_events
                ]
            if t.role.value == "drums" and not t.locked:
                # Strip late fills so missing_end_fill becomes true
                bpb = 4
                cut = (out.length_bars - 1) * bpb + 2.0
                t.drum_events = [d for d in t.drum_events if d.onset_beats < cut]
                t.note_events = [
                    n
                    for n in t.note_events
                    if n.onset_beats < cut or not (n.source and "fill" in n.source)
                ]
    # healthy_loop: no spoil
    return out
