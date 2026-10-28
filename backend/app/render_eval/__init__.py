"""Render evaluation: technical checks + musical heuristics (Phase 4)."""

from backend.app.render_eval.evaluate import CritiqueBundle, evaluate_project
from backend.app.render_eval.metrics import RenderMetrics, scoreboard_from_evaluations
from backend.app.render_eval.simulate import simulate_render_metrics

__all__ = [
    "CritiqueBundle",
    "RenderMetrics",
    "evaluate_project",
    "scoreboard_from_evaluations",
    "simulate_render_metrics",
]
