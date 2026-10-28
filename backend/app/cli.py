"""CLI entrypoint: music-ai compose / doctor / probe."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from backend.app.core.config import DawMode, Settings, get_settings
from backend.app.core.logging import setup_logging
from backend.app.daw.fake import FakeDawAdapter
from backend.app.daw.midi_fallback import MidiExportAdapter
from backend.app.services.compose import compose_from_prompt

app = typer.Typer(help="Private AI Music Producer — Phase 0 CLI", no_args_is_help=True)
console = Console()


@app.command()
def compose(
    prompt: str = typer.Argument(..., help="Creative brief, e.g. 'mellow Afrobeats 110 BPM in A minor'"),
    seed: Optional[int] = typer.Option(None, help="Explicit RNG seed for reproducibility"),
    bars: int = typer.Option(8, help="Loop length in bars"),
    mode: Optional[str] = typer.Option(None, help="simulation | midi_export"),
    workspace: Optional[Path] = typer.Option(None, help="Override workspace directory"),
) -> None:
    """Generate an 8-bar drum/bass/chord MIDI project from a prompt."""
    settings = get_settings()
    if workspace is not None:
        settings = Settings(
            workspace_dir=workspace,
            database_url=f"sqlite:///{workspace / 'music_ai.db'}",
            daw_mode=DawMode(mode) if mode else settings.daw_mode,
            log_level=settings.log_level,
        )
    elif mode is not None:
        settings = Settings(
            workspace_dir=settings.workspace_dir,
            database_url=settings.database_url,
            daw_mode=DawMode(mode),
            log_level=settings.log_level,
        )
    setup_logging(settings.log_level)

    adapter = None
    if settings.daw_mode == DawMode.MIDI_EXPORT:
        from backend.app.storage.assets import AssetStore

        adapter = MidiExportAdapter(AssetStore(settings))
    else:
        adapter = FakeDawAdapter()

    result = compose_from_prompt(prompt, seed=seed, bars=bars, settings=settings, adapter=adapter)

    console.print(f"[bold green]Project[/] {result.project.id}")
    console.print(f"  name: {result.project.name}")
    console.print(f"  seed: {result.project.seed}  bpm: {result.project.bpm}  key: {result.project.key_estimate}")
    console.print(f"  genre intent: {result.intent.get('genre')}  mood: {result.intent.get('mood')}")
    console.print(f"  metadata: {result.metadata_path}")

    table = Table(title="Exported MIDI")
    table.add_column("Role")
    table.add_column("Path")
    table.add_column("Notes")
    for role, path in result.midi_paths.items():
        note_count = next(
            (len(t.note_events) for t in result.project.tracks if t.role.value == role),
            "—",
        )
        table.add_row(role, str(path), str(note_count))
    console.print(table)

    daw = result.daw_result
    console.print(
        f"DAW [{settings.daw_mode.value}]: succeeded={daw.succeeded} verified={daw.verified}"
    )
    if daw.user_action_required:
        console.print(f"[yellow]User action:[/] {daw.user_action_required}")


@app.command()
def doctor() -> None:
    """Inspect local environment (safe checks only)."""
    from backend.app.core.doctor import run_doctor

    report = run_doctor()
    console.print_json(json.dumps(report, indent=2, default=str))


@app.command("probe-daw")
def probe_daw() -> None:
    """Probe DAW bridge availability (simulation / midi_export / postfader if present)."""
    settings = get_settings()
    setup_logging(settings.log_level)
    report: dict = {
        "configured_mode": settings.daw_mode.value,
        "platform": __import__("platform").platform(),
        "fl_studio_path_env": settings.fl_studio_path,
        "postfader_path_env": settings.postfader_path,
        "live_bridge": False,
        "adapters": {},
    }

    fake = FakeDawAdapter()
    fake.connect()
    report["adapters"]["fake"] = fake.probe_capabilities().as_dict()

    midi = MidiExportAdapter()
    midi.connect()
    report["adapters"]["midi_export"] = midi.probe_capabilities().as_dict()

    # Safe probe: do not install anything; just look for common markers
    import platform
    import shutil
    from pathlib import Path as P

    markers = []
    if platform.system() == "Darwin":
        candidates = [
            P("/Applications/FL Studio 2024.app"),
            P("/Applications/FL Studio 2025.app"),
            P("/Applications/FL Studio.app"),
        ]
        for c in candidates:
            if c.exists():
                markers.append(str(c))
        if shutil.which("python3"):
            markers.append("python3_present")
    report["macos_markers"] = markers
    report["note"] = (
        "Cloud/Linux CI: FL Studio, PostFader, and IAC MIDI are N/A. "
        "Use simulation or midi_export mode. Live probe belongs on the user's Apple Silicon Mac."
    )
    console.print_json(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    app()
