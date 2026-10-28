# Optional audio models (Phase 2+)

Music-AI defaults to **simulation stems** and a **stub transcriber** so CI and local
dev work without multi‑hundred‑MB downloads. Neural models are allowed by spec v1.1
(dual-path) but must be **opt-in and user-approved**.

## Defaults (always available)

| Capability | Adapter | Notes |
|------------|---------|-------|
| Stem separation | `simulation` | Band/transient DSP split → vocals/drums/bass/other. Bleed expected. |
| Transcription | `stub` | Onset + ACF pitch → editable MIDI candidate. Not Basic Pitch. |
| Features | numpy DSP | BPM/key/groove **estimates** with confidence. Optional librosa. |

```bash
music-ai ref-pipeline path/to/ref.wav
# equivalent stepwise:
music-ai import-ref path/to/ref.wav --license-class owned
music-ai analyse <reference-id>
music-ai separate <reference-id>          # --separator simulation
music-ai transcribe <reference-id> --stem bass
music-ai profile <reference-id>
```

Env knobs (`.env`):

```
MUSIC_AI_SEPARATOR=simulation
MUSIC_AI_TRANSCRIBER=stub
```

## Enable Demucs later (manual)

1. Approve the download on your machine (weights are large).
2. Install the optional extra:

```bash
pip install -e ".[demucs]"
```

3. Place or let Demucs fetch a local checkpoint; set `DEMUCS_MODEL_PATH` if needed.
4. Run with `--separator demucs` **or** `MUSIC_AI_SEPARATOR=demucs`.

The adapter currently **refuses to auto-download** weights even if the package
imports — extend `backend/app/audio/separators/demucs_adapter.py` once a local
checkpoint is confirmed. Until then, keep `simulation`.

Upstream note: original Facebook Demucs maintenance status is uncertain; evaluate
maintained forks before production commitment (spec §20).

## Enable Basic Pitch later (manual)

```bash
pip install -e ".[basic-pitch]"
music-ai transcribe <id> --stem bass --transcriber basic_pitch
```

Same policy: no silent weight download in CI. Wire `predict()` in
`backend/app/transcription/basic_pitch_adapter.py` after local install.

## Optional librosa

```bash
pip install -e ".[librosa]"
# PREFER_LIBROSA=true
```

Used only when `Settings.prefer_librosa` is true; numpy path remains default.

## Rights reminder

Separated stems and transcribed MIDI from third-party references inherit rights
constraints. `direct-sample` use_mode requires explicit acknowledgement; unknown
license is never silently treated as cleared for release.
