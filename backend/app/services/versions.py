"""Version timeline helpers — list / restore CIR tips."""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from backend.app.core.config import Settings, get_settings
from backend.app.models.db import init_db
from backend.app.models.schemas import MusicalDiff, MusicProject, ProjectVersion
from backend.app.music.diff import diff_projects
from backend.app.storage.assets import AssetStore
from backend.app.storage.repository import ProjectRepository


@dataclass
class VersionTimelineEntry:
    version_id: UUID
    parent_version_id: UUID | None
    created_at: str | None
    one_line_diff: str | None
    seed: int | None
    restorable: bool
    musical_diff: MusicalDiff | None = None


def list_version_timeline(
    project_id: UUID,
    *,
    settings: Settings | None = None,
) -> list[VersionTimelineEntry]:
    settings = settings or get_settings()
    repo = ProjectRepository(init_db(settings))
    assets = AssetStore(settings)
    versions = repo.list_versions(project_id)
    # Prefer chronological; repository order may already be creation order
    entries: list[VersionTimelineEntry] = []
    for v in versions:
        seed = None
        snap = v.canonical_project_snapshot or {}
        if isinstance(snap, dict):
            seed = snap.get("seed")
        # Prefer on-disk musical diff if present
        md = v.musical_diff
        if md is None and v.parent_version_id:
            diff_path = (
                assets.root
                / "projects"
                / str(project_id)
                / f"diff_{v.id}.json"
            )
            if diff_path.exists():
                md = MusicalDiff.model_validate(json.loads(diff_path.read_text(encoding="utf-8")))
        entries.append(
            VersionTimelineEntry(
                version_id=v.id,
                parent_version_id=v.parent_version_id,
                created_at=v.created_at.isoformat() if v.created_at else None,
                one_line_diff=v.one_line_diff,
                seed=seed,
                restorable=v.restorable,
                musical_diff=md,
            )
        )
    return entries


def load_version_project(
    project_id: UUID,
    version_id: UUID,
    *,
    settings: Settings | None = None,
) -> MusicProject:
    settings = settings or get_settings()
    assets = AssetStore(settings)
    path = assets.root / "projects" / str(project_id) / "versions" / f"{version_id}.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return MusicProject.model_validate(json.loads(path.read_text(encoding="utf-8")))


def diff_versions(
    project_id: UUID,
    from_version_id: UUID,
    to_version_id: UUID,
    *,
    settings: Settings | None = None,
) -> MusicalDiff:
    before = load_version_project(project_id, from_version_id, settings=settings)
    after = load_version_project(project_id, to_version_id, settings=settings)
    return diff_projects(
        before,
        after,
        from_version_id=from_version_id,
        to_version_id=to_version_id,
        expected_locked=[t.role.value for t in before.tracks if t.locked],
    )


def restore_version(
    project_id: UUID,
    version_id: UUID,
    *,
    settings: Settings | None = None,
) -> ProjectVersion:
    """Point project tip metadata at an older restorable version (CIR copy as new tip)."""
    from backend.app.models.schemas import new_id, utcnow
    from backend.app.music.midi import export_project_midi

    settings = settings or get_settings()
    assets = AssetStore(settings)
    repo = ProjectRepository(init_db(settings))
    stored = repo.get_project(project_id)
    if stored is None:
        raise ValueError(f"unknown project {project_id}")
    restored = load_version_project(project_id, version_id, settings=settings)
    restored.id = project_id
    midi_paths = export_project_midi(restored, assets.midi_dir(project_id) / f"restore_{version_id}")
    version = ProjectVersion(
        id=new_id(),
        parent_version_id=stored.version_id,
        canonical_project_snapshot=restored.model_dump(mode="json"),
        exported_midi_paths=[str(p) for p in midi_paths.values()],
        user_message=f"restore:{version_id}",
        one_line_diff=f"Restored CIR from {version_id}",
        recipe_id=restored.recipe_id,
        created_at=utcnow(),
        restorable=True,
    )
    restored.version_id = version.id
    repo.save_project(restored)
    repo.save_version(version, project_id)
    assets.write_json(
        f"projects/{project_id}/versions/{version.id}.json",
        restored.model_dump(mode="json"),
    )
    meta_path = assets.root / "projects" / str(project_id) / "metadata.json"
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update(
        {
            "project_id": str(project_id),
            "version_id": str(version.id),
            "restored_from": str(version_id),
            "seed": restored.seed,
            "bpm": restored.bpm,
            "key": restored.key_estimate,
            "bars": restored.length_bars,
        }
    )
    assets.write_json(f"projects/{project_id}/metadata.json", meta)
    return version
