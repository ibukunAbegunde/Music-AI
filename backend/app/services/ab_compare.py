"""A/B comparison path — loudness-matched audio when present, else MIDI proxies.

Simulation / no-render environments pair CandidatePackages via combined MIDI
paths and record PreferenceComparison + musical diff. Real renders plug in via
``Render.audio_path`` later without changing this contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from backend.app.core.config import Settings, get_settings
from backend.app.models.schemas import (
    LoudnessNotes,
    MusicalDiff,
    MusicProject,
    PreferenceComparison,
    Render,
    new_id,
    utcnow,
)
from backend.app.music.diff import diff_projects
from backend.app.storage.assets import AssetStore


Choice = Literal["a", "b", "tie", "skip"]


@dataclass
class AbSide:
    label: str
    version_id: UUID
    candidate_id: UUID | None
    seed: int | None
    midi_proxy_path: str | None
    render_id: UUID | None
    audio_path: str | None
    loudness_notes: LoudnessNotes
    one_line_diff: str


@dataclass
class AbCompareResult:
    comparison_id: UUID
    project_id: UUID
    side_a: AbSide
    side_b: AbSide
    musical_diff: MusicalDiff
    path_mode: str  # "audio" | "midi_proxy"
    preference: PreferenceComparison | None
    session_path: Path


def _load_version_cir(assets: AssetStore, project_id: UUID, version_id: UUID) -> MusicProject:
    path = assets.root / "projects" / str(project_id) / "versions" / f"{version_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"missing CIR snapshot {path}")
    return MusicProject.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _combined_midi(paths: list[str]) -> str | None:
    for p in paths:
        if p.endswith("combined.mid"):
            return p
    return paths[0] if paths else None


def _side_from_session_entry(entry: dict[str, Any], label: str) -> AbSide:
    midi_paths = entry.get("midi_paths") or []
    loud = entry.get("loudness_notes") or {}
    return AbSide(
        label=label,
        version_id=UUID(entry["version_id"]),
        candidate_id=UUID(entry["candidate_id"]) if entry.get("candidate_id") else None,
        seed=entry.get("seed"),
        midi_proxy_path=_combined_midi(midi_paths),
        render_id=None,
        audio_path=None,
        loudness_notes=LoudnessNotes.model_validate(
            {
                "target_lufs": loud.get("target_lufs", -14.0),
                "measured_lufs": loud.get("measured_lufs"),
                "normalization_status": loud.get("normalization_status", "midi_proxy"),
            }
        ),
        one_line_diff=entry.get("one_line_diff") or "",
    )


def compare_candidates(
    project_id: UUID,
    version_a: UUID,
    version_b: UUID,
    *,
    session_path: Path | None = None,
    choice: Choice | None = None,
    reason: str | None = None,
    tags: list[str] | None = None,
    settings: Settings | None = None,
) -> AbCompareResult:
    settings = settings or get_settings()
    assets = AssetStore(settings)
    proj_dir = assets.root / "projects" / str(project_id)

    session: dict[str, Any] | None = None
    if session_path and session_path.exists():
        session = json.loads(session_path.read_text(encoding="utf-8"))
    else:
        # Discover latest candidate session
        sessions = sorted(proj_dir.glob("candidate_session_*.json"))
        if sessions:
            session = json.loads(sessions[-1].read_text(encoding="utf-8"))

    entry_a = entry_b = None
    if session:
        by_ver = {c["version_id"]: c for c in session.get("candidates", [])}
        entry_a = by_ver.get(str(version_a))
        entry_b = by_ver.get(str(version_b))

    cir_a = _load_version_cir(assets, project_id, version_a)
    cir_b = _load_version_cir(assets, project_id, version_b)
    musical_diff = diff_projects(
        cir_a,
        cir_b,
        from_version_id=version_a,
        to_version_id=version_b,
    )

    if entry_a:
        side_a = _side_from_session_entry(entry_a, "A")
    else:
        side_a = AbSide(
            label="A",
            version_id=version_a,
            candidate_id=None,
            seed=cir_a.seed,
            midi_proxy_path=None,
            render_id=None,
            audio_path=None,
            loudness_notes=LoudnessNotes(normalization_status="midi_proxy"),
            one_line_diff="",
        )
        # Fall back to version MIDI paths on disk
        midi_dir = assets.root / "midi" / str(project_id)
        combined = list(midi_dir.rglob("combined.mid"))
        if combined:
            side_a.midi_proxy_path = str(combined[0])

    if entry_b:
        side_b = _side_from_session_entry(entry_b, "B")
    else:
        side_b = AbSide(
            label="B",
            version_id=version_b,
            candidate_id=None,
            seed=cir_b.seed,
            midi_proxy_path=None,
            render_id=None,
            audio_path=None,
            loudness_notes=LoudnessNotes(normalization_status="midi_proxy"),
            one_line_diff="",
        )

    # Prefer audio if either side has a render path recorded on CIR metadata
    path_mode = "midi_proxy"
    if side_a.audio_path and side_b.audio_path:
        path_mode = "audio"
        side_a.loudness_notes.normalization_status = "pending"
        side_b.loudness_notes.normalization_status = "pending"

    # Synthetic Render stubs for preference linkage (no WAV fabricated)
    render_a = Render(
        project_id=project_id,
        version_id=version_a,
        audio_path=side_a.audio_path or side_a.midi_proxy_path,
        render_settings={"mode": path_mode, "target_lufs": -14.0},
        listening_status="ready_proxy" if path_mode == "midi_proxy" else "ready",
        created_at=utcnow(),
    )
    render_b = Render(
        project_id=project_id,
        version_id=version_b,
        audio_path=side_b.audio_path or side_b.midi_proxy_path,
        render_settings={"mode": path_mode, "target_lufs": -14.0},
        listening_status="ready_proxy" if path_mode == "midi_proxy" else "ready",
        created_at=utcnow(),
    )
    side_a.render_id = render_a.id
    side_b.render_id = render_b.id

    preference = None
    if choice is not None:
        preference = PreferenceComparison(
            context={
                "project_id": str(project_id),
                "task": "phase3_ab",
                "path_mode": path_mode,
                "musical_diff": musical_diff.one_line_summary,
            },
            render_a_id=render_a.id,
            render_b_id=render_b.id,
            user_choice=choice,
            optional_reason=reason,
            tags=list(tags or []),
            timestamp=utcnow(),
            blind_status=False,
        )

    comparison_id = preference.id if preference else new_id()
    payload = {
        "comparison_id": str(comparison_id),
        "project_id": str(project_id),
        "path_mode": path_mode,
        "side_a": {
            "version_id": str(side_a.version_id),
            "candidate_id": str(side_a.candidate_id) if side_a.candidate_id else None,
            "seed": side_a.seed,
            "midi_proxy_path": side_a.midi_proxy_path,
            "render_id": str(side_a.render_id) if side_a.render_id else None,
            "loudness_notes": side_a.loudness_notes.model_dump(mode="json"),
            "one_line_diff": side_a.one_line_diff,
        },
        "side_b": {
            "version_id": str(side_b.version_id),
            "candidate_id": str(side_b.candidate_id) if side_b.candidate_id else None,
            "seed": side_b.seed,
            "midi_proxy_path": side_b.midi_proxy_path,
            "render_id": str(side_b.render_id) if side_b.render_id else None,
            "loudness_notes": side_b.loudness_notes.model_dump(mode="json"),
            "one_line_diff": side_b.one_line_diff,
        },
        "musical_diff": musical_diff.model_dump(mode="json"),
        "preference": preference.model_dump(mode="json") if preference else None,
        "note": (
            "No audio render available — A/B uses MIDI preview proxies with "
            "matched target LUFS notes. Swap in Render.audio_path when bounce exists."
        ),
    }
    out = assets.write_json(
        f"projects/{project_id}/ab_{comparison_id}.json",
        payload,
    )
    assets.write_json(
        f"projects/{project_id}/diff_ab_{version_a}_{version_b}.json",
        musical_diff.model_dump(mode="json"),
    )
    return AbCompareResult(
        comparison_id=comparison_id,
        project_id=project_id,
        side_a=side_a,
        side_b=side_b,
        musical_diff=musical_diff,
        path_mode=path_mode,
        preference=preference,
        session_path=out,
    )


def compare_session_pair(
    project_id: UUID,
    *,
    index_a: int = 0,
    index_b: int = 1,
    choice: Choice | None = None,
    reason: str | None = None,
    settings: Settings | None = None,
) -> AbCompareResult:
    """A/B the i-th and j-th candidates from the latest multi-candidate session."""
    settings = settings or get_settings()
    assets = AssetStore(settings)
    sessions = sorted(
        (assets.root / "projects" / str(project_id)).glob("candidate_session_*.json")
    )
    if not sessions:
        raise FileNotFoundError(f"no candidate session for project {project_id}")
    session_path = sessions[-1]
    session = json.loads(session_path.read_text(encoding="utf-8"))
    cands = session["candidates"]
    if index_a >= len(cands) or index_b >= len(cands):
        raise IndexError(f"session has {len(cands)} candidates")
    return compare_candidates(
        project_id,
        UUID(cands[index_a]["version_id"]),
        UUID(cands[index_b]["version_id"]),
        session_path=session_path,
        choice=choice,
        reason=reason,
        settings=settings,
    )
