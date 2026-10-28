"""Application configuration loaded from environment / .env."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
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
    schema_version: str = Field(default="0.3.0", description="Domain schema version")
    # Phase 2 audio adapters — defaults stay simulation/stub (no large downloads)
    music_ai_separator: str = "simulation"
    music_ai_transcriber: str = "stub"
    prefer_librosa: bool = False
    # Phase 5 taste — simulation encoder by default; optional requires explicit flag
    taste_encoder: str = "simulation"  # simulation | optional
    # Prefer MUSIC_AI_ALLOW_ENCODER_DOWNLOAD; bare ALLOW_ENCODER_DOWNLOAD also accepted.
    music_ai_allow_encoder_download: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "MUSIC_AI_ALLOW_ENCODER_DOWNLOAD",
            "ALLOW_ENCODER_DOWNLOAD",
            "music_ai_allow_encoder_download",
            "allow_encoder_download",
        ),
    )
    # Phase 7 research — defaults stay deterministic / stub (no large downloads)
    midi_specialist: str = "deterministic"  # deterministic | optional
    vocal_workflow: str = "stub"  # stub | optional
    music_ai_allow_specialist_download: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "MUSIC_AI_ALLOW_SPECIALIST_DOWNLOAD",
            "ALLOW_SPECIALIST_DOWNLOAD",
            "music_ai_allow_specialist_download",
        ),
    )
    music_ai_allow_vocal_model_download: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "MUSIC_AI_ALLOW_VOCAL_MODEL_DOWNLOAD",
            "ALLOW_VOCAL_MODEL_DOWNLOAD",
            "music_ai_allow_vocal_model_download",
        ),
    )

    @property
    def allow_encoder_download(self) -> bool:
        """Compat alias for music_ai_allow_encoder_download."""
        return self.music_ai_allow_encoder_download

    def ensure_workspace(self) -> Path:
        """Create workspace subdirectories used by Phase 0–7."""
        root = self.workspace_dir
        for sub in (
            "projects",
            "midi",
            "renders",
            "stems",
            "references",
            "references/by_hash",
            "logs",
            "snapshots",
            "models",
            "models/taste",
            "taste",
            "taste/comparisons",
            "taste/journal",
            "taste/features",
            "taste/style_vectors",
            "recipes",
            "research",
            "research/action_effect",
            "research/action_effect/outcomes",
            "research/eval",
        ):
            (root / sub).mkdir(parents=True, exist_ok=True)
        return root


@lru_cache
def get_settings() -> Settings:
    return Settings()
