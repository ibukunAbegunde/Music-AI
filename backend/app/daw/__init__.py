"""DAW adapter interfaces and implementations."""

from backend.app.daw.base import DawAdapter, DawResult
from backend.app.daw.fake import FakeDawAdapter
from backend.app.daw.midi_fallback import MidiExportAdapter
from backend.app.daw.registry import adapter_for_settings, get_daw_adapter, list_daw_adapters
from backend.app.daw.stubs import (
    AbletonStubAdapter,
    LogicStubAdapter,
    PostFaderStubAdapter,
    ReaperStubAdapter,
)

__all__ = [
    "AbletonStubAdapter",
    "DawAdapter",
    "DawResult",
    "FakeDawAdapter",
    "LogicStubAdapter",
    "MidiExportAdapter",
    "PostFaderStubAdapter",
    "ReaperStubAdapter",
    "adapter_for_settings",
    "get_daw_adapter",
    "list_daw_adapters",
]
