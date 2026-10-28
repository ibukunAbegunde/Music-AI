# Private AI Music Producer

Local-first AI music production assistant. **Spec v1.1** — constraint-first briefs, role-locks, musical diffs, candidate packaging, **reference → stems → MIDI** pipeline, reference-conditioned loops, **eval-driven critic → typed PatchOps**, **personal taste ranking**. CIR/MIDI is the system of record; neural audio dual-path is allowed later without delaying models for product reasons.

> Phase 0–5 (simulation / MIDI manual-import / render fixtures / taste sim encoder). No live FL Studio claimed on Linux CI.  
> Default stems + transcription + taste encoder are **simulated/stub** — no large model downloads.  
> Phase 3 can use fixture `ReferenceProfile` adapters or real Phase 2 profiles.  
> Phase 4 critic uses CIR simulation + optional render fixtures (`--fixture`).  
> Phase 5 ranking head trains on frozen sim embeds; activates only if holdout beats retrieval.

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

# Phase 4 critic / bounded revision loop (simulation + fixtures)
music-ai critique <project-id> --fixture hot_clipping
music-ai revise-loop <project-id> --fixture muddy_sub          # suggest-only (collaborative)
music-ai revise-loop <project-id> --apply --max-iters 3        # measured apply + rollback
music-ai restore <project-id> <version-id>
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

### Phase 3 demo (reference → candidates → A/B → revise)

```bash
music-ai ref-compose "original mellow Afrobeats with bass bounce" \
  --trait bass_bounce --trait percussion_texture --seed 42 --n 2 --bars 8
# paste project id:
music-ai ab <project-id> --choice b --reason "prefer B bass"
music-ai revise <project-id> "keep the drums, replace bass" --seed 99
music-ai versions <project-id>
music-ai recipe-save <project-id> --name "winner"
music-ai recipe-apply <recipe-id> --n 2 --seed 11
```

Outputs under `workspace/midi/<id>/`, `workspace/projects/<id>/` (metadata, brief, CIR, candidates, A/B, diffs), and `workspace/renders/<id>/`.

### Phase 5 demo (personal taste)

```bash
music-ai taste-simulate --n-projects 8 --pairs 4
music-ai taste-train          # activates only if holdout > retrieval
music-ai taste-eval
music-ai taste-registry
music-ai taste-profile
music-ai journal-add <project-id> "liked the bass" --rating 4 --tag bass
# after recipe-save --approved path / approved recipes:
music-ai style-vectors
music-ai taste-rollback       # previous checkpoint
```

A/B choices also land in the taste dataset:

```bash
music-ai compose "Afrobeats 110 BPM" --seed 42 --n 2
music-ai ab <project-id> --choice b --reason "prefer B bass"
```

### Tests

```bash
pytest
pytest tests/unit/test_taste_*.py tests/integration/test_phase5_taste.py
```

## What's implemented

**Real (sim):** Reference import (hash + rights + immutable store), numpy BPM/key/groove estimates, simulation stem separator, stub transcription → editable MIDI, ReferenceProfile, stem→role (+ lock), borrow chips (canonical `BorrowTrait` + aliases), BriefDocument, genre templates, conditioned generators, role-locks, MusicalDiff, multi-candidate packaging, A/B MIDI proxies, recipe apply with locked CIR MIDI replay, FakeDaw / midi_export, **eval-driven critic → typed PatchOps**, CIR PatchOp applicator, bounded revision loop with measured improvement + rollback (fixture overlays drop once CIR healthy), render fixtures, CLI.

**Stubbed / pending:** Demucs / Basic Pitch (optional adapters, no auto-download), embeddings, listening journal UI, audition-in-context, React UI, live PostFader, neural audio models.

## Docs

- [Architecture](docs/architecture.md)
- [Audio models (optional Demucs / Basic Pitch)](docs/audio-models.md)
- [Tool capabilities](docs/tool-capabilities.md)
- [macOS + FL Studio setup](docs/setup-macos-fl-studio.md)
- [Evaluation / critic](docs/evaluation.md)
- [PHASE_0_REPORT.md](PHASE_0_REPORT.md) · [PHASE_1_REPORT.md](PHASE_1_REPORT.md) · [PHASE_2_REPORT.md](PHASE_2_REPORT.md) · [PHASE_3_REPORT.md](PHASE_3_REPORT.md) · [PHASE_4_REPORT.md](PHASE_4_REPORT.md)
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)

## Config

See `.env.example`. `DAW_MODE=simulation|midi_export|postfader`.  
`MUSIC_AI_SEPARATOR=simulation` · `MUSIC_AI_TRANSCRIBER=stub`.  
Keep `ALLOW_CLOUD_AUDIO=false` unless you opt in.

## Safety

- No large model installs without approval.
- Simulation success ≠ live FL control.
- Separated stems / transcribed MIDI inherit reference rights — unknown ≠ cleared for release.
- Fixture references ≠ cleared sampling rights for release.
- `workspace/`, `.env`, and user audio are gitignored.
