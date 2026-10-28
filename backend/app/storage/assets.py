"""Local asset store under the gitignored workspace directory."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import UUID

from backend.app.core.config import Settings, get_settings


class AssetStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.ensure_workspace()

    def project_dir(self, project_id: UUID) -> Path:
        path = self.root / "projects" / str(project_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def midi_dir(self, project_id: UUID) -> Path:
        path = self.root / "midi" / str(project_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def reference_dir(self, reference_id: UUID) -> Path:
        path = self.root / "references" / str(reference_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def stems_dir(self, reference_id: UUID) -> Path:
        path = self.root / "stems" / str(reference_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, relative: str, data: dict) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def copy_into(self, src: Path, relative: str) -> Path:
        dest = self.root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest
