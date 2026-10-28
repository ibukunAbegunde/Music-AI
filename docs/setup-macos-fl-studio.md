# Setup — Apple Silicon Mac mini + FL Studio

This guide is for the **user’s Mac**, not the Linux cloud CI environment. On the cloud VM, FL Studio / PostFader / IAC are N/A; use simulation or MIDI-export mode.

## Prerequisites

1. **macOS** on Apple Silicon (M4 Mac mini).
2. **FL Studio** installed (spec cites 26.1.3+ as a candidate; confirm your exact build via About).
3. **Python 3.11 or 3.12** (Homebrew recommended): `brew install python@3.12`.
4. **Xcode Command Line Tools** if compiling native wheels: `xcode-select --install`.

## Clone and local install

```bash
git clone <this-repo>
cd <repo>
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# set DAW_MODE=midi_export until PostFader is verified
# DAW_MODE=postfader selects a refuse stub until live-probed — compose fails
# honestly (DawWriteError) rather than returning OK with buried daw failure.
mkdir -p workspace
python -m scripts.doctor
pytest
```

## MIDI manual-import workflow (Phase 0 / fallback)

1. Generate stems:

```bash
music-ai compose "mellow Afrobeats 110 BPM in A minor" --seed 42 --mode midi_export
```

2. Open FL Studio with a scratch project (never overwrite masters without a backup).
3. Set project tempo to the reported BPM.
4. For each file under `workspace/midi/<project-id>/`:
   - `drums.mid`, `bass.mid`, `chord.mid` — drag onto Channel Rack or **File → Import → MIDI file**.
5. Assign instruments (kick/snare/hat kit, bass, Rhodes/keys).
6. Optional: import `combined.mid` only if you prefer a single multi-channel file.
7. Bounce/export audio manually when you want a render; place the file under `workspace/renders/` if you want the app to pick it up in later phases.

## IAC Driver (needed for PostFader / MIDI scripting bridges)

1. Open **Audio MIDI Setup** → Window → **Show MIDI Studio**.
2. Double-click **IAC Driver** → enable **Device is online**.
3. Ensure at least one bus (e.g. `IAC Bus 1`) exists.
4. In FL Studio, enable the IAC port for input/output as required by the bridge docs.

## PostFader (only after user approval)

Reference (verify versions yourself; do not assume APIs):  
https://github.com/synopsys0/postfader-fl-studio-mcp

Checklist before enabling `DAW_MODE=postfader`:

- [ ] FL Studio version recorded in `docs/tool-capabilities.md`
- [ ] PostFader installed and reachable
- [ ] IAC online
- [ ] `music-ai probe-daw` (or future live probe script) lists real tool contracts
- [ ] Scratch `.flp` used for all write tests; backup outside the project tree
- [ ] Capability matrix updated with ✅ / ❌ from **live** probes — never invent method names

## Phase 6 full-length import

`music-ai full-compose` produces a **multi-section** instrumental (typically 48–80 bars) plus an arrangement plan. Live Playlist automation is **not** available without a verified PostFader/FL bridge — place patterns manually.

1. Generate:

```bash
music-ai full-compose "mellow Afrobeats 110 BPM in A minor" --seed 42 --mode midi_export
# or from a fixture reference:
music-ai full-compose "Afrobeats with bass bounce" --ref --fixture afrobeats --seed 11
```

2. Open a **Scratch** `.flp` (use `--scratch`; avoid `--release` until you have reviewed MIDI).
3. Set tempo to the BPM printed by the CLI / `arrangement_plan.json`.
4. Import `workspace/midi/<project-id>/drums.mid`, `bass.mid`, `chord.mid` (File → Import → MIDI file or drag to Channel Rack).
5. Assign instruments using the **instrument palette** hints in `workspace/projects/<project-id>/arrangement_plan.json`.
6. On the **Playlist**, arrange / duplicate patterns to match `section_map` bar ranges (also listed in `manual_fl_steps.json`), e.g. intro 1–8, verse 9–24, chorus 25–40, …
7. Optional: import `combined.mid` as a single multi-channel reference track, then mute once stems are placed.
8. Bounce/export audio manually → `workspace/renders/` if you want later phases to pick up a render.

Release mode (`--release`): the app exports MIDI + plan but **does not** auto-write FakeDaw notes — review first, then re-run with `--scratch`, or bypass the gate explicitly with `--release --autonomy autonomous --force` (logged). Autonomous alone is not enough.

## Safety

- Back up `.flp` files before any automated write.
- Keep `ALLOW_CLOUD_AUDIO=false` unless you explicitly opt in.
- Do not point the agent at irreversible “save over original” paths.
- Phase 0 will not install large models or modify FL Studio configuration without approval.

## Image-Line MIDI scripting (background)

Official MIDI scripting is primarily a **controller** API, not a full external DAW API:  
https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm  

Treat any bridge as versioned and probe-driven.
