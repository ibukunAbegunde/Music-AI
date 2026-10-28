# Phase 3 report — reference-conditioned compositions (v1.1)

Date: 2026-10-28  
Branch: `cursor/phase-3-ref-conditioned-b20d`  
Base: `main` (Phase 0–1 merged)  
Host: Ubuntu cloud VM — FL Studio / PostFader / IAC = **N/A**

## Verdict

Phase 3 **simulation exit met**. Reference (fixture `ReferenceProfile`) → borrow-chip conditioning → novel **8–16 bar** MIDI as **N CandidatePackages** (seed + CIR + loudness notes + one-line diff) → **A/B via MIDI preview proxies** + musical diff → **`keep drums, replace bass`** revision with locks verified → recipe apply + version timeline. **Phase 2 not on main** — adapters/schemas first; fixture analyzer stands in. Live audio render not claimed.

## Phase 2 dependency

| Item | Status |
|------|--------|
| `ReferenceProfile` / `ReferenceAsset` / `BorrowChip` schemas | Shared (Phase 1+); Phase 3 consumes |
| `ReferenceAnalyzer` protocol + `FixtureReferenceAnalyzer` | Phase 3 stub |
| Real import → separate → analyse → embeddings | **Waiting on Phase 2 PR** — rebase/wire when present |
| Stem → role → lock UX | Deferred to Phase 2; Phase 3 enforces locks in revise/candidates |

Documented on CLI (`ref-compose` Phase 2 note) and in candidate session JSON (`phase2_dependency`).

## What is real

| Item | Status |
|------|--------|
| Borrow-trait conditioning (`bass_bounce`, `percussion_texture`, …) | Real knobs → generators |
| N candidates with explicit seeds | Real (`generate_candidates`) |
| Recipe apply seeds brief + locks | Real; locked roles identical across candidates |
| A/B path (MIDI proxies + PreferenceComparison) | Real; audio path ready when `Render.audio_path` exists |
| Musical diff in A/B + revise | Real CIR diff |
| Version timeline + restore helper | Real |
| `keep drums, replace bass` | Real role-lock revise |
| FakeDaw / midi_export | Real |
| pytest | **46 passed** |

## What is stubbed / deferred

| Item | Notes |
|------|-------|
| Live reference DSP / stems | Fixture profiles only |
| Loudness-normalized WAV bounce | `loudness_notes` + `midi_proxy` status |
| Neural audio dual-path | Allowed by v1.1; not installed |
| React brief / A-B UI | CLI surfaces |
| Critic PatchOps | Still heuristic stubs (Phase 4) |

## Demo

```bash
pip install -e ".[dev]"
music-ai ref-compose "original mellow Afrobeats with bass bounce" \
  --trait bass_bounce --trait percussion_texture --seed 42 --n 2 --bars 8
music-ai ab <project-id> --choice b --reason "prefer B"
music-ai revise <project-id> "keep the drums, replace bass" --seed 99
music-ai versions <project-id>
music-ai recipe-save <project-id> --name "winner"
music-ai recipe-apply <recipe-id> --n 2 --seed 11
```

## Spec alignment (v1.1 Phase 3 exit)

- [x] Borrow chips condition generation (abstract features, not copy)
- [x] Multiple original 8–16 bar loops as CandidatePackages
- [x] A/B + musical diff (MIDI proxies when no render)
- [x] Targeted revision honors locks (`keep drums, replace bass`)
- [x] Recipe apply
- [x] Version timeline + musical diff
- [x] Creative KPI note: measure in listening sessions (&lt;15 min / ≤3 prompts) — not a CI gate; log in eval docs later
- [ ] Live FL / real stem pipeline (Phase 2 + Mac probe)

## Creative eval KPI

Session KPI (&lt;15 min / ≤3 prompts) is a **listening-session** metric, not automated here. CLI path above is ≤3 prompts for a usable MIDI idea in simulation.
