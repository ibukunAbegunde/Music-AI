# Phase 7 report — Research upgrades

Date: 2026-10-28  
Spec: **v1.1** (`ai-music-producer-build-spec.md` §16 Phase 7 + `product-upgrades-v1.1.md` §7 dual-path)  
Mode: **simulation-first** — interfaces, honest stubs, eval harnesses. **No** foundation-model downloads or train-from-scratch.

## Exit criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Specialist MIDI composition hooks | ✅ | `research/midi_specialist.py`; default = deterministic generators; optional neural refuses without flag |
| Action-effect / revision outcome scaffolding | ✅ | `RevisionOutcome` log + `HeuristicActionEffectPredictor`; revision loop persists outcomes |
| Advanced mix / mastering heuristics stubs | ✅ | `research/mix_heuristics.py` (sidechain/stereo/master/sub/DR proxies) |
| Optional vocal workflow stubs | ✅ | Guide-MIDI `StubVocalWorkflow`; neural vocal refuses without approval |
| Multi-DAW adapter interface beyond FakeDaw/MidiExport | ✅ | `daw/registry.py` + Ableton/Logic/Reaper/PostFader refuse stubs |
| Neural dual-path without abandoning CIR | ✅ | `research/dual_path.py` policy + side-artifact helper |
| Blind listening eval vs Phase 6 baseline | ✅ harness | `run_phase7_baseline_eval` + `BlindListeningHarness` — **simulation proxy**; real listening `not_run` in CI |
| No large model download / train-from-scratch | ✅ | All optional paths refuse without flags; no weights bundled |
| Cheap UI polish (MIDI audition + jobs cancel) | ✅ | `/midi-audition` stub + Workspace paths; Jobs cancel labeled status-only stub |
| Tests + status docs | ✅ | unit + integration; this report; `IMPLEMENTATION_STATUS.md` |

## What is real vs stub

| Piece | Reality |
|-------|---------|
| `MidiSpecialist` Protocol + deterministic adapter | **Real hook**; behavior = Phase 1–6 generators |
| Optional neural MIDI specialist | **Honest refuse** until `MUSIC_AI_ALLOW_SPECIALIST_DOWNLOAD` + future install |
| RevisionOutcome persistence | **Real** JSON under `workspace/research/action_effect/` |
| Action-effect predictor | **Heuristic stub** (mean historical Δ by action_type) — not trained |
| Advanced mix heuristics | **Sim/CIR proxies** — not a mastering AI / live bounce |
| Vocal guide MIDI | **Real CIR track** placeholder; no singing synthesis |
| Multi-DAW registry | **Real discovery**; non-Fake/MIDI adapters **refuse** live ops |
| Blind eval harness | **Real scaffolding**; CI preference_proxy ≠ listening study win |
| MIDI audition UI | **Path list + midi_proxy copy** — no in-browser audio decode |
| Jobs cancel | **SQLite status flip only** — does not abort in-flight work |

## What shipped

- `backend/app/research/` — midi_specialist, action_effect, mix_heuristics, vocal, dual_path, eval_harness, registry
- `backend/app/daw/registry.py` + `daw/stubs.py`
- Compose path uses `get_midi_specialist()`; revision loop appends `RevisionOutcome`
- CLI: `research-status`, `research-eval`, `action-effect-log`, `mix-heuristics`, `vocal-stub`, `list-daws`
- API: `/api/research/status`, `/api/research/eval`, `/api/projects/{id}/midi-audition`; jobs cancel returns `cancel_stub`
- UI: Workspace MIDI audition stub; Jobs cancel button + stub labeling
- Schemas: `MidiAuditionStub`
- Docs: this report; status / README / architecture / evaluation / audio-models / tool-capabilities

## Non-claims

- Simulation `preference_proxy` does **not** satisfy the product blind-listening exit by itself.
- Heuristic action-effect ≠ trained world model.
- Advanced mix stubs ≠ radio-ready mastering.
- Vocal guide MIDI ≠ synthesized / cloned vocals.
- Ableton/Logic/Reaper/PostFader stubs ≠ live DAW control.
- No foundation models downloaded or fine-tuned in this phase.

## How to verify

```bash
pip install -e ".[dev]"
pytest tests/unit/test_phase7_research.py tests/integration/test_phase7_research.py
pytest   # full suite

music-ai research-status
music-ai list-daws
music-ai research-eval "mellow Afrobeats 110 BPM" --seed 42
music-ai compose "Afrobeats 110" --seed 42
music-ai revise-loop <project-id> --apply --fixture muddy_sub
music-ai action-effect-log
music-ai mix-heuristics <project-id>
music-ai vocal-stub <project-id> --lyric "na na" --apply
```

## Verification labels

| Path | Label |
|------|-------|
| Specialist hook / outcomes / mix / vocal stub / multi-DAW / eval harness | `mock-tested` |
| Optional neural MIDI / vocal models | `blocked` until approved download |
| Real blind listening preference study | `manual-fallback` / not run in CI |
| Live multi-DAW control | `blocked` (Linux CI) |
