# Phase 0 report — environment and feasibility spike

Date: 2026-10-28  
Branch: `cursor/phase-0-environment-spike-5499`  
Agent host: Ubuntu 24.04 cloud VM (Linux x86_64), Python 3.12.3, ~15 GiB RAM

## Verdict

Phase 0 **foundation is complete in simulation / manual-import mode**. Live FL Studio / PostFader / IAC are **N/A on this host** and were not faked as working. Phase 1+ is **not** claimed complete.

## What runs here

| Capability | Status |
|------------|--------|
| `pip install -e ".[dev]"` | Works |
| `python -m scripts.doctor` | Reports OS/Python/memory; marks DAW N/A |
| `music-ai compose "<prompt>" --seed N` | Generates 8-bar drums/bass/chords, writes MIDI + metadata, SQLite rows |
| `music-ai compose ... --mode midi_export` | Same + explicit manual-import `user_action_required` |
| `music-ai probe-daw` | Fake + MIDI adapters; no live bridge |
| `pytest` | Unit + integration pass in simulation |

## What is simulated

- Entire DAW control surface via `FakeDawAdapter` (in-memory tracks, tempo, snapshots).
- Audio bounce (returns `user_action_required`; no synthetic WAV pretending to be a render).
- Genre/BPM/key intent (lightweight parser, not LLM).
- PostFader tool contracts — **not invented**; documented as unprobed.

## What needs user action (Mac mini)

1. Install Python 3.11/3.12 venv and this package (`docs/setup-macos-fl-studio.md`).
2. Enable IAC Driver if planning a MIDI/PostFader bridge.
3. Import generated `.mid` files into a **scratch** FL Studio project; set tempo; assign instruments.
4. Optionally evaluate PostFader against installed FL Studio version; update `docs/tool-capabilities.md` with real tool names after probe.
5. Approve before any large model download, FL Studio config changes, or cloud audio transmission.

## Artifacts produced by compose

Under gitignored `workspace/`:

- `midi/<project-id>/{drums,bass,chord,combined}.mid`
- `projects/<project-id>/metadata.json`
- `music_ai.db` (projects + versions)

## Exit criteria mapping (spec §16 Phase 0)

| Criterion | Met? |
|-----------|------|
| Repo skeleton, doctor, config loader | Yes |
| Inspect macOS/FL/PostFader/IAC via safe checks | Yes — documented N/A on Linux; Mac setup doc provided |
| Capability matrix in `docs/tool-capabilities.md` | Yes |
| Fake DAW + MIDI fallback | Yes |
| Reproducible tested 8-bar MIDI export | Yes |
| Setup instructions | Yes (`README.md`, `docs/setup-macos-fl-studio.md`) |

## How to run

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
pytest
music-ai doctor
music-ai compose "mellow Afrobeats 110 BPM in A minor" --seed 42
music-ai compose "Amapiano 112 BPM" --seed 7 --mode midi_export
```

## Next steps (Phase 1 — not started)

- Typed plan parser → MusicProject → adapter apply with verification/undo.
- Truthful path: live FL notes **or** labelled manual-import + bounce detection.
- Still no large models without approval.

## Blockers

- **Live DAW verification blocked** until user runs probes on Apple Silicon Mac.
- PostFader exact API unknown until installed version is inspected (do not hard-code method names).
