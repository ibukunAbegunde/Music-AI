"""Specialist MIDI composition hooks (Phase 7).

Default path delegates to deterministic generators (Phase 1–6).
Optional neural / fine-tuned specialist adapters refuse without approval + install.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from backend.app.core.config import Settings, get_settings
from backend.app.models.schemas import BriefDocument, MusicProject
from backend.app.music.conditioning import ConditioningPlan
from backend.app.music.generators import generate_from_brief

SPECIALIST_DETERMINISTIC = "deterministic_generators"
SPECIALIST_OPTIONAL_NEURAL = "optional_neural_midi"
SPECIALIST_VERSION = "0.7.0"


@dataclass
class MidiSpecialistRequest:
    brief: BriefDocument
    plan: ConditioningPlan | None = None
    reference_ids: list | None = None
    name: str | None = None
    # Future fine-tune / conditioned generation knobs (ignored by deterministic stub).
    style_vector: list[float] | None = None
    specialist_checkpoint: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class MidiSpecialistResult:
    project: MusicProject
    specialist_name: str
    specialist_version: str
    mode: str  # deterministic | neural_stub | neural
    notes: list[str] = field(default_factory=list)
    cir_is_system_of_record: bool = True


class MidiSpecialist(Protocol):
    name: str
    version: str

    def compose(self, request: MidiSpecialistRequest) -> MidiSpecialistResult: ...


@dataclass
class DeterministicMidiSpecialist:
    """Honest Phase 1–6 path wrapped as a specialist hook — always available."""

    name: str = SPECIALIST_DETERMINISTIC
    version: str = SPECIALIST_VERSION

    def compose(self, request: MidiSpecialistRequest) -> MidiSpecialistResult:
        project = generate_from_brief(
            request.brief,
            name=request.name,
            plan=request.plan,
            reference_ids=request.reference_ids,
        )
        notes = [
            "Deterministic generators (drums/bass/chords) — not a trained MIDI model.",
            "CIR remains system of record for role-locks / PatchOps / revise.",
        ]
        if request.style_vector is not None:
            notes.append(
                "style_vector provided but ignored by deterministic specialist "
                "(wire into fine-tuned adapter after approval)."
            )
        if request.specialist_checkpoint:
            notes.append(
                f"specialist_checkpoint={request.specialist_checkpoint!r} ignored "
                "(no weights loaded)."
            )
        return MidiSpecialistResult(
            project=project,
            specialist_name=self.name,
            specialist_version=self.version,
            mode="deterministic",
            notes=notes,
            cir_is_system_of_record=True,
        )


class OptionalNeuralMidiSpecialist:
    """Refuses to download / fine-tune / load large MIDI models until approved."""

    name = SPECIALIST_OPTIONAL_NEURAL
    version = "stub-0"

    def compose(self, request: MidiSpecialistRequest) -> MidiSpecialistResult:
        raise RuntimeError(
            "Optional neural MIDI specialist is not installed. "
            "Default path uses DeterministicMidiSpecialist (Phase 1–6 generators). "
            "Do not fine-tune or download foundation MIDI models without explicit "
            "approval — see docs/audio-models.md#phase-7-research."
        )


def get_midi_specialist(
    settings: Settings | None = None,
    *,
    prefer_optional: bool = False,
) -> MidiSpecialist:
    """Return the active MIDI specialist.

    Default: DeterministicMidiSpecialist.
    Optional neural path requires MUSIC_AI_ALLOW_SPECIALIST_DOWNLOAD + future install.
    """
    settings = settings or get_settings()
    allow = bool(getattr(settings, "music_ai_allow_specialist_download", False))
    mode = getattr(settings, "midi_specialist", "deterministic")
    if prefer_optional or mode in ("optional", "neural", SPECIALIST_OPTIONAL_NEURAL):
        if not allow:
            raise RuntimeError(
                "midi_specialist=optional requires MUSIC_AI_ALLOW_SPECIALIST_DOWNLOAD=true "
                "(no large model downloads without explicit approval)."
            )
        raise RuntimeError(
            "Optional neural MIDI specialist approved via flag but not bundled. "
            "Use deterministic specialist or install a compatible adapter when available."
        )
    return DeterministicMidiSpecialist()
