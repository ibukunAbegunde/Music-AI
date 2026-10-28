"""Phase 0 composition pipeline: prompt → project → MIDI → DAW adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from backend.app.core.config import DawMode, Settings, get_settings
from backend.app.core.logging import log_event, setup_logging
from backend.app.daw.base import DawAdapter, DawResult
from backend.app.daw.fake import FakeDawAdapter
from backend.app.daw.midi_fallback import MidiExportAdapter
from backend.app.models.db import init_db
from backend.app.models.schemas import MusicProject, ProjectStatus, ProjectVersion, new_id, utcnow
from backend.app.music.generators import generate_eight_bar_project, parse_prompt
from backend.app.music.midi import assert_eight_bars_span, export_project_midi
from backend.app.storage.assets import AssetStore
from backend.app.storage.repository import ProjectRepository


@dataclass
class ComposeResult:
    project: MusicProject
    version: ProjectVersion
    midi_paths: dict[str, Path]
    daw_result: DawResult
    intent: dict[str, Any]
    metadata_path: Path


def select_adapter(settings: Settings, assets: AssetStore) -> DawAdapter:
    if settings.daw_mode == DawMode.MIDI_EXPORT:
        return MidiExportAdapter(assets)
    # POSTFADER not available in Phase 0 cloud VM — fall back to fake
    return FakeDawAdapter()


def compose_from_prompt(
    prompt: str,
    *,
    seed: int | None = None,
    bars: int = 8,
    settings: Settings | None = None,
    adapter: DawAdapter | None = None,
) -> ComposeResult:
    settings = settings or get_settings()
    logger = setup_logging(settings.log_level)
    settings.ensure_workspace()
    session_factory = init_db(settings)
    repo = ProjectRepository(session_factory)
    assets = AssetStore(settings)

    intent = parse_prompt(prompt, seed=seed, bars=bars)
    project = generate_eight_bar_project(prompt, seed=seed, bars=bars)
    assert_eight_bars_span(project)

    log_event(
        logger,
        "compose.start",
        project_id=str(project.id),
        seed=project.seed,
        bpm=project.bpm,
        genre=intent.genre,
    )

    midi_dir = assets.midi_dir(project.id)
    midi_paths = export_project_midi(project, midi_dir)

    daw = adapter or select_adapter(settings, assets)
    daw.connect()
    daw_result = daw.create_or_update_notes(project)
    if isinstance(daw, FakeDawAdapter):
        daw.set_tempo(project.bpm)
        daw.verify_postcondition({"bpm": project.bpm, "min_tracks": 3, "min_notes": 10})
    elif isinstance(daw, MidiExportAdapter):
        daw.verify_postcondition({"min_files": 3, "roles": ["drums", "bass", "chord"]})

    project.status = ProjectStatus.COMPLETED
    project.updated_at = utcnow()
    repo.save_project(project)

    version = ProjectVersion(
        id=new_id(),
        canonical_project_snapshot=project.model_dump(mode="json"),
        exported_midi_paths=[str(p) for p in midi_paths.values()],
        user_message=prompt,
        created_at=utcnow(),
        restorable=True,
    )
    project.version_id = version.id
    repo.save_project(project)
    repo.save_version(version, project.id)

    meta = {
        "project_id": str(project.id),
        "version_id": str(version.id),
        "seed": project.seed,
        "bpm": project.bpm,
        "key": project.key_estimate,
        "bars": project.length_bars,
        "brief": project.generation_brief,
        "intent": {
            "genre": intent.genre,
            "mood": intent.mood,
            "bpm": intent.bpm,
            "key": intent.key,
        },
        "midi_paths": {k: str(v) for k, v in midi_paths.items()},
        "daw": daw_result.as_dict(),
        "schema_version": project.schema_version,
        "mode": settings.daw_mode.value,
    }
    metadata_path = assets.write_json(f"projects/{project.id}/metadata.json", meta)
    log_event(logger, "compose.done", project_id=str(project.id), midi_dir=str(midi_dir))
    return ComposeResult(
        project=project,
        version=version,
        midi_paths=midi_paths,
        daw_result=daw_result,
        intent=meta["intent"],
        metadata_path=metadata_path,
    )


def load_project_metadata(project_id: UUID, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    path = settings.workspace_dir / "projects" / str(project_id) / "metadata.json"
    return json.loads(path.read_text(encoding="utf-8"))
