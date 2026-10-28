"""Genre structure template library (Phase 1)."""

from __future__ import annotations

from backend.app.models.schemas import GenreTemplate, SectionDraft

_TEMPLATES: dict[str, GenreTemplate] = {
    "afrobeats": GenreTemplate(
        id="afrobeats",
        name="Afrobeats",
        default_bpm=110,
        bpm_range=(100, 120),
        typical_key_modes=["minor", "major"],
        section_map=[SectionDraft(name="loop_a", start_bar=1, end_bar=8, intensity_target=0.6)],
        role_defaults=["drums", "bass", "chord", "percussion"],
        groove_density=0.65,
        progression_key="afrobeats",
        notes="Syncopated kick, clap on 2/4, warm keys",
    ),
    "amapiano": GenreTemplate(
        id="amapiano",
        name="Amapiano",
        default_bpm=112,
        bpm_range=(108, 115),
        typical_key_modes=["minor"],
        section_map=[SectionDraft(name="loop_a", start_bar=1, end_bar=8, intensity_target=0.55)],
        role_defaults=["drums", "bass", "chord", "perc"],
        groove_density=0.7,
        progression_key="amapiano",
        notes="Log drum feel, rolling hats, spacious chords",
    ),
    "rnb": GenreTemplate(
        id="rnb",
        name="R&B",
        default_bpm=90,
        bpm_range=(70, 100),
        typical_key_modes=["minor", "major"],
        section_map=[SectionDraft(name="loop_a", start_bar=1, end_bar=8, intensity_target=0.45)],
        role_defaults=["drums", "bass", "chord", "pad"],
        groove_density=0.45,
        progression_key="rnb",
        notes="Laid-back pocket, lush chords",
    ),
    "trap": GenreTemplate(
        id="trap",
        name="Trap",
        default_bpm=140,
        bpm_range=(130, 160),
        typical_key_modes=["minor"],
        section_map=[SectionDraft(name="loop_a", start_bar=1, end_bar=8, intensity_target=0.7)],
        role_defaults=["drums", "bass", "chord"],
        groove_density=0.75,
        progression_key="trap",
        notes="808s, hi-hat rolls, sparse harmony",
    ),
    "drill": GenreTemplate(
        id="drill",
        name="Drill",
        default_bpm=140,
        bpm_range=(135, 150),
        typical_key_modes=["minor"],
        section_map=[SectionDraft(name="loop_a", start_bar=1, end_bar=8, intensity_target=0.75)],
        role_defaults=["drums", "bass", "chord"],
        groove_density=0.7,
        progression_key="trap",
        notes="Sliding 808s, stark drums",
    ),
    "pop": GenreTemplate(
        id="pop",
        name="Pop",
        default_bpm=120,
        bpm_range=(100, 130),
        typical_key_modes=["major", "minor"],
        section_map=[SectionDraft(name="loop_a", start_bar=1, end_bar=8, intensity_target=0.6)],
        role_defaults=["drums", "bass", "chord"],
        groove_density=0.55,
        progression_key="pop",
        notes="Four-on-floor friendly, clear progressions",
    ),
    "default": GenreTemplate(
        id="default",
        name="Default groove",
        default_bpm=110,
        bpm_range=(80, 140),
        typical_key_modes=["minor", "major"],
        section_map=[SectionDraft(name="loop_a", start_bar=1, end_bar=8, intensity_target=0.5)],
        role_defaults=["drums", "bass", "chord"],
        groove_density=0.5,
        progression_key="default",
        notes="Generic 8-bar starter",
    ),
}


def list_templates() -> list[GenreTemplate]:
    return list(_TEMPLATES.values())


def get_template(template_id: str) -> GenreTemplate:
    return _TEMPLATES.get(template_id, _TEMPLATES["default"])


def resolve_genre_id(name: str) -> str:
    key = name.lower().strip()
    aliases = {
        "afrobeat": "afrobeats",
        "afrobeats": "afrobeats",
        "amapiano": "amapiano",
        "r&b": "rnb",
        "rnb": "rnb",
        "trap": "trap",
        "drill": "drill",
        "pop": "pop",
    }
    return aliases.get(key, key if key in _TEMPLATES else "default")
