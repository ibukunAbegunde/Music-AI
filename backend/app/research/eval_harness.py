"""Phase 7 research eval harness — simulation-first vs Phase 6 baseline.

Exit criterion (spec): blind listening preference improvements against Phase 6
baseline. CI cannot run real human listening; this harness:

1. Builds a Phase 6-style deterministic baseline candidate.
2. Builds a Phase 7 path candidate (specialist hook + optional advanced mix notes).
3. Scores technical/musical proxies + optional taste ranking if available.
4. Emits a ResearchEvalResult suitable for later real blind sessions.

Does NOT claim blind-listening wins in CI. Labels results as simulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.core.config import Settings, get_settings
from backend.app.models.schemas import new_id, utcnow
from backend.app.music.brief import parse_brief
from backend.app.render_eval.evaluate import evaluate_project
from backend.app.research.midi_specialist import (
    DeterministicMidiSpecialist,
    MidiSpecialistRequest,
    get_midi_specialist,
)
from backend.app.research.mix_heuristics import run_advanced_mix_heuristics


class ResearchEvalResult(BaseModel):
    id: UUID = Field(default_factory=new_id)
    prompt: str
    seed: int
    baseline_label: str = "phase6_deterministic"
    candidate_label: str = "phase7_specialist_hook"
    baseline_technical: float
    baseline_musical: float
    candidate_technical: float
    candidate_musical: float
    delta_technical: float
    delta_musical: float
    mix_score_baseline: float | None = None
    mix_score_candidate: float | None = None
    preference_proxy: str  # baseline | candidate | tie
    blind_listening_status: str = "not_run"  # not_run | scheduled | completed
    simulation: bool = True
    notes: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class BlindListeningHarness:
    """Scaffold for real blind A/B sessions (manual / future UI)."""

    session_id: UUID = field(default_factory=new_id)
    pairs: list[dict[str, Any]] = field(default_factory=list)
    completed_choices: list[dict[str, Any]] = field(default_factory=list)

    def add_pair(
        self,
        *,
        baseline_project_id: str,
        candidate_project_id: str,
        render_a: str | None = None,
        render_b: str | None = None,
    ) -> None:
        self.pairs.append(
            {
                "baseline_project_id": baseline_project_id,
                "candidate_project_id": candidate_project_id,
                "render_a": render_a,
                "render_b": render_b,
                "blind": True,
                "status": "pending",
            }
        )

    def record_choice(self, pair_index: int, choice: str, reason: str | None = None) -> None:
        if pair_index < 0 or pair_index >= len(self.pairs):
            raise IndexError("pair_index out of range")
        self.pairs[pair_index]["status"] = "completed"
        self.pairs[pair_index]["choice"] = choice
        self.completed_choices.append(
            {"pair_index": pair_index, "choice": choice, "reason": reason}
        )

    def preference_rate(self, *, prefer: str = "candidate") -> float | None:
        if not self.completed_choices:
            return None
        wins = sum(1 for c in self.completed_choices if c["choice"] == prefer)
        return wins / len(self.completed_choices)


def run_phase7_baseline_eval(
    prompt: str = "mellow Afrobeats 110 BPM in A minor",
    *,
    seed: int = 42,
    bars: int = 8,
    settings: Settings | None = None,
) -> ResearchEvalResult:
    """Compare Phase 6 deterministic baseline vs Phase 7 specialist-hook path.

    In the default configuration both paths use deterministic generators, so
    deltas are ~0 — the harness still validates wiring and documents that real
    blind listening is required for the Phase 7 product exit.
    """
    settings = settings or get_settings()
    brief = parse_brief(prompt, seed=seed, bars=bars)

    baseline_spec = DeterministicMidiSpecialist()
    baseline = baseline_spec.compose(MidiSpecialistRequest(brief=brief, name="phase6-baseline"))
    baseline_board = evaluate_project(baseline.project).scoreboard
    baseline_mix = run_advanced_mix_heuristics(baseline.project)

    specialist = get_midi_specialist(settings)
    candidate = specialist.compose(
        MidiSpecialistRequest(brief=brief, name="phase7-candidate")
    )
    candidate_board = evaluate_project(candidate.project).scoreboard
    candidate_mix = run_advanced_mix_heuristics(candidate.project)

    dt = candidate_board.technical - baseline_board.technical
    dm = candidate_board.musical - baseline_board.musical
    if abs(dt) < 1e-9 and abs(dm) < 1e-9:
        pref = "tie"
    elif (dt + dm) > 0:
        pref = "candidate"
    else:
        pref = "baseline"

    return ResearchEvalResult(
        prompt=prompt,
        seed=seed,
        baseline_technical=float(baseline_board.technical),
        baseline_musical=float(baseline_board.musical),
        candidate_technical=float(candidate_board.technical),
        candidate_musical=float(candidate_board.musical),
        delta_technical=float(dt),
        delta_musical=float(dm),
        mix_score_baseline=float(baseline_mix.overall_mix_score),
        mix_score_candidate=float(candidate_mix.overall_mix_score),
        preference_proxy=pref,
        blind_listening_status="not_run",
        simulation=True,
        notes=[
            "Simulation proxy only — does not satisfy blind listening exit by itself.",
            "Default specialist == Phase 6 deterministic generators (expected tie).",
            "Schedule real blind A/B via BlindListeningHarness when renders exist.",
            f"specialist={candidate.specialist_name} mode={candidate.mode}",
        ],
        metadata={
            "baseline_project_id": str(baseline.project.id),
            "candidate_project_id": str(candidate.project.id),
            "daw_mode": settings.daw_mode.value,
            "midi_specialist": getattr(settings, "midi_specialist", "deterministic"),
        },
    )
