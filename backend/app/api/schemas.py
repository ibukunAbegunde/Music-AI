"""Typed request/response DTOs for the local UI API."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class HealthResponse(BaseModel):
    status: str = "ok"
    schema_version: str
    daw_mode: str
    workspace: str


class BriefParseRequest(BaseModel):
    prompt: str
    seed: int | None = None
    bars: int = Field(default=8, ge=8, le=128)
    locked_roles: list[str] = Field(default_factory=list)
    scratch_or_release: Literal["scratch", "release"] = "scratch"


class ComposeRequest(BaseModel):
    prompt: str
    seed: int | None = None
    # Wide field bound; mode-aware check below (loop 8–16, full 32–256).
    bars: int = Field(default=8, ge=8, le=256)
    locked_roles: list[str] = Field(default_factory=list)
    recipe_id: UUID | None = None
    mode: Literal["loop", "full"] = "loop"
    structure_id: str | None = None
    scratch_or_release: Literal["scratch", "release"] = "scratch"
    autonomy_mode: Literal["suggest-only", "collaborative", "autonomous"] = "collaborative"
    # When non-empty → reference-conditioned path (loop: ref-compose; full: full_compose_from_reference).
    traits: list[str] = Field(default_factory=list)
    fixture: str = "afrobeats"

    @model_validator(mode="after")
    def bars_match_mode(self) -> ComposeRequest:
        if self.mode == "full":
            # Coerce loop default (8) / undersized values to the full-length default.
            if self.bars < 32:
                self.bars = 64
            if self.bars > 256:
                raise ValueError("full mode bars must be 32–256")
        else:
            if self.bars < 8 or self.bars > 16:
                raise ValueError("loop mode bars must be 8–16")
        return self


class ReviseRequest(BaseModel):
    prompt: str
    seed: int | None = None
    locked_roles: list[str] = Field(default_factory=list)


class RefComposeRequest(BaseModel):
    prompt: str
    traits: list[str] = Field(default_factory=lambda: ["bass_bounce", "percussion_texture"])
    fixture: str = "afrobeats"
    n: int = Field(default=2, ge=1, le=8)
    seed: int | None = None
    bars: int = Field(default=8, ge=8, le=16)
    locked_roles: list[str] = Field(default_factory=list)


class AbCompareRequest(BaseModel):
    version_a: UUID | None = None
    version_b: UUID | None = None
    index_a: int = 0
    index_b: int = 1
    choice: Literal["a", "b", "tie", "skip"] | None = None
    reason: str | None = None
    tags: list[str] = Field(default_factory=list)


class RestoreRequest(BaseModel):
    version_id: UUID


class JobCreateRequest(BaseModel):
    kind: str
    project_id: UUID | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class SettingsResponse(BaseModel):
    daw_mode: str
    workspace_dir: str
    llm_provider: str
    allow_cloud_audio: bool
    allow_cloud_llm: bool
    music_ai_separator: str
    music_ai_transcriber: str
    taste_encoder: str
    autonomy_default: str = "collaborative"
    schema_version: str
