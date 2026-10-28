"""MIDI-export fallback adapter for manual FL Studio import."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.core.config import get_settings
from backend.app.daw.base import DawAdapter, DawResult
from backend.app.models.schemas import MusicProject
from backend.app.music.midi import export_project_midi, read_note_ons
from backend.app.storage.assets import AssetStore


class MidiExportAdapter(DawAdapter):
    """Writes MIDI stems for the user to drag into FL Studio (manual-import mode)."""

    name = "midi_export"

    def __init__(self, asset_store: AssetStore | None = None) -> None:
        self.assets = asset_store or AssetStore(get_settings())
        self.connected = False
        self.last_paths: dict[str, Path] = {}
        self.project: MusicProject | None = None
        self.bpm: float = 120.0

    def connect(self) -> DawResult:
        self.connected = True
        _ = self.assets.root  # ensure workspace
        return DawResult(
            True,
            True,
            True,
            True,
            observations={"adapter": self.name, "workspace": str(self.assets.root)},
            user_action_required="Import exported .mid files into FL Studio patterns/playlist.",
        )

    def probe_capabilities(self) -> DawResult:
        caps = {
            "connect": True,
            "read_project": False,
            "read_tracks": False,
            "create_or_update_notes": True,  # via file export
            "set_tempo": True,  # embedded in MIDI
            "set_track_params": False,
            "choose_existing_preset": False,
            "arrange_section": False,
            "save_snapshot": False,
            "export_audio": False,
            "verify_postcondition": True,  # verify MIDI files parse
            "undo_or_restore": False,
            "live_fl_studio": False,
            "manual_import": True,
        }
        return DawResult(True, True, True, True, observations={"capabilities": caps, "mode": "midi_export"})

    def read_project(self) -> DawResult:
        return DawResult(
            False,
            True,
            False,
            False,
            error="MIDI export adapter cannot read FL Studio project state",
            user_action_required="Open the project in FL Studio and inspect manually.",
        )

    def read_tracks(self) -> DawResult:
        if self.project is None:
            return DawResult(False, True, False, False, error="no project loaded")
        return DawResult(
            True,
            True,
            True,
            False,
            observations={
                "tracks": [
                    {"role": t.role.value, "notes": len(t.note_events)} for t in self.project.tracks
                ],
                "source": "local_canonical_project",
            },
            user_action_required="Track state is from local CIR, not live FL Studio.",
        )

    def create_or_update_notes(self, project: MusicProject) -> DawResult:
        if not self.connected:
            return DawResult(True, True, False, False, error="not connected")
        out_dir = self.assets.midi_dir(project.id)
        paths = export_project_midi(project, out_dir)
        self.last_paths = paths
        self.project = project
        self.bpm = project.bpm
        # Verify each file has note_ons
        verified = True
        counts: dict[str, int] = {}
        for role, path in paths.items():
            if role == "combined":
                continue
            ons = read_note_ons(path)
            counts[role] = len(ons)
            if len(ons) == 0:
                verified = False
        return DawResult(
            True,
            True,
            True,
            verified,
            observations={
                "midi_paths": {k: str(v) for k, v in paths.items()},
                "note_on_counts": counts,
            },
            user_action_required=(
                "In FL Studio: File → Import → MIDI file for each stem, or drag .mid onto Channel Rack. "
                f"Files at: {out_dir}"
            ),
        )

    def set_tempo(self, bpm: float) -> DawResult:
        self.bpm = bpm
        if self.project is not None:
            self.project.bpm = bpm
        return DawResult(
            True,
            True,
            True,
            False,
            observations={"bpm": bpm},
            user_action_required="Re-export MIDI after tempo change, then set project tempo in FL Studio.",
        )

    def set_track_params(self, track_id: str, params: dict[str, Any]) -> DawResult:
        return DawResult(
            False,
            True,
            False,
            False,
            error="track params not supported in MIDI export mode",
            user_action_required="Adjust mixer/instrument params manually in FL Studio.",
        )

    def choose_existing_preset(self, track_id: str, preset: str) -> DawResult:
        return DawResult(
            False,
            True,
            False,
            False,
            error="presets not supported in MIDI export mode",
            user_action_required=f"Load preset '{preset}' manually on the target channel.",
        )

    def arrange_section(self, section: dict[str, Any]) -> DawResult:
        return DawResult(
            False,
            True,
            False,
            False,
            error="playlist arrangement not supported in MIDI export mode",
            user_action_required="Place imported patterns on the Playlist for the requested section.",
        )

    def save_snapshot(self, label: str) -> DawResult:
        return DawResult(
            False,
            True,
            False,
            False,
            error="DAW snapshot not supported",
            user_action_required="Save a copy of your .flp manually before importing new MIDI.",
        )

    def export_audio_or_request_manual_bounce(self, out_path: str) -> DawResult:
        return DawResult(
            False,
            True,
            False,
            False,
            observations={"requested_path": out_path},
            user_action_required=f"Bounce/export audio from FL Studio to {out_path}.",
        )

    def verify_postcondition(self, expected: dict[str, Any]) -> DawResult:
        if not self.last_paths:
            return DawResult(True, True, False, False, error="no MIDI exported yet")
        ok = True
        obs: dict[str, Any] = {"paths": {k: str(v) for k, v in self.last_paths.items()}}
        if "min_files" in expected:
            ok = ok and len(self.last_paths) >= int(expected["min_files"])
        if "roles" in expected:
            for role in expected["roles"]:
                path = self.last_paths.get(role)
                if path is None or not path.exists():
                    ok = False
                else:
                    ons = read_note_ons(path)
                    if len(ons) < 1:
                        ok = False
        return DawResult(True, True, ok, ok, observations=obs, error=None if ok else "MIDI verify failed")

    def undo_or_restore(self, snapshot_ref: str) -> DawResult:
        return DawResult(
            False,
            True,
            False,
            False,
            error="undo not supported in MIDI export mode",
            user_action_required="Restore a previous .flp backup manually.",
        )
