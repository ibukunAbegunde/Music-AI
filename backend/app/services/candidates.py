"""N-candidate generation with explicit seeds + CandidatePackage packaging."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from backend.app.agents.critic import propose_next_moves
from backend.app.core.config import DawMode, Settings, get_settings
from backend.app.core.logging import log_event, setup_logging
from backend.app.daw.base import ensure_daw_write_ok
from backend.app.daw.fake import FakeDawAdapter
from backend.app.daw.midi_fallback import MidiExportAdapter
from backend.app.models.db import init_db
from backend.app.models.schemas import (
    BriefDocument,
    CandidatePackage,
    DawOperation,
    LoudnessNotes,
    MusicalDiff,
    MusicProject,
    ProjectStatus,
    ProjectVersion,
    ReferenceProfile,
    new_id,
    utcnow,
)
from backend.app.music.coedit import apply_role_locks, merge_preserving_locks
from backend.app.music.conditioning import (
    apply_conditioning_to_brief,
    build_conditioning_plan,
)
from backend.app.music.diff import baseline_diff_summary, diff_projects
from backend.app.music.midi import assert_eight_bars_span, export_project_midi
from backend.app.research.midi_specialist import compose_cir_from_brief
from backend.app.services.compose import select_adapter
from backend.app.storage.assets import AssetStore
from backend.app.storage.repository import ProjectRepository


@dataclass
class CandidateBundle:
    """One packaged candidate within a multi-seed exploration session."""

    index: int
    seed: int
    project: MusicProject
    version: ProjectVersion
    candidate: CandidatePackage
    midi_paths: dict[str, Path]
    diff_vs_baseline: MusicalDiff | None = None
    next_moves: list[DawOperation] = field(default_factory=list)


@dataclass
class MultiCandidateResult:
    session_id: UUID
    brief: BriefDocument
    conditioning: dict[str, Any]
    baseline: CandidateBundle
    candidates: list[CandidateBundle]
    session_path: Path | None = None
    reference_profile_id: str | None = None
    recipe_id: str | None = None
    recipe_cir_restored: bool = False
    phase2_dependency: str = (
        "Phase 2 ReferenceProfile pipeline available; "
        "FixtureReferenceAnalyzer remains for demos without a live file"
    )


def _package_one(
    *,
    brief: BriefDocument,
    seed: int,
    settings: Settings,
    assets: AssetStore,
    repo: ProjectRepository,
    adapter,
    plan,
    reference_ids: list[UUID],
    name: str | None,
    parent_version_id: UUID | None,
    baseline_project: MusicProject | None,
    index: int,
    shared_project_id: UUID | None,
) -> CandidateBundle:
    seeded = brief.model_copy(deep=True)
    seeded.seed = seed
    project = compose_cir_from_brief(
        seeded,
        settings=settings,
        name=name or f"{seeded.genre_template_id}-c{index}",
        plan=plan,
        reference_ids=reference_ids,
    ).project
    # Variations must share locked material from baseline (recipe / role-locks)
    if baseline_project is not None and brief.locked_roles:
        locked_base = apply_role_locks(baseline_project, brief.locked_roles)
        project = merge_preserving_locks(locked_base, project)
        project = apply_role_locks(project, brief.locked_roles)
        project.seed = seed
        project.name = name or f"{seeded.genre_template_id}-c{index}"
        project.generation_brief = brief.free_text
        project.brief_id = brief.id
        project.recipe_id = brief.recipe_id
        project.reference_ids = list(reference_ids)
    if shared_project_id is not None:
        project.id = shared_project_id
    assert_eight_bars_span(project)

    midi_dir = assets.midi_dir(project.id) / f"cand_{index}_s{seed}"
    midi_paths = export_project_midi(project, midi_dir)

    daw = adapter
    daw.connect()
    daw_result = daw.create_or_update_notes(project)
    ensure_daw_write_ok(daw_result, context=f"candidates[{index}]")
    if isinstance(daw, FakeDawAdapter):
        daw.set_tempo(project.bpm)
        daw.verify_postcondition({"bpm": project.bpm, "min_tracks": 3, "min_notes": 10})
    elif isinstance(daw, MidiExportAdapter):
        daw.verify_postcondition({"min_files": 3, "roles": ["drums", "bass", "chord"]})

    if baseline_project is None:
        one_line = baseline_diff_summary(project)
        musical_diff = None
    else:
        musical_diff = diff_projects(
            baseline_project,
            project,
            expected_locked=list(brief.locked_roles) if brief.locked_roles else None,
        )
        one_line = musical_diff.one_line_summary

    project.status = ProjectStatus.COMPLETED
    project.updated_at = utcnow()

    version = ProjectVersion(
        id=new_id(),
        parent_version_id=parent_version_id,
        canonical_project_snapshot=project.model_dump(mode="json"),
        exported_midi_paths=[str(p) for p in midi_paths.values()],
        user_message=brief.free_text,
        one_line_diff=one_line,
        musical_diff=musical_diff,
        recipe_id=project.recipe_id,
        created_at=utcnow(),
        restorable=True,
    )
    project.version_id = version.id
    if musical_diff is not None:
        musical_diff.to_version_id = version.id
        musical_diff.from_version_id = parent_version_id

    repo.save_project(project)
    repo.save_version(version, project.id)

    cir_ref = f"projects/{project.id}/versions/{version.id}.json"
    assets.write_json(cir_ref, project.model_dump(mode="json"))
    if musical_diff is not None:
        assets.write_json(
            f"projects/{project.id}/diff_{version.id}.json",
            musical_diff.model_dump(mode="json"),
        )

    candidate = CandidatePackage(
        project_id=project.id,
        version_id=version.id,
        seed=seed,
        cir_snapshot_ref=cir_ref,
        midi_paths=[str(p) for p in midi_paths.values()],
        loudness_notes=LoudnessNotes(
            target_lufs=-14.0,
            normalization_status="midi_proxy"
            if settings.daw_mode == DawMode.SIMULATION
            else "manual_required",
        ),
        one_line_diff=one_line,
        musical_diff_id=musical_diff.id if musical_diff else None,
        parent_version_id=parent_version_id,
    )
    assets.write_json(
        f"projects/{project.id}/candidate_{candidate.id}.json",
        candidate.model_dump(mode="json"),
    )

    next_moves = propose_next_moves(project, diff=musical_diff)
    _ = daw_result  # recorded in session meta by caller
    return CandidateBundle(
        index=index,
        seed=seed,
        project=project,
        version=version,
        candidate=candidate,
        midi_paths=midi_paths,
        diff_vs_baseline=musical_diff,
        next_moves=next_moves,
    )


def generate_candidates(
    brief: BriefDocument,
    *,
    n: int = 2,
    base_seed: int | None = None,
    settings: Settings | None = None,
    adapter=None,
    profile: ReferenceProfile | None = None,
    reference_ids: list[UUID] | None = None,
    name: str | None = None,
    baseline_project: MusicProject | None = None,
) -> MultiCandidateResult:
    """Generate N independent CandidatePackages with seeds base, base+1, ….

    When ``baseline_project`` is set (e.g. recipe CIR) and the brief has
    ``locked_roles``, locked track events are restored from that CIR into
    every candidate via ``merge_preserving_locks``.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    if brief.length_bars < 8 or brief.length_bars > 16:
        raise ValueError("Phase 3 loops must be 8–16 bars")

    settings = settings or get_settings()
    logger = setup_logging(settings.log_level)
    settings.ensure_workspace()
    session_factory = init_db(settings)
    repo = ProjectRepository(session_factory)
    assets = AssetStore(settings)
    daw = adapter or select_adapter(settings, assets)

    plan = build_conditioning_plan(brief, profile)
    conditioned = apply_conditioning_to_brief(brief, plan)
    seed0 = base_seed if base_seed is not None else (conditioned.seed or 0)

    session_id = new_id()
    shared_id = new_id()
    refs = list(reference_ids or [])
    if profile is not None and profile.id not in refs:
        # profile.id is not a ReferenceAsset id — keep separate; refs are asset ids
        pass

    # Recipe / explicit CIR: restore locked roles into cand0 (and later cands).
    locked_source = baseline_project
    if locked_source is not None and conditioned.locked_roles:
        locked_source = apply_role_locks(locked_source, conditioned.locked_roles)

    baseline = _package_one(
        brief=conditioned,
        seed=seed0,
        settings=settings,
        assets=assets,
        repo=repo,
        adapter=daw,
        plan=plan,
        reference_ids=refs,
        name=name,
        parent_version_id=None,
        baseline_project=locked_source,
        index=0,
        shared_project_id=shared_id,
    )

    # Subsequent candidates share locked material from the packaged baseline
    # (which already carries recipe CIR locked tracks when provided).
    lock_baseline = baseline.project
    candidates = [baseline]
    for i in range(1, n):
        bundle = _package_one(
            brief=conditioned,
            seed=seed0 + i,
            settings=settings,
            assets=assets,
            repo=repo,
            adapter=daw,
            plan=plan,
            reference_ids=refs,
            name=name,
            parent_version_id=baseline.version.id,
            baseline_project=lock_baseline,
            index=i,
            shared_project_id=shared_id,
        )
        candidates.append(bundle)

    tip = candidates[-1]
    tip.project.version_id = tip.version.id
    repo.save_project(tip.project)

    recipe_cir_restored = bool(
        locked_source is not None and conditioned.locked_roles
    )
    session_meta = {
        "session_id": str(session_id),
        "project_id": str(shared_id),
        "n": n,
        "base_seed": seed0,
        "brief": conditioned.model_dump(mode="json"),
        "conditioning": plan.as_dict(),
        "reference_profile_id": str(profile.id) if profile else None,
        "reference_ids": [str(r) for r in refs],
        "recipe_id": str(conditioned.recipe_id) if conditioned.recipe_id else None,
        "recipe_cir_restored": recipe_cir_restored,
        "phase2_dependency": (
            "Phase 2 ReferenceProfile pipeline available; "
            "FixtureReferenceAnalyzer remains for demos without a live file"
        ),
        "candidates": [
            {
                "index": c.index,
                "seed": c.seed,
                "version_id": str(c.version.id),
                "candidate_id": str(c.candidate.id),
                "one_line_diff": c.candidate.one_line_diff,
                "midi_paths": [str(p) for p in c.midi_paths.values()],
                "cir_snapshot_ref": c.candidate.cir_snapshot_ref,
                "loudness_notes": c.candidate.loudness_notes.model_dump(mode="json"),
                "musical_diff": c.diff_vs_baseline.model_dump(mode="json")
                if c.diff_vs_baseline
                else None,
            }
            for c in candidates
        ],
        "tip_version_id": str(tip.version.id),
        "schema_version": "0.3.0",
    }
    session_path = assets.write_json(
        f"projects/{shared_id}/candidate_session_{session_id}.json",
        session_meta,
    )
    # Tip metadata for revise / recipe-save
    assets.write_json(
        f"projects/{shared_id}/metadata.json",
        {
            "project_id": str(shared_id),
            "version_id": str(tip.version.id),
            "session_id": str(session_id),
            "seed": tip.seed,
            "bpm": tip.project.bpm,
            "key": tip.project.key_estimate,
            "bars": tip.project.length_bars,
            "recipe_id": str(conditioned.recipe_id) if conditioned.recipe_id else None,
            "candidate": tip.candidate.model_dump(mode="json"),
            "conditioning": plan.as_dict(),
            "mode": settings.daw_mode.value,
            "schema_version": tip.project.schema_version,
            "phase": 3,
        },
    )
    assets.write_json(
        f"projects/{shared_id}/brief.json",
        conditioned.model_dump(mode="json"),
    )

    log_event(
        logger,
        "candidates.done",
        project_id=str(shared_id),
        n=n,
        base_seed=seed0,
        session_id=str(session_id),
    )
    return MultiCandidateResult(
        session_id=session_id,
        brief=conditioned,
        conditioning=plan.as_dict(),
        baseline=baseline,
        candidates=candidates,
        session_path=session_path,
        reference_profile_id=str(profile.id) if profile else None,
        recipe_id=str(conditioned.recipe_id) if conditioned.recipe_id else None,
        recipe_cir_restored=recipe_cir_restored,
    )
