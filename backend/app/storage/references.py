"""Reference asset / profile persistence (SQLite + workspace JSON)."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.db import ReferenceRecord
from backend.app.models.schemas import ReferenceAsset, ReferenceProfile, utcnow


class ReferenceRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def save(self, asset: ReferenceAsset, profile: ReferenceProfile | None = None) -> ReferenceAsset:
        with self._sf() as session:
            row = session.get(ReferenceRecord, str(asset.id))
            payload = asset.model_dump(mode="json")
            profile_json = profile.model_dump_json() if profile is not None else None
            if row is None:
                row = ReferenceRecord(
                    id=str(asset.id),
                    sha256=asset.immutable_sha256,
                    original_filename=asset.original_filename,
                    license_class=asset.license_class.value,
                    use_mode=asset.use_mode.value,
                    analysis_status=asset.analysis_status,
                    payload_json=json.dumps(payload),
                    profile_json=profile_json,
                )
                session.add(row)
            else:
                row.sha256 = asset.immutable_sha256
                row.original_filename = asset.original_filename
                row.license_class = asset.license_class.value
                row.use_mode = asset.use_mode.value
                row.analysis_status = asset.analysis_status
                row.payload_json = json.dumps(payload)
                if profile_json is not None:
                    row.profile_json = profile_json
                row.updated_at = utcnow()
            session.commit()
        return asset

    def get(self, reference_id: UUID) -> tuple[ReferenceAsset, ReferenceProfile | None] | None:
        with self._sf() as session:
            row = session.get(ReferenceRecord, str(reference_id))
            if row is None:
                return None
            asset = ReferenceAsset.model_validate(json.loads(row.payload_json))
            profile = (
                ReferenceProfile.model_validate_json(row.profile_json)
                if row.profile_json
                else None
            )
            return asset, profile

    def get_by_hash(self, sha256: str) -> ReferenceAsset | None:
        with self._sf() as session:
            row = (
                session.query(ReferenceRecord)
                .filter(ReferenceRecord.sha256 == sha256)
                .order_by(ReferenceRecord.created_at.asc())
                .first()
            )
            if row is None:
                return None
            return ReferenceAsset.model_validate(json.loads(row.payload_json))

    def list_all(self) -> list[tuple[ReferenceAsset, ReferenceProfile | None]]:
        with self._sf() as session:
            rows = (
                session.query(ReferenceRecord)
                .order_by(ReferenceRecord.created_at.desc())
                .all()
            )
            out: list[tuple[ReferenceAsset, ReferenceProfile | None]] = []
            for row in rows:
                asset = ReferenceAsset.model_validate(json.loads(row.payload_json))
                profile = (
                    ReferenceProfile.model_validate_json(row.profile_json)
                    if row.profile_json
                    else None
                )
                out.append((asset, profile))
            return out
