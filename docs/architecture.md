# Architecture — Private AI Music Producer

Version: 0.5.0 (Phase 0–6 + local API/UI) | Spec: build spec **v1.1** + `product-upgrades-v1.1.md` (Agent Store)

## Purpose

Local-first, reference-aware music production assistant for a single user on Apple Silicon + FL Studio. Creative intent flows through a **BriefDocument** (constraint-first canvas) into a **canonical intermediate representation (CIR)** (`MusicProject`), then adapters apply or export that state. Phase 2 adds reference ingest, feature estimates, stem separation adapters (default simulation), and pitched-stem transcription adapters (default stub) with stem→role mapping and borrow chips. Phase 3 adds reference-conditioned multi-candidate generation, A/B (MIDI proxies), recipe apply, and lock-honoring revise. Phase 4 adds `render_eval` (technical + musical), critic → typed PatchOps, and a bounded revision loop with measured improvement + rollback — still simulation / fixtures. Neural audio dual-path is allowed by v1.1; CIR remains system of record.

## High-level diagram

```
 CLI + Local FastAPI (`backend/app/api`) + Vite React UI (`frontend/`)
              |
  compose / full-compose / ref-pipeline / ref-compose / candidates / revise / ab / critique / revise-loop
       |              |                |              |              |
  conditioning   audio/*          storage         daw adapters   render_eval + critic
  + generators   ingest/analyse   (SQLite +       FakeDaw |      (fixtures / CIR sim
  brief/diff     separators/*     workspace/)     MidiExport |   → typed PatchOps)
  coedit/patch   transcription/*                  PostFader*)
  arrangement/*  (Phase 6 full-length)
       \____________|________________|______________|______________/
         MusicProject (CIR) + ReferenceProfile + CandidatePackage + ArrangementPlan
```

\* PostFader is **not** available in the cloud Linux VM; documented for the user's Mac only.  
\* `FixtureReferenceAnalyzer` remains available for Phase 3 demos without a live reference file.

## Domain modules (status)

| Module | Role | Status |
|--------|------|--------|
| `api` | Local HTTP (FastAPI) for React UI | **Shipped** — thin wrappers over compose / full / ref / A/B / jobs |
| `orchestrator` | Task state machine | Compose / reference / candidates / revise / revision_loop |
| `llm` | Tool-using providers | Stub / unused |
| `audio` | Ingest, analyse, stems + reference analyzer protocol/fixtures | **Phase 2** (sim) + Phase 3 fixtures |
| `transcription` | Audio → MIDI | **Phase 2** (stub default) |
| `music` | Theory, groove, generators, MIDI, brief, diff, coedit, conditioning, recipes, patch_apply | **Phase 1+3+4** |
| `generation` | Symbolic / neural | Deterministic + borrow conditioning |
| `taste` | Preference / ranking | PreferenceComparison on A/B; model later |
| `daw` | DAW adapters | Fake + MIDI export (+ verify/undo) |
| `agents` | Critic / planner | **Eval-driven typed PatchOps** (≤3 next moves) |
| `render_eval` | Bounce / mix analysis | **Technical + musical + fixtures** |
| `assets` | Sample/VST manifest | Workspace paths |
| `storage` | SQLite, versions, refs | Projects + versions + references + sessions + renders |
| `ui` | React local UI (Vite/TS) | **Shipped** — Workspace / References / Candidates / Jobs / Settings |

## Core data contracts

Pydantic models in `backend/app/models/schemas.py` (schema_version **0.3.0**): `MusicProject`, `ReferenceAsset`, `ReferenceProfile`, `StemAsset`, `StemRoleMapping`, `BorrowTrait` / `BorrowChip`, `NoteEvent`, `DrumEvent`, `MusicTrack`, `Section`, `BriefDocument`, `Recipe`, `CandidatePackage`, `MusicalDiff`, `PreferenceComparison`, `DawOperation`/`PatchOp`, …

## Phase 3 flow

