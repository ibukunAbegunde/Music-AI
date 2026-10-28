"""Technical + musical render evaluation (fixture + CIR simulation)."""

from __future__ import annotations

from backend.app.models.schemas import new_id
from backend.app.music.generators import generate_eight_bar_project
from backend.app.render_eval.evaluate import evaluate_project
from backend.app.render_eval.metrics import RenderMetrics, improved, scoreboard_from_evaluations
from backend.app.render_eval.musical import kick_bass_overlap, run_musical_checks
from backend.app.render_eval.simulate import list_fixtures, load_fixture, simulate_render_metrics
from backend.app.render_eval.technical import run_technical_checks


def test_fixtures_packaged() -> None:
    names = list_fixtures()
    assert "hot_clipping" in names
    assert "muddy_sub" in names
    assert "healthy_loop" in names
    hot = load_fixture("hot_clipping")
    assert hot["clipping_ratio"] > 0.01


def test_technical_clipping_fail() -> None:
    m = RenderMetrics(
        render_id=new_id(),
        peak_dbfs=0.5,
        clipping_ratio=0.05,
        velocity_hot_ratio=0.4,
        measured_lufs=-9.0,
    )
    ev = run_technical_checks(m)
    fails = {e.metric_name: e.value for e in ev if e.metric_name.endswith(".fail")}
    assert fails["technical.clipping.fail"] == 1.0
    assert fails["technical.hot_velocity.fail"] == 1.0
    score = next(e.value for e in ev if e.metric_name == "technical.score")
    assert score < 0.8


def test_technical_healthy() -> None:
    m = RenderMetrics(render_id=new_id())
    ev = run_technical_checks(m)
    assert all(e.value == 0.0 for e in ev if e.metric_name.endswith(".fail"))
    score = next(e.value for e in ev if e.metric_name == "technical.score")
    assert score > 0.85


def test_musical_checks_and_overlap() -> None:
    p = generate_eight_bar_project("Afrobeats 110", seed=3)
    m = simulate_render_metrics(p)
    assert abs(m.kick_bass_overlap_ratio - kick_bass_overlap(p)) < 1e-9
    ev = run_musical_checks(p, m)
    assert any(e.metric_name == "musical.score" for e in ev)


def test_fixture_overlay_on_simulation() -> None:
    p = generate_eight_bar_project("trap 140", seed=9)
    m = simulate_render_metrics(p, fixture_id="hot_clipping")
    assert m.source == "fixture"
    assert m.fixture_id == "hot_clipping"
    assert m.clipping_ratio >= 0.04
    bundle = evaluate_project(p, fixture_id="hot_clipping")
    assert bundle.scoreboard is not None
    assert bundle.scoreboard.technical_fail_count >= 1


def test_scoreboard_improved_helper() -> None:
    bad_m = RenderMetrics(
        render_id=new_id(),
        peak_dbfs=0.0,
        clipping_ratio=0.05,
        velocity_hot_ratio=0.4,
        measured_lufs=-6.0,
    )
    good_m = RenderMetrics(render_id=new_id())
    p = generate_eight_bar_project("pop 120", seed=1)
    before = scoreboard_from_evaluations(
        run_technical_checks(bad_m) + run_musical_checks(p, bad_m)
    )
    after = scoreboard_from_evaluations(
        run_technical_checks(good_m) + run_musical_checks(p, good_m)
    )
    assert improved(before, after)
    assert not improved(after, before)
