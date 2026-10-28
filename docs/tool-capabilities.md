# Tool capabilities matrix

Last probed: 2026-10-28 (cloud Linux VM)  
Target production host: Apple Silicon Mac mini + FL Studio (user machine — **not** this VM)

## Environment probe summary

| Check | Result |
|-------|--------|
| OS | Ubuntu 24.04 LTS (Linux x86_64 cloud agent) |
| Python | 3.12.3 (meets ≥3.11 preference) |
| Memory | ~15 GiB total (see `scripts/doctor.py` for live numbers) |
| FL Studio | **N/A** — not macOS; not installed |
| PostFader MCP | **N/A** — not installed; do not assume |
| IAC Driver (virtual MIDI) | **N/A** — macOS only |
| Operating mode | `simulation` + `midi_export` |

Safe doctor command (no installs):

```bash
python -m scripts.doctor
# or
music-ai doctor
music-ai probe-daw
```

## Adapter capability matrix

Legend: ✅ supported & verified in tests · ⚠️ partial / manual · ❌ unsupported · 🔲 not probed live

| Operation | FakeDawAdapter | MidiExportAdapter | PostFader / Ableton / Logic / Reaper stubs | PostFader (live Mac) |
|-----------|----------------|-------------------|---------------------------------------------|----------------------|
| `connect` | ✅ | ✅ | ❌ refuse | 🔲 |
| `probe_capabilities` | ✅ | ✅ | ✅ (reports stub) | 🔲 |
| `read_project` | ✅ (in-memory) | ❌ | ❌ refuse | 🔲 |
| `read_tracks` | ✅ | ⚠️ local CIR only | ❌ refuse | 🔲 |
| `create_or_update_notes` | ✅ | ✅ via `.mid` files | ❌ refuse | 🔲 |
| `set_tempo` | ✅ | ⚠️ embedded in MIDI | ❌ refuse | 🔲 |
| `set_track_params` | ✅ | ❌ | ❌ refuse | 🔲 |
| `choose_existing_preset` | ✅ | ❌ | ❌ refuse | 🔲 |
| `arrange_section` | ✅ | ❌ | ❌ refuse | 🔲 |
| `save_snapshot` | ✅ | ❌ (save `.flp` manually) | ❌ refuse | 🔲 |
| `export_audio_or_request_manual_bounce` | ⚠️ user bounce | ⚠️ user bounce | ❌ refuse | 🔲 |
| `verify_postcondition` | ✅ | ✅ MIDI parse | ❌ refuse | 🔲 |
| `undo_or_restore` | ✅ | ❌ | ❌ refuse | 🔲 |

`music-ai list-daws` prints the Phase 7 multi-DAW registry.

## Verified Phase 0 operations (simulation)

1. Parse creative prompt → intent (genre/BPM/key/mood/seed).
2. Generate 8-bar drums, bass, chords as CIR.
3. Export per-track + combined Standard MIDI files; parse `note_on` events in tests.
4. Persist project + version rows in SQLite.
5. Fake DAW apply / verify / snapshot / restore.
6. MIDI export adapter writes files and returns `user_action_required` import instructions.

## Audio reference pipeline (Phase 2 — simulation defaults)

| Capability | Status |
|------------|--------|
| Stem separation | ✅ **Simulation** adapter (`MUSIC_AI_SEPARATOR=simulation`) — band/transient split; bleed expected. Demucs optional, refuses without install. |
| Transcription | ✅ **Stub** adapter (`MUSIC_AI_TRANSCRIBER=stub`) → editable MIDI. Basic Pitch optional, refuses without install. |
| BPM / key / groove estimates | ✅ Numpy heuristics (`is_estimate=True`) |
| Embeddings (CLAP/MERT) | ❌ Deferred |
| Taste / preference model | ✅ Phase 5 simulation encoder + ranking head |
| Phase 7 specialist MIDI | ✅ Deterministic hook; optional neural refuses |
| Phase 7 multi-DAW registry | ✅ Discoverable; non-Fake/MIDI adapters refuse live |
| Phase 7 blind eval harness | ✅ Simulation proxy; real listening not_run in CI |

See `docs/audio-models.md` for optional Demucs / Basic Pitch / Phase 7 enablement (no auto-download).

## Explicitly unsupported / not claimed

- Live FL Studio project mutation from this VM.
- Unattended audio bounce.
- PostFader tool names or method signatures (must be discovered on the Mac; never fabricated).
- Neural stem separation / Basic Pitch / MIDI specialist / vocal models without an explicit local install + approval flag.
- Blind listening preference wins from CI simulation alone.
- Live Ableton / Logic / Reaper control (stubs only).
- Sending user audio to external services (`ALLOW_CLOUD_AUDIO=false`).

## When the user probes on macOS

Document actual PostFader tool list, FL Studio version, Python bridge version, and IAC port status in this file under a new dated section. Update `IMPLEMENTATION_STATUS.md` labels: `mock-tested` → `live-tested` only after readback verification.
