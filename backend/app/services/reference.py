"""Phase 2 reference pipeline: import → analyse → separate → transcribe → profile."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from backend.app.audio.analyse import analyse_audio
from backend.app.audio.ingest import (
    import_reference,
    load_reference_asset,
    save_reference_asset,
)
from backend.app.audio.io import load_audio, read_wav
from backend.app.audio.separators import get_separator
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import log_event, setup_logging
from backend.app.models.db import init_db
from backend.app.models.schemas import (
    STEM_TYPE_TO_ROLE,
    BorrowChip,
    BriefDocument,
    LicenseClass,
    MusicTrack,
    NoteEvent,
    ReferenceAsset,
    ReferenceProfile,
    StemAsset,
    StemRoleMapping,
    TrackRole,
    UseMode,
    new_id,
)
from backend.app.music.borrow import normalize_borrow_trait
from backend.app.music.brief import parse_brief
from backend.app.music.midi import track_to_midifile
from backend.app.storage.assets import AssetStore
from backend.app.storage.references import ReferenceRepository
from backend.app.transcription import get_transcriber


@dataclass
class ReferencePipelineResult:
    asset: ReferenceAsset
    profile: ReferenceProfile
    stems: list[StemAsset] = field(default_factory=list)
    transcription_notes: list[NoteEvent] = field(default_factory=list)
    transcription_midi: Path | None = None
    brief_with_borrows: BriefDocument | None = None
    separator_name: str = "simulation"
    transcriber_name: str = "stub"
    simulated: dict[str, bool] = field(default_factory=dict)


def _repo(settings: Settings) -> ReferenceRepository:
    return ReferenceRepository(init_db(settings))


def _default_stem_mappings(stems: list[StemAsset]) -> list[StemRoleMapping]:
    mappings = []
    for s in stems:
        role = STEM_TYPE_TO_ROLE.get(s.stem_type, TrackRole.OTHER)
        mappings.append(
            StemRoleMapping(
                stem_id=s.id,
                stem_type=s.stem_type,
                role=role,
                locked=False,
            )
        )
        s.mapped_role = role
    return mappings


def run_import(
    source: Path,
    *,
    settings: Settings | None = None,
    license_class: str = "unknown",
    permission_notes: str | None = None,
    use_mode: str = "analysis",
) -> ReferenceAsset:
    settings = settings or get_settings()
    settings.ensure_workspace()
    asset = import_reference(
        source,
        settings=settings,
        license_class=LicenseClass(license_class),
        permission_notes=permission_notes,
        use_mode=UseMode(use_mode),
    )
    _repo(settings).save(asset)
    return asset


def run_analyse(
    reference_id: UUID,
    *,
    settings: Settings | None = None,
) -> tuple[ReferenceAsset, ReferenceProfile]:
    settings = settings or get_settings()
    logger = setup_logging(settings.log_level)
    asset = load_reference_asset(reference_id, settings)
    analysis_path = Path(asset.analysis_wav_path or asset.source_uri_or_local_path)
    result = analyse_audio(
        analysis_path,
        reference_id=asset.id,
        prefer_librosa=settings.prefer_librosa,
    )
    profile = result.profile
    asset.feature_profile_id = profile.id
    asset.analysis_status = "analysed"
    asset.duration_sec = len(result.samples) / float(result.sample_rate)
    asset.sample_rate = result.sample_rate
    save_reference_asset(asset, settings)

    assets = AssetStore(settings)
    profile_path = assets.reference_dir(asset.id) / "profile.json"
    profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    _repo(settings).save(asset, profile)
    log_event(
        logger,
        "reference.analysed",
        reference_id=str(asset.id),
        bpm=profile.bpm_estimate,
        key=profile.key_estimate,
    )
    return asset, profile


def run_separate(
    reference_id: UUID,
    *,
    settings: Settings | None = None,
    separator_name: str | None = None,
) -> tuple[ReferenceAsset, list[StemAsset], ReferenceProfile | None]:
    settings = settings or get_settings()
    logger = setup_logging(settings.log_level)
    asset = load_reference_asset(reference_id, settings)
    sep_name = separator_name or settings.music_ai_separator
    separator = get_separator(sep_name)

    analysis_path = Path(asset.analysis_wav_path or asset.source_uri_or_local_path)
    samples, sr, _ = load_audio(analysis_path, target_sr=22050)
    assets = AssetStore(settings)
    out_dir = assets.stems_dir(asset.id)
    stem_set = separator.separate(samples, sr, output_dir=out_dir)

    stems: list[StemAsset] = []
    for sa in stem_set.stems:
        stem_path = out_dir / f"{sa.stem_type}.wav"
        stem = StemAsset(
            id=new_id(),
            reference_id=asset.id,
            stem_type=sa.stem_type,
            file_path=str(stem_path),
            separation_model=stem_set.model,
            separation_version=stem_set.version,
            confidence_or_quality_flags=list(sa.confidence_flags),
            bleed_notes=sa.bleed_notes,
            lineage={
                "simulated": stem_set.simulated,
                "limitations": stem_set.limitations,
            },
        )
        stems.append(stem)

    mappings = _default_stem_mappings(stems)
    asset.stem_ids = [s.id for s in stems]
    asset.stem_role_mappings = mappings
    asset.analysis_status = "separated"
    save_reference_asset(asset, settings)

    stems_meta = out_dir / "stems.json"
    stems_meta.write_text(
        json.dumps([s.model_dump(mode="json") for s in stems], indent=2),
        encoding="utf-8",
    )

    profile = None
    profile_path = assets.reference_dir(asset.id) / "profile.json"
    if profile_path.exists():
        profile = ReferenceProfile.model_validate_json(profile_path.read_text(encoding="utf-8"))
        profile.stem_role_mappings = mappings
        profile.limitations = list(dict.fromkeys([*profile.limitations, *stem_set.limitations]))
        profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        _repo(settings).save(asset, profile)
    else:
        _repo(settings).save(asset)

    log_event(
        logger,
        "reference.separated",
        reference_id=str(asset.id),
        separator=stem_set.model,
        simulated=stem_set.simulated,
        stem_count=len(stems),
    )
    return asset, stems, profile


def _load_stems(reference_id: UUID, settings: Settings) -> list[StemAsset]:
    assets = AssetStore(settings)
    meta = assets.stems_dir(reference_id) / "stems.json"
    if not meta.exists():
        return []
    raw = json.loads(meta.read_text(encoding="utf-8"))
    return [StemAsset.model_validate(x) for x in raw]


def _save_stems(reference_id: UUID, stems: list[StemAsset], settings: Settings) -> None:
    assets = AssetStore(settings)
    meta = assets.stems_dir(reference_id) / "stems.json"
    meta.write_text(
        json.dumps([s.model_dump(mode="json") for s in stems], indent=2),
        encoding="utf-8",
    )


def run_transcribe(
    reference_id: UUID,
    *,
    stem_type: str = "bass",
    settings: Settings | None = None,
    transcriber_name: str | None = None,
    lock_role: bool = False,
) -> tuple[ReferenceAsset, StemAsset, list[NoteEvent], Path | None]:
    settings = settings or get_settings()
    logger = setup_logging(settings.log_level)
    asset = load_reference_asset(reference_id, settings)
    stems = _load_stems(reference_id, settings)
    if not stems:
        raise FileNotFoundError("no stems found — run separate first")

    target = next((s for s in stems if s.stem_type == stem_type), None)
    if target is None:
        raise FileNotFoundError(f"stem type {stem_type!r} not found")

    samples, sr = read_wav(Path(target.file_path))
    assets = AssetStore(settings)
    profile_bpm = 110.0
    profile_path = assets.reference_dir(asset.id) / "profile.json"
    profile = None
    if profile_path.exists():
        profile = ReferenceProfile.model_validate_json(profile_path.read_text(encoding="utf-8"))
        if profile.bpm_estimate:
            profile_bpm = float(profile.bpm_estimate)

    t_name = transcriber_name or settings.music_ai_transcriber
    transcriber = get_transcriber(t_name)
    midi_out = assets.reference_dir(asset.id) / f"transcription_{stem_type}.mid"
    result = transcriber.transcribe(
        samples, sr, bpm=profile_bpm, output_midi=midi_out
    )

    target.note_events = result.notes
    target.transcription_midi_path = str(result.midi_path) if result.midi_path else str(midi_out)
    role = STEM_TYPE_TO_ROLE.get(stem_type, TrackRole.BASS)
    target.mapped_role = role
    target.role_locked = lock_role

    # Update mappings
    mappings = list(asset.stem_role_mappings)
    updated = False
    for m in mappings:
        if m.stem_id == target.id or m.stem_type == stem_type:
            m.locked = lock_role
            m.role = role
            updated = True
    if not updated:
        mappings.append(
            StemRoleMapping(
                stem_id=target.id,
                stem_type=stem_type,
                role=role,
                locked=lock_role,
                lock_reason="user-lock after transcription" if lock_role else None,
            )
        )
    asset.stem_role_mappings = mappings
    asset.analysis_status = "transcribed"
    save_reference_asset(asset, settings)
    _save_stems(reference_id, stems, settings)

    if profile is not None:
        profile.transcription_summary = {
            "stem_type": stem_type,
            "note_count": len(result.notes),
            "model": result.model,
            "simulated": result.simulated,
            "confidence_mean": result.confidence_mean,
            "midi_path": str(result.midi_path) if result.midi_path else None,
        }
        profile.stem_role_mappings = mappings
        profile.limitations = list(
            dict.fromkeys([*profile.limitations, *result.limitations])
        )
        profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        _repo(settings).save(asset, profile)
    else:
        _repo(settings).save(asset)

    log_event(
        logger,
        "reference.transcribed",
        reference_id=str(asset.id),
        stem_type=stem_type,
        notes=len(result.notes),
        simulated=result.simulated,
    )
    return asset, target, result.notes, result.midi_path


def bind_borrow_chips(
    brief: BriefDocument,
    reference_id: UUID,
    traits: list[str],
    *,
    weight: float = 1.0,
) -> BriefDocument:
    """Attach borrow chips for selected reference traits onto a brief.

    Traits are normalized onto the canonical ``BorrowTrait`` set (Phase 2/3
    aliases like ``groove_swing`` → ``groove``). Also backfills
    ``reference_id`` on existing NL-parsed chips that match the selected
    traits but were created without a reference binding.
    """
    normalized = [normalize_borrow_trait(t) for t in traits]
    trait_set = set(normalized)
    chips: list[BorrowChip] = []
    seen: set[str] = set()
    for chip in brief.borrow_chips:
        chip_trait = normalize_borrow_trait(chip.trait)
        if chip_trait != chip.trait:
            chip = chip.model_copy(update={"trait": chip_trait})
        if chip.trait in trait_set and chip.reference_id is None:
            chip = chip.model_copy(update={"reference_id": reference_id})
        chips.append(chip)
        seen.add(chip.trait)
    for trait in normalized:
        if trait in seen:
            # Ensure bound copy exists even if NL chip already present
            if not any(c.trait == trait and c.reference_id == reference_id for c in chips):
                chips.append(
                    BorrowChip(reference_id=reference_id, trait=trait, weight=weight)
                )
            continue
        chips.append(BorrowChip(reference_id=reference_id, trait=trait, weight=weight))
        seen.add(trait)
    brief.borrow_chips = chips
    return brief


def load_profile(reference_id: UUID, settings: Settings | None = None) -> ReferenceProfile:
    settings = settings or get_settings()
    assets = AssetStore(settings)
    path = assets.reference_dir(reference_id) / "profile.json"
    if not path.exists():
        raise FileNotFoundError(f"profile not found for {reference_id} — run analyse first")
    return ReferenceProfile.model_validate_json(path.read_text(encoding="utf-8"))


def run_pipeline(
    source: Path,
    *,
    settings: Settings | None = None,
    license_class: str = "owned",
    use_mode: str = "analysis",
    permission_notes: str | None = None,
    separator_name: str | None = None,
    transcriber_name: str | None = None,
    borrow_traits: list[str] | None = None,
    lock_bass: bool = False,
    prompt_for_brief: str | None = None,
) -> ReferencePipelineResult:
    """Full Phase 2 path: import → analyse → separate → transcribe bass → profile."""
    settings = settings or get_settings()
    settings.ensure_workspace()
    asset = run_import(
        source,
        settings=settings,
        license_class=license_class,
        permission_notes=permission_notes,
        use_mode=use_mode,
    )
    asset, profile = run_analyse(asset.id, settings=settings)
    asset, stems, profile = run_separate(
        asset.id,
        settings=settings,
        separator_name=separator_name,
    )
    if profile is None:
        profile = load_profile(asset.id, settings)

    asset, _bass_stem, notes, midi_path = run_transcribe(
        asset.id,
        stem_type="bass",
        settings=settings,
        transcriber_name=transcriber_name,
        lock_role=lock_bass,
    )
    # refresh profile + stems after transcription
    profile = load_profile(asset.id, settings)
    asset = load_reference_asset(asset.id, settings)
    stems = _load_stems(asset.id, settings)

    brief = None
    traits = borrow_traits or ["bass_bounce", "drums", "groove"]
    if prompt_for_brief:
        brief = parse_brief(prompt_for_brief)
    else:
        brief = BriefDocument(
            title=f"from:{asset.original_filename}",
            free_text="reference pipeline",
            bpm=profile.bpm_estimate,
            key=profile.key_estimate,
        )
    brief = bind_borrow_chips(brief, asset.id, traits)
    assets = AssetStore(settings)
    assets.write_json(
        f"references/{asset.id}/brief_borrows.json",
        brief.model_dump(mode="json"),
    )

    sep = separator_name or settings.music_ai_separator
    tr = transcriber_name or settings.music_ai_transcriber
    return ReferencePipelineResult(
        asset=asset,
        profile=profile,
        stems=stems,
        transcription_notes=notes,
        transcription_midi=midi_path,
        brief_with_borrows=brief,
        separator_name=sep,
        transcriber_name=tr,
        simulated={
            "separator": sep in ("simulation", "fake", "stub", "sim"),
            "transcriber": tr in ("stub", "simulation", "fake", "heuristic"),
            "analysis": True,
        },
    )


def stem_to_music_track(stem: StemAsset, *, locked: bool | None = None) -> MusicTrack:
    """Map a transcribed stem into a CIR MusicTrack (role-lock aware)."""
    role = stem.mapped_role or STEM_TYPE_TO_ROLE.get(stem.stem_type, TrackRole.OTHER)
    return MusicTrack(
        role=role,
        note_events=list(stem.note_events),
        locked=stem.role_locked if locked is None else locked,
        source_reference_id=stem.reference_id,
        source_stem_id=stem.id,
        tags=[stem.stem_type, "from-reference"],
        audio_clips=(
            [{"path": stem.file_path, "kind": "stem"}] if stem.file_path else []
        ),
    )


def export_transcription_track_midi(
    notes: list[NoteEvent],
    *,
    bpm: float,
    path: Path,
    role: TrackRole = TrackRole.BASS,
) -> Path:
    track = MusicTrack(role=role, note_events=notes)
    mid = track_to_midifile(track, bpm=bpm)
    path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(path))
    return path
