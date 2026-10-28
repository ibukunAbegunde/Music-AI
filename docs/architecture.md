# Architecture — Private AI Music Producer

Version: 0.3.0 (Phase 2) | Spec: build spec **v1.1** + `product-upgrades-v1.1.md` (Agent Store)

## Purpose

Local-first, reference-aware music production assistant for a single user on Apple Silicon + FL Studio. Creative intent flows through a **BriefDocument** (constraint-first canvas) into a **canonical intermediate representation (CIR)** (`MusicProject`), then adapters apply or export that state. Phase 2 adds reference ingest, feature estimates, stem separation adapters (default simulation), and pitched-stem transcription adapters (default stub) with stem→role mapping and borrow chips.

## High-level diagram

```
 CLI (Phase 0–2) / future Local API + UI
              |
     compose / reference pipeline / orchestrator
       |              |                |              |
  generators     audio/*          storage         daw adapters
  brief/diff     ingest/analyse   (SQLite +       FakeDaw | MidiExport | PostFader*
  coedit         separators/*     workspace/)
  transcription/*
       \____________|________________|______________/
              MusicProject (CIR) + ReferenceProfile
```

\* PostFader is **not** available in the cloud Linux VM; documented for the user's Mac only.

## Domain modules (status)

| Module | Role | Status |
|--------|------|--------|
| `api` | Local HTTP / events | Deferred (CLI only) |
| `orchestrator` | Task state machine | Compose + reference pipelines |
| `llm` | Tool-using providers | Stub / unused |
| `audio` | Ingest, analyse, stems | **Phase 2** (sim separator default) |
| `transcription` | Audio → MIDI | **Phase 2** (stub default) |
| `music` | Theory, groove, generators, MIDI, brief, diff, coedit | Phase 1 |
| `generation` | Symbolic / neural | Deterministic templates + genre pack |
| `taste` | Preference / ranking | Schema stubs only |
| `daw` | DAW adapters | Fake + MIDI export (+ verify/undo) |
| `agents` | Critic / planner | PatchOp stub next-moves |
| `render_eval` | Bounce analysis | Not started |
| `assets` | Sample/VST manifest | Workspace paths |
| `storage` | SQLite, versions, refs | Projects + versions + references |
| `ui` | React local UI | Not started |

## Core data contracts

Pydantic models in `backend/app/models/schemas.py` (schema_version **0.3.0** for references): `MusicProject`, `ReferenceAsset`, `ReferenceProfile`, `StemAsset`, `StemRoleMapping`, `BorrowTrait` / `BorrowChip`, `NoteEvent`, `DrumEvent`, `MusicTrack`, `Section`, `BriefDocument`, `Recipe`, `CandidatePackage`, `MusicalDiff`, `DawOperation`/`PatchOp`, …

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

## Persistence

- **SQLite** (`workspace/music_ai.db`): projects, versions, jobs, **references**.
- **Asset store** (`workspace/`): `projects/`, `midi/`, `renders/`, `stems/`, `references/` (+ `by_hash/`), `logs/`, `snapshots/`, `models/` — gitignored.
- Original user audio is **immutable** after import (content hash verified).

## Assumptions

1. CI on Linux cloud VM → no FL Studio / PostFader / IAC; no large weight downloads.
2. Target production host: user’s Apple Silicon Mac mini + FL Studio (probe on device).
3. Default audio path is simulation/stub; neural models opt-in after approval.
4. Generators remain deterministic given `(prompt, seed)` until Phase 3 conditions on profiles.
5. MIDI export remains the truthful DAW fallback.

## Staged acceptance (from spec §16)

- **Phase 0–1:** capability docs + brief → 8-bar MIDI ← done (simulation)
- **Phase 2:** reference → stems (limitations) + editable MIDI + tempo/groove + role mapping ← *this slice*
- **Phase 3+:** reference-conditioned candidates, A/B, taste, full arrangement

## Config

`DAW_MODE`, `WORKSPACE_DIR`, `DATABASE_URL`, `ALLOW_CLOUD_*`,  
`MUSIC_AI_SEPARATOR=simulation`, `MUSIC_AI_TRANSCRIBER=stub`.
