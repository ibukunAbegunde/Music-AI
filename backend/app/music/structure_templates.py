"""Full-song structure templates (Phase 6).

Genre templates remain 8-bar loop starters (Phase 1). These extend them with
intro/verse/chorus/… maps for autonomous full-length production.
"""

from __future__ import annotations

from backend.app.models.schemas import SectionDraft, StructureTemplate
from backend.app.music.templates import resolve_genre_id

_PALETTES: dict[str, dict[str, str]] = {
    "afrobeats": {
        "drums": "Afrobeats kit (kick/clap/hats)",
        "bass": "Warm sub / electric bass",
        "chord": "Rhodes / soft keys",
    },
    "amapiano": {
        "drums": "Amapiano kit + shakers",
        "bass": "Log-drum / rolling bass",
        "chord": "Pad + soft keys",
    },
    "rnb": {
        "drums": "Laid-back R&B kit",
        "bass": "Round electric bass",
        "chord": "Electric piano / pad",
    },
    "trap": {
        "drums": "Trap kit + hat rolls",
        "bass": "808 sub",
        "chord": "Dark pad / bells",
    },
    "drill": {
        "drums": "Drill kit",
        "bass": "Sliding 808",
        "chord": "Sparse dark keys",
    },
    "pop": {
        "drums": "Four-on-floor / pop kit",
        "bass": "Synth bass",
        "chord": "Bright keys / guitar bed",
    },
    "default": {
        "drums": "General MIDI drum kit",
        "bass": "Synth bass",
        "chord": "Keys / pad",
    },
}


def _map(*parts: tuple[str, int, int, float]) -> list[SectionDraft]:
    return [
        SectionDraft(name=name, start_bar=start, end_bar=end, intensity_target=intensity)
        for name, start, end, intensity in parts
    ]


# Canonical full-length skeletons (bars inclusive). Default ~64–80 bars.
_STRUCTURES: dict[str, StructureTemplate] = {
    "afrobeats_full": StructureTemplate(
        id="afrobeats_full",
        name="Afrobeats full instrumental",
        genre_template_id="afrobeats",
        length_bars=64,
        section_map=_map(
            ("intro", 1, 8, 0.30),
            ("verse", 9, 24, 0.50),
            ("chorus", 25, 40, 0.78),
            ("bridge", 41, 48, 0.42),
            ("chorus", 49, 64, 0.85),
        ),
        instrument_palette=_PALETTES["afrobeats"],
        notes="64-bar Afrobeats instrumental: intro→verse→chorus→bridge→chorus",
    ),
    "amapiano_full": StructureTemplate(
        id="amapiano_full",
        name="Amapiano full instrumental",
        genre_template_id="amapiano",
        length_bars=80,
        section_map=_map(
            ("intro", 1, 8, 0.28),
            ("groove", 9, 24, 0.55),
            ("drop", 25, 40, 0.80),
            ("break", 41, 48, 0.35),
            ("drop", 49, 72, 0.82),
            ("outro", 73, 80, 0.25),
        ),
        instrument_palette=_PALETTES["amapiano"],
        notes="80-bar Amapiano instrumental with break + extended drop",
    ),
    "rnb_full": StructureTemplate(
        id="rnb_full",
        name="R&B full instrumental",
        genre_template_id="rnb",
        length_bars=64,
        section_map=_map(
            ("intro", 1, 8, 0.25),
            ("verse", 9, 24, 0.45),
            ("chorus", 25, 40, 0.70),
            ("bridge", 41, 48, 0.40),
            ("chorus", 49, 64, 0.75),
        ),
        instrument_palette=_PALETTES["rnb"],
    ),
    "trap_full": StructureTemplate(
        id="trap_full",
        name="Trap full instrumental",
        genre_template_id="trap",
        length_bars=64,
        section_map=_map(
            ("intro", 1, 8, 0.35),
            ("verse", 9, 24, 0.55),
            ("chorus", 25, 40, 0.82),
            ("bridge", 41, 48, 0.40),
            ("chorus", 49, 64, 0.88),
        ),
        instrument_palette=_PALETTES["trap"],
    ),
    "drill_full": StructureTemplate(
        id="drill_full",
        name="Drill full instrumental",
        genre_template_id="drill",
        length_bars=64,
        section_map=_map(
            ("intro", 1, 8, 0.40),
            ("verse", 9, 24, 0.60),
            ("chorus", 25, 40, 0.85),
            ("bridge", 41, 48, 0.45),
            ("chorus", 49, 64, 0.90),
        ),
        instrument_palette=_PALETTES["drill"],
    ),
    "pop_full": StructureTemplate(
        id="pop_full",
        name="Pop full instrumental",
        genre_template_id="pop",
        length_bars=64,
        section_map=_map(
            ("intro", 1, 8, 0.30),
            ("verse", 9, 24, 0.50),
            ("prechorus", 25, 32, 0.60),
            ("chorus", 33, 48, 0.80),
            ("bridge", 49, 56, 0.45),
            ("chorus", 57, 64, 0.85),
        ),
        instrument_palette=_PALETTES["pop"],
    ),
    "default_full": StructureTemplate(
        id="default_full",
        name="Default full instrumental",
        genre_template_id="default",
        length_bars=64,
        section_map=_map(
            ("intro", 1, 8, 0.30),
            ("verse", 9, 24, 0.50),
            ("chorus", 25, 40, 0.75),
            ("bridge", 41, 48, 0.40),
            ("chorus", 49, 64, 0.80),
        ),
        instrument_palette=_PALETTES["default"],
        notes="Generic 64-bar instrumental skeleton",
    ),
}


def list_structure_templates() -> list[StructureTemplate]:
    return list(_STRUCTURES.values())


def get_structure_template(template_id: str) -> StructureTemplate:
    if template_id in _STRUCTURES:
        return _STRUCTURES[template_id]
    # Allow genre id → "<genre>_full"
    genre = resolve_genre_id(template_id.removesuffix("_full"))
    key = f"{genre}_full"
    return _STRUCTURES.get(key, _STRUCTURES["default_full"])


def resolve_structure_id(genre_or_structure: str | None, genre_template_id: str | None = None) -> str:
    """Pick a structure template id from an explicit id or genre hint."""
    if genre_or_structure:
        raw = genre_or_structure.lower().strip()
        if raw in _STRUCTURES:
            return raw
        if raw.endswith("_full") and raw in _STRUCTURES:
            return raw
        genre = resolve_genre_id(raw.removesuffix("_full"))
        key = f"{genre}_full"
        if key in _STRUCTURES:
            return key
    if genre_template_id:
        key = f"{resolve_genre_id(genre_template_id)}_full"
        if key in _STRUCTURES:
            return key
    return "default_full"


def validate_section_map(section_map: list[SectionDraft], length_bars: int) -> None:
    if not section_map:
        raise ValueError("section_map must not be empty")
    if section_map[0].start_bar != 1:
        raise ValueError("section_map must start at bar 1")
    if section_map[-1].end_bar != length_bars:
        raise ValueError(
            f"section_map must end at length_bars={length_bars}, got {section_map[-1].end_bar}"
        )
    prev_end = 0
    for sec in section_map:
        if sec.end_bar < sec.start_bar:
            raise ValueError(f"invalid section {sec.name}: end < start")
        if sec.start_bar != prev_end + 1:
            raise ValueError(
                f"section gap/overlap before {sec.name}: expected start {prev_end + 1}"
            )
        prev_end = sec.end_bar
