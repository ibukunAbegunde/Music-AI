"""FastAPI entrypoint for the local Music AI UI."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import jobs, projects, references
from backend.app.api.schemas import HealthResponse, SettingsResponse
from backend.app.core.config import get_settings
from backend.app.core.doctor import run_doctor
from backend.app.models.db import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.ensure_workspace()
    init_db(settings)
    yield


app = FastAPI(
    title="Music AI Local API",
    version="0.5.0",
    description="Phase-adjacent HTTP surface over existing compose / reference / jobs services.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(references.router)
app.include_router(jobs.router)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        schema_version=settings.schema_version,
        daw_mode=settings.daw_mode.value,
        workspace=str(settings.workspace_dir.resolve()),
    )


@app.get("/api/settings", response_model=SettingsResponse)
def settings_view() -> SettingsResponse:
    settings = get_settings()
    return SettingsResponse(
        daw_mode=settings.daw_mode.value,
        workspace_dir=str(settings.workspace_dir.resolve()),
        llm_provider=settings.llm_provider,
        allow_cloud_audio=settings.allow_cloud_audio,
        allow_cloud_llm=settings.allow_cloud_llm,
        music_ai_separator=settings.music_ai_separator,
        music_ai_transcriber=settings.music_ai_transcriber,
        taste_encoder=settings.taste_encoder,
        schema_version=settings.schema_version,
    )


@app.get("/api/doctor")
def doctor() -> dict:
    return run_doctor()


def run() -> None:
    """Console script: music-ai-api"""
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    run()
