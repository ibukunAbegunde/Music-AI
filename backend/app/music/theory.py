"""Minimal music-theory helpers for Phase 0 generators."""

from __future__ import annotations

SCALE_INTERVALS: dict[str, list[int]] = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NAME_TO_PC = {n: i for i, n in enumerate(NOTE_NAMES)}
NAME_TO_PC.update({"Db": 1, "Eb": 3, "Gb": 6, "Ab": 8, "Bb": 10})

# Common progressions as scale degrees (1-indexed)
PROGRESSIONS: dict[str, list[int]] = {
    "pop": [1, 5, 6, 4],
    "afrobeats": [1, 4, 5, 4],
    "amapiano": [1, 6, 4, 5],
    "rnb": [1, 6, 4, 5],
    "trap": [1, 6, 7, 5],
    "default": [1, 5, 6, 4],
}


def parse_key(key: str) -> tuple[int, str]:
    """Parse 'Amin', 'C', 'F# major' → (pitch_class, mode)."""
    raw = key.strip()
    lower = raw.lower()
    mode = "minor" if ("minor" in lower or lower.endswith("m") or lower.endswith("min")) and "major" not in lower else "major"
    cleaned = (
        raw.replace("minor", "")
        .replace("major", "")
        .replace("Minor", "")
        .replace("Major", "")
        .replace("min", "")
        .strip()
    )
    if cleaned.lower().endswith("m") and len(cleaned) > 1:
        cleaned = cleaned[:-1]
    cleaned = cleaned.strip() or "C"
    # Normalize accidental casing: f# → F#, bb → Bb
    if len(cleaned) >= 2 and cleaned[1] in "#b":
        root_token = cleaned[0].upper() + cleaned[1]
    else:
        root_token = cleaned[0].upper() + cleaned[1:]
    pc = NAME_TO_PC.get(root_token, NAME_TO_PC.get(root_token[:2], 0))
    return pc, mode


def scale_pitch(root_pc: int, degree: int, octave: int, mode: str = "major") -> int:
    """Map 1-indexed scale degree to MIDI pitch."""
    intervals = SCALE_INTERVALS.get(mode, SCALE_INTERVALS["major"])
    idx = (degree - 1) % len(intervals)
    octave_shift = (degree - 1) // len(intervals)
    pitch = root_pc + intervals[idx] + (octave + octave_shift) * 12
    return max(0, min(127, pitch))


def triad(root_pc: int, degree: int, octave: int, mode: str = "major") -> list[int]:
    """Return MIDI pitches for a triad on the given scale degree."""
    return [
        scale_pitch(root_pc, degree, octave, mode),
        scale_pitch(root_pc, degree + 2, octave, mode),
        scale_pitch(root_pc, degree + 4, octave, mode),
    ]


def beats_per_bar(meter: str = "4/4") -> int:
    num, _, _den = meter.partition("/")
    try:
        return int(num)
    except ValueError:
        return 4
