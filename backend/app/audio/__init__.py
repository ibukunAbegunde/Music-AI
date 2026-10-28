"""Audio ingestion, analysis, stem separation, and reference adapters."""

from backend.app.audio.analyse import analyse_audio
from backend.app.audio.ingest import import_reference
from backend.app.audio.reference import (
    FixtureReferenceAnalyzer,
    ReferenceAnalyzer,
    bind_borrow_chips,
    load_fixture_profile,
)
from backend.app.audio.separators import get_separator

__all__ = [
    "FixtureReferenceAnalyzer",
    "ReferenceAnalyzer",
    "analyse_audio",
    "bind_borrow_chips",
    "get_separator",
    "import_reference",
    "load_fixture_profile",
]
