"""Abstract DAW adapter contract (spec §9)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from backend.app.models.schemas import MusicProject


@dataclass
class DawResult:
    supported: bool
    attempted: bool
    succeeded: bool
    verified: bool
    observations: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    user_action_required: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "verified": self.verified,
            "observations": self.observations,
            "error": self.error,
            "user_action_required": self.user_action_required,
        }


class DawAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def connect(self) -> DawResult: ...

    @abstractmethod
    def probe_capabilities(self) -> DawResult: ...

    @abstractmethod
    def read_project(self) -> DawResult: ...

    @abstractmethod
    def read_tracks(self) -> DawResult: ...

    @abstractmethod
    def create_or_update_notes(self, project: MusicProject) -> DawResult: ...

    @abstractmethod
    def set_tempo(self, bpm: float) -> DawResult: ...

    @abstractmethod
    def set_track_params(self, track_id: str, params: dict[str, Any]) -> DawResult: ...

    @abstractmethod
    def choose_existing_preset(self, track_id: str, preset: str) -> DawResult: ...

    @abstractmethod
    def arrange_section(self, section: dict[str, Any]) -> DawResult: ...

    @abstractmethod
    def save_snapshot(self, label: str) -> DawResult: ...

    @abstractmethod
    def export_audio_or_request_manual_bounce(self, out_path: str) -> DawResult: ...

    @abstractmethod
    def verify_postcondition(self, expected: dict[str, Any]) -> DawResult: ...

    @abstractmethod
    def undo_or_restore(self, snapshot_ref: str) -> DawResult: ...
