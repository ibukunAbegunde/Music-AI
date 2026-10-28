"""Taste model registry — versioned checkpoints with activate / rollback."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from backend.app.core.config import Settings, get_settings
from backend.app.models.schemas import TasteModelCheckpoint
from backend.app.storage.assets import AssetStore


def _registry_dir(assets: AssetStore) -> Path:
    path = assets.root / "models" / "taste"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_path(assets: AssetStore) -> Path:
    return _registry_dir(assets) / "registry.json"


def _load_index(assets: AssetStore) -> dict:
    path = _index_path(assets)
    if not path.exists():
        return {"active_id": None, "history": [], "checkpoints": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_index(assets: AssetStore, index: dict) -> None:
    _index_path(assets).write_text(json.dumps(index, indent=2), encoding="utf-8")


def save_checkpoint(
    checkpoint: TasteModelCheckpoint,
    *,
    settings: Settings | None = None,
    activate_if_better: bool = False,
) -> Path:
    """Persist checkpoint JSON and register it. Optionally activate if marked better."""
    settings = settings or get_settings()
    assets = AssetStore(settings)
    root = _registry_dir(assets)
    path = root / f"{checkpoint.id}.json"
    path.write_text(json.dumps(checkpoint.model_dump(mode="json"), indent=2), encoding="utf-8")

    index = _load_index(assets)
    cid = str(checkpoint.id)
    if cid not in index["checkpoints"]:
        index["checkpoints"].append(cid)
    if activate_if_better and checkpoint.better_than_baseline:
        # deactivate others on disk
        _set_active(assets, index, checkpoint)
    _save_index(assets, index)
    return path


def _set_active(assets: AssetStore, index: dict, checkpoint: TasteModelCheckpoint) -> None:
    prev = index.get("active_id")
    if prev:
        index.setdefault("history", []).append(prev)
        prev_path = _registry_dir(assets) / f"{prev}.json"
        if prev_path.exists():
            prev_ckpt = TasteModelCheckpoint.model_validate(
                json.loads(prev_path.read_text(encoding="utf-8"))
            )
            prev_ckpt.active = False
            prev_path.write_text(
                json.dumps(prev_ckpt.model_dump(mode="json"), indent=2), encoding="utf-8"
            )
    checkpoint.active = True
    path = _registry_dir(assets) / f"{checkpoint.id}.json"
    path.write_text(json.dumps(checkpoint.model_dump(mode="json"), indent=2), encoding="utf-8")
    index["active_id"] = str(checkpoint.id)


def list_checkpoints(*, settings: Settings | None = None) -> list[TasteModelCheckpoint]:
    settings = settings or get_settings()
    assets = AssetStore(settings)
    index = _load_index(assets)
    out: list[TasteModelCheckpoint] = []
    for cid in index.get("checkpoints", []):
        path = _registry_dir(assets) / f"{cid}.json"
        if path.exists():
            out.append(
                TasteModelCheckpoint.model_validate(json.loads(path.read_text(encoding="utf-8")))
            )
    return out


def get_active_checkpoint(*, settings: Settings | None = None) -> TasteModelCheckpoint | None:
    settings = settings or get_settings()
    assets = AssetStore(settings)
    index = _load_index(assets)
    active = index.get("active_id")
    if not active:
        return None
    path = _registry_dir(assets) / f"{active}.json"
    if not path.exists():
        return None
    return TasteModelCheckpoint.model_validate(json.loads(path.read_text(encoding="utf-8")))


def activate_checkpoint(
    checkpoint_id: UUID,
    *,
    settings: Settings | None = None,
    force: bool = False,
) -> TasteModelCheckpoint:
    """Activate a registered checkpoint.

    Refuses unless ``better_than_baseline`` (deploy gate) unless ``force=True``.
    Forced activations are logged via a ``force_activated`` note on the checkpoint.
    """
    settings = settings or get_settings()
    assets = AssetStore(settings)
    path = _registry_dir(assets) / f"{checkpoint_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"unknown checkpoint {checkpoint_id}")
    ckpt = TasteModelCheckpoint.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if not ckpt.better_than_baseline and not force:
        raise ValueError(
            f"refusing to activate checkpoint {checkpoint_id}: "
            "better_than_baseline=False (pass force=True to override the deploy gate)"
        )
    if force and not ckpt.better_than_baseline:
        marker = "force_activated=true (bypassed better-than-retrieval gate)"
        existing = (ckpt.notes or "").strip()
        if marker not in existing:
            ckpt.notes = f"{existing}; {marker}".strip("; ") if existing else marker
    index = _load_index(assets)
    _set_active(assets, index, ckpt)
    _save_index(assets, index)
    return ckpt


def rollback_checkpoint(*, settings: Settings | None = None) -> TasteModelCheckpoint | None:
    """Roll back to the previous active checkpoint (if any)."""
    settings = settings or get_settings()
    assets = AssetStore(settings)
    index = _load_index(assets)
    history: list[str] = list(index.get("history") or [])
    if not history:
        # deactivate current only
        active = index.get("active_id")
        if active:
            path = _registry_dir(assets) / f"{active}.json"
            if path.exists():
                ckpt = TasteModelCheckpoint.model_validate(
                    json.loads(path.read_text(encoding="utf-8"))
                )
                ckpt.active = False
                path.write_text(
                    json.dumps(ckpt.model_dump(mode="json"), indent=2), encoding="utf-8"
                )
            index["active_id"] = None
            _save_index(assets, index)
        return None
    prev_id = history.pop()
    index["history"] = history
    path = _registry_dir(assets) / f"{prev_id}.json"
    if not path.exists():
        index["active_id"] = None
        _save_index(assets, index)
        return None
    ckpt = TasteModelCheckpoint.model_validate(json.loads(path.read_text(encoding="utf-8")))
    _set_active(assets, index, ckpt)
    _save_index(assets, index)
    return ckpt
