# Phase 2 report — audio reference pipeline (v1.1)

Date: 2026-10-28  
Branch: `cursor/phase-2-audio-reference-pipeline-a016`  
Host: Ubuntu cloud VM — FL Studio / PostFader / IAC = **N/A**; large models **not** downloaded

## Verdict

Phase 2 **exit met in simulation mode**: reference upload → immutable store + rights → BPM/key/groove estimates → isolated stems (simulated, with limitations) → editable MIDI candidate (stub transcription) → reference profile + stem→role mapping + borrow chips on brief. **Live FL Studio not claimed. Demucs / Basic Pitch not installed** (documented optional enablement).

## What is real

| Item | Status |
|------|--------|
| Import WAV/MP3/FLAC/M4A (hash, rights, immutable `workspace/references/`) | Real (MP3/FLAC/M4A via ffmpeg when present) |
| Analysis WAV derivative (non-destructive) | Real |
| BPM / key / beat grid / groove features + confidence | Real numpy DSP **estimates** |
| Stem separator adapter interface | Real |
| Simulation stems (4-way band/transient split) | Real (labelled simulated) |
| Transcription adapter interface | Real |
| Stub pitched-stem → MIDI candidate | Real (editable `.mid`) |
| ReferenceProfile + borrow traits + stem→role (+ lock) | Real |
| CLI: `import-ref` / `analyse` / `separate` / `transcribe` / `profile` / `ref-pipeline` | Real |
| SQLite `references` table + workspace JSON | Real |
| pytest fixtures + unit/integration | Real |

## What is simulated / stubbed / optional

| Item | Notes |
|------|-------|
| Stem separation quality | **Simulation** — not Demucs; bleed expected |
| Transcription accuracy | **Stub** heuristic — not Basic Pitch |
| Demucs adapter | Raises unless installed + local weights; no auto-download |
| Basic Pitch adapter | Raises unless installed; no auto-download |
| librosa tempo path | Optional extra; off by default |
| Audio embeddings (CLAP/MERT) | Interface deferred; profile notes limitation |
| Live FL / PostFader | N/A on this host |
| Neural generative audio | Not installed (allowed later; CIR remains SoR) |

## How to run

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
pytest

# Synthetic demo (or any legally held WAV/MP3/FLAC/M4A)
python - <<'PY'
from pathlib import Path
from backend.app.audio.io import synth_tone_wav
synth_tone_wav(Path("workspace/demo_ref.wav"), duration_sec=6.0, bpm=110.0)
print("wrote workspace/demo_ref.wav")
PY

music-ai ref-pipeline workspace/demo_ref.wav --license-class owned \
  --borrow bass_bounce --borrow drums --lock-bass \
  --prompt "mellow Afrobeats with this bass bounce"

# Stepwise:
# music-ai import-ref … && music-ai analyse <id> && music-ai separate <id>
# music-ai transcribe <id> --stem bass && music-ai profile <id>
```

Enable real models later: see [docs/audio-models.md](docs/audio-models.md).

## Spec alignment (v1.1 Phase 2 exit)

- [x] Reference upload → isolated stems (with limitations)  
- [x] Editable MIDI candidate  
- [x] Tempo / groove summary  
- [x] Stem → role mapping (+ optional role-lock)  
- [x] Borrow chips wired to reference profile traits  
- [ ] Live FL Studio (N/A — truthful)  
- [x] No large model download; optional path documented  

## Blockers / next

- Mac live probe still required for FL claims  
- Phase 3: reference-conditioned generation honoring borrow chips + locks  
- User approval before Demucs / Basic Pitch / cloud audio  
