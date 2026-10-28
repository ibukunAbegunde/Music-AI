# Implementation status

Last updated: 2026-10-28  
Spec: **v1.1** (Agent Store)  
Current phase: **Phase 1 — DAW control & generated beat (simulation)**

## Phase checklist

| Phase | Name | Status |
|-------|------|--------|
| 0 | Environment & feasibility | ✅ Implemented (simulation / manual-import) |
| 1 | DAW control & generated beat | ✅ Implemented (FakeDaw + midi_export; live FL blocked) |
| 2 | Audio reference pipeline | ❌ Not started |
| 3 | Reference-conditioned compositions | ❌ Not started |
| 4 | Critic + multi-iteration | ❌ Not started (PatchOp stub only) |
| 5 | Personal taste model | ❌ Not started |
| 6 | Autonomous full-length | ❌ Not started |
| 7 | Research upgrades | ❌ Not started |

## Module status

| Module | Status | Verification |
|--------|--------|----------------|
| Domain schemas v0.2 (Brief, Recipe, Candidate, MusicalDiff, PatchOp, …) | ✅ | mock-tested |
| Genre templates library | ✅ | mock-tested |
| NL → BriefDocument parser | ✅ | mock-tested |
| Richer drum/bass/chord generators | ✅ | mock-tested |
| Role-locks + bar-lock + humanize | ✅ | mock-tested |
| MusicalDiff | ✅ | mock-tested |
| CandidatePackage packaging | ✅ | mock-tested |
| Compose + revise pipelines | ✅ | mock-tested |
| FakeDaw verify/undo | ✅ | mock-tested |
| MidiExportAdapter | ✅ | mock-tested / manual-fallback |
| Critic → typed PatchOps | 🚧 stub heuristics | mock-tested |
| Recipe persistence UI | 🚧 schema only | — |
| AuditionRequest / sound match | 🚧 schema stub | — |
| Listening journal | 🚧 schema only | — |
| Full brief-canvas UI | ❌ | — |
| Live PostFader / FL Studio | ❌ | blocked (N/A on Linux CI) |
| Stem separation / embeddings | ❌ | — |

## Known limitations

- No live FL Studio on cloud Linux VM.
- Soften-bass / fill are heuristic revise ops, not a full PatchOp executor.
- Critic next-moves are stubs (not audio-informed).
- Recipe save/load CLI not wired (schema present).
- Neural audio dual-path documented in spec; not installed (awaiting approval).

## Next (Phase 2 prep)

1. Reference import + stem→role mapping.
2. Borrow chips wired to real reference profiles.
3. Mac live probe for PostFader when user ready.
