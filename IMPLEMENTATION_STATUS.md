# Implementation status

Last updated: 2026-10-28  
Spec: **v1.1** (Agent Store)  
Current phase: **Phase 2 — audio reference pipeline (simulation)**

## Phase checklist

| Phase | Name | Status |
|-------|------|--------|
| 0 | Environment & feasibility | ✅ Implemented (simulation / manual-import) |
| 1 | DAW control & generated beat | ✅ Implemented (FakeDaw + midi_export; live FL blocked) |
| 2 | Audio reference pipeline | ✅ Implemented (simulation stems + stub transcription) |
| 3 | Reference-conditioned compositions | ❌ Not started |
| 4 | Critic + multi-iteration | ❌ Not started (PatchOp stub only) |
| 5 | Personal taste model | ❌ Not started |
| 6 | Autonomous full-length | ❌ Not started |
| 7 | Research upgrades | ❌ Not started |

## Module status

| Module | Status | Verification |
|--------|--------|----------------|
| Domain schemas v0.3 (BorrowTrait, StemRoleMapping, profile fields) | ✅ | mock-tested |
| Genre templates library | ✅ | mock-tested |
| NL → BriefDocument parser | ✅ | mock-tested |
| Richer drum/bass/chord generators | ✅ | mock-tested |
| Role-locks + bar-lock merge + humanize | ✅ | mock-tested |
| MusicalDiff (count + pitch/content) | ✅ | mock-tested |
| CandidatePackage packaging (compose + revise) | ✅ | mock-tested |
| Compose + revise pipelines (genre_template_id persisted) | ✅ | mock-tested |
| FakeDaw verify/undo | ✅ | mock-tested |
| MidiExportAdapter | ✅ | mock-tested / manual-fallback |
| Critic → typed PatchOps | 🚧 stub heuristics (lock-aware) | mock-tested |
| Recipe save/load stubs + compose `recipe_id` | ✅ | mock-tested |
| Reference ingest (hash, rights, immutable store) | ✅ | mock-tested |
| Feature analysis (BPM/key/groove estimates) | ✅ | mock-tested |
| Stem separator interface + simulation adapter | ✅ | mock-tested |
| Demucs adapter | 🚧 optional stub (no auto-download) | refuses without install |
| Transcription interface + stub MIDI | ✅ | mock-tested |
| Basic Pitch adapter | 🚧 optional stub (no auto-download) | refuses without install |
| Borrow chips ↔ reference profile | ✅ | mock-tested |
| Stem → role → role-lock | ✅ | mock-tested |
| AuditionRequest / sound match | 🚧 schema stub | — |
| Listening journal | 🚧 schema only | — |
| Full brief-canvas UI | ❌ | — |
| Live PostFader / FL Studio | ❌ | blocked (N/A on Linux CI) |
| Audio embeddings (CLAP/MERT) | ❌ | deferred |

## Known limitations

- No live FL Studio on cloud Linux VM.
- Default stems are **simulated** band/transient splits — not Demucs; bleed expected.
- Default transcription is a **stub** heuristic — not Basic Pitch.
- Soften-bass / fill are heuristic revise ops, not a full PatchOp executor.
- Critic next-moves are stubs (not audio-informed).
- Recipe apply / seeding candidates deferred to Phase 3.
- Neural audio dual-path documented; models not installed (awaiting approval).
- MP3/FLAC/M4A decode requires ffmpeg on PATH.

## Next (Phase 3 prep)

1. Condition generators on borrow chips / reference groove features.
2. Multi-candidate packages with musical diff + loudness-matched A/B path.
3. “Keep drums, change bass” revision verified against stem→role locks.
4. Mac live probe for PostFader when user ready.
5. Optional Demucs / Basic Pitch only after explicit approval (see `docs/audio-models.md`).
