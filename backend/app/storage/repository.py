"""Project / version repository over SQLite."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.db import JobRecord, ProjectRecord, VersionRecord
from backend.app.models.schemas import MusicProject, ProjectVersion, utcnow


class ProjectRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def save_project(self, project: MusicProject) -> MusicProject:
        project.updated_at = utcnow()
        with self._sf() as session:
            row = session.get(ProjectRecord, str(project.id))
            payload = project.model_dump(mode="json")
            if row is None:
                row = ProjectRecord(
                    id=str(project.id),
                    name=project.name,
                    status=project.status.value,
                    bpm=str(project.bpm),
                    key_estimate=project.key_estimate,
                    length_bars=str(project.length_bars),
                    generation_brief=project.generation_brief,
                    seed=str(project.seed) if project.seed is not None else None,
                    payload_json=json.dumps(payload),
                )
                session.add(row)
            else:
                row.name = project.name
                row.status = project.status.value
                row.bpm = str(project.bpm)
                row.key_estimate = project.key_estimate
                row.length_bars = str(project.length_bars)
                row.generation_brief = project.generation_brief
                row.seed = str(project.seed) if project.seed is not None else None
                row.payload_json = json.dumps(payload)
                row.updated_at = utcnow()
            session.commit()
        return project

    def get_project(self, project_id: UUID) -> MusicProject | None:
        with self._sf() as session:
            row = session.get(ProjectRecord, str(project_id))
            if row is None:
                return None
            return MusicProject.model_validate(json.loads(row.payload_json))

    def save_version(self, version: ProjectVersion, project_id: UUID) -> ProjectVersion:
        with self._sf() as session:
            row = VersionRecord(
                id=str(version.id),
                project_id=str(project_id),
                parent_version_id=(
                    str(version.parent_version_id) if version.parent_version_id else None
                ),
                payload_json=json.dumps(version.model_dump(mode="json")),
                midi_paths_json=json.dumps(version.exported_midi_paths),
                user_message=version.user_message,
            )
            session.add(row)
            session.commit()
        return version

    def list_versions(self, project_id: UUID) -> list[ProjectVersion]:
        with self._sf() as session:
            rows = (
                session.query(VersionRecord)
                .filter(VersionRecord.project_id == str(project_id))
                .order_by(VersionRecord.created_at.asc())
                .all()
            )
            return [ProjectVersion.model_validate(json.loads(r.payload_json)) for r in rows]

    def list_projects(self) -> list[MusicProject]:
        with self._sf() as session:
            rows = (
                session.query(ProjectRecord)
                .order_by(ProjectRecord.updated_at.desc())
                .all()
            )
            return [MusicProject.model_validate(json.loads(r.payload_json)) for r in rows]

    def create_job(self, kind: str, project_id: UUID | None = None, detail: dict | None = None) -> str:
        with self._sf() as session:
            row = JobRecord(
                project_id=str(project_id) if project_id else None,
                kind=kind,
                status="pending",
                detail_json=json.dumps(detail or {}),
            )
            session.add(row)
            session.commit()
            return row.id

    def get_job(self, job_id: str) -> dict | None:
        with self._sf() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                return None
            return {
                "id": row.id,
                "project_id": row.project_id,
                "kind": row.kind,
                "status": row.status,
                "detail": json.loads(row.detail_json or "{}"),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }

    def list_jobs(self, *, limit: int = 50) -> list[dict]:
        with self._sf() as session:
            rows = (
                session.query(JobRecord)
                .order_by(JobRecord.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "project_id": r.project_id,
                    "kind": r.kind,
                    "status": r.status,
                    "detail": json.loads(r.detail_json or "{}"),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        detail: dict | None = None,
    ) -> dict | None:
        with self._sf() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                return None
            if status is not None:
                row.status = status
            if detail is not None:
                row.detail_json = json.dumps(detail)
            row.updated_at = utcnow()
            session.commit()
            return {
                "id": row.id,
                "project_id": row.project_id,
                "kind": row.kind,
                "status": row.status,
                "detail": json.loads(row.detail_json or "{}"),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
