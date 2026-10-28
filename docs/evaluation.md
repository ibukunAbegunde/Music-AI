# Evaluation & critic (Phase 4)

Simulation-first render evaluation and typed critic patches. Live bounce metrics are out of scope until PostFader is probed on macOS.

## Dimensions (never collapsed)

1. **Technical** — clipping, silence, loudness vs −14 LUFS target, excess sub, stereo imbalance, hot velocity proxy.
2. **Musical** — empty roles, density, kick/bass overlap, groove grid error, end-of-loop fill.
3. **Brief/reference fit** — partial via musical heuristics + conditioning notes; dedicated fit scorer deferred.
4. **Personal preference** — deferred (Phase 5).

Each dimension yields separate `Evaluation` rows (`technical.*` / `musical.*`). `Scoreboard` keeps `technical` and `musical` aggregates distinct.

## Metrics sources

| Source | When |
|--------|------|
| CIR simulation | Default — derive proxies from notes/drums/velocities |
| Fixture JSON | `tests/fixtures/renders/*.json` overlay for CI / demos |
| Live bounce | Not available on Linux CI |

Fixture overlays influence **critic proposals** only while CIR still shows fails. Once the CIR scoreboard is healthy (`any_fail` clear), the revision loop **drops the fixture overlay** so final next-moves are not sticky fixture ghosts. **Measured improvement** always re-scores via CIR simulation so PatchOps remain falsifiable without audio. When `revise-loop --apply --fixture …` runs, matching CIR defects are seeded from the fixture (`seed_cir_defects_from_fixture`) so the scoreboard can actually move.

## Critic contract

- Actionable output = validated `DawOperation` / `PatchOp` list (≤3 next moves for the playback loop).
- Free-text `explanation` / `findings_summary` are annotations only.
- Locked roles are never targeted; applicator rejects lock violations.

## Revision loop

```
evaluate → critique (≤3 ops) → [user confirm | --apply] → patch CIR → re-score
  → accept if improved() else FakeDaw/CIR rollback
```

CLI: `music-ai critique`, `music-ai revise-loop`, `music-ai restore`.

## Fixtures

- `hot_clipping` — peaks / hot velocity → `soften_velocity`
- `muddy_sub` — excess sub + kick/bass stack → soften / nudge; missing end fill
- `healthy_loop` — clean baseline
