"""NL → BriefDocument parser (Phase 1; no LLM required)."""

from __future__ import annotations

import hashlib
import re

from backend.app.models.schemas import (
    BorrowChip,
    BriefDocument,
    EnergyPoint,
    SectionDraft,
    utcnow,
)
from backend.app.music.templates import get_template, resolve_genre_id


def _seed_from_text(text: str, explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


_KEY_RE = re.compile(
    r"\b([A-Ga-g](?:#|b)?)\s*(major|minor|maj|min|m)?\b"
)


def explicit_key_from_text(text: str) -> str | None:
    """Return a key string only when the text names a pitch class + optional mode.

    Avoids false positives from bare letters (e.g. ``\"b\"`` inside ``\"bass\"``).
    """
    match = _KEY_RE.search(text)
    if not match:
        return None
    root = match.group(1)
    root = root[0].upper() + root[1:]
    mode_tok = (match.group(2) or "").lower()
    lower = text.lower()
    if mode_tok in ("m", "min", "minor"):
        return f"{root} minor"
    if mode_tok in ("maj", "major"):
        return f"{root} major"
    if "minor" in lower and "major" not in lower:
        return f"{root} minor"
    if "major" in lower:
        return f"{root} major"
    # Bare pitch class with no mode word — treat as explicit only if mode nearby
    # e.g. "in A" is ambiguous; require major/minor elsewhere or mode token.
    if mode_tok:
        return f"{root} minor"
    return None


def explicit_genre_from_text(text: str) -> str | None:
    lower = text.lower()
    for g in ("amapiano", "afrobeats", "afrobeat", "rnb", "r&b", "trap", "drill", "pop"):
        if g in lower:
            return resolve_genre_id(g)
    return None


def explicit_bpm_from_text(text: str) -> float | None:
    match = re.search(r"(\d{2,3})\s*bpm", text.lower())
    return float(match.group(1)) if match else None


def parse_brief(
    text: str,
    *,
    seed: int | None = None,
    bars: int | None = None,
    locked_roles: list[str] | None = None,
    scratch_or_release: str = "scratch",
) -> BriefDocument:
    """Parse free text into a constraint-first BriefDocument."""
    lower = text.lower()
    genre_id = explicit_genre_from_text(text) or "default"
    tmpl = get_template(genre_id)

    bpm = explicit_bpm_from_text(text)
    if bpm is None:
        bpm = tmpl.default_bpm

    key = explicit_key_from_text(text)
    if key is None:
        key = "A minor"

    novelty = 0.4
    if any(w in lower for w in ("wild", "experimental", "novel", "crazy")):
        novelty = 0.8
    elif any(w in lower for w in ("safe", "classic", "simple")):
        novelty = 0.2
    elif any(w in lower for w in ("mellow", "chill", "soft")):
        novelty = 0.35

    length = bars if bars is not None else 8
    section_map = [
        SectionDraft(
            name=s.name,
            start_bar=s.start_bar,
            end_bar=min(s.end_bar, length) if s.end_bar else length,
            intensity_target=s.intensity_target,
        )
        for s in tmpl.section_map
    ] or [SectionDraft(name="loop_a", start_bar=1, end_bar=length, intensity_target=0.5)]

    # Simple rising/falling energy from mood words
    if any(w in lower for w in ("build", "bigger", "rising")):
        energy = [EnergyPoint(bar=i + 1, value=round(0.3 + 0.6 * i / max(length - 1, 1), 3)) for i in range(length)]
    elif any(w in lower for w in ("mellow", "chill", "soft", "atmospheric")):
        energy = [EnergyPoint(bar=i + 1, value=0.4) for i in range(length)]
    else:
        energy = [EnergyPoint(bar=i + 1, value=0.55) for i in range(length)]

    chips: list[BorrowChip] = []
    for trait, keys in (
        ("bass_bounce", ("bass bounce", "bass feel", "bassline")),
        ("percussion_texture", ("percussion", "perc", "hats", "drums bounce")),
        ("atmosphere", ("atmosphere", "pad", "space")),
        ("chord_feel", ("chords", "rhodes", "keys", "harmony")),
    ):
        if any(k in lower for k in keys):
            chips.append(BorrowChip(trait=trait, weight=0.8))

    locks = list(locked_roles or [])
    # NL lock phrases
    if re.search(r"\bkeep (the )?drums\b", lower):
        if "drums" not in locks:
            locks.append("drums")
    if re.search(r"\bkeep (the )?bass\b", lower):
        if "bass" not in locks:
            locks.append("bass")
    if re.search(r"\bkeep (the )?chords?\b", lower):
        if "chord" not in locks:
            locks.append("chord")

    autonomy = "collaborative"
    if "suggest only" in lower or "suggest-only" in lower:
        autonomy = "suggest-only"
    elif "autonomous" in lower:
        autonomy = "autonomous"

    release = "release" if "release mode" in lower else scratch_or_release

    return BriefDocument(
        title=f"{tmpl.name} brief",
        free_text=text.strip(),
        bpm=bpm,
        bpm_range=tmpl.bpm_range,
        key=key,
        meter="4/4",
        genre_template_id=tmpl.id,
        energy_curve=energy,
        borrow_chips=chips,
        section_map=section_map,
        novelty=novelty,
        length_bars=length,
        locked_roles=locks,
        scratch_or_release=release,
        autonomy_mode=autonomy,
        seed=_seed_from_text(text.strip(), seed),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
