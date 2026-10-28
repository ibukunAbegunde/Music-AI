"""Projects, brief parse, compose, revise, versions, A/B."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException

from backend.app.api.deps import projects_repo, settings_dep
from backend.app.api.schemas import (
    AbCompareRequest,
    BriefParseRequest,
    ComposeRequest,
    RefComposeRequest,
    RestoreRequest,
    ReviseRequest,
)
from backend.app.music.brief import parse_brief
from backend.app.music.templates import list_templates
from backend.app.services.ab_compare import compare_candidates, compare_session_pair
from backend.app.services.compose import compose_from_prompt, load_project_metadata
from backend.app.services.full_compose import (
    full_compose_from_prompt,
    full_compose_from_reference,
)
from backend.app.services.reference_compose import compose_from_reference
from backend.app.services.revise import revise_project
from backend.app.services.versions import list_version_timeline, restore_version

router = APIRouter(prefix="/api", tags=["projects"])


def _paths_to_str(paths: dict[str, Path]) -> dict[str, str]:
    return {k: str(v) for k, v in paths.items()}


def _compose_payload(result: Any) -> dict[str, Any]:
    brief = getattr(result, "brief", None)
    return {
        "project": result.project.model_dump(mode="json"),
        "version": result.version.model_dump(mode="json"),
        "brief": brief.model_dump(mode="json") if brief is not None else None,
        "candidate": result.candidate.model_dump(mode="json") if result.candidate else None,
        "midi_paths": _paths_to_str(result.midi_paths),
        "next_moves": [o.model_dump(mode="json") for o in (result.next_moves or [])],
        "daw": result.daw_result.as_dict() if hasattr(result, "daw_result") else None,
        "snapshot_ref": getattr(result, "snapshot_ref", None),
        "specialist_name": getattr(result, "specialist_name", None),
        "specialist_mode": getattr(result, "specialist_mode", None),
    }


@router.get("/templates")
def get_templates() -> list[dict]:
    return [t.model_dump(mode="json") for t in list_templates()]


@router.post("/brief/parse")
def parse_brief_endpoint(body: BriefParseRequest) -> dict:
    brief = parse_brief(
        body.prompt,
        seed=body.seed,
        bars=body.bars if body.bars <= 16 else 8,
        locked_roles=body.locked_roles or None,
        scratch_or_release=body.scratch_or_release,
    )
    if body.bars > 16:
        brief.length_bars = body.bars
    return brief.model_dump(mode="json")


@router.get("/projects")
def list_projects() -> list[dict]:
    return [p.model_dump(mode="json") for p in projects_repo().list_projects()]


@router.get("/projects/{project_id}")
def get_project(project_id: UUID) -> dict:
    repo = projects_repo()
    project = repo.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    meta: dict[str, Any] = {}
    try:
        meta = load_project_metadata(project_id)
    except FileNotFoundError:
        meta = {}
    return {
        "project": project.model_dump(mode="json"),
        "metadata": meta,
    }


@router.post("/compose")
def compose(body: ComposeRequest) -> dict:
    settings = settings_dep()
    repo = projects_repo()
    job_kind = "full-compose" if body.mode == "full" else ("ref-compose" if body.traits else "compose")
    job_id = repo.create_job(
        job_kind,
        detail={"prompt": body.prompt, "mode": body.mode, "traits": body.traits},
    )
    try:
        if body.mode == "full":
            if body.traits:
                result = full_compose_from_reference(
                    body.prompt,
                    traits=body.traits,
                    fixture=body.fixture,
                    seed=body.seed,
                    structure_id=body.structure_id,
                    bars=body.bars,
                    scratch_or_release=body.scratch_or_release,
                    autonomy_mode=body.autonomy_mode,
                    settings=settings,
                    locked_roles=body.locked_roles or None,
                )
            else:
                result = full_compose_from_prompt(
                    body.prompt,
                    seed=body.seed,
                    structure_id=body.structure_id,
                    bars=body.bars,
                    scratch_or_release=body.scratch_or_release,
                    autonomy_mode=body.autonomy_mode,
                    settings=settings,
                    locked_roles=body.locked_roles or None,
                )
            payload = _compose_payload(result)
            payload["arrangement"] = {
                "plan": result.plan.model_dump(mode="json"),
                "manual_steps": result.manual_steps,
                "gated": result.gated,
            }
            project_id = result.project.id
            version_id = result.version.id
        elif body.traits:
            # Workspace borrow chips → reference-conditioned loop (single baseline).
            ref = compose_from_reference(
                body.prompt,
                traits=body.traits,
                fixture_genre=body.fixture,
                n=1,
                seed=body.seed,
                bars=body.bars,
                settings=settings,
                locked_roles=body.locked_roles or None,
                recipe_id=body.recipe_id,
            )
            baseline = ref.multi.baseline
            payload = {
                "project": baseline.project.model_dump(mode="json"),
                "version": baseline.version.model_dump(mode="json"),
                "brief": ref.multi.brief.model_dump(mode="json"),
                "candidate": baseline.candidate.model_dump(mode="json"),
                "midi_paths": _paths_to_str(baseline.midi_paths),
                "next_moves": [o.model_dump(mode="json") for o in (baseline.next_moves or [])],
                "daw": None,
                "snapshot_ref": None,
                "traits": ref.traits,
                "conditioning": ref.multi.conditioning,
            }
            project_id = baseline.project.id
            version_id = baseline.version.id
        else:
            result = compose_from_prompt(
                body.prompt,
                seed=body.seed,
                bars=body.bars,
                settings=settings,
                locked_roles=body.locked_roles or None,
                recipe_id=body.recipe_id,
            )
            payload = _compose_payload(result)
            project_id = result.project.id
            version_id = result.version.id
        repo.update_job(
            job_id,
            status="completed",
            detail={
                "prompt": body.prompt,
                "mode": body.mode,
                "traits": body.traits,
                "project_id": str(project_id),
                "version_id": str(version_id),
            },
        )
        payload["job_id"] = job_id
        return payload
    except Exception as exc:  # noqa: BLE001 — surface to client + mark job failed
        repo.update_job(job_id, status="failed", detail={"error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/revise")
def revise(project_id: UUID, body: ReviseRequest) -> dict:
    settings = settings_dep()
    repo = projects_repo()
    # Role-locks are parsed from NL ("keep the drums…"); prepend explicit locks if UI sends them.
    instruction = body.prompt
    if body.locked_roles:
        locks = ", ".join(body.locked_roles)
        instruction = f"keep the {locks}. {body.prompt}"
    job_id = repo.create_job("revise", project_id=project_id, detail={"prompt": instruction})
    try:
        result = revise_project(
            project_id,
            instruction,
            seed=body.seed,
            settings=settings,
        )
        repo.update_job(
            job_id,
            status="completed",
            detail={
                "prompt": body.prompt,
                "project_id": str(project_id),
                "version_id": str(result.version.id),
                "one_line_diff": result.diff.one_line_summary,
            },
        )
        return {
            **_compose_payload(result),
            "diff": result.diff.model_dump(mode="json"),
            "undo_available": result.undo_available,
            "job_id": job_id,
        }
    except FileNotFoundError as exc:
        repo.update_job(job_id, status="failed", detail={"error": str(exc)})
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        repo.update_job(job_id, status="failed", detail={"error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/ref-compose")
def ref_compose(body: RefComposeRequest) -> dict:
    settings = settings_dep()
    repo = projects_repo()
    job_id = repo.create_job("ref-compose", detail={"prompt": body.prompt, "traits": body.traits})
    try:
        result = compose_from_reference(
            body.prompt,
            traits=body.traits,
            fixture_genre=body.fixture,
            n=body.n,
            seed=body.seed,
            bars=body.bars,
            settings=settings,
            locked_roles=body.locked_roles or None,
        )
        project_id = result.multi.baseline.project.id
        candidates = []
        for c in result.multi.candidates:
            candidates.append(
                {
                    "index": c.index,
                    "seed": c.seed,
                    "version_id": str(c.version.id),
                    "candidate": c.candidate.model_dump(mode="json"),
                    "midi_paths": _paths_to_str(c.midi_paths),
                    "one_line_diff": c.candidate.one_line_diff,
                }
            )
        repo.update_job(
            job_id,
            status="completed",
            detail={"project_id": str(project_id), "n": body.n},
        )
        return {
            "job_id": job_id,
            "project_id": str(project_id),
            "analyzer": result.analyzer,
            "profile": result.profile.model_dump(mode="json"),
            "traits": result.traits,
            "session_id": str(result.multi.session_id),
            "conditioning": result.multi.conditioning,
            "candidates": candidates,
            "phase2_note": result.phase2_note,
            "brief": result.multi.brief.model_dump(mode="json"),
        }
    except Exception as exc:  # noqa: BLE001
        repo.update_job(job_id, status="failed", detail={"error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/versions")
def versions(project_id: UUID) -> list[dict]:
    settings = settings_dep()
    if projects_repo().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    entries = list_version_timeline(project_id, settings=settings)
    return [
        {
            "version_id": str(e.version_id),
            "parent_version_id": str(e.parent_version_id) if e.parent_version_id else None,
            "created_at": e.created_at,
            "one_line_diff": e.one_line_diff,
            "seed": e.seed,
            "restorable": e.restorable,
            "musical_diff": e.musical_diff.model_dump(mode="json") if e.musical_diff else None,
        }
        for e in entries
    ]


@router.post("/projects/{project_id}/restore")
def restore(project_id: UUID, body: RestoreRequest) -> dict:
    try:
        version = restore_version(project_id, body.version_id, settings=settings_dep())
        return version.model_dump(mode="json")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/ab")
def ab_compare(project_id: UUID, body: AbCompareRequest) -> dict:
    settings = settings_dep()
    try:
        if body.version_a and body.version_b:
            result = compare_candidates(
                project_id,
                body.version_a,
                body.version_b,
                choice=body.choice,
                reason=body.reason,
                tags=body.tags or None,
                settings=settings,
            )
        else:
            result = compare_session_pair(
                project_id,
                index_a=body.index_a,
                index_b=body.index_b,
                choice=body.choice,
                reason=body.reason,
                settings=settings,
            )
    except (FileNotFoundError, IndexError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "comparison_id": str(result.comparison_id),
        "project_id": str(result.project_id),
        "path_mode": result.path_mode,
        "side_a": {
            "label": result.side_a.label,
            "version_id": str(result.side_a.version_id),
            "candidate_id": str(result.side_a.candidate_id) if result.side_a.candidate_id else None,
            "seed": result.side_a.seed,
            "midi_proxy_path": result.side_a.midi_proxy_path,
            "loudness_notes": result.side_a.loudness_notes.model_dump(mode="json"),
            "one_line_diff": result.side_a.one_line_diff,
        },
        "side_b": {
            "label": result.side_b.label,
            "version_id": str(result.side_b.version_id),
            "candidate_id": str(result.side_b.candidate_id) if result.side_b.candidate_id else None,
            "seed": result.side_b.seed,
            "midi_proxy_path": result.side_b.midi_proxy_path,
            "loudness_notes": result.side_b.loudness_notes.model_dump(mode="json"),
            "one_line_diff": result.side_b.one_line_diff,
        },
        "musical_diff": result.musical_diff.model_dump(mode="json"),
        "preference": result.preference.model_dump(mode="json") if result.preference else None,
        "session_path": str(result.session_path),
    }


@router.get("/projects/{project_id}/candidates")
def list_candidates(project_id: UUID) -> dict:
    """Load latest multi-candidate session for A/B UI."""
    from backend.app.storage.assets import AssetStore

    assets = AssetStore(settings_dep())
    proj_dir = assets.root / "projects" / str(project_id)
    if not proj_dir.exists():
        raise HTTPException(status_code=404, detail="project not found")
    sessions = sorted(proj_dir.glob("candidate_session_*.json"))
    if not sessions:
        return {"project_id": str(project_id), "session": None, "candidates": []}
    import json

    session = json.loads(sessions[-1].read_text(encoding="utf-8"))
    return {
        "project_id": str(project_id),
        "session_path": str(sessions[-1]),
        "session": session,
        "candidates": session.get("candidates", []),
    }
