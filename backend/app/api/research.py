"""Phase 7 research + MIDI audition stubs for the local UI."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException

from backend.app.api.deps import projects_repo, settings_dep
from backend.app.models.schemas import MidiAuditionStub
from backend.app.research.eval_harness import run_phase7_baseline_eval
from backend.app.research.registry import research_status
from backend.app.storage.assets import AssetStore

router = APIRouter(tags=["research"])


@router.get("/api/research/status")
def research_status_view() -> dict:
    return research_status(settings_dep())


@router.post("/api/research/eval")
def research_eval_run(
    prompt: str = "mellow Afrobeats 110 BPM in A minor",
    seed: int = 42,
    bars: int = 8,
) -> dict:
    settings = settings_dep()
    result = run_phase7_baseline_eval(prompt, seed=seed, bars=bars, settings=settings)
    assets = AssetStore(settings)
    assets.write_json(f"research/eval/{result.id}.json", result.model_dump(mode="json"))
    return result.model_dump(mode="json")


@router.get("/api/projects/{project_id}/midi-audition")
def midi_audition(project_id: UUID) -> dict:
    """Honest MIDI audition stub — returns paths + midi_proxy note (no audio decode)."""
    repo = projects_repo()
    project = repo.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    settings = settings_dep()
    assets = AssetStore(settings)
    midi_dir = assets.root / "midi" / str(project_id)
    paths: dict[str, str] = {}
    if midi_dir.is_dir():
        for p in sorted(midi_dir.glob("*.mid")):
            paths[p.stem] = str(p.resolve())
    # Also surface candidate package paths from metadata when present.
    meta_path = assets.root / "projects" / str(project_id) / "metadata.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            cand = meta.get("candidate") or {}
            for mp in cand.get("midi_paths") or []:
                path = Path(mp)
                paths.setdefault(path.stem, str(path.resolve() if path.is_absolute() else (assets.root / path).resolve()))
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    stub = MidiAuditionStub(
        project_id=project_id,
        version_id=project.version_id,
        midi_paths=paths,
        normalization_status="midi_proxy",
        playable_in_ui=False,
    )
    return stub.model_dump(mode="json")
