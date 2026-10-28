# Phase 1 report — DAW control & generated beat (v1.1)

Date: 2026-10-28  
Branch: `cursor/phase-1-brief-daw-slice-5499` (from Phase 0)  
Host: Ubuntu 24.04 cloud VM — FL Studio / PostFader / IAC = **N/A**

## Verdict

Phase 1 **simulation / midi_export exit met**. NL/brief → 8-bar editable MIDI via FakeDaw and MidiExportAdapter; role-locks + musical diff on revise; CandidatePackage (seed, CIR, loudness notes, one-line diff); brief canvas data model; genre templates; critic PatchOp stubs. **Phase 2+ not claimed. Live FL Studio not claimed.**

## What is real

| Item | Status |
|------|--------|
| `BriefDocument` + `music-ai brief` | Real parser |
| Genre templates | Real library |
| Generators (drums/bass/chords) | Real deterministic MIDI |
| Role-locks / merge / humanize | Real CIR ops |
| MusicalDiff | Real CIR diff |
| CandidatePackage | Real metadata on disk |
| FakeDaw snapshot/verify/undo | Real in-memory |
| MidiExport `.mid` files | Real Standard MIDI |
| `music-ai compose` / `revise` | Real CLI |
| pytest (36) | Passing |

## What is stubbed

| Item | Notes |
|------|-------|
| Critic next moves | Heuristic PatchOps, not render-aware |
| Recipe apply / kit panel | Schema + save/load stubs (`recipe-save` / `recipe-list`); apply in Phase 3 |
| AuditionRequest | Schema stub |
| Listening journal | Schema only |
| Brief canvas UI / DAW drawer / loop strip | Data model only; CLI surfaces |
| Full PatchOp executor | Soften-bass / keep-drums heuristics in revise |
| Live FL Studio / PostFader | N/A on this host |
| Loudness-normalized audio render | `loudness_notes` metadata; bounce = user action |
| Neural audio models | Not installed (allowed by v1.1 dual-path; awaiting approval) |

## How to run demo

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
pytest
music-ai templates
music-ai brief "mellow Afrobeats 110 BPM in A minor with Rhodes"
music-ai compose "mellow Afrobeats 110 BPM in A minor" --seed 42
music-ai compose "Amapiano 112 BPM" --seed 7 --mode midi_export
# after compose, revise (use printed project id):
music-ai revise <project-id> "keep the drums, soften bass" --seed 43
```

## Requires user's Mac

- Import MIDI into scratch FL project (`docs/setup-macos-fl-studio.md`)
- Live capability probe → update `docs/tool-capabilities.md`
- Approval before large models / FL config / cloud audio

## Blockers

- Live DAW verification blocked until Mac probe
- PR may be blocked if remote is still `agent_temp` (same as Phase 0)

## Spec alignment (v1.1 Phase 1 exit)

- [x] BriefDocument + NL parser  
- [x] Role-locks  
- [x] MusicalDiff + one-line summary  
- [x] CandidatePackage (seed, CIR, loudness notes, diff)  
- [x] Recipe schema stub  
- [x] FakeDaw + midi_export path with verify/undo  
- [x] Collaborative default  
- [x] Genre templates  
- [ ] Live FL Studio notes (N/A — truthful manual-import instead)
