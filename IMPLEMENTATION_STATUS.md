# Implementation status

Last updated: 2026-10-28  
Spec: **v1.1** (Agent Store)  
Current phase: **Phase 6 — Autonomous full-length (simulation / MIDI)**

## Phase checklist

| Phase | Name | Status |
|-------|------|--------|
| 0 | Environment & feasibility | ✅ Implemented (simulation / manual-import) |
| 1 | DAW control & generated beat | ✅ Implemented (FakeDaw + midi_export; live FL blocked) |
| 2 | Audio reference pipeline | ✅ Implemented (simulation stems + stub transcription) |
| 3 | Reference-conditioned compositions | ✅ Implemented (simulation; MIDI A/B proxies) |
| 4 | Critic + multi-iteration | ✅ Implemented (simulation + fixtures; eval-driven PatchOps) |
| 5 | Personal taste model | ✅ Implemented (simulation encoder + ranking head; no CLAP download) |
| 6 | Autonomous full-length | ✅ Implemented (sim/FakeDaw/MIDI; manual FL Playlist steps) |
| 7 | Research upgrades | ❌ Not started |

## Module status

| Module | Status | Verification |
|--------|--------|----------------|
| Domain schemas v0.3+ (BorrowTrait, StemRoleMapping, Brief, Recipe, Candidate, MusicalDiff, PatchOp, Taste*, …) | ✅ | mock-tested |
| Genre templates library | ✅ | mock-tested |
| NL → BriefDocument parser | ✅ | mock-tested |
| Richer drum/bass/chord generators + conditioning | ✅ | mock-tested |
| Role-locks + bar-lock merge + humanize | ✅ | mock-tested |
| MusicalDiff (count + pitch/content) | ✅ | mock-tested |
| CandidatePackage packaging (compose + revise + multi) | ✅ | mock-tested |
| Compose + revise + replace-bass (genre_template_id persisted) | ✅ | mock-tested |
| N-candidate exploration + seeds | ✅ | mock-tested |
| Borrow-trait conditioning (canonical `BorrowTrait` + aliases) | ✅ | mock-tested |
| `ReferenceAnalyzer` + FixtureReferenceAnalyzer | ✅ stub | mock-tested |
| A/B compare (MIDI proxy / audio-ready) → taste dataset | ✅ | mock-tested |
| Recipe save/load/**apply** (locked CIR MIDI replay) | ✅ | mock-tested |
| Version timeline + restore | ✅ | mock-tested |
| FakeDaw verify/undo | ✅ | mock-tested |
| MidiExportAdapter | ✅ | mock-tested / manual-fallback |
| Critic → typed PatchOps | ✅ | mock-tested (eval-driven + lock-aware) |
| PatchOp CIR applicator | ✅ | mock-tested |
| `render_eval` technical + musical | ✅ | mock-tested (fixtures + CIR sim) |
| Bounded revision loop + rollback | ✅ | mock-tested |
| Reference ingest (hash, rights, immutable store) | ✅ | mock-tested |
| Feature analysis (BPM/key/groove estimates) | ✅ | mock-tested |
| Stem separator interface + simulation adapter | ✅ | mock-tested |
| Demucs adapter | 🚧 optional stub (no auto-download) | refuses without install |
| Transcription interface + stub MIDI | ✅ | mock-tested |
| Basic Pitch adapter | 🚧 optional stub (no auto-download) | refuses without install |
| Borrow chips ↔ reference profile | ✅ | mock-tested |
| Stem → role → role-lock | ✅ | mock-tested |
| Pairwise taste dataset + listening journal | ✅ | mock-tested |
| Retrieval preference baseline | ✅ | mock-tested |
| Frozen-encoder ranking head (sim projection) | ✅ | mock-tested |
| Optional pretrained audio encoder (CLAP/MERT) | 🚧 stub refuses | no download without flag |
| Holdout-by-project eval + calibration | ✅ | mock-tested |
| Taste model registry / rollback | ✅ | mock-tested |
| Style vectors from approved recipes | ✅ | mock-tested |
| Full-song structure templates | ✅ | mock-tested |
| Arrangement engine (multi-section + intensity) | ✅ | mock-tested |
| `full-compose` brief/ref → MIDI + version | ✅ | mock-tested |
| Scratch vs Release compose gate | ✅ | mock-tested (Release blocks DAW write) |
| Instrument palette hints | ✅ | mock-tested |
| AuditionRequest / sound match | 🚧 schema stub | — |
| FastAPI local API (compose/revise/ref/full/jobs) | ✅ | mock-tested |
| React+Vite UI (Workspace / Refs / A/B / Jobs / Settings) | ✅ | build + API smoke |
| Brief canvas + role-lock controls (UI scaffold) | ✅ | wired to parse/compose/revise |
| Version timeline + A/B musical diff (UI) | ✅ | wired to existing services |
| DAW approval drawer UI | 🚧 stub next-moves list | — |
| Live loop strip / sound-library audition | ❌ | deferred |
| Live PostFader / FL Studio | ❌ | blocked (N/A on Linux CI) |
| Audio embeddings (CLAP/MERT) | 🚧 interface only | deferred (approval flag) |

## Known limitations

- No live FL Studio on cloud Linux VM; render metrics are CIR-simulated or fixture overlays.
- Default stems are **simulated** band/transient splits — not Demucs; bleed expected.
- Default transcription is a **stub** heuristic — not Basic Pitch.
- Fixture overlays drive critic *proposals* until CIR fails clear (then overlay drops); scoreboard deltas always use CIR simulation so PatchOps remain measurable.
- Recipe apply restores locked-track events from `cir_snapshot_ref` when the CIR file is present.
- Soften-bass / fill / replace-bass remain heuristic revise ops; PatchOp executor covers critic-loop ops.
- A/B uses MIDI preview proxies until bounce WAVs exist (`loudness_notes.normalization_status=midi_proxy`).
- Neural audio dual-path documented; models not installed (awaiting approval).
- MP3/FLAC/M4A decode requires ffmpeg on PATH.
- Taste frozen encoder defaults to **simulation CIR projection** — not CLAP/MERT. Ranking head is real numpy logistic; deploy gated on beating retrieval holdout.
- Style vectors require **approved** recipes with recoverable CIR; never invented.
- Phase 6 full-length uses simulation generators tiled across structure templates — not a learned long-form model.
- Live FL Playlist arrangement is **manual** (`docs/setup-macos-fl-studio.md#phase-6-full-length-import`).
- Release mode (collaborative) exports MIDI + plan but does not auto-write FakeDaw notes.

## Next

1. Phase 7 research upgrades (optional research track).
2. Wire live bounce metrics on Mac when PostFader probed.
3. Optional Demucs / Basic Pitch / audio encoder only after explicit approval (see `docs/audio-models.md`).
4. Collect real listening pairwise data to replace/augment `taste-simulate`.
5. Live loop strip + loudness-matched audition + DAW approval drawer polish.
