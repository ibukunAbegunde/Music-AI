"""Job listing / status — thin wrappers over JobRecord."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.api.deps import projects_repo
from backend.app.api.schemas import JobCreateRequest

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(limit: int = 50) -> list[dict]:
    return projects_repo().list_jobs(limit=limit)


@router.get("/{job_id}")
def get_job(job_id: str) -> dict:
    job = projects_repo().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("")
def create_job_stub(body: JobCreateRequest) -> dict:
    """Record a pending job stub (UI history). Heavy work still runs via compose routes."""
    repo = projects_repo()
    job_id = repo.create_job(
        body.kind,
        project_id=body.project_id,
        detail=body.detail,
    )
    job = repo.get_job(job_id)
    assert job is not None
    return job


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    repo = projects_repo()
    job = repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] in ("completed", "failed", "cancelled"):
        return job
    updated = repo.update_job(job_id, status="cancelled", detail={**job["detail"], "cancelled": True})
    assert updated is not None
    return updated
