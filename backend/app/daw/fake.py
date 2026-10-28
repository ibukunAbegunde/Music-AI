"""In-memory FakeDawAdapter for CI / simulation mode."""

from __future__ import annotations

import copy
from typing import Any
from uuid import uuid4

from backend.app.daw.base import DawAdapter, DawResult
from backend.app.models.schemas import MusicProject


class FakeDawAdapter(DawAdapter):
    name = "fake"

    def __init__(self) -> None:
        self.connected = False
        self.bpm: float = 120.0
        self.project: MusicProject | None = None
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.track_params: dict[str, dict[str, Any]] = {}
        self.presets: dict[str, str] = {}
        self.sections: list[dict[str, Any]] = []
        self.last_export: str | None = None

    def connect(self) -> DawResult:
        self.connected = True
        return DawResult(
            supported=True,
            attempted=True,
            succeeded=True,
            verified=True,
            observations={"adapter": self.name, "connected": True},
        )

    def probe_capabilities(self) -> DawResult:
        caps = {
            "connect": True,
            "read_project": True,
            "read_tracks": True,
            "create_or_update_notes": True,
            "set_tempo": True,
            "set_track_params": True,
            "choose_existing_preset": True,
            "arrange_section": True,
            "save_snapshot": True,
            "export_audio": False,  # simulated bounce only
            "verify_postcondition": True,
            "undo_or_restore": True,
            "live_fl_studio": False,
            "postfader": False,
            "iac_midi": False,
        }
        return DawResult(
            supported=True,
            attempted=True,
            succeeded=True,
            verified=True,
            observations={"capabilities": caps, "mode": "simulation"},
        )

    def read_project(self) -> DawResult:
        if not self.connected:
            return DawResult(True, True, False, False, error="not connected")
        payload = self.project.model_dump(mode="json") if self.project else None
        return DawResult(
            True,
            True,
            True,
            True,
            observations={"project": payload, "bpm": self.bpm},
        )

    def read_tracks(self) -> DawResult:
        if self.project is None:
            return DawResult(True, True, True, True, observations={"tracks": []})
        tracks = [
            {
                "id": str(t.id),
                "role": t.role.value,
                "note_count": len(t.note_events),
                "drum_count": len(t.drum_events),
                "locked": t.locked,
            }
            for t in self.project.tracks
        ]
        return DawResult(True, True, True, True, observations={"tracks": tracks})

    def create_or_update_notes(self, project: MusicProject) -> DawResult:
        if not self.connected:
            return DawResult(True, True, False, False, error="not connected")
        self.project = copy.deepcopy(project)
        self.bpm = project.bpm
        return DawResult(
            True,
            True,
            True,
            True,
            observations={
                "track_count": len(project.tracks),
                "note_total": sum(len(t.note_events) for t in project.tracks),
            },
        )

    def set_tempo(self, bpm: float) -> DawResult:
        if bpm <= 0:
            return DawResult(True, True, False, False, error="bpm must be > 0")
        self.bpm = bpm
        if self.project is not None:
            self.project.bpm = bpm
        return DawResult(True, True, True, True, observations={"bpm": bpm})

    def set_track_params(self, track_id: str, params: dict[str, Any]) -> DawResult:
        self.track_params[track_id] = {**self.track_params.get(track_id, {}), **params}
        return DawResult(True, True, True, True, observations={"track_id": track_id, "params": params})

    def choose_existing_preset(self, track_id: str, preset: str) -> DawResult:
        self.presets[track_id] = preset
        return DawResult(True, True, True, True, observations={"track_id": track_id, "preset": preset})

    def arrange_section(self, section: dict[str, Any]) -> DawResult:
        self.sections.append(section)
        return DawResult(True, True, True, True, observations={"section": section})

    def save_snapshot(self, label: str) -> DawResult:
        ref = f"snap-{uuid4()}"
        self.snapshots[ref] = {
            "label": label,
            "bpm": self.bpm,
            "project": self.project.model_dump(mode="json") if self.project else None,
            "track_params": copy.deepcopy(self.track_params),
            "presets": copy.deepcopy(self.presets),
        }
        return DawResult(True, True, True, True, observations={"snapshot_ref": ref, "label": label})

    def export_audio_or_request_manual_bounce(self, out_path: str) -> DawResult:
        # Simulation: do not invent audio bytes; report manual action required.
        self.last_export = out_path
        return DawResult(
            supported=True,
            attempted=True,
            succeeded=False,
            verified=False,
            observations={"requested_path": out_path, "mode": "simulation"},
            user_action_required=(
                "Simulation mode cannot bounce audio. On your Mac, export/bounce from FL Studio "
                f"to {out_path} or use MIDI import workflow."
            ),
        )

    def verify_postcondition(self, expected: dict[str, Any]) -> DawResult:
        obs: dict[str, Any] = {}
        ok = True
        if "bpm" in expected:
            obs["bpm"] = self.bpm
            ok = ok and abs(self.bpm - float(expected["bpm"])) < 1e-6
        if "min_tracks" in expected:
            count = len(self.project.tracks) if self.project else 0
            obs["track_count"] = count
            ok = ok and count >= int(expected["min_tracks"])
        if "min_notes" in expected:
            total = sum(len(t.note_events) for t in self.project.tracks) if self.project else 0
            obs["note_total"] = total
            ok = ok and total >= int(expected["min_notes"])
        return DawResult(True, True, ok, ok, observations=obs, error=None if ok else "postcondition failed")

    def undo_or_restore(self, snapshot_ref: str) -> DawResult:
        snap = self.snapshots.get(snapshot_ref)
        if snap is None:
            return DawResult(True, True, False, False, error=f"unknown snapshot {snapshot_ref}")
        self.bpm = snap["bpm"]
        self.track_params = copy.deepcopy(snap["track_params"])
        self.presets = copy.deepcopy(snap["presets"])
        if snap["project"] is not None:
            self.project = MusicProject.model_validate(snap["project"])
        else:
            self.project = None
        return DawResult(True, True, True, True, observations={"restored": snapshot_ref})
