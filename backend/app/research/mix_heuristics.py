"""Advanced mix / mastering heuristic stubs (Phase 7).

Extends Phase 4 technical checks with simulation-first sidechain / stereo /
master-bus suggestions. No live mastering chain; no downloaded models.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from backend.app.models.schemas import MusicProject, new_id, utcnow
from backend.app.render_eval.evaluate import evaluate_project
from backend.app.render_eval.metrics import RenderMetrics


class MixHeuristic(BaseModel):
    id: str
    name: str
    severity: str  # info | warn | fail
    score: float  # 0..1 higher = healthier
    suggestion: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    cir_editable: bool = True


class AdvancedMixReport(BaseModel):
    id: str = Field(default_factory=lambda: str(new_id()))
    project_id: str | None = None
    source: str = "simulation"  # simulation | fixture | live
    heuristics: list[MixHeuristic] = Field(default_factory=list)
    overall_mix_score: float = 0.0
    notes: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())
    evaluator: str = "advanced_mix_heuristics"
    version: str = "0.7.0"


class AdvancedMixEngine(Protocol):
    name: str
    version: str

    def analyse(
        self,
        project: MusicProject,
        *,
        metrics: RenderMetrics | None = None,
    ) -> AdvancedMixReport: ...


class StubAdvancedMixHeuristics:
    """CIR/sim-derived mix suggestions — honest stubs, not a mastering AI."""

    name = "stub_advanced_mix"
    version = "0.7.0"

    def analyse(
        self,
        project: MusicProject,
        *,
        metrics: RenderMetrics | None = None,
    ) -> AdvancedMixReport:
        if metrics is None:
            bundle = evaluate_project(project)
            metrics = bundle.metrics

        heuristics: list[MixHeuristic] = []

        # Sidechain / kick-bass masking proxy
        overlap = float(metrics.kick_bass_overlap_ratio)
        sidechain_score = max(0.0, 1.0 - overlap * 1.5)
        heuristics.append(
            MixHeuristic(
                id="sidechain_proxy",
                name="Kick/bass masking (sidechain proxy)",
                severity="warn" if overlap > 0.35 else "info",
                score=sidechain_score,
                suggestion=(
                    "Consider ducking bass under kick (sidechain) or nudging bass off grid."
                    if overlap > 0.35
                    else "Kick/bass overlap within simulated comfort band."
                ),
                evidence={"kick_bass_overlap_ratio": overlap},
            )
        )

        # Stereo / mono compatibility proxy
        imb = float(metrics.stereo_imbalance)
        stereo_score = max(0.0, 1.0 - imb)
        heuristics.append(
            MixHeuristic(
                id="stereo_balance",
                name="Stereo balance",
                severity="warn" if imb > 0.4 else "info",
                score=stereo_score,
                suggestion=(
                    "Reduce hard L/R skew or check mono compatibility."
                    if imb > 0.4
                    else "Stereo balance looks centred (sim)."
                ),
                evidence={"stereo_imbalance": imb},
            )
        )

        # Master bus headroom / loudness
        peak = float(metrics.peak_dbfs)
        lufs = float(metrics.measured_lufs)
        headroom_ok = peak < -1.0 and abs(lufs + 14.0) < 6.0
        master_score = 1.0 if headroom_ok else max(0.0, 0.7 - abs(peak) * 0.02)
        if peak > -0.3:
            master_score = max(0.0, master_score - 0.35)
        heuristics.append(
            MixHeuristic(
                id="master_bus_headroom",
                name="Master bus headroom / loudness",
                severity="fail" if peak > -0.3 else ("warn" if not headroom_ok else "info"),
                score=master_score,
                suggestion=(
                    "Back off master gain / soft-clip; target ~−14 LUFS for A/B."
                    if not headroom_ok
                    else "Simulated master headroom near target."
                ),
                evidence={"peak_dbfs": peak, "measured_lufs": lufs},
            )
        )

        # Sub energy / mud
        sub = float(metrics.excess_sub_energy)
        sub_score = max(0.0, 1.0 - sub)
        heuristics.append(
            MixHeuristic(
                id="sub_mud",
                name="Excess sub / mud",
                severity="warn" if sub > 0.4 else "info",
                score=sub_score,
                suggestion=(
                    "High-pass non-bass roles; check kick/bass octave stacking."
                    if sub > 0.4
                    else "Sub energy within simulated band."
                ),
                evidence={"excess_sub_energy": sub},
            )
        )

        # Dynamic range proxy
        dr = float(metrics.dynamic_range_db)
        dr_score = 1.0 if 4.0 <= dr <= 14.0 else max(0.2, 1.0 - abs(dr - 8.0) / 12.0)
        heuristics.append(
            MixHeuristic(
                id="dynamic_range",
                name="Dynamic range (proxy)",
                severity="warn" if dr < 3.0 or dr > 18.0 else "info",
                score=dr_score,
                suggestion=(
                    "Over-compressed or overly quiet dynamics (sim)."
                    if dr < 3.0 or dr > 18.0
                    else "Dynamic range in a workable simulated band."
                ),
                evidence={"dynamic_range_db": dr},
            )
        )

        overall = sum(h.score for h in heuristics) / max(1, len(heuristics))
        return AdvancedMixReport(
            project_id=str(project.id),
            source=metrics.source,
            heuristics=heuristics,
            overall_mix_score=float(overall),
            notes=[
                "Advanced mix heuristics are simulation/CIR proxies — not a mastering AI.",
                "Live bounce metrics replace these when PostFader is probed on macOS.",
                "CIR remains editable SoR; mix suggestions map to PatchOps / manual DAW moves.",
            ],
        )


def run_advanced_mix_heuristics(
    project: MusicProject,
    *,
    metrics: RenderMetrics | None = None,
) -> AdvancedMixReport:
    return StubAdvancedMixHeuristics().analyse(project, metrics=metrics)
