"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.core.config import DawMode, Settings


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    ws = tmp_path / "workspace"
    return Settings(
        app_env="test",
        log_level="WARNING",
        workspace_dir=ws,
        database_url=f"sqlite:///{ws / 'test.db'}",
        daw_mode=DawMode.SIMULATION,
        allow_cloud_audio=False,
        allow_cloud_llm=False,
    )
