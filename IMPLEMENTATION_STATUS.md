# Implementation status

Last updated: 2026-10-28  
Spec: **v1.1** (Agent Store)  
Current phase: **Phase 3 — reference-conditioned compositions (simulation)**

## Phase checklist

| Phase | Name | Status |
|-------|------|--------|
| 0 | Environment & feasibility | ✅ Implemented (simulation / manual-import) |
| 1 | DAW control & generated beat | ✅ Implemented (FakeDaw + midi_export; live FL blocked) |
| 2 | Audio reference pipeline | ✅ Implemented (simulation stems + stub transcription) |
| 3 | Reference-conditioned compositions | ✅ Implemented (simulation; MIDI A/B proxies) |
| 4 | Critic + multi-iteration | ❌ Not started (PatchOp stub only) |
| 5 | Personal taste model | ❌ Not started |
| 6 | Autonomous full-length | ❌ Not started |
| 7 | Research upgrades | ❌ Not started |

## Module status

| Module | Status | Verification |
|--------|--------|----------------|
| Domain schemas v0.3 (BorrowTrait, StemRoleMapping, Brief, Recipe, Candidate, MusicalDiff, PatchOp, …) | ✅ | mock-tested |
| Genre templates library | ✅ | mock-tested |
| NL → BriefDocument parser | ✅ | mock-tested |
| Richer drum/bass/chord generators + conditioning | ✅ | mock-tested |
| Role-locks + bar-lock merge + humanize | ✅ | mock-tested |
| MusicalDiff (count + pitch/content) | ✅ | mock-tested |
| CandidatePackage packaging (compose + revise + multi) | ✅ | mock-tested |
| Compose + revise + replace-bass (genre_template_id persisted) | ✅ | mock-tested |
| N-candidate exploration + seeds | ✅ | mock-tested |
| Borrow-trait conditioning (aligned to `BorrowTrait`) | ✅ | mock-tested |
| `ReferenceAnalyzer` + FixtureReferenceAnalyzer | ✅ stub | mock-tested |
| A/B compare (MIDI proxy / audio-ready) | ✅ | mock-tested |
| Recipe save/load/**apply** | ✅ | mock-tested |
| Version timeline + restore | ✅ | mock-tested |
| FakeDaw verify/undo | ✅ | mock-tested |
| MidiExportAdapter | ✅ | mock-tested / manual-fallback |
| Critic → typed PatchOps | 🚧 stub heuristics (lock-aware) | mock-tested |
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
- Soften-bass / fill / replace-bass are heuristic revise ops, not a full PatchOp executor.
- Critic next-moves are stubs (not audio-informed).
- A/B uses MIDI preview proxies until bounce WAVs exist (`loudness_notes.normalization_status=midi_proxy`).
- Neural audio dual-path documented; models not installed (awaiting approval).
- MP3/FLAC/M4A decode requires ffmpeg on PATH.

## Next

1. Phase 4: critic typed PatchOps + playback-centric ≤3 next moves with measured improvement.
2. Wire real Phase 2 profiles into `ref-compose` (fixture analyzer remains available).
3. Mac live probe for PostFader when user ready.
4. Optional Demucs / Basic Pitch only after explicit approval (see `docs/audio-models.md`).
