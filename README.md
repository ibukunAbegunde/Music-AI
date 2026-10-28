# Private AI Music Producer

Local-first AI music production assistant (Phase 0). Describe a groove → get reproducible **8-bar drum / bass / chord MIDI** plus project metadata. FL Studio integration is adapter-based: **simulation** and **MIDI manual-import** work today; live PostFader control is for the user’s Apple Silicon Mac after probing.

> Phase 0 only. No stem separation, taste model, or live DAW writes are claimed.

## Requirements

- Python **3.11** or **3.12**
- macOS + FL Studio optional (required only for live DAW later)
- Linux CI / cloud agents run in **simulation mode** (FL Studio / PostFader / IAC = N/A)

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
mkdir -p workspace
```

### Doctor (safe environment checks)

```bash
python -m scripts.doctor
# or
music-ai doctor
music-ai probe-daw
```

### Generate an 8-bar loop

```bash
music-ai compose "mellow Afrobeats 110 BPM in A minor" --seed 42
```

MIDI lands in `workspace/midi/<project-id>/` (`drums.mid`, `bass.mid`, `chord.mid`, `combined.mid`). Metadata: `workspace/projects/<project-id>/metadata.json`.

Manual-import mode (explicit FL Studio instructions):

```bash
music-ai compose "Amapiano 112 BPM" --seed 7 --mode midi_export
```

### Tests

```bash
pytest
```

## Project layout

```
backend/app/          # schemas, music generators, daw adapters, CLI, storage
docs/                 # architecture, capabilities, macOS+FL setup
scripts/doctor.py     # environment probe
tests/                # unit + integration
workspace/            # gitignored local DB, MIDI, future audio
IMPLEMENTATION_STATUS.md
PHASE_0_REPORT.md
```

## Configuration

See `.env.example`. Important flags:

| Variable | Meaning |
|----------|---------|
| `DAW_MODE` | `simulation` (default) \| `midi_export` \| `postfader` (Mac only, after probe) |
| `WORKSPACE_DIR` | Local artifact root (default `workspace`) |
| `ALLOW_CLOUD_AUDIO` | Keep `false` unless you opt in |
| `ALLOW_CLOUD_LLM` | Keep `false` unless you opt in |

## Docs

- [Architecture](docs/architecture.md)
- [Tool capabilities](docs/tool-capabilities.md)
- [macOS + FL Studio setup](docs/setup-macos-fl-studio.md)
- [Phase 0 report](PHASE_0_REPORT.md)
- [Implementation status](IMPLEMENTATION_STATUS.md)

## Safety

- No large model installs or dataset downloads in Phase 0.
- No user audio or credentials in git (`workspace/`, `.env`, media extensions ignored).
- Do not treat simulation success as live FL Studio control.
