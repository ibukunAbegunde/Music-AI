"""Honest multi-DAW stubs beyond FakeDaw / MidiExport (Phase 7).

These adapters exist so the registry can discover Ableton / Logic / Reaper /
PostFader targets without pretending live control works on Linux CI.
"""

from __future__ import annotations

from typing import Any

from backend.app.daw.base import DawAdapter, DawResult
from backend.app.models.schemas import MusicProject


class _RefuseDawAdapter(DawAdapter):
    """Base for DAW stubs that refuse live operations until probed on-device."""

    name = "refuse"
    daw_label = "Unknown DAW"
    setup_doc = "docs/setup-macos-fl-studio.md"

    def _refuse(self, op: str) -> DawResult:
        return DawResult(
            supported=False,
            attempted=False,
            succeeded=False,
            verified=False,
            error=(
                f"{self.daw_label} adapter is a Phase 7 stub — '{op}' not available. "
                f"Use FakeDawAdapter or MidiExportAdapter in simulation. "
                f"Probe live on the target host; see {self.setup_doc}."
            ),
            user_action_required=(
                f"Install/configure {self.daw_label} on the production host, then "
                "replace this stub with a real adapter after capability probes."
            ),
            observations={
                "adapter": self.name,
                "daw": self.daw_label,
                "phase": 7,
                "stub": True,
            },
        )

    def connect(self) -> DawResult:
        return self._refuse("connect")

    def probe_capabilities(self) -> DawResult:
        caps = {
            "connect": False,
            "read_project": False,
            "create_or_update_notes": False,
            "export_audio": False,
            "live_control": False,
            "stub": True,
        }
        return DawResult(
            supported=False,
            attempted=True,
            succeeded=True,
            verified=True,
            observations={
                "capabilities": caps,
                "adapter": self.name,
                "daw": self.daw_label,
                "mode": "stub_refused",
            },
            user_action_required=f"{self.daw_label} not probed live — stub only.",
        )

    def read_project(self) -> DawResult:
        return self._refuse("read_project")

    def read_tracks(self) -> DawResult:
        return self._refuse("read_tracks")

    def create_or_update_notes(self, project: MusicProject) -> DawResult:
        del project
        return self._refuse("create_or_update_notes")

    def set_tempo(self, bpm: float) -> DawResult:
        del bpm
        return self._refuse("set_tempo")

    def set_track_params(self, track_id: str, params: dict[str, Any]) -> DawResult:
        del track_id, params
        return self._refuse("set_track_params")

    def choose_existing_preset(self, track_id: str, preset: str) -> DawResult:
        del track_id, preset
        return self._refuse("choose_existing_preset")

    def arrange_section(self, section: dict[str, Any]) -> DawResult:
        del section
        return self._refuse("arrange_section")

    def save_snapshot(self, label: str) -> DawResult:
        del label
        return self._refuse("save_snapshot")

    def export_audio_or_request_manual_bounce(self, out_path: str) -> DawResult:
        del out_path
        return self._refuse("export_audio_or_request_manual_bounce")

    def verify_postcondition(self, expected: dict[str, Any]) -> DawResult:
        del expected
        return self._refuse("verify_postcondition")

    def undo_or_restore(self, snapshot_ref: str) -> DawResult:
        del snapshot_ref
        return self._refuse("undo_or_restore")


class AbletonStubAdapter(_RefuseDawAdapter):
    name = "ableton_stub"
    daw_label = "Ableton Live"


class LogicStubAdapter(_RefuseDawAdapter):
    name = "logic_stub"
    daw_label = "Logic Pro"


class ReaperStubAdapter(_RefuseDawAdapter):
    name = "reaper_stub"
    daw_label = "REAPER"


class PostFaderStubAdapter(_RefuseDawAdapter):
    """PostFader / FL Studio stub for environments without a live probe."""

    name = "postfader_stub"
    daw_label = "FL Studio (PostFader)"
    setup_doc = "docs/setup-macos-fl-studio.md"
