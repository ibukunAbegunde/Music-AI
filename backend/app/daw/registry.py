"""Multi-DAW adapter registry (Phase 7) — discover + construct by name."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.app.core.config import DawMode, Settings, get_settings
from backend.app.daw.base import DawAdapter
from backend.app.daw.fake import FakeDawAdapter
from backend.app.daw.midi_fallback import MidiExportAdapter
from backend.app.daw.stubs import (
    AbletonStubAdapter,
    LogicStubAdapter,
    PostFaderStubAdapter,
    ReaperStubAdapter,
)
from backend.app.storage.assets import AssetStore

AdapterFactory = Callable[[Settings], DawAdapter]


def _fake(_settings: Settings) -> DawAdapter:
    return FakeDawAdapter()


def _midi(settings: Settings) -> DawAdapter:
    return MidiExportAdapter(AssetStore(settings))


def _ableton(_settings: Settings) -> DawAdapter:
    return AbletonStubAdapter()


def _logic(_settings: Settings) -> DawAdapter:
    return LogicStubAdapter()


def _reaper(_settings: Settings) -> DawAdapter:
    return ReaperStubAdapter()


def _postfader(_settings: Settings) -> DawAdapter:
    return PostFaderStubAdapter()


_REGISTRY: dict[str, dict[str, Any]] = {
    "fake": {
        "factory": _fake,
        "live": False,
        "description": "In-memory FakeDaw for CI / simulation",
    },
    "simulation": {
        "factory": _fake,
        "live": False,
        "description": "Alias for FakeDaw (DAW_MODE=simulation)",
    },
    "midi_export": {
        "factory": _midi,
        "live": False,
        "description": "Standard MIDI file export + manual import",
    },
    "ableton": {
        "factory": _ableton,
        "live": False,
        "description": "Ableton Live stub — refuses until real adapter lands",
    },
    "ableton_stub": {
        "factory": _ableton,
        "live": False,
        "description": "Ableton Live stub",
    },
    "logic": {
        "factory": _logic,
        "live": False,
        "description": "Logic Pro stub — refuses until real adapter lands",
    },
    "logic_stub": {
        "factory": _logic,
        "live": False,
        "description": "Logic Pro stub",
    },
    "reaper": {
        "factory": _reaper,
        "live": False,
        "description": "REAPER stub — refuses until real adapter lands",
    },
    "reaper_stub": {
        "factory": _reaper,
        "live": False,
        "description": "REAPER stub",
    },
    "postfader": {
        "factory": _postfader,
        "live": False,
        "description": "PostFader/FL stub when not probed live (Linux CI)",
    },
    "postfader_stub": {
        "factory": _postfader,
        "live": False,
        "description": "PostFader/FL stub",
    },
}


def list_daw_adapters() -> list[dict[str, Any]]:
    return [
        {
            "id": key,
            "live": meta["live"],
            "description": meta["description"],
        }
        for key, meta in sorted(_REGISTRY.items())
    ]


def get_daw_adapter(
    name: str | None = None,
    *,
    settings: Settings | None = None,
) -> DawAdapter:
    """Resolve a DAW adapter by registry name or Settings.daw_mode."""
    settings = settings or get_settings()
    key = (name or settings.daw_mode.value).lower().strip()
    if key not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Unknown DAW adapter {name!r}. Known: {known}")
    return _REGISTRY[key]["factory"](settings)


def adapter_for_settings(settings: Settings | None = None) -> DawAdapter:
    """Back-compat helper used by compose / CLI."""
    settings = settings or get_settings()
    if settings.daw_mode == DawMode.MIDI_EXPORT:
        return get_daw_adapter("midi_export", settings=settings)
    if settings.daw_mode == DawMode.POSTFADER:
        # Honest stub on CI; live Mac will replace once probed.
        return get_daw_adapter("postfader", settings=settings)
    return get_daw_adapter("fake", settings=settings)