1. **Phase 2 profile or fixture** → bind borrow traits (`BorrowTrait`) → `ConditioningPlan`
2. **N seeds** → CIR + MIDI + `CandidatePackage` each
3. **A/B** → MIDI proxies (or audio when present) + musical diff + optional preference
4. **Revise** → role-locks (`keep drums, replace bass`) → version + diff
5. **Recipe apply** → seed brief + locks + **replay locked MIDI from recipe CIR** → N candidates sharing that locked material

## Phase 4 flow

1. **Evaluate** CIR (and optional render fixture) → technical + musical scoreboard
2. **Critic** → ≤3 typed `DawOperation` / `PatchOp` (locked roles never targeted)
3. **Apply** via CIR `patch_apply` (reject-on-lock)
4. **Re-measure** → accept if `improved()`, else FakeDaw snapshot rollback
5. **Collaborative default** awaits `--apply`; `restore` CLI for version tip

## Reference pipeline (Phase 2)

```
import-ref → analyse → separate → transcribe → profile
     │          │          │           │
  immutable   BPM/key    StemSet    MIDI notes
  sha256+     groove     (sim/      + stem→role
  rights      estimates   demucs*)   (+ optional lock)
```

\* Demucs / Basic Pitch are optional adapters that **refuse** without local install — see `docs/audio-models.md`.

Borrow chips selected from `available_borrow_traits` bind onto `BriefDocument.borrow_chips` for Phase 3 conditioning.

Project status machine: `CREATED → PLANNED → ANALYSING → COMPOSING → APPLYING → VERIFYING → RENDER_PENDING → EVALUATING → AWAITING_FEEDBACK → COMPLETED` plus `FAILED` / `CANCELLED` / `PAUSED`. Phase 3 compose path: `COMPOSING → COMPLETED` with multi-version candidate session. Phase 4 loop adds `EVALUATING` ↔ apply/rollback.

## Persistence

- **SQLite** (`workspace/music_ai.db`): projects, versions, jobs, **references**.
- **Asset store** (`workspace/`): `projects/`, `midi/`, `renders/`, `stems/`, `references/` (+ `by_hash/`), `recipes/`, `logs/`, `snapshots/`, `models/` — gitignored.
- Original user audio is **immutable** after import (content hash verified).

## Assumptions

1. CI on Linux cloud VM → no FL Studio / PostFader / IAC; no large weight downloads.
2. Target production host: user’s Apple Silicon Mac mini + FL Studio (probe on device).
3. Default audio path is simulation/stub; neural models opt-in after approval.
4. Generators are deterministic given `(brief, seed, conditioning)`; they are templates, not a trained composer.
5. MIDI export / MIDI A/B proxies are the truthful fallback when DAW bounce is absent.
6. Critic scoreboard deltas use CIR simulation so PatchOps stay falsifiable without live bounce.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| DAW API limits / missing PostFader | Capability matrix + MIDI manual import |
| Claiming live control without probe | Simulation labels; `tool-capabilities.md` |
| Music rights / sampling | Rights fields on references; abstract borrow only |
| Phase 2/3 trait drift | Canonical `BorrowTrait` + aliases in conditioning |
| Overfitting “taste” later | Preference rows only; no ranking model yet |
| Workspace / secret leakage | `.gitignore`, `.env.example`, no credentials in repo |

## Staged acceptance (from spec §16)

- **Phase 0–1:** capability docs + brief → 8-bar MIDI + locks/diff ← *done*
- **Phase 2:** reference → stems (limitations) + editable MIDI + tempo/groove + role mapping ← *done (simulation)*
- **Phase 3:** reference → novel 8–16 bar MIDI, A/B, keep-drums replace-bass ← *done (simulation)*
- **Phase 4:** critic typed PatchOps + bounded loop + measured/confirmable improvement + rollback ← *done (simulation)*
- **Phase 5:** personal taste ranking + registry ← *done (simulation)*
- **Phase 6:** full arrangement / `full-compose` ← *done (simulation)*
- Later: Phase 7 research upgrades — see `IMPLEMENTATION_STATUS.md`

## Config

`DAW_MODE`, `WORKSPACE_DIR`, `DATABASE_URL`, `ALLOW_CLOUD_*`,  
`MUSIC_AI_SEPARATOR=simulation`, `MUSIC_AI_TRANSCRIBER=stub`.
