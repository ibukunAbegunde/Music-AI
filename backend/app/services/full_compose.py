"""Phase 6: brief/reference → full-length instrumental + MIDI + versioned project."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from backend.app.agents.critic import propose_next_moves
from backend.app.core.config import DawMode, Settings, get_settings
from backend.app.core.logging import log_event, setup_logging
from backend.app.daw.base import DawAdapter, DawResult, ensure_daw_write_ok
from backend.app.daw.fake import FakeDawAdapter
from backend.app.daw.midi_fallback import MidiExportAdapter
from backend.app.models.db import init_db
from backend.app.models.schemas import (
    ArrangementPlan,
    BriefDocument,
    CandidatePackage,
    LoudnessNotes,
    MusicProject,
    ProjectStatus,
    ProjectVersion,
    new_id,
    utcnow,
)
from backend.app.music.arrangement import (
    MAX_FULL_BARS,
    MIN_FULL_BARS,
    brief_for_full_compose,
    generate_arranged_with_specialist,
    section_dicts_for_daw,
)
from backend.app.music.conditioning import ConditioningPlan, build_conditioning_plan
from backend.app.music.diff import baseline_diff_summary
from backend.app.music.midi import assert_project_span, export_project_midi
from backend.app.research.midi_specialist import specialist_metadata
from backend.app.services.compose import select_adapter
from backend.app.storage.assets import AssetStore
from backend.app.storage.repository import ProjectRepository


@dataclass
class FullComposeResult:
    project: MusicProject
    version: ProjectVersion
    brief: BriefDocument
    plan: ArrangementPlan
    midi_paths: dict[str, Path]
    daw_result: DawResult
    arrange_results: list[DawResult] = field(default_factory=list)
    candidate: CandidatePackage | None = None
    next_moves: list = field(default_factory=list)
    metadata_path: Path | None = None
    arrangement_plan_path: Path | None = None
    snapshot_ref: str | None = None
    manual_steps: list[str] = field(default_factory=list)
    gated: bool = False  # True when Release mode blocked DAW write
    specialist_name: str | None = None
    specialist_mode: str | None = None


def _manual_fl_steps(project: MusicProject, plan: ArrangementPlan, midi_dir: Path) -> list[str]:
    steps = [
        "Open a Scratch FL Studio project (never overwrite masters without backup).",
        f"Set project tempo to {project.bpm:g} BPM.",
        f"Import MIDI stems from {midi_dir}/ (drums.mid, bass.mid, chord.mid).",
        "Assign instruments per palette hints in arrangement_plan.json.",
        "On the Playlist, place/duplicate patterns to match section_map bars:",
    ]
    for s in plan.section_map:
        steps.append(
            f"  - {s.name}: bars {s.start_bar}–{s.end_bar} "
            f"(intensity≈{s.intensity_target:.2f})"
        )
    steps.extend(
        [
            "Optional: import combined.mid as a single multi-channel reference.",
            "Bounce/export audio manually when needed → workspace/renders/.",
            "See docs/setup-macos-fl-studio.md#phase-6-full-length-import.",
        ]
    )
    return steps


def full_compose_from_brief(
    brief: BriefDocument,
    plan: ArrangementPlan,
    *,
    settings: Settings | None = None,
    adapter: DawAdapter | None = None,
    name: str | None = None,
    conditioning: ConditioningPlan | None = None,
    reference_ids: list[UUID] | None = None,
    force: bool = False,
) -> FullComposeResult:
    settings = settings or get_settings()
    logger = setup_logging(settings.log_level)
    settings.ensure_workspace()
    session_factory = init_db(settings)
    repo = ProjectRepository(session_factory)
    assets = AssetStore(settings)

    if plan.length_bars < MIN_FULL_BARS or plan.length_bars > MAX_FULL_BARS:
        raise ValueError(f"bars must be {MIN_FULL_BARS}–{MAX_FULL_BARS}")

    specialist_result = generate_arranged_with_specialist(
        brief,
        plan,
        name=name,
        plan_conditioning=conditioning,
        reference_ids=reference_ids,
        settings=settings,
    )
    project = specialist_result.project
    project.brief_id = brief.id
    brief.project_id = project.id
    assert_project_span(project)

    midi_dir = assets.midi_dir(project.id)
    midi_paths = export_project_midi(project, midi_dir)

    daw = adapter or select_adapter(settings, assets)
    daw.connect()
    snapshot_ref = None
    arrange_results: list[DawResult] = []
    gated = False
    daw_result: DawResult

    release = plan.scratch_or_release == "release"
    # Release mode: MIDI + plan only unless Scratch, or autonomous + --force (logged).
    release_force_bypass = (
        release and plan.autonomy_mode == "autonomous" and force
    )
    if release and not release_force_bypass:
        gated = True
        daw_result = DawResult(
            supported=True,
            attempted=False,
            succeeded=False,
            verified=False,
            observations={
                "gate": "release_mode",
                "approvals_required": plan.approvals_required,
                "autonomy_mode": plan.autonomy_mode,
                "force": force,
            },
            user_action_required=(
                "Release mode: review arrangement_plan.json + MIDI, then re-run with "
                "--scratch, or --release --autonomy autonomous --force after approval."
            ),
        )
    else:
        if release_force_bypass:
            log_event(
                logger,
                "full_compose.release_force_bypass",
                autonomy_mode=plan.autonomy_mode,
                structure=plan.structure_template_id,
            )
        if isinstance(daw, FakeDawAdapter):
            snap = daw.save_snapshot("pre-full-compose")
            snapshot_ref = snap.observations.get("snapshot_ref")
        daw_result = daw.create_or_update_notes(project)
        ensure_daw_write_ok(daw_result, context="full_compose")
        if isinstance(daw, FakeDawAdapter):
            daw.set_tempo(project.bpm)
            for sec in section_dicts_for_daw(project):
                arrange_results.append(daw.arrange_section(sec))
            daw.verify_postcondition(
                {"bpm": project.bpm, "min_tracks": 3, "min_notes": 20}
            )
        elif isinstance(daw, MidiExportAdapter):
            daw.verify_postcondition({"min_files": 3, "roles": ["drums", "bass", "chord"]})
            for sec in section_dicts_for_daw(project):
                arrange_results.append(daw.arrange_section(sec))

    one_line = (
        f"Full {project.length_bars}-bar {plan.structure_template_id} instrumental "
        f"({len(project.sections)} sections) — {baseline_diff_summary(project)}"
    )
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

    plan_path = assets.write_json(
        f"projects/{project.id}/arrangement_plan.json",
        {
            **plan.model_dump(mode="json"),
            "project_id": str(project.id),
            "version_id": str(version.id),
            "instrument_palette": plan.instrument_palette,
            "section_playlist": section_dicts_for_daw(project),
        },
    )

    try:
        from backend.app.agents.critic import critique_project

        next_moves = critique_project(project, max_moves=3).next_moves or propose_next_moves(
            project
        )
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "full_compose.critic_fallback", error=str(exc))
        next_moves = propose_next_moves(project)

    manual_steps = _manual_fl_steps(project, plan, midi_dir)
    spec_meta = specialist_metadata(specialist_result)
    meta = {
        "phase": 6,
        "project_id": str(project.id),
        "version_id": str(version.id),
        "brief": brief.model_dump(mode="json"),
        "arrangement_plan": plan.model_dump(mode="json"),
        "seed": project.seed,
        "bpm": project.bpm,
        "key": project.key_estimate,
        "genre_template_id": project.genre_template_id,
        "structure_template_id": plan.structure_template_id,
        "bars": project.length_bars,
        "sections": [s.model_dump(mode="json") for s in project.sections],
        "instrument_palette": plan.instrument_palette,
        "candidate": candidate.model_dump(mode="json"),
        "next_moves": [o.model_dump(mode="json") for o in next_moves],
        "daw": daw_result.as_dict(),
        "arrange_results": [r.as_dict() for r in arrange_results],
        "snapshot_ref": snapshot_ref,
        "mode": settings.daw_mode.value,
        "scratch_or_release": plan.scratch_or_release,
        "gated": gated,
        "manual_fl_steps": manual_steps,
        "schema_version": project.schema_version,
        **spec_meta,
    }
    metadata_path = assets.write_json(f"projects/{project.id}/metadata.json", meta)
    assets.write_json(f"projects/{project.id}/brief.json", brief.model_dump(mode="json"))
    assets.write_json(
        f"projects/{project.id}/manual_fl_steps.json",
        {"steps": manual_steps, "doc": plan.manual_fl_steps_ref},
    )
    log_event(
        logger,
        "full_compose.done",
        project_id=str(project.id),
        bars=project.length_bars,
        sections=len(project.sections),
        gated=gated,
        specialist_name=specialist_result.specialist_name,
    )

    return FullComposeResult(
        project=project,
        version=version,
        brief=brief,
        plan=plan,
        midi_paths=midi_paths,
        daw_result=daw_result,
        arrange_results=arrange_results,
        candidate=candidate,
        next_moves=next_moves,
        metadata_path=metadata_path,
        arrangement_plan_path=plan_path,
        snapshot_ref=snapshot_ref,
        manual_steps=manual_steps,
        gated=gated,
        specialist_name=specialist_result.specialist_name,
        specialist_mode=specialist_result.mode,
    )


def full_compose_from_prompt(
    prompt: str,
    *,
    seed: int | None = None,
    structure_id: str | None = None,
    bars: int | None = None,
    scratch_or_release: str = "scratch",
    autonomy_mode: str = "collaborative",
    settings: Settings | None = None,
    adapter: DawAdapter | None = None,
    locked_roles: list[str] | None = None,
    force: bool = False,
) -> FullComposeResult:
    brief, plan = brief_for_full_compose(
        prompt,
        seed=seed,
        structure_id=structure_id,
        bars=bars,
        scratch_or_release=scratch_or_release,
        autonomy_mode=autonomy_mode,
        locked_roles=locked_roles,
    )
    return full_compose_from_brief(
        brief, plan, settings=settings, adapter=adapter, force=force
    )


def full_compose_from_reference(
    prompt: str,
    *,
    traits: list[str] | None = None,
    fixture: str = "afrobeats",
    seed: int | None = None,
    structure_id: str | None = None,
    bars: int | None = None,
    scratch_or_release: str = "scratch",
    autonomy_mode: str = "collaborative",
    settings: Settings | None = None,
    adapter: DawAdapter | None = None,
    locked_roles: list[str] | None = None,
    force: bool = False,
) -> FullComposeResult:
    """Reference-conditioned full-length path (fixture profile → borrow → arrange)."""
    from backend.app.audio.reference import FixtureReferenceAnalyzer, bind_borrow_chips
    from backend.app.models.schemas import LicenseClass

    settings = settings or get_settings()
    az = FixtureReferenceAnalyzer()
    ref_asset, profile = az.register_fixture(
        name=f"{fixture}-full-ref.wav",
        genre=fixture,
        license_class=LicenseClass.OWNED,
    )
    brief, plan = brief_for_full_compose(
        prompt,
        seed=seed,
        structure_id=structure_id or f"{fixture}_full",
        bars=bars,
        scratch_or_release=scratch_or_release,
        autonomy_mode=autonomy_mode,
        locked_roles=locked_roles,
    )
    chips = bind_borrow_chips(
        profile,
        list(traits or ["bass_bounce", "groove"]),
        reference_id=ref_asset.id,
    )
    existing = {c.trait for c in brief.borrow_chips}
    for c in chips:
        if c.trait not in existing:
            brief.borrow_chips.append(c)
    conditioning = build_conditioning_plan(brief, profile)
    return full_compose_from_brief(
        brief,
        plan,
        settings=settings,
        adapter=adapter,
        conditioning=conditioning,
        reference_ids=[ref_asset.id],
        force=force,
    )


def load_arrangement_plan(project_id: UUID, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    path = settings.workspace_dir / "projects" / str(project_id) / "arrangement_plan.json"
    return json.loads(path.read_text(encoding="utf-8"))
