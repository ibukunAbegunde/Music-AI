"""Targeted revision with role-locks, musical diff, verify/undo (Phase 1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from backend.app.agents.critic import propose_next_moves
from backend.app.core.config import DawMode, Settings, get_settings
from backend.app.core.logging import log_event, setup_logging
from backend.app.daw.base import DawAdapter, DawResult
from backend.app.daw.fake import FakeDawAdapter
from backend.app.daw.midi_fallback import MidiExportAdapter
from backend.app.models.db import init_db
from backend.app.models.schemas import (
    CandidatePackage,
    DawOperation,
    LoudnessNotes,
    MusicProject,
    MusicalDiff,
    ProjectStatus,
    ProjectVersion,
    new_id,
    utcnow,
)
from backend.app.music.brief import parse_brief
from backend.app.music.coedit import (
    apply_role_locks,
    humanize_project,
    merge_preserving_locks,
    parse_lock_roles_from_text,
)
from backend.app.music.diff import diff_projects
from backend.app.music.generators import generate_from_brief
from backend.app.music.midi import export_project_midi
from backend.app.services.compose import select_adapter
from backend.app.storage.assets import AssetStore
from backend.app.storage.repository import ProjectRepository


@dataclass
class ReviseResult:
    project: MusicProject
    parent: MusicProject
    version: ProjectVersion
    diff: MusicalDiff
    midi_paths: dict[str, Path]
    daw_result: DawResult
    candidate: CandidatePackage
    next_moves: list[DawOperation] = field(default_factory=list)
    snapshot_ref: str | None = None
    undo_available: bool = False


def _load_cir(assets: AssetStore, project_id: UUID, version_id: UUID | None) -> MusicProject | None:
    if version_id is None:
        meta_path = assets.root / "projects" / str(project_id) / "metadata.json"
        if not meta_path.exists():
            return None
        import json

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        version_id = UUID(meta["version_id"])
    path = assets.root / "projects" / str(project_id) / "versions" / f"{version_id}.json"
    if not path.exists():
        return None
    import json

    return MusicProject.model_validate(json.loads(path.read_text(encoding="utf-8")))


def revise_project(
    project_id: UUID,
    instruction: str,
    *,
    seed: int | None = None,
    settings: Settings | None = None,
    adapter: DawAdapter | None = None,
    parent_version_id: UUID | None = None,
) -> ReviseResult:
    settings = settings or get_settings()
    logger = setup_logging(settings.log_level)
    settings.ensure_workspace()
    session_factory = init_db(settings)
    repo = ProjectRepository(session_factory)
    assets = AssetStore(settings)

    stored = repo.get_project(project_id)
    if stored is None:
        raise ValueError(f"unknown project {project_id}")

    parent = _load_cir(assets, project_id, parent_version_id or stored.version_id) or stored
    locks = parse_lock_roles_from_text(instruction)
    # Also keep already-locked roles
    locks = sorted(set(locks) | {t.role.value for t in parent.tracks if t.locked})
    parent_locked = apply_role_locks(parent, locks)

    brief = parse_brief(
        instruction if instruction.strip() else (parent.generation_brief or "revise"),
        seed=seed if seed is not None else (int(parent.seed or 0) + 1),
        bars=parent.length_bars,
        locked_roles=locks,
    )
    # Preserve BPM/key from parent unless instruction overrides with explicit bpm/key already parsed
    if "bpm" not in instruction.lower():
        brief.bpm = parent.bpm
    if not any(k in instruction.lower() for k in ("major", "minor", "#", "b")):
        brief.key = parent.key_estimate

    regenerated = generate_from_brief(brief, name=parent.name + "-rev")
    # Soften bass heuristic
    if "soften bass" in instruction.lower() or "softer bass" in instruction.lower():
        for t in regenerated.tracks:
            if t.role.value == "bass":
                t.note_events = [
                    n.model_copy(update={"velocity": max(1, int(n.velocity * 0.7))})
                    for n in t.note_events
                ]

    if "humanize" in instruction.lower():
        regenerated = humanize_project(regenerated, seed=brief.seed or 0)

    merged = merge_preserving_locks(parent_locked, regenerated)
    merged.id = parent.id
    merged.generation_brief = instruction
    merged.updated_at = utcnow()
    merged.status = ProjectStatus.APPLYING

    musical_diff = diff_projects(
        parent_locked,
        merged,
        from_version_id=parent.version_id,
        expected_locked=locks,
    )
    if not musical_diff.locked_roles_respected:
        raise RuntimeError(f"role-lock violation: {musical_diff.details}")

    daw = adapter or select_adapter(settings, assets)
    daw.connect()
    snapshot_ref = None
    if isinstance(daw, FakeDawAdapter):
        # Load parent into fake DAW then snapshot
        daw.create_or_update_notes(parent_locked)
        snap = daw.save_snapshot("pre-revise")
        snapshot_ref = snap.observations.get("snapshot_ref")

    daw_result = daw.create_or_update_notes(merged)
    if isinstance(daw, FakeDawAdapter):
        verify = daw.verify_postcondition({"min_tracks": 3, "min_notes": 5})
        daw_result = verify if not daw_result.verified else daw_result
    elif isinstance(daw, MidiExportAdapter):
        daw.verify_postcondition({"roles": ["drums", "bass", "chord"]})

    midi_paths = export_project_midi(merged, assets.midi_dir(merged.id))
    version = ProjectVersion(
        id=new_id(),
        parent_version_id=parent.version_id,
        canonical_project_snapshot=merged.model_dump(mode="json"),
        exported_midi_paths=[str(p) for p in midi_paths.values()],
        user_message=instruction,
        one_line_diff=musical_diff.one_line_summary,
        musical_diff=musical_diff,
        created_at=utcnow(),
        restorable=True,
    )
    merged.version_id = version.id
    merged.status = ProjectStatus.COMPLETED
    repo.save_project(merged)
    repo.save_version(version, merged.id)

    cir_ref = f"projects/{merged.id}/versions/{version.id}.json"
    assets.write_json(cir_ref, merged.model_dump(mode="json"))
    assets.write_json(
        f"projects/{merged.id}/diff_{version.id}.json",
        musical_diff.model_dump(mode="json"),
    )

    candidate = CandidatePackage(
        project_id=merged.id,
        version_id=version.id,
        seed=int(merged.seed or 0),
        cir_snapshot_ref=cir_ref,
        midi_paths=[str(p) for p in midi_paths.values()],
        loudness_notes=LoudnessNotes(normalization_status="manual_required"),
        one_line_diff=musical_diff.one_line_summary,
        musical_diff_id=musical_diff.id,
        parent_version_id=parent.version_id,
    )
    next_moves = propose_next_moves(merged, diff=musical_diff)
    log_event(
        logger,
        "revise.done",
        project_id=str(merged.id),
        diff=musical_diff.one_line_summary,
        locks=locks,
    )
    return ReviseResult(
        project=merged,
        parent=parent_locked,
        version=version,
        diff=musical_diff,
        midi_paths=midi_paths,
        daw_result=daw_result,
        candidate=candidate,
        next_moves=next_moves,
        snapshot_ref=snapshot_ref,
        undo_available=snapshot_ref is not None,
    )


def undo_fake_daw(adapter: FakeDawAdapter, snapshot_ref: str) -> DawResult:
    return adapter.undo_or_restore(snapshot_ref)
