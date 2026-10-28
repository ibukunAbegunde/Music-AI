"""Reference import / pipeline / list endpoints."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.app.api.deps import references_repo, settings_dep
from backend.app.audio.io import synth_tone_wav
from backend.app.services.reference import (
    load_profile,
    run_analyse,
    run_import,
    run_pipeline,
    run_separate,
    run_transcribe,
)
from backend.app.storage.assets import AssetStore
from backend.app.storage.repository import ProjectRepository
from backend.app.models.db import init_db

router = APIRouter(prefix="/api/references", tags=["references"])


@router.get("")
def list_references() -> list[dict]:
    rows = references_repo().list_all()
    out = []
    for asset, profile in rows:
        out.append(
            {
                "asset": asset.model_dump(mode="json"),
                "profile": profile.model_dump(mode="json") if profile else None,
            }
        )
    return out


@router.get("/{reference_id}")
def get_reference(reference_id: UUID) -> dict:
    row = references_repo().get(reference_id)
    if row is None:
        raise HTTPException(status_code=404, detail="reference not found")
    asset, profile = row
    stems = []
    assets = AssetStore(settings_dep())
    stems_meta = assets.stems_dir(reference_id) / "stems.json"
    if stems_meta.exists():
        import json

        stems = json.loads(stems_meta.read_text(encoding="utf-8"))
    return {
        "asset": asset.model_dump(mode="json"),
        "profile": profile.model_dump(mode="json") if profile else None,
        "stems": stems,
    }


@router.get("/{reference_id}/profile")
def get_profile(reference_id: UUID) -> dict:
    try:
        profile = load_profile(reference_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return profile.model_dump(mode="json")


@router.post("/import")
async def import_reference(
    file: UploadFile = File(...),
    license_class: str = Form("owned"),
    use_mode: str = Form("analysis"),
    permission_notes: str | None = Form(None),
) -> dict:
    settings = settings_dep()
    suffix = Path(file.filename or "upload.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        data = await file.read()
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        asset = run_import(
            tmp_path,
            settings=settings,
            license_class=license_class,
            use_mode=use_mode,
            permission_notes=permission_notes,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)
    return asset.model_dump(mode="json")


@router.post("/demo-fixture")
def create_demo_fixture(bpm: float = 110.0, duration_sec: float = 6.0) -> dict:
    """Synthesize a short tone WAV and run the full Phase 2 pipeline (simulation)."""
    settings = settings_dep()
    repo = ProjectRepository(init_db(settings))
    job_id = repo.create_job("ref-pipeline", detail={"fixture": True, "bpm": bpm})
    assets = AssetStore(settings)
    out = assets.root / "references" / "_uploads" / "demo_ref.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    synth_tone_wav(out, duration_sec=duration_sec, bpm=bpm)
    try:
        result = run_pipeline(
            out,
            settings=settings,
            license_class="owned",
            use_mode="analysis",
            borrow_traits=["bass_bounce", "drums", "groove"],
            prompt_for_brief="mellow Afrobeats with this bass bounce",
        )
        repo.update_job(
            job_id,
            status="completed",
            detail={"reference_id": str(result.asset.id)},
        )
        return {
            "job_id": job_id,
            "asset": result.asset.model_dump(mode="json"),
            "profile": result.profile.model_dump(mode="json"),
            "stems": [s.model_dump(mode="json") for s in result.stems],
            "brief_with_borrows": (
                result.brief_with_borrows.model_dump(mode="json")
                if result.brief_with_borrows
                else None
            ),
            "separator_name": result.separator_name,
            "transcriber_name": result.transcriber_name,
            "simulated": result.simulated,
            "transcription_note_count": len(result.transcription_notes),
        }
    except Exception as exc:  # noqa: BLE001
        repo.update_job(job_id, status="failed", detail={"error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{reference_id}/analyse")
def analyse(reference_id: UUID) -> dict:
    try:
        asset, profile = run_analyse(reference_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "asset": asset.model_dump(mode="json"),
        "profile": profile.model_dump(mode="json"),
    }


@router.post("/{reference_id}/separate")
def separate(reference_id: UUID) -> dict:
    try:
        asset, stems, profile = run_separate(reference_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "asset": asset.model_dump(mode="json"),
        "stems": [s.model_dump(mode="json") for s in stems],
        "profile": profile.model_dump(mode="json") if profile else None,
    }


@router.post("/{reference_id}/transcribe")
def transcribe(
    reference_id: UUID,
    stem_type: str = "bass",
    lock_role: bool = False,
) -> dict:
    try:
        asset, stem, notes, midi_path = run_transcribe(
            reference_id,
            stem_type=stem_type,
            lock_role=lock_role,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "asset": asset.model_dump(mode="json"),
        "stem": stem.model_dump(mode="json"),
        "note_count": len(notes),
        "midi_path": str(midi_path) if midi_path else None,
    }


@router.post("/pipeline")
async def pipeline_upload(
    file: UploadFile = File(...),
    license_class: str = Form("owned"),
    use_mode: str = Form("analysis"),
    borrow: str = Form("bass_bounce,drums,groove"),
    prompt: str | None = Form(None),
    lock_bass: bool = Form(False),
) -> dict:
    settings = settings_dep()
    repo = ProjectRepository(init_db(settings))
    job_id = repo.create_job("ref-pipeline", detail={"filename": file.filename})
    suffix = Path(file.filename or "upload.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        traits = [t.strip() for t in borrow.split(",") if t.strip()]
        result = run_pipeline(
            tmp_path,
            settings=settings,
            license_class=license_class,
            use_mode=use_mode,
            borrow_traits=traits,
            lock_bass=lock_bass,
            prompt_for_brief=prompt,
        )
        repo.update_job(
            job_id,
            status="completed",
            detail={"reference_id": str(result.asset.id)},
        )
        return {
            "job_id": job_id,
            "asset": result.asset.model_dump(mode="json"),
            "profile": result.profile.model_dump(mode="json"),
            "stems": [s.model_dump(mode="json") for s in result.stems],
            "brief_with_borrows": (
                result.brief_with_borrows.model_dump(mode="json")
                if result.brief_with_borrows
                else None
            ),
            "simulated": result.simulated,
            "transcription_note_count": len(result.transcription_notes),
        }
    except Exception as exc:  # noqa: BLE001
        repo.update_job(job_id, status="failed", detail={"error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)
