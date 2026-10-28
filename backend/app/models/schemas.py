"""Versioned Pydantic domain contracts (spec §4)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> UUID:
    return uuid4()


class LicenseClass(str, Enum):
    OWNED = "owned"
    LICENSED = "licensed"
    UNKNOWN = "unknown"


class UseMode(str, Enum):
    INSPIRATION = "inspiration"
    ANALYSIS = "analysis"
    DIRECT_SAMPLE = "direct-sample"


class TrackRole(str, Enum):
    KICK = "kick"
    SNARE = "snare"
    HAT = "hat"
    PERCUSSION = "percussion"
    BASS = "bass"
    CHORD = "chord"
    LEAD = "lead"
    PAD = "pad"
    FX = "fx"
    VOCAL = "vocal"
    OTHER = "other"
    DRUMS = "drums"


class ProjectStatus(str, Enum):
    CREATED = "CREATED"
    PLANNED = "PLANNED"
    ANALYSING = "ANALYSING"
    COMPOSING = "COMPOSING"
    APPLYING = "APPLYING"
    VERIFYING = "VERIFYING"
    RENDER_PENDING = "RENDER_PENDING"
    EVALUATING = "EVALUATING"
    AWAITING_FEEDBACK = "AWAITING_FEEDBACK"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


class RightsPolicy(BaseModel):
    allow_direct_sample: bool = False
    require_license_ack: bool = True
    notes: str | None = None


class AutonomyPolicy(BaseModel):
    mode: str = "collaborative"  # suggest-only | collaborative | autonomous
    max_generations: int = 4
    max_renders: int = 4
    require_approval_for_writes: bool = True


class NoteEvent(BaseModel):
    pitch: int = Field(ge=0, le=127)
    onset_beats: float = Field(ge=0)
    duration_beats: float = Field(gt=0)
    velocity: int = Field(ge=1, le=127)
    channel: int = Field(default=0, ge=0, le=15)
    articulation: str | None = None
    cents_bend: float | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str | None = None


class DrumEvent(BaseModel):
    instrument_role: str
    onset_beats: float = Field(ge=0)
    velocity: int = Field(ge=1, le=127)
    duration_beats: float | None = Field(default=0.25, gt=0)
    microtiming_ms: float = 0.0
    sample_id: str | None = None


class MusicTrack(BaseModel):
    id: UUID = Field(default_factory=new_id)
    role: TrackRole
    note_events: list[NoteEvent] = Field(default_factory=list)
    drum_events: list[DrumEvent] = Field(default_factory=list)
    audio_clips: list[dict[str, Any]] = Field(default_factory=list)
    instrument_asset_id: UUID | None = None
    mixer_slot: int | None = None
    enabled: bool = True
    locked: bool = False
    source_reference_id: UUID | None = None
    tags: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class Section(BaseModel):
    id: UUID = Field(default_factory=new_id)
    name: str
    start_bar: int = Field(ge=1)
    end_bar: int = Field(ge=1)
    intensity_target: float = Field(default=0.5, ge=0, le=1)
    active_track_ids: list[UUID] = Field(default_factory=list)
    transition_notes: str | None = None

    @field_validator("end_bar")
    @classmethod
    def end_after_start(cls, v: int, info: Any) -> int:
        start = info.data.get("start_bar")
        if start is not None and v < start:
            raise ValueError("end_bar must be >= start_bar")
        return v


class MusicProject(BaseModel):
    id: UUID = Field(default_factory=new_id)
    name: str
    owner: str = "local-user"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    bpm: float = Field(default=110.0, gt=0)
    meter: str = "4/4"
    key_estimate: str | None = None
    key_confidence: float | None = Field(default=None, ge=0, le=1)
    tonal_mode: str | None = None
    length_bars: int = Field(default=8, ge=1)
    reference_ids: list[UUID] = Field(default_factory=list)
    track_ids: list[UUID] = Field(default_factory=list)
    section_ids: list[UUID] = Field(default_factory=list)
    tracks: list[MusicTrack] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    generation_brief: str | None = None
    daw_type: str = "fl_studio"
    daw_path: str | None = None
    version_id: UUID | None = None
    status: ProjectStatus = ProjectStatus.CREATED
    rights_policy: RightsPolicy = Field(default_factory=RightsPolicy)
    autonomy_policy: AutonomyPolicy = Field(default_factory=AutonomyPolicy)
    seed: int | None = None
    schema_version: str = "0.1.0"


class ReferenceAsset(BaseModel):
    id: UUID = Field(default_factory=new_id)
    original_filename: str
    immutable_sha256: str
    source_uri_or_local_path: str
    license_class: LicenseClass = LicenseClass.UNKNOWN
    permission_notes: str | None = None
    use_mode: UseMode = UseMode.ANALYSIS
    imported_at: datetime = Field(default_factory=utcnow)
    duration_sec: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    analysis_status: str = "pending"
    stem_ids: list[UUID] = Field(default_factory=list)
    feature_profile_id: UUID | None = None
    embedding_ids: list[UUID] = Field(default_factory=list)
    lineage: dict[str, Any] = Field(default_factory=dict)


class GrooveFeatures(BaseModel):
    onset_grid: list[float] = Field(default_factory=list)
    microtiming_offsets: list[float] = Field(default_factory=list)
    syncopation: float | None = None
    swing_estimate: float | None = None


class ReferenceProfile(BaseModel):
    id: UUID = Field(default_factory=new_id)
    bpm_estimate: float | None = None
    bpm_confidence: float | None = None
    meter: str | None = None
    beat_times: list[float] = Field(default_factory=list)
    key_estimate: str | None = None
    key_confidence: float | None = None
    chords: list[dict[str, Any]] = Field(default_factory=list)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    energy_curve: list[float] = Field(default_factory=list)
    timbre_tags: list[str] = Field(default_factory=list)
    genre_hypotheses: list[str] = Field(default_factory=list)
    instrumentation_hypotheses: list[str] = Field(default_factory=list)
    groove_features: GrooveFeatures = Field(default_factory=GrooveFeatures)
    bass_features: dict[str, Any] = Field(default_factory=dict)
    mix_metrics: dict[str, Any] = Field(default_factory=dict)
    embedding_refs: list[UUID] = Field(default_factory=list)
    analyst_versions: dict[str, str] = Field(default_factory=dict)


class StemAsset(BaseModel):
    id: UUID = Field(default_factory=new_id)
    reference_id: UUID
    stem_type: str
    file_path: str
    separation_model: str | None = None
    separation_version: str | None = None
    confidence_or_quality_flags: list[str] = Field(default_factory=list)
    bleed_notes: str | None = None
    original_mix_start_time: float = 0.0
    lineage: dict[str, Any] = Field(default_factory=dict)


class ProductionPlan(BaseModel):
    id: UUID = Field(default_factory=new_id)
    project_id: UUID
    user_goal: str
    target_features: dict[str, Any] = Field(default_factory=dict)
    reference_features_to_keep: list[str] = Field(default_factory=list)
    new_features: list[str] = Field(default_factory=list)
    proposed_operations: list[dict[str, Any]] = Field(default_factory=list)
    acceptance_checks: list[str] = Field(default_factory=list)
    estimated_cost: dict[str, Any] = Field(default_factory=dict)
    approvals_required: list[str] = Field(default_factory=list)
    status: str = "draft"


class DawOperation(BaseModel):
    operation_id: UUID = Field(default_factory=new_id)
    action_type: str
    target_track_id: UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    prerequisite_state: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    expected_postcondition: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "low"
    requires_approval: bool = True
    observed_result: dict[str, Any] | None = None
    verification_status: str = "pending"
    rollback_reference: str | None = None


class Render(BaseModel):
    id: UUID = Field(default_factory=new_id)
    project_id: UUID
    version_id: UUID
    audio_path: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    render_settings: dict[str, Any] = Field(default_factory=dict)
    duration: float | None = None
    analysed_metrics: dict[str, Any] = Field(default_factory=dict)
    reference_similarity: float | None = None
    listening_status: str = "pending"


class PreferenceComparison(BaseModel):
    id: UUID = Field(default_factory=new_id)
    context: dict[str, Any] = Field(default_factory=dict)
    render_a_id: UUID
    render_b_id: UUID
    user_choice: str  # a | b | tie | skip
    optional_reason: str | None = None
    tags: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utcnow)
    confidence: float | None = None
    blind_status: bool = True


class Evaluation(BaseModel):
    id: UUID = Field(default_factory=new_id)
    render_id: UUID
    metric_name: str
    value: float
    uncertainty: float | None = None
    evaluator_name: str
    evaluator_version: str = "0.1.0"
    explanation: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    human_override: float | None = None


class ProjectVersion(BaseModel):
    id: UUID = Field(default_factory=new_id)
    parent_version_id: UUID | None = None
    daw_snapshot_path: str | None = None
    canonical_project_snapshot: dict[str, Any] = Field(default_factory=dict)
    exported_midi_paths: list[str] = Field(default_factory=list)
    rendered_audio_path: str | None = None
    operation_ids: list[UUID] = Field(default_factory=list)
    user_message: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    restorable: bool = True


class AssetManifest(BaseModel):
    id: UUID = Field(default_factory=new_id)
    name: str
    type: str
    vst_identifier: str | None = None
    preset_identifier: str | None = None
    path: str | None = None
    role_tags: list[str] = Field(default_factory=list)
    genre_tags: list[str] = Field(default_factory=list)
    compatible_host: str | None = None
    licensing: str | None = None
    sample_preview_path: str | None = None
    sample_rate: int | None = None
    installed_verified: bool = False
