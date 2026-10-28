"""Application configuration loaded from environment / .env."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DawMode(str, Enum):
    SIMULATION = "simulation"
    MIDI_EXPORT = "midi_export"
    POSTFADER = "postfader"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    workspace_dir: Path = Path("workspace")
    database_url: str = "sqlite:///workspace/music_ai.db"
    daw_mode: DawMode = DawMode.SIMULATION
    llm_provider: str = "stub"
    allow_cloud_audio: bool = False
    allow_cloud_llm: bool = False
    fl_studio_path: str | None = None
    postfader_path: str | None = None
    schema_version: str = Field(default="0.1.0", description="Domain schema version")

    def ensure_workspace(self) -> Path:
        """Create workspace subdirectories used by Phase 0."""
        root = self.workspace_dir
        for sub in (
            "projects",
            "midi",
            "renders",
            "stems",
            "references",
            "logs",
            "snapshots",
        ):
            (root / sub).mkdir(parents=True, exist_ok=True)
        return root


@lru_cache
def get_settings() -> Settings:
    return Settings()
