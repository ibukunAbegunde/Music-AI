"""Technical mix checks — warnings, not absolute disqualifiers (spec §10)."""

from __future__ import annotations

from backend.app.models.schemas import Evaluation
from backend.app.render_eval.metrics import RenderMetrics

EVALUATOR = "technical_checks"
VERSION = "0.4.0"


def _eval(
    render_id,
    name: str,
    value: float,
    *,
    explanation: str,
    evidence: list[str] | None = None,
) -> Evaluation:
    return Evaluation(
        render_id=render_id,
        metric_name=name,
        value=value,
        evaluator_name=EVALUATOR,
        evaluator_version=VERSION,
        explanation=explanation,
        evidence_refs=evidence or [],
    )


def run_technical_checks(metrics: RenderMetrics) -> list[Evaluation]:
    """Produce per-check evaluations + an aggregate technical.score in [0,1]."""
    rid = metrics.render_id
    out: list[Evaluation] = []
    penalties = 0.0
    fails = 0

    # Clipping
    clip_fail = metrics.clipping_ratio > 0.01 or metrics.peak_dbfs > -0.3
    out.append(
        _eval(
            rid,
            "technical.clipping.fail",
            1.0 if clip_fail else 0.0,
            explanation=f"peak={metrics.peak_dbfs:.2f} dBFS, clip_ratio={metrics.clipping_ratio:.4f}",
            evidence=["peak_dbfs", "clipping_ratio"],
        )
    )
    if clip_fail:
        penalties += 0.25
        fails += 1

    # Unexpected silence
    silence_fail = metrics.silence_ratio > 0.35
    silence_warn = metrics.silence_ratio > 0.15
    out.append(
        _eval(
            rid,
            "technical.silence.fail",
            1.0 if silence_fail else 0.0,
            explanation=f"silence_ratio={metrics.silence_ratio:.3f}",
            evidence=["silence_ratio"],
        )
    )
    if silence_fail:
        penalties += 0.2
        fails += 1
    elif silence_warn:
        penalties += 0.08

    # Loudness vs target (-14 LUFS integrated typical)
    target = -14.0
    lufs_err = abs(metrics.measured_lufs - target)
    loud_fail = lufs_err > 8.0
    out.append(
        _eval(
            rid,
            "technical.loudness.fail",
            1.0 if loud_fail else 0.0,
            explanation=f"measured_lufs={metrics.measured_lufs:.2f} (target {target})",
            evidence=["measured_lufs"],
        )
    )
    if loud_fail:
        penalties += 0.15
        fails += 1
    else:
        penalties += min(0.12, lufs_err / 40.0)

    # Excess sub
    sub_fail = metrics.excess_sub_energy > 0.65
    out.append(
        _eval(
            rid,
            "technical.excess_sub.fail",
            1.0 if sub_fail else 0.0,
            explanation=f"excess_sub_energy={metrics.excess_sub_energy:.3f}",
            evidence=["excess_sub_energy"],
        )
    )
    if sub_fail:
        penalties += 0.12
        fails += 1
    elif metrics.excess_sub_energy > 0.4:
        penalties += 0.05

    # Stereo imbalance
    stereo_fail = metrics.stereo_imbalance > 0.55
    out.append(
        _eval(
            rid,
            "technical.stereo.fail",
            1.0 if stereo_fail else 0.0,
            explanation=f"stereo_imbalance={metrics.stereo_imbalance:.3f}",
            evidence=["stereo_imbalance"],
        )
    )
    if stereo_fail:
        penalties += 0.1
        fails += 1

    # Hot velocities (proxy for peaks when no audio)
    hot_fail = metrics.velocity_hot_ratio > 0.25
    out.append(
        _eval(
            rid,
            "technical.hot_velocity.fail",
            1.0 if hot_fail else 0.0,
            explanation=f"velocity_hot_ratio={metrics.velocity_hot_ratio:.3f}",
            evidence=["velocity_hot_ratio"],
        )
    )
    if hot_fail:
        penalties += 0.15
        fails += 1
    elif metrics.velocity_hot_ratio > 0.1:
        penalties += 0.05

    score = max(0.0, min(1.0, 1.0 - penalties))
    out.append(
        _eval(
            rid,
            "technical.score",
            score,
            explanation=f"aggregate technical health; fails={fails}",
            evidence=[f"fail_count={fails}"],
        )
    )
    return out
