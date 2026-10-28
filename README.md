# Private AI Music Producer

Local-first AI music production assistant. **Spec v1.1** — constraint-first briefs, role-locks, musical diffs, candidate packaging, **reference → stems → MIDI** pipeline. CIR/MIDI is the system of record; neural audio dual-path is allowed later without delaying models for product reasons.

> Phase 0–2 (simulation / MIDI manual-import). No live FL Studio claimed on Linux CI.  
> Default stems + transcription are **simulated/stub** — no large model downloads.

## Requirements

- Python **3.11** or **3.12**
- `ffmpeg` recommended for MP3/FLAC/M4A import (WAV works without it)
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

### Phase 1 demo (compose / revise)

```bash
music-ai doctor
music-ai templates
music-ai brief "mellow Afrobeats 110 BPM in A minor with Rhodes chords"
music-ai compose "mellow Afrobeats 110 BPM in A minor" --seed 42
music-ai revise <project-id> "keep the drums, soften bass" --seed 43
```

### Phase 2 demo (reference pipeline)

```bash
# synthetic fixture (or pass any legally held WAV/MP3/FLAC/M4A)
python -c "from pathlib import Path; from backend.app.audio.io import synth_tone_wav; synth_tone_wav(Path('workspace/demo_ref.wav'), duration_sec=6, bpm=110)"

music-ai ref-pipeline workspace/demo_ref.wav --license-class owned \
  --borrow bass_bounce --borrow drums --lock-bass \
  --prompt "mellow Afrobeats with this bass bounce"

# stepwise:
# music-ai import-ref … && music-ai analyse <id> && music-ai separate <id>
# music-ai transcribe <id> --stem bass && music-ai profile <id>
```

Outputs under `workspace/references/<id>/`, `workspace/stems/<id>/`, plus MIDI candidates.

Optional real models (manual, user-approved): [docs/audio-models.md](docs/audio-models.md).

### Tests

```bash
pytest
```

## What's in Phase 2

**Real:** Reference import (hash + rights + immutable store), numpy BPM/key/groove estimates, simulation stem separator, stub transcription → editable MIDI, ReferenceProfile, stem→role (+ lock), borrow chips on briefs, CLI pipeline.

**Simulated / stubbed:** Demucs (optional adapter, no auto-download), Basic Pitch (same), embeddings, live PostFader, full UI.

**Still from Phase 1:** BriefDocument, genre templates, generators, role-locks, MusicalDiff, CandidatePackage, FakeDaw / midi_export, critic PatchOp stubs.

## Docs

- [Architecture](docs/architecture.md)
- [Audio models (optional Demucs / Basic Pitch)](docs/audio-models.md)
- [Tool capabilities](docs/tool-capabilities.md)
- [macOS + FL Studio setup](docs/setup-macos-fl-studio.md)
- [PHASE_0_REPORT.md](PHASE_0_REPORT.md) · [PHASE_1_REPORT.md](PHASE_1_REPORT.md) · [PHASE_2_REPORT.md](PHASE_2_REPORT.md)
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)

## Config

See `.env.example`. `DAW_MODE=simulation|midi_export|postfader`.  
`MUSIC_AI_SEPARATOR=simulation` · `MUSIC_AI_TRANSCRIBER=stub`.  
Keep `ALLOW_CLOUD_AUDIO=false` unless you opt in.

## Safety

- No large model installs without approval.
- Simulation success ≠ live FL control.
- Separated stems / transcribed MIDI inherit reference rights — unknown ≠ cleared for release.
- `workspace/`, `.env`, and user audio are gitignored.
