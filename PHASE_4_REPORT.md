# Phase 4 report — Critic + multi-iteration workflows

Date: 2026-10-28  
Spec: **v1.1** (`ai-music-producer-build-spec.md` §16 Phase 4 + `product-upgrades-v1.1.md` §5–6)  
Mode: **simulation** (FakeDaw + CIR-derived / fixture render metrics). No live FL Studio.

## Exit criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Technical render checks | ✅ | `backend/app/render_eval/technical.py` + fixtures |
| Musical consistency heuristics | ✅ | `backend/app/render_eval/musical.py` on CIR |
| Critic emits **typed PatchOps only** | ✅ | `critique_project` → `DawOperation` / `PatchOp`; essays are annotations only |
| Playback-centric ≤3 next moves | ✅ | `CriticResult.next_moves` capped at 3; CLI `critique` / `revise-loop` |
| Bounded revision loops | ✅ | `run_revision_loop(max_iterations≤policy)` |
| Measured or user-confirmable improvement | ✅ | Scoreboard compare via `improved()`; collaborative default awaits `--apply` |
| Rollback verified | ✅ | Per-iter FakeDaw snapshot restore + `restore` CLI + tests |
| Simulation / fixtures (Phases 2–3 not required) | ✅ | `tests/fixtures/renders/*.json`; CIR metric simulation |

## What shipped

- **`render_eval`**: `RenderMetrics`, technical checks, musical heuristics, fixture overlay, CIR simulation bounce.
- **Critic (Phase 4)**: evaluation → validated PatchOps (`soften_velocity`, `scale_velocity`, `quantize_role`, `add_fill`, `reduce_density`, `nudge_bass_off_kick`, `regenerate_role`, `humanize_role`); locked roles never targeted.
- **`patch_apply`**: CIR applicator with reject-on-lock.
- **`revision_loop`**: evaluate → ≤3 ops → apply → re-measure → accept or rollback; suggest-only without `--apply`.
- **CLI**: `music-ai critique`, `revise-loop`, `restore`.
- **Tests**: unit (eval/critic/patch) + integration (improvement, undo, locks, fixtures).

## Non-claims

- No live bounce / PostFader / loudness from real audio — metrics are simulated or fixture-based.
- No personal taste model (Phase 5).
- No essay-only critic path as the actionable artifact.
- Rebased onto Phase 2–3 main; loop remains fixture-friendly when no live bounce.

## How to demo

```bash
pip install -e ".[dev]"
pytest tests/unit/test_render_eval.py tests/unit/test_patch_apply_and_critic.py tests/integration/test_phase4_revision_loop.py
music-ai compose "Afrobeats 110 BPM in A minor" --seed 41
music-ai critique <project-id> --fixture hot_clipping
music-ai revise-loop <project-id> --fixture muddy_sub          # suggest-only
music-ai revise-loop <project-id> --apply --fixture hot_clipping --max-iters 3
# → measured improve + per-iter rollback; music-ai restore <id> <version>
```

## Verification labels

| Path | Label |
|------|-------|
| Critic PatchOps + revision loop | `mock-tested` (simulation) |
| Render metrics | `mock-tested` (fixture / CIR simulation) |
| Live FL bounce eval | `blocked` (N/A on Linux CI) |
