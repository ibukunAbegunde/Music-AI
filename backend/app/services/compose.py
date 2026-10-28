"""Phase 1 composition pipeline: brief → project → MIDI → DAW → candidate package."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from backend.app.agents.critic import propose_next_moves
from backend.app.core.config import DawMode, Settings, get_settings
from backend.app.core.logging import log_event, setup_logging
from backend.app.daw.base import DawAdapter, DawResult
from backend.app.daw.fake import FakeDawAdapter
from backend.app.daw.midi_fallback import MidiExportAdapter
from backend.app.models.db import init_db
from backend.app.models.schemas import (
    BriefDocument,
    CandidatePackage,
    DawOperation,
    LoudnessNotes,
    MusicProject,
    ProjectStatus,
    ProjectVersion,
    new_id,
    utcnow,
)
from backend.app.music.brief import parse_brief
from backend.app.music.diff import baseline_diff_summary
from backend.app.music.generators import generate_from_brief
from backend.app.music.midi import assert_eight_bars_span, export_project_midi
from backend.app.storage.assets import AssetStore
from backend.app.storage.repository import ProjectRepository


@dataclass
class ComposeResult:
    project: MusicProject
    version: ProjectVersion
    brief: BriefDocument
    midi_paths: dict[str, Path]
    daw_result: DawResult
    candidate: CandidatePackage
    next_moves: list[DawOperation] = field(default_factory=list)
    metadata_path: Path | None = None
    snapshot_ref: str | None = None
    intent: dict[str, Any] = field(default_factory=dict)


def select_adapter(settings: Settings, assets: AssetStore) -> DawAdapter:
    if settings.daw_mode == DawMode.MIDI_EXPORT:
        return MidiExportAdapter(assets)
    return FakeDawAdapter()


def compose_from_brief(
    brief: BriefDocument,
    *,
    settings: Settings | None = None,
    adapter: DawAdapter | None = None,
    name: str | None = None,
) -> ComposeResult:
    settings = settings or get_settings()
    logger = setup_logging(settings.log_level)
    settings.ensure_workspace()
    session_factory = init_db(settings)
    repo = ProjectRepository(session_factory)
    assets = AssetStore(settings)

    project = generate_from_brief(brief, name=name)
    project.brief_id = brief.id
    project.recipe_id = brief.recipe_id
    brief.project_id = project.id
    assert_eight_bars_span(project)

    log_event(
        logger,
        "compose.start",
        project_id=str(project.id),
        seed=project.seed,
        bpm=project.bpm,
        genre=brief.genre_template_id,
    )

    midi_dir = assets.midi_dir(project.id)
    midi_paths = export_project_midi(project, midi_dir)

    daw = adapter or select_adapter(settings, assets)
    daw.connect()
    snapshot_ref = None
    if isinstance(daw, FakeDawAdapter):
        snap = daw.save_snapshot("pre-compose")
        snapshot_ref = snap.observations.get("snapshot_ref")

    daw_result = daw.create_or_update_notes(project)
    if isinstance(daw, FakeDawAdapter):
        daw.set_tempo(project.bpm)
        daw.verify_postcondition({"bpm": project.bpm, "min_tracks": 3, "min_notes": 10})
    elif isinstance(daw, MidiExportAdapter):
        daw.verify_postcondition({"min_files": 3, "roles": ["drums", "bass", "chord"]})

    one_line = baseline_diff_summary(project)
    project.status = ProjectStatus.COMPLETED
    project.updated_at = utcnow()
    repo.save_project(project)

    version = ProjectVersion(
        id=new_id(),
        canonical_project_snapshot=project.model_dump(mode="json"),
        exported_midi_paths=[str(p) for p in midi_paths.values()],
        user_message=brief.free_text,
        one_line_diff=one_line,
        recipe_id=project.recipe_id,
        created_at=utcnow(),
        restorable=True,
    )
    project.version_id = version.id
    repo.save_project(project)
    repo.save_version(version, project.id)

    cir_ref = f"projects/{project.id}/versions/{version.id}.json"
    assets.write_json(cir_ref, project.model_dump(mode="json"))

    candidate = CandidatePackage(
        project_id=project.id,
        version_id=version.id,
        seed=int(project.seed or 0),
        cir_snapshot_ref=cir_ref,
        midi_paths=[str(p) for p in midi_paths.values()],
        loudness_notes=LoudnessNotes(
            target_lufs=-14.0,
            normalization_status="manual_required"
            if settings.daw_mode != DawMode.SIMULATION
            else "n/a",
        ),
        one_line_diff=one_line,
    )
    assets.write_json(
        f"projects/{project.id}/candidate_{candidate.id}.json",
        candidate.model_dump(mode="json"),
    )

    try:
        from backend.app.agents.critic import critique_project

        next_moves = critique_project(project, max_moves=3).next_moves or propose_next_moves(
            project
        )
    except Exception as exc:  # noqa: BLE001 — never block compose on critic failures
        log_event(logger, "compose.critic_fallback", error=str(exc))
        next_moves = propose_next_moves(project)
    meta = {
        "project_id": str(project.id),
        "version_id": str(version.id),
        "brief": brief.model_dump(mode="json"),
        "seed": project.seed,
        "bpm": project.bpm,
        "key": project.key_estimate,
        "genre_template_id": project.genre_template_id,
        "bars": project.length_bars,
        "recipe_id": str(project.recipe_id) if project.recipe_id else None,
        "candidate": candidate.model_dump(mode="json"),
        "next_moves": [o.model_dump(mode="json") for o in next_moves],
        "daw": daw_result.as_dict(),
        "snapshot_ref": snapshot_ref,
        "mode": settings.daw_mode.value,
        "schema_version": project.schema_version,
    }
    metadata_path = assets.write_json(f"projects/{project.id}/metadata.json", meta)
    assets.write_json(f"projects/{project.id}/brief.json", brief.model_dump(mode="json"))
    log_event(logger, "compose.done", project_id=str(project.id), midi_dir=str(midi_dir))

    return ComposeResult(
        project=project,
        version=version,
        brief=brief,
        midi_paths=midi_paths,
        daw_result=daw_result,
        candidate=candidate,
        next_moves=next_moves,
        metadata_path=metadata_path,
        snapshot_ref=snapshot_ref,
        intent={
            "genre": brief.genre_template_id,
            "bpm": brief.bpm,
            "key": brief.key,
            "novelty": brief.novelty,
            "locked_roles": brief.locked_roles,
        },
    )


def compose_from_prompt(
    prompt: str,
    *,
    seed: int | None = None,
    bars: int = 8,
    settings: Settings | None = None,
    adapter: DawAdapter | None = None,
    locked_roles: list[str] | None = None,
    recipe_id: UUID | None = None,
) -> ComposeResult:
    brief = parse_brief(prompt, seed=seed, bars=bars, locked_roles=locked_roles)
    if recipe_id is not None:
        brief.recipe_id = recipe_id
    return compose_from_brief(brief, settings=settings, adapter=adapter)


def load_project_metadata(project_id: UUID, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    path = settings.workspace_dir / "projects" / str(project_id) / "metadata.json"
    return json.loads(path.read_text(encoding="utf-8"))
