"""Versioned Pydantic domain contracts (spec §4)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


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


class BorrowTrait(str, Enum):
    """Selectable reference traits for brief borrow chips (v1.1)."""

    BASS_BOUNCE = "bass_bounce"
    DRUMS = "drums"
    PERCUSSION_TEXTURE = "percussion_texture"
    ATMOSPHERE = "atmosphere"
    CHORDS = "chords"
    ARRANGEMENT = "arrangement"
    BASS_RHYTHM = "bass_rhythm"
    GROOVE = "groove"
    ENERGY = "energy"


# Default stem_type → TrackRole mapping for stem→role UX
STEM_TYPE_TO_ROLE: dict[str, TrackRole] = {
    "vocals": TrackRole.VOCAL,
    "drums": TrackRole.DRUMS,
    "bass": TrackRole.BASS,
    "other": TrackRole.OTHER,
}


class StemRoleMapping(BaseModel):
    """Stem → track role (+ optional role-lock) for Phase 2 UX."""

    stem_id: UUID
    stem_type: str
    role: TrackRole
    locked: bool = False
    lock_reason: str | None = None


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
    mode: str = "collaborative"  # suggest-only | collaborative | autonomous — collaborative is default
    max_generations: int = 4
    max_renders: int = 4
    require_approval_for_writes: bool = True
    scratch_or_release: str = "scratch"  # scratch | release


class BarRange(BaseModel):
    start_bar: int = Field(ge=1)
    end_bar: int = Field(ge=1)


class BorrowChip(BaseModel):
    reference_id: UUID | None = None
    trait: str  # prefer BorrowTrait values; free-form allowed for forward compat
    weight: float = Field(default=1.0, ge=0, le=1)


class EnergyPoint(BaseModel):
    bar: int = Field(ge=1)
    value: float = Field(ge=0, le=1)


class SectionDraft(BaseModel):
    name: str
    start_bar: int = Field(ge=1)
    end_bar: int = Field(ge=1)
    intensity_target: float = Field(default=0.5, ge=0, le=1)


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
    locked_bar_ranges: list[BarRange] = Field(default_factory=list)
    source_reference_id: UUID | None = None
    source_stem_id: UUID | None = None
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
    genre_template_id: str | None = None
    daw_type: str = "fl_studio"
    daw_path: str | None = None
    version_id: UUID | None = None
    status: ProjectStatus = ProjectStatus.CREATED
    rights_policy: RightsPolicy = Field(default_factory=RightsPolicy)
    autonomy_policy: AutonomyPolicy = Field(default_factory=AutonomyPolicy)
    seed: int | None = None
    brief_id: UUID | None = None
    recipe_id: UUID | None = None
    schema_version: str = "0.2.0"


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
    analysis_status: str = "pending"  # pending | analysed | separated | transcribed | failed
    stem_ids: list[UUID] = Field(default_factory=list)
    feature_profile_id: UUID | None = None
    embedding_ids: list[UUID] = Field(default_factory=list)
    lineage: dict[str, Any] = Field(default_factory=dict)
    analysis_wav_path: str | None = None
    available_borrow_traits: list[str] = Field(default_factory=list)
    stem_role_mappings: list[StemRoleMapping] = Field(default_factory=list)
    schema_version: str = "0.3.0"


class GrooveFeatures(BaseModel):
    onset_grid: list[float] = Field(default_factory=list)
    microtiming_offsets: list[float] = Field(default_factory=list)
    syncopation: float | None = None
    swing_estimate: float | None = None
    onset_density: float | None = None
    beat_strength: float | None = None


class ReferenceProfile(BaseModel):
    id: UUID = Field(default_factory=new_id)
    reference_id: UUID | None = None
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
    available_borrow_traits: list[str] = Field(default_factory=list)
    stem_role_mappings: list[StemRoleMapping] = Field(default_factory=list)
    transcription_summary: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    is_estimate: bool = True  # all Phase 2 DSP outputs are marked estimates


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
    mapped_role: TrackRole | None = None
    role_locked: bool = False
    transcription_midi_path: str | None = None
    note_events: list[NoteEvent] = Field(default_factory=list)


class BriefDocument(BaseModel):
    """Constraint-first creative brief (canvas source of truth)."""

    id: UUID = Field(default_factory=new_id)
    project_id: UUID | None = None
    title: str = "untitled brief"
    free_text: str = ""
    bpm: float | None = Field(default=None, gt=0)
    bpm_range: tuple[float, float] | None = None
    key: str | None = None
    meter: str = "4/4"
    genre_template_id: str | None = None
    energy_curve: list[EnergyPoint] = Field(default_factory=list)
    borrow_chips: list[BorrowChip] = Field(default_factory=list)
    section_map: list[SectionDraft] = Field(default_factory=list)
    novelty: float = Field(default=0.4, ge=0, le=1)
    length_bars: int = Field(default=8, ge=1)
    locked_roles: list[str] = Field(default_factory=list)
    recipe_id: UUID | None = None
    scratch_or_release: str = "scratch"
    autonomy_mode: str = "collaborative"
    seed: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class GenreTemplate(BaseModel):
    id: str
    name: str
    default_bpm: float
    bpm_range: tuple[float, float]
    typical_key_modes: list[str] = Field(default_factory=list)
    section_map: list[SectionDraft] = Field(default_factory=list)
    role_defaults: list[str] = Field(default_factory=list)
    groove_density: float = Field(default=0.5, ge=0, le=1)
    progression_key: str = "default"
    notes: str | None = None


class Recipe(BaseModel):
    id: UUID = Field(default_factory=new_id)
    name: str
    genre_tags: list[str] = Field(default_factory=list)
    groove_fingerprint: dict[str, Any] = Field(default_factory=dict)
    palette_asset_ids: list[UUID] = Field(default_factory=list)
    arrangement_skeleton: list[SectionDraft] = Field(default_factory=list)
    locked_roles: list[str] = Field(default_factory=list)
    brief_snapshot: dict[str, Any] = Field(default_factory=dict)
    cir_snapshot_ref: str | None = None
    source_project_id: UUID | None = None
    approved: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class ProductionPlan(BaseModel):
    id: UUID = Field(default_factory=new_id)
    project_id: UUID
    brief_id: UUID | None = None
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
    target_role: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    prerequisite_state: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    expected_postcondition: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "low"
    requires_approval: bool = True
    predicted_impact: str | None = None
    explanation: str | None = None
    observed_result: dict[str, Any] | None = None
    verification_status: str = "pending"
    rollback_reference: str | None = None


# Alias: critic emits PatchOps ≡ DawOperation
PatchOp = DawOperation


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


class LoudnessNotes(BaseModel):
    target_lufs: float | None = -14.0
    measured_lufs: float | None = None
    normalization_status: str = "pending"  # pending | applied | manual_required | n/a


class MusicalDiff(BaseModel):
    id: UUID = Field(default_factory=new_id)
    from_version_id: UUID | None = None
    to_version_id: UUID | None = None
    roles_changed: list[str] = Field(default_factory=list)
    note_count_delta_by_role: dict[str, int] = Field(default_factory=dict)
    density_delta: float = 0.0
    harmony_delta_notes: list[str] = Field(default_factory=list)
    groove_delta_notes: list[str] = Field(default_factory=list)
    locked_roles_respected: bool = True
    one_line_summary: str = ""
    details: list[str] = Field(default_factory=list)


class CandidatePackage(BaseModel):
    id: UUID = Field(default_factory=new_id)
    project_id: UUID
    version_id: UUID
    seed: int
    cir_snapshot_ref: str
    midi_paths: list[str] = Field(default_factory=list)
    render_id: UUID | None = None
    loudness_notes: LoudnessNotes = Field(default_factory=LoudnessNotes)
    one_line_diff: str = ""
    musical_diff_id: UUID | None = None
    parent_version_id: UUID | None = None


class ProjectVersion(BaseModel):
    id: UUID = Field(default_factory=new_id)
    parent_version_id: UUID | None = None
    daw_snapshot_path: str | None = None
    canonical_project_snapshot: dict[str, Any] = Field(default_factory=dict)
    exported_midi_paths: list[str] = Field(default_factory=list)
    rendered_audio_path: str | None = None
    operation_ids: list[UUID] = Field(default_factory=list)
    user_message: str | None = None
    one_line_diff: str | None = None
    musical_diff: MusicalDiff | None = None
    recipe_id: UUID | None = None
    created_at: datetime = Field(default_factory=utcnow)
    restorable: bool = True


class ListeningJournalEntry(BaseModel):
    id: UUID = Field(default_factory=new_id)
    project_id: UUID
    version_id: UUID | None = None
    notes: str = ""
    tags: list[str] = Field(default_factory=list)
    rating: float | None = Field(default=None, ge=0, le=5)
    created_at: datetime = Field(default_factory=utcnow)


class AuditionRequest(BaseModel):
    """Stub: loudness-matched in-loop sound audition (Phase 3+ wiring)."""

    id: UUID = Field(default_factory=new_id)
    asset_ids: list[UUID] = Field(default_factory=list)
    context_project_version_id: UUID | None = None
    loudness_match: bool = True
    in_loop_context: bool = True


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
