"""Reference analysis adapter interfaces + Phase 2 fixture stubs.

Phase 2 will replace ``FixtureReferenceAnalyzer`` with real import → analyse →
stem → profile wiring. Phase 3 only needs a ``ReferenceProfile`` (+ optional
asset metadata) and borrow-chip binding — keep schemas stable so Phase 2 can
drop in without rewriting conditioning.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from backend.app.models.schemas import (
    BorrowChip,
    GrooveFeatures,
    LicenseClass,
    ReferenceAsset,
    ReferenceProfile,
    UseMode,
    utcnow,
)

# Canonical vocab = Phase 2 ``BorrowTrait`` values. Legacy Phase 3 aliases
# (chord_feel / groove_swing / energy_curve) normalize onto these.
KNOWN_BORROW_TRAITS = frozenset(
    {
        "bass_bounce",
        "drums",
        "percussion_texture",
        "atmosphere",
        "chords",
        "arrangement",
        "bass_rhythm",
        "groove",
        "energy",
    }
)

# Map free-form / legacy chip names → BorrowTrait values.
TRAIT_ALIASES: dict[str, str] = {
    "bass": "bass_bounce",
    "bass_feel": "bass_bounce",
    "percussion": "percussion_texture",
    "perc": "percussion_texture",
    "pads": "atmosphere",
    "space": "atmosphere",
    "pad": "atmosphere",
    "chord_feel": "chords",
    "harmony": "chords",
    "rhodes": "chords",
    "keys": "chords",
    "groove_swing": "groove",
    "swing": "groove",
    "energy_curve": "energy",
}


class ReferenceAnalyzer(Protocol):
    """Phase 2 fills this; Phase 3 only calls ``analyse`` / ``get_profile``."""

    def ingest(
        self,
        path: Path | str,
        *,
        license_class: LicenseClass = LicenseClass.UNKNOWN,
        use_mode: UseMode = UseMode.ANALYSIS,
    ) -> ReferenceAsset: ...

    def analyse(self, reference_id: UUID) -> ReferenceProfile: ...

    def get_profile(self, reference_id: UUID) -> ReferenceProfile | None: ...

    def get_asset(self, reference_id: UUID) -> ReferenceAsset | None: ...


def bind_borrow_chips(
    profile: ReferenceProfile,
    traits: list[str],
    *,
    reference_id: UUID | None = None,
    weight: float = 0.85,
) -> list[BorrowChip]:
    """Map selected abstract traits onto brief borrow chips (no audio copy)."""
    chips: list[BorrowChip] = []
    for trait in traits:
        t = trait.strip().lower().replace(" ", "_").replace("-", "_")
        t = TRAIT_ALIASES.get(t, t)
        chips.append(
            BorrowChip(
                reference_id=reference_id or profile.id,
                trait=t,
                weight=weight,
            )
        )
    return chips


def afrobeats_fixture_profile(*, profile_id: UUID | None = None) -> ReferenceProfile:
    """Synthetic Afrobeats-like profile — stand-in until Phase 2 analysis exists."""
    return ReferenceProfile(
        id=profile_id or uuid4(),
        bpm_estimate=110.0,
        bpm_confidence=0.82,
        meter="4/4",
        beat_times=[float(i) * (60.0 / 110.0) for i in range(32)],
        key_estimate="A minor",
        key_confidence=0.7,
        chords=[
            {"bar": 1, "label": "Am", "confidence": 0.65},
            {"bar": 2, "label": "F", "confidence": 0.6},
            {"bar": 3, "label": "C", "confidence": 0.62},
            {"bar": 4, "label": "G", "confidence": 0.58},
        ],
        sections=[
            {"label": "intro", "start": 0.0, "end": 8.0, "confidence": 0.5},
            {"label": "groove", "start": 8.0, "end": 32.0, "confidence": 0.55},
        ],
        energy_curve=[0.4, 0.45, 0.5, 0.55, 0.6, 0.58, 0.62, 0.65],
        timbre_tags=["warm", "percussive", "bass-forward"],
        genre_hypotheses=["afrobeats", "amapiano"],
        instrumentation_hypotheses=["drums", "bass", "keys", "perc"],
        groove_features=GrooveFeatures(
            onset_grid=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
            microtiming_offsets=[-8.0, 5.0, -3.0, 10.0],
            syncopation=0.62,
            swing_estimate=0.18,
        ),
        bass_features={
            "register": "low",
            "contour": "bouncy",
            "offbeat_bias": 0.55,
            "note_density_per_bar": 2.5,
            "typical_durations": [1.5, 0.75, 0.5],
        },
        mix_metrics={"estimated_lufs": -11.5, "stereo_width": 0.55},
        analyst_versions={"fixture": "phase3-stub-0.1", "phase2_status": "pending"},
    )


def trap_fixture_profile(*, profile_id: UUID | None = None) -> ReferenceProfile:
    return ReferenceProfile(
        id=profile_id or uuid4(),
        bpm_estimate=140.0,
        bpm_confidence=0.88,
        meter="4/4",
        key_estimate="C minor",
        key_confidence=0.75,
        energy_curve=[0.55, 0.6, 0.7, 0.75, 0.8, 0.78, 0.85, 0.9],
        timbre_tags=["dark", "808", "hat-rolls"],
        genre_hypotheses=["trap", "drill"],
        instrumentation_hypotheses=["drums", "bass", "pad"],
        groove_features=GrooveFeatures(
            onset_grid=[0.0, 0.25, 0.5, 0.75, 1.0],
            microtiming_offsets=[0.0, 2.0, -1.0],
            syncopation=0.4,
            swing_estimate=0.05,
        ),
        bass_features={
            "register": "sub",
            "contour": "sustained",
            "offbeat_bias": 0.15,
            "note_density_per_bar": 1.5,
            "typical_durations": [3.5, 0.1],
        },
        mix_metrics={"estimated_lufs": -9.0},
        analyst_versions={"fixture": "phase3-stub-0.1", "phase2_status": "pending"},
    )


FIXTURE_LIBRARY = {
    "afrobeats": afrobeats_fixture_profile,
    "amapiano": afrobeats_fixture_profile,
    "trap": trap_fixture_profile,
    "drill": trap_fixture_profile,
}


def load_fixture_profile(name: str = "afrobeats") -> ReferenceProfile:
    key = name.lower().strip()
    factory = FIXTURE_LIBRARY.get(key, afrobeats_fixture_profile)
    return factory()


class FixtureReferenceAnalyzer:
    """In-memory stub analyzer — no DSP. Phase 2 replaces this implementation."""

    def __init__(self) -> None:
        self._assets: dict[UUID, ReferenceAsset] = {}
        self._profiles: dict[UUID, ReferenceProfile] = {}

    def ingest(
        self,
        path: Path | str,
        *,
        license_class: LicenseClass = LicenseClass.UNKNOWN,
        use_mode: UseMode = UseMode.ANALYSIS,
        fixture_genre: str | None = None,
    ) -> ReferenceAsset:
        p = Path(path)
        digest = hashlib.sha256(p.name.encode("utf-8")).hexdigest()
        if p.exists() and p.is_file():
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
        asset = ReferenceAsset(
            original_filename=p.name,
            immutable_sha256=digest,
            source_uri_or_local_path=str(p.resolve()) if p.exists() else str(p),
            license_class=license_class,
            use_mode=use_mode,
            analysis_status="pending",
            lineage={
                "analyzer": "FixtureReferenceAnalyzer",
                "fixture_genre": fixture_genre or "afrobeats",
                "phase2_dependency": True,
            },
            imported_at=utcnow(),
        )
        self._assets[asset.id] = asset
        return asset

    def analyse(self, reference_id: UUID) -> ReferenceProfile:
        asset = self._assets.get(reference_id)
        if asset is None:
            raise KeyError(f"unknown reference {reference_id}")
        genre = (asset.lineage or {}).get("fixture_genre", "afrobeats")
        profile = load_fixture_profile(str(genre))
        # Stable id linked to asset for borrow chips
        profile = profile.model_copy(update={"id": uuid4()})
        asset.feature_profile_id = profile.id
        asset.analysis_status = "fixture_complete"
        self._assets[reference_id] = asset
        self._profiles[reference_id] = profile
        self._profiles[profile.id] = profile
        return profile

    def get_profile(self, reference_id: UUID) -> ReferenceProfile | None:
        return self._profiles.get(reference_id)

    def get_asset(self, reference_id: UUID) -> ReferenceAsset | None:
        return self._assets.get(reference_id)

    def register_fixture(
        self,
        *,
        name: str = "fixture-ref.wav",
        genre: str = "afrobeats",
        license_class: LicenseClass = LicenseClass.OWNED,
    ) -> tuple[ReferenceAsset, ReferenceProfile]:
        """Convenience: ingest + analyse a named fixture without a real file."""
        asset = self.ingest(
            Path(f"/fixture/{name}"),
            license_class=license_class,
            use_mode=UseMode.ANALYSIS,
            fixture_genre=genre,
        )
        profile = self.analyse(asset.id)
        return asset, profile
