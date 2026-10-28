"""Optional vocal workflow stubs (Phase 7).

No singing-voice synthesis / stem-to-MIDI vocal models downloaded.
Plans and CIR vocal-role scaffolding only — plug real models later with approval.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.core.config import Settings, get_settings
from backend.app.models.schemas import (
    BriefDocument,
    MusicProject,
    MusicTrack,
    NoteEvent,
    TrackRole,
    new_id,
    utcnow,
)


class VocalPlan(BaseModel):
    """Declarative vocal intent — not rendered audio."""

    id: UUID = Field(default_factory=new_id)
    project_id: UUID | None = None
    mode: str = "stub"  # stub | guide_midi | neural_refused
    style_tags: list[str] = Field(default_factory=list)
    lyric_placeholder: str | None = None
    guide_melody_enabled: bool = True
    target_role: str = TrackRole.VOCAL.value
    bars: int = 8
    notes: list[str] = Field(default_factory=list)
    cir_is_system_of_record: bool = True
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())
    extra: dict[str, Any] = Field(default_factory=dict)


class VocalWorkflow(Protocol):
    name: str
    version: str

    def plan_vocals(
        self,
        project: MusicProject,
        *,
        brief: BriefDocument | None = None,
        lyric_hint: str | None = None,
    ) -> VocalPlan: ...

    def apply_guide_melody(self, project: MusicProject, plan: VocalPlan) -> MusicProject: ...


class StubVocalWorkflow:
    """Honest vocal stub: optional guide-MIDI placeholder track, no synthesis."""

    name = "stub_vocal_workflow"
    version = "0.7.0"

    def plan_vocals(
        self,
        project: MusicProject,
        *,
        brief: BriefDocument | None = None,
        lyric_hint: str | None = None,
    ) -> VocalPlan:
        tags: list[str] = []
        if brief and brief.genre_template_id:
            tags.append(brief.genre_template_id)
        tags.append("guide_melody")
        return VocalPlan(
            project_id=project.id,
            mode="stub",
            style_tags=tags,
            lyric_placeholder=lyric_hint or "[instrumental / vocal TBD]",
            guide_melody_enabled=True,
            bars=project.length_bars,
            notes=[
                "Vocal workflow is a stub — no neural singing / voice cloning.",
                "Guide melody is editable CIR NoteEvents on role=vocal.",
                "Real vocal models require MUSIC_AI_ALLOW_VOCAL_MODEL_DOWNLOAD + install.",
            ],
        )

    def apply_guide_melody(self, project: MusicProject, plan: VocalPlan) -> MusicProject:
        """Add or replace a sparse vocal guide-MIDI track (C major pentatonic-ish)."""
        # Prefer chord root + fifth as a sparse topline placeholder.
        bpm = project.bpm or 110.0
        del bpm
        events: list[NoteEvent] = []
        bpb = 4
        for bar in range(min(plan.bars, project.length_bars)):
            onset = float(bar * bpb)
            # Simple call-response: bar 0,2 → mid; bar 1,3 → higher
            pitch = 72 if bar % 2 == 0 else 76
            events.append(
                NoteEvent(
                    pitch=pitch,
                    onset_beats=onset,
                    duration_beats=1.5,
                    velocity=70,
                    channel=3,
                    articulation="legato",
                    source="vocal_stub:guide",
                )
            )
            events.append(
                NoteEvent(
                    pitch=pitch + 7,
                    onset_beats=onset + 2.0,
                    duration_beats=1.0,
                    velocity=64,
                    channel=3,
                    articulation="legato",
                    source="vocal_stub:guide",
                )
            )
        vocal = MusicTrack(
            role=TrackRole.VOCAL,
            note_events=events,
            tags=["vocal", "guide_melody", "phase7_stub"],
            locked=False,
        )
        # Drop existing unlocked vocal tracks; keep locked ones.
        kept = [
            t
            for t in project.tracks
            if t.role != TrackRole.VOCAL or t.locked
        ]
        project.tracks = [*kept, vocal]
        project.track_ids = [t.id for t in project.tracks]
        project.updated_at = utcnow()
        return project


class OptionalNeuralVocalStub:
    """Refuses neural vocal generation until explicitly approved."""

    name = "optional_neural_vocal"
    version = "stub-0"

    def plan_vocals(
        self,
        project: MusicProject,
        *,
        brief: BriefDocument | None = None,
        lyric_hint: str | None = None,
    ) -> VocalPlan:
        del brief
        raise RuntimeError(
            "Optional neural vocal model refused. Use StubVocalWorkflow for guide MIDI. "
            "Set MUSIC_AI_ALLOW_VOCAL_MODEL_DOWNLOAD=true only after approval — "
            "see docs/audio-models.md#phase-7-research."
        )

    def apply_guide_melody(self, project: MusicProject, plan: VocalPlan) -> MusicProject:
        raise RuntimeError("Optional neural vocal model refused.")


def get_vocal_workflow(
    settings: Settings | None = None,
    *,
    prefer_optional: bool = False,
) -> VocalWorkflow:
    settings = settings or get_settings()
    allow = bool(getattr(settings, "music_ai_allow_vocal_model_download", False))
    mode = getattr(settings, "vocal_workflow", "stub")
    if prefer_optional or mode in ("optional", "neural"):
        if not allow:
            raise RuntimeError(
                "vocal_workflow=optional requires MUSIC_AI_ALLOW_VOCAL_MODEL_DOWNLOAD=true."
            )
        raise RuntimeError(
            "Optional neural vocal model approved via flag but not bundled in this build."
        )
    return StubVocalWorkflow()
