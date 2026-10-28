"""Combine technical + musical checks into a critique bundle."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.app.models.schemas import Evaluation, MusicProject, Render
from backend.app.render_eval.metrics import RenderMetrics, Scoreboard, scoreboard_from_evaluations
from backend.app.render_eval.musical import run_musical_checks
from backend.app.render_eval.simulate import simulate_render_metrics
from backend.app.render_eval.technical import run_technical_checks


@dataclass
class CritiqueBundle:
    project: MusicProject
    metrics: RenderMetrics
    render: Render
    evaluations: list[Evaluation] = field(default_factory=list)
    scoreboard: Scoreboard | None = None

    def model_dump(self) -> dict:
        return {
            "project_id": str(self.project.id),
            "version_id": str(self.project.version_id) if self.project.version_id else None,
            "metrics": self.metrics.model_dump(mode="json"),
            "render": self.render.model_dump(mode="json"),
            "evaluations": [e.model_dump(mode="json") for e in self.evaluations],
            "scoreboard": self.scoreboard.model_dump(mode="json") if self.scoreboard else None,
        }


def evaluate_project(
    project: MusicProject,
    *,
    fixture_id: str | None = None,
    fixture_dir: Path | None = None,
    metrics: RenderMetrics | None = None,
    audio_path: str | None = None,
) -> CritiqueBundle:
    """Run technical + musical checks. Uses fixtures/CIR simulation — no live bounce required."""
    m = metrics or simulate_render_metrics(
        project, fixture_id=fixture_id, fixture_dir=fixture_dir
    )
    render = Render(
        id=m.render_id,
        project_id=project.id,
        version_id=project.version_id or project.id,
        audio_path=audio_path,
        render_settings={
            "mode": m.source,
            "fixture_id": m.fixture_id,
            "simulation": True,
        },
        duration=m.duration_sec,
        analysed_metrics=m.model_dump(mode="json"),
        listening_status="simulated",
    )
    evaluations = run_technical_checks(m) + run_musical_checks(project, m)
    board = scoreboard_from_evaluations(evaluations)
    return CritiqueBundle(
        project=project,
        metrics=m,
        render=render,
        evaluations=evaluations,
        scoreboard=board,
    )


def persist_evaluation(
    bundle: CritiqueBundle,
    assets,
) -> Path:
    """Write render + evaluation artifacts under workspace/renders/."""
    pid = bundle.project.id
    rid = bundle.render.id
    assets.write_json(
        f"renders/{pid}/{rid}_metrics.json",
        bundle.metrics.model_dump(mode="json"),
    )
    assets.write_json(
        f"renders/{pid}/{rid}_evaluations.json",
        {
            "evaluations": [e.model_dump(mode="json") for e in bundle.evaluations],
            "scoreboard": bundle.scoreboard.model_dump(mode="json") if bundle.scoreboard else None,
        },
    )
    return assets.root / "renders" / str(pid) / f"{rid}_evaluations.json"
