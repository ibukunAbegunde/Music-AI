# Private AI Music Producer

Local-first AI music production assistant. **Spec v1.1** — constraint-first briefs, role-locks, musical diffs, candidate packaging. CIR/MIDI is the system of record; neural audio dual-path is allowed later without delaying models for product reasons.

> Phase 0 + Phase 1 (simulation / MIDI manual-import). No live FL Studio claimed on Linux CI.

## Requirements

- Python **3.11** or **3.12**
- macOS + FL Studio optional (live DAW later)

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
mkdir -p workspace
pytest
```

### Phase 1 demo

```bash
music-ai doctor
music-ai templates
music-ai brief "mellow Afrobeats 110 BPM in A minor with Rhodes chords"
music-ai compose "mellow Afrobeats 110 BPM in A minor" --seed 42
music-ai compose "Amapiano 112 BPM" --seed 7 --mode midi_export

# Revise with role-locks (paste project id from compose output)
music-ai revise <project-id> "keep the drums, soften bass" --seed 43
```

Outputs under `workspace/midi/<id>/` and `workspace/projects/<id>/` (metadata, brief, CIR snapshot, candidate package, diffs).

### Tests

```bash
pytest
```

## What's in Phase 1

**Real:** BriefDocument parser, genre templates, richer generators, role-locks, MusicalDiff, CandidatePackage, FakeDaw verify/undo, MidiExport, compose/revise CLI, critic PatchOp stubs.

**Stubbed:** Recipe apply (save/load stubs wired), listening journal, audition-in-context, full PatchOp executor, React brief canvas / DAW drawer UI, live PostFader.

## Docs

- [Architecture](docs/architecture.md)
- [Tool capabilities](docs/tool-capabilities.md)
- [macOS + FL Studio setup](docs/setup-macos-fl-studio.md)
- [PHASE_0_REPORT.md](PHASE_0_REPORT.md) · [PHASE_1_REPORT.md](PHASE_1_REPORT.md)
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)

Product store (source of truth): build spec **v1.1** + `product-upgrades-v1.1.md`.

## Config

See `.env.example`. `DAW_MODE=simulation|midi_export|postfader`. Keep `ALLOW_CLOUD_AUDIO=false` unless you opt in.

## Safety

- No large model installs without approval.
- Simulation success ≠ live FL control.
- `workspace/`, `.env`, and user audio are gitignored.
