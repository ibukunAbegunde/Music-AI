"""Neural audio dual-path refinements without abandoning CIR (Phase 7 / v1.1).

Documents and exposes the dual-path contract: generative audio may produce
texture / ideation / captions, but CIR/MIDI stays the editable system of record
for track-level edits ("keep drums, change bass").
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.models.schemas import MusicProject, new_id, utcnow


class DualPathArtifact(BaseModel):
    """Optional neural-audio side artifact linked to a CIR project/version."""

    id: str = Field(default_factory=lambda: str(new_id()))
    project_id: str
    version_id: str | None = None
    kind: str  # texture | ideation | caption | generative_audio_preview
    path: str | None = None
    model_name: str | None = None
    model_version: str | None = None
    cir_snapshot_ref: str | None = None
    editable_via_cir: bool = True
    notes: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())


class DualPathPolicy(BaseModel):
    cir_is_system_of_record: bool = True
    allow_neural_audio_side_path: bool = True
    black_box_audio_only_forbidden: bool = True
    require_cir_for_role_edits: bool = True
    notes: list[str] = Field(
        default_factory=lambda: [
            "Neural / generative audio welcome for texture, ideation, captions, previews.",
            "CIR/MIDI remains SoR for role-locks, PatchOps, revise, and musical diffs.",
            "Black-box-audio-only tracks are not acceptable for keep-X-change-Y edits.",
        ]
    )


def dual_path_policy() -> DualPathPolicy:
    return DualPathPolicy()


def register_side_artifact(
    project: MusicProject,
    *,
    kind: str,
    path: str | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    cir_snapshot_ref: str | None = None,
) -> DualPathArtifact:
    """Record a neural-audio side artifact without replacing CIR."""
    return DualPathArtifact(
        project_id=str(project.id),
        version_id=str(project.version_id) if project.version_id else None,
        kind=kind,
        path=path,
        model_name=model_name,
        model_version=model_version,
        cir_snapshot_ref=cir_snapshot_ref,
        editable_via_cir=True,
        notes=[
            "Side artifact only — edits still target CIR tracks/roles.",
            "No foundation model was downloaded by this helper.",
        ],
    )


def assert_cir_editable_for_role_edit(project: MusicProject) -> dict[str, Any]:
    """Guardrail helper: role edits require CIR tracks, not audio-only blobs."""
    roles = [t.role.value for t in project.tracks]
    return {
        "ok": len(project.tracks) > 0,
        "roles": roles,
        "cir_is_system_of_record": True,
        "policy": dual_path_policy().model_dump(),
    }
