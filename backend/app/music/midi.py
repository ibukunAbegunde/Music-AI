"""MIDI file write / read helpers using mido."""

from __future__ import annotations

from pathlib import Path

import mido

from backend.app.models.schemas import MusicProject, MusicTrack, NoteEvent, TrackRole

TICKS_PER_BEAT = 480


def _tempo_from_bpm(bpm: float) -> int:
    return int(60_000_000 / bpm)


def track_to_midifile(
    track: MusicTrack,
    *,
    bpm: float,
    meters: tuple[int, int] = (4, 4),
) -> mido.MidiFile:
    mid = mido.MidiFile(ticks_per_beat=TICKS_PER_BEAT)
    meta = mido.MidiTrack()
    mid.tracks.append(meta)
    meta.append(mido.MetaMessage("set_tempo", tempo=_tempo_from_bpm(bpm), time=0))
    meta.append(
        mido.MetaMessage(
            "time_signature",
            numerator=meters[0],
            denominator=meters[1],
            time=0,
        )
    )
    meta.append(mido.MetaMessage("track_name", name=track.role.value, time=0))

    notes = list(track.note_events)
    # Convert absolute beat times → delta-tick note_on/off
    events: list[tuple[int, mido.Message]] = []
    for n in notes:
        start = int(round(n.onset_beats * TICKS_PER_BEAT))
        end = int(round((n.onset_beats + n.duration_beats) * TICKS_PER_BEAT))
        events.append(
            (
                start,
                mido.Message(
                    "note_on",
                    note=n.pitch,
                    velocity=n.velocity,
                    channel=n.channel,
                    time=0,
                ),
            )
        )
        events.append(
            (
                end,
                mido.Message(
                    "note_off",
                    note=n.pitch,
                    velocity=0,
                    channel=n.channel,
                    time=0,
                ),
            )
        )
    events.sort(key=lambda x: (x[0], 0 if x[1].type == "note_off" else 1))

    note_track = mido.MidiTrack()
    mid.tracks.append(note_track)
    last = 0
    for abs_tick, msg in events:
        delta = abs_tick - last
        msg.time = max(0, delta)
        note_track.append(msg)
        last = abs_tick
    note_track.append(mido.MetaMessage("end_of_track", time=0))
    meta.append(mido.MetaMessage("end_of_track", time=0))
    return mid


def export_project_midi(project: MusicProject, out_dir: Path) -> dict[str, Path]:
    """Export one MIDI file per track plus a combined file. Returns path map."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    meters = (4, 4)
    if "/" in project.meter:
        n, d = project.meter.split("/", 1)
        meters = (int(n), int(d))

    combined = mido.MidiFile(ticks_per_beat=TICKS_PER_BEAT)
    tempo_track = mido.MidiTrack()
    combined.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=_tempo_from_bpm(project.bpm), time=0))
    tempo_track.append(
        mido.MetaMessage(
            "time_signature",
            numerator=meters[0],
            denominator=meters[1],
            time=0,
        )
    )
    tempo_track.append(mido.MetaMessage("track_name", name=project.name, time=0))
    tempo_track.append(mido.MetaMessage("end_of_track", time=0))

    for track in project.tracks:
        mid = track_to_midifile(track, bpm=project.bpm, meters=meters)
        path = out_dir / f"{track.role.value}.mid"
        mid.save(path)
        paths[track.role.value] = path

        # Merge note track into combined (skip meta-only first track)
        if len(mid.tracks) > 1:
            merged = mido.MidiTrack()
            merged.append(mido.MetaMessage("track_name", name=track.role.value, time=0))
            for msg in mid.tracks[1]:
                if msg.type == "end_of_track":
                    continue
                merged.append(msg.copy())
            merged.append(mido.MetaMessage("end_of_track", time=0))
            combined.tracks.append(merged)

    combined_path = out_dir / "combined.mid"
    combined.save(combined_path)
    paths["combined"] = combined_path
    return paths


def read_note_ons(path: Path) -> list[tuple[int, int, int]]:
    """Return list of (absolute_tick, pitch, velocity) for note_on with velocity>0."""
    mid = mido.MidiFile(path)
    notes: list[tuple[int, int, int]] = []
    for track in mid.tracks:
        t = 0
        for msg in track:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                notes.append((t, msg.note, msg.velocity))
    return notes


def count_note_events(project: MusicProject) -> dict[str, int]:
    return {t.role.value: len(t.note_events) for t in project.tracks}


def flatten_notes(track: MusicTrack) -> list[NoteEvent]:
    return list(track.note_events)


def assert_eight_bars_span(project: MusicProject, bpb: int = 4) -> None:
    """Sanity: at least one note starts inside the final bar window."""
    end = project.length_bars * bpb
    starts = [n.onset_beats for t in project.tracks for n in t.note_events]
    if not starts:
        raise AssertionError("project has no notes")
    if max(starts) >= end:
        raise AssertionError(f"note onset {max(starts)} exceeds length {end}")
    if max(starts) < (project.length_bars - 1) * bpb:
        # Soft check: generators should place material in last bars for chords/bass
        roles = {t.role for t in project.tracks}
        if TrackRole.CHORD in roles or TrackRole.BASS in roles:
            raise AssertionError("expected harmonic material spanning into final bars")
