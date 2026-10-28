# Architecture — Private AI Music Producer

Version: 0.2.0 (Phase 1) | Spec: build spec **v1.1** + `product-upgrades-v1.1.md` (Agent Store)

## Purpose

Local-first, reference-aware music production assistant for a single user on Apple Silicon + FL Studio. Creative intent flows through a **BriefDocument** (constraint-first canvas) into a **canonical intermediate representation (CIR)** (`MusicProject`), then adapters apply or export that state. Phase 0 delivered skeleton + FakeDaw + MIDI export. Phase 1 adds brief parser, genre templates, role-locks, musical diff, candidate packaging, revise/undo — still without live FL Studio or large models. Neural audio dual-path is allowed by v1.1; CIR remains system of record.

## High-level diagram

```
 CLI (Phase 0) / future Local API + UI
              |
     compose / orchestrator
       |            |              |
  generators    storage         daw adapters
  (drums/bass/  (SQLite +       FakeDaw | MidiExport | PostFader*
   chords/MIDI)  workspace/)
       \____________|______________/
              MusicProject (CIR)
```

\* PostFader is **not** available in the cloud Linux VM; documented for the user's Mac only.

## Domain modules (status)

| Module | Role | Phase 0 |
|--------|------|---------|
| `api` | Local HTTP / events | Deferred (CLI only) |
| `orchestrator` | Task state machine | Minimal compose pipeline |
| `llm` | Tool-using providers | Stub / unused |
| `audio` | Ingest, stems, features | Not started |
| `transcription` | Audio → MIDI | Not started |
| `music` | Theory, groove, generators, MIDI, brief, diff, coedit | **Phase 1 generators + brief + diff + locks** |
| `generation` | Symbolic / neural | Deterministic templates + genre pack |
| `taste` | Preference / ranking | Schema stubs only |
| `daw` | DAW adapters | **Fake + MIDI export** (+ verify/undo) |
| `agents` | Critic / planner | **PatchOp stub next-moves** |
| `render_eval` | Bounce analysis | Not started |
| `assets` | Sample/VST manifest | Workspace paths only |
| `storage` | SQLite, versions, blobs | **Projects + versions** |
| `ui` | React local UI | Not started |

## Core data contracts

Pydantic models in `backend/app/models/schemas.py` implement spec §4: `MusicProject`, `ReferenceAsset`, `ReferenceProfile`, `StemAsset`, `NoteEvent`, `DrumEvent`, `MusicTrack`, `Section`, `ProductionPlan`, `DawOperation`, `Render`, `PreferenceComparison`, `Evaluation`, `ProjectVersion`, `AssetManifest`. IDs are UUIDs; schema_version is `0.1.0`.

## State machine (project / job)

`CREATED → PLANNED → ANALYSING → COMPOSING → APPLYING → VERIFYING → RENDER_PENDING → EVALUATING → AWAITING_FEEDBACK → COMPLETED` plus `FAILED` / `CANCELLED` / `PAUSED`. Phase 0 compose path: `CREATED/COMPOSING → COMPLETED` with version + MIDI artifacts recorded.

## DAW adapter contract

Every method returns `{supported, attempted, succeeded, verified, observations, error, user_action_required}`. No optimistic “success” without verification.

| Adapter | Use |
|---------|-----|
| `FakeDawAdapter` | CI / simulation; in-memory project, snapshot/restore |
| `MidiExportAdapter` | Manual import: write `.mid` stems under `workspace/midi/` |
| `PostFaderAdapter` | Future — only after live capability probe on Mac |

## Persistence

- **SQLite** (`workspace/music_ai.db`): projects, versions, jobs.
- **Asset store** (`workspace/`): `projects/`, `midi/`, `renders/`, `stems/`, `references/`, `logs/`, `snapshots/` — gitignored.
- Original user audio must remain immutable once Phase 2 lands; Phase 0 does not ingest audio.

## Assumptions (Phase 0)

1. Development/CI runs on Linux cloud VM → **no FL Studio, PostFader, or IAC**.
2. Target production host is the user’s Apple Silicon Mac mini + FL Studio (version TBD; probe on device).
3. No large models, datasets, or cloud audio transmission without explicit user approval.
4. Generators are deterministic given `(prompt, seed)`; they are templates, not a trained composer.
5. MIDI export is the truthful fallback when DAW bridge is absent.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| DAW API limits / missing PostFader | Capability matrix + MIDI manual import |
| Claiming live control without probe | Simulation labels; `tool-capabilities.md` |
| Music rights / sampling | Rights fields on references; no scraping; Phase 0 generates original MIDI only |
| Overfitting “taste” later | Deferred; never collapse scores in Phase 0 |
| Workspace / secret leakage | `.gitignore`, `.env.example`, no credentials in repo |

## Staged acceptance (from spec §16)

- **Phase 0 exit:** capability docs + reproducible setup + tested 8-bar MIDI export ← *this slice*
- **Phase 1:** NL → editable MIDI in FL Studio **or** labelled manual-import + bounce path
- Later phases: references, stems, A/B, taste, full arrangement (see `IMPLEMENTATION_STATUS.md`)

## Config

Environment via `.env` / `Settings` (`backend/app/core/config.py`): `DAW_MODE=simulation|midi_export|postfader`, `WORKSPACE_DIR`, `DATABASE_URL`, privacy flags `ALLOW_CLOUD_*`.
