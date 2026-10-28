# Phase 3 report — reference-conditioned compositions (v1.1)

Date: 2026-10-28  
Branch: `cursor/phase-3-ref-conditioned-b20d`  
Base: `main` @ `24a3869` (Phase 0–2 merged; rebased)  
Host: Ubuntu cloud VM — FL Studio / PostFader / IAC = **N/A**

## Verdict

Phase 3 **simulation exit met**. Reference (fixture or Phase 2 `ReferenceProfile`) → borrow-chip conditioning (`BorrowTrait`-aligned) → novel **8–16 bar** MIDI as **N CandidatePackages** (seed + CIR + loudness notes + one-line diff) → **A/B via MIDI preview proxies** + musical diff → **`keep drums, replace bass`** revision with locks verified → recipe apply + version timeline. Fixture analyzer remains for demos without a live file. Live audio render not claimed.

## Phase 2 dependency

| Item | Status |
|------|--------|
| `ReferenceProfile` / `ReferenceAsset` / `BorrowTrait` / `BorrowChip` | On `main` (Phase 2); Phase 3 conditions on chips |
| `ReferenceAnalyzer` protocol + `FixtureReferenceAnalyzer` | Phase 3 stub (real pipeline via `ref-pipeline`) |
| Real import → separate → analyse | ✅ Phase 2 on `main` (sim stems / stub transcription) |
| Stem → role → lock UX | ✅ Phase 2; Phase 3 enforces locks in revise/candidates |

Borrow-trait aliases (`chord_feel`→`chords`, `groove_swing`→`groove`, `energy_curve`→`energy`) normalize onto Phase 2 `BorrowTrait`.

## What is real

| Item | Status |
|------|--------|
| Borrow-trait conditioning (`bass_bounce`, `percussion_texture`, …) | Real knobs → generators |
| N candidates with explicit seeds | Real (`generate_candidates`) |
| Recipe apply seeds brief + locks + CIR locked MIDI | Real; locked track events replayed from `cir_snapshot_ref` |
| A/B path (MIDI proxies + PreferenceComparison) | Real; audio path ready when `Render.audio_path` exists |
| Musical diff in A/B + revise | Real CIR diff |
| Version timeline + restore helper | Real |
| `keep drums, replace bass` | Real role-lock revise |
| FakeDaw / midi_export | Real |
| pytest | **46 passed** |

## What is stubbed / deferred

| Item | Notes |
|------|-------|
| Live reference DSP / stems | Fixture default on `ref-compose`; real Phase 2 pipeline via `ref-pipeline` |
| Loudness-normalized WAV bounce | `loudness_notes` + `midi_proxy` status |
| Neural audio dual-path | Allowed by v1.1; not installed |
| React brief / A-B UI | CLI surfaces |
| Critic PatchOps | ✅ Phase 4 on `main` (eval-driven typed PatchOps) |

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
