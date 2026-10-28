"""Shared FastAPI dependencies."""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.config import Settings, get_settings
from backend.app.models.db import init_db
from backend.app.storage.assets import AssetStore
from backend.app.storage.references import ReferenceRepository
from backend.app.storage.repository import ProjectRepository


@lru_cache
def _session_factory():
    return init_db(get_settings())


def settings_dep() -> Settings:
    return get_settings()


def projects_repo() -> ProjectRepository:
    return ProjectRepository(_session_factory())


def references_repo() -> ReferenceRepository:
    return ReferenceRepository(_session_factory())


def assets_store() -> AssetStore:
    return AssetStore(get_settings())
