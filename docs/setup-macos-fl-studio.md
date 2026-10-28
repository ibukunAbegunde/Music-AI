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

## Safety

- Back up `.flp` files before any automated write.
- Keep `ALLOW_CLOUD_AUDIO=false` unless you explicitly opt in.
- Do not point the agent at irreversible “save over original” paths.
- Phase 0 will not install large models or modify FL Studio configuration without approval.

## Image-Line MIDI scripting (background)

Official MIDI scripting is primarily a **controller** API, not a full external DAW API:  
https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm  

Treat any bridge as versioned and probe-driven.
