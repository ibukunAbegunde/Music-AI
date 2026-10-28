"""CLI entrypoint: music-ai compose / revise / reference pipeline / doctor."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import typer
from rich.console import Console
from rich.table import Table

from backend.app.core.config import DawMode, Settings, get_settings
from backend.app.core.logging import setup_logging
from backend.app.daw.fake import FakeDawAdapter
from backend.app.daw.midi_fallback import MidiExportAdapter
from backend.app.music.brief import parse_brief
from backend.app.music.templates import list_templates
from backend.app.services.compose import compose_from_prompt
from backend.app.services.revise import revise_project
from backend.app.storage.assets import AssetStore

app = typer.Typer(
    help="Private AI Music Producer — Phase 2 CLI (references + brief + MIDI)",
    no_args_is_help=True,
)
console = Console()


def _settings(mode: str | None, workspace: Path | None) -> Settings:
    base = get_settings()
    if workspace is not None:
        return Settings(
            workspace_dir=workspace,
            database_url=f"sqlite:///{workspace / 'music_ai.db'}",
            daw_mode=DawMode(mode) if mode else base.daw_mode,
            log_level=base.log_level,
        )
    if mode is not None:
        return Settings(
            workspace_dir=base.workspace_dir,
            database_url=base.database_url,
            daw_mode=DawMode(mode),
            log_level=base.log_level,
        )
    return base


def _adapter(settings: Settings):
    if settings.daw_mode == DawMode.MIDI_EXPORT:
        return MidiExportAdapter(AssetStore(settings))
    return FakeDawAdapter()


def _print_moves(moves) -> None:
    if not moves:
        return
    console.print("[bold]Next moves (typed PatchOps):[/]")
    for i, op in enumerate(moves, 1):
        console.print(
            f"  {i}. {op.action_type} → {op.target_role} — {op.predicted_impact or op.explanation}"
        )


@app.command()
def compose(
    prompt: str = typer.Argument(..., help="Creative brief / NL request"),
    seed: int | None = typer.Option(None, help="Explicit RNG seed"),
    bars: int = typer.Option(8, help="Loop length in bars"),
    mode: str | None = typer.Option(None, help="simulation | midi_export"),
    workspace: Path | None = typer.Option(None, help="Override workspace directory"),
    lock: list[str] | None = typer.Option(None, help="Roles to lock (repeatable)"),
    recipe_id: str | None = typer.Option(None, help="Attach existing recipe UUID metadata"),
) -> None:
    """NL/brief → 8-bar drum/bass/chord MIDI + candidate package."""
    settings = _settings(mode, workspace)
    setup_logging(settings.log_level)
    result = compose_from_prompt(
        prompt,
        seed=seed,
        bars=bars,
        settings=settings,
        adapter=_adapter(settings),
        locked_roles=list(lock or []),
        recipe_id=UUID(recipe_id) if recipe_id else None,
    )
    console.print(f"[bold green]Project[/] {result.project.id}")
    console.print(f"  brief: {result.brief.title} ({result.brief.genre_template_id})")
    console.print(
        f"  seed: {result.project.seed}  bpm: {result.project.bpm}  key: {result.project.key_estimate}"
    )
    console.print(f"  locks: {result.brief.locked_roles or '—'}")
    console.print(f"  candidate: {result.candidate.id}")
    console.print(f"  one-line diff: {result.candidate.one_line_diff}")
    console.print(f"  CIR: {result.candidate.cir_snapshot_ref}")
    console.print(
        f"  loudness: {result.candidate.loudness_notes.normalization_status} "
        f"(target {result.candidate.loudness_notes.target_lufs} LUFS)"
    )

    table = Table(title="Exported MIDI")
    table.add_column("Role")
    table.add_column("Path")
    table.add_column("Notes")
    for role, path in result.midi_paths.items():
        note_count = next(
            (len(t.note_events) for t in result.project.tracks if t.role.value == role),
            "—",
        )
        locked = next(
            (t.locked for t in result.project.tracks if t.role.value == role),
            False,
        )
        label = f"{role}{' 🔒' if locked else ''}"
        table.add_row(label, str(path), str(note_count))
    console.print(table)
    console.print(
        f"DAW [{settings.daw_mode.value}]: succeeded={result.daw_result.succeeded} "
        f"verified={result.daw_result.verified}"
    )
    if result.daw_result.user_action_required:
        console.print(f"[yellow]User action:[/] {result.daw_result.user_action_required}")
    _print_moves(result.next_moves)


@app.command()
def brief(
    prompt: str = typer.Argument(..., help="Text to parse into BriefDocument JSON"),
    seed: int | None = typer.Option(None),
    bars: int = typer.Option(8),
) -> None:
    """Parse NL into a constraint-first brief canvas document (no generation)."""
    doc = parse_brief(prompt, seed=seed, bars=bars)
    console.print_json(doc.model_dump_json(indent=2))


@app.command()
def revise(
    project_id: str = typer.Argument(..., help="Existing project UUID"),
    instruction: str = typer.Argument(
        ...,
        help="e.g. 'keep the drums, soften bass and add a fill before bar 8'",
    ),
    seed: int | None = typer.Option(None),
    mode: str | None = typer.Option(None, help="simulation | midi_export"),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Revise a project honoring role-locks; print musical diff + next moves."""
    settings = _settings(mode, workspace)
    setup_logging(settings.log_level)
    adapter = _adapter(settings)
    result = revise_project(
        UUID(project_id),
        instruction,
        seed=seed,
        settings=settings,
        adapter=adapter,
    )
    console.print(f"[bold green]Revised[/] {result.project.id} → version {result.version.id}")
    console.print(f"  musical diff: {result.diff.one_line_summary}")
    console.print(f"  locks respected: {result.diff.locked_roles_respected}")
    console.print(f"  roles changed: {result.diff.roles_changed}")
    if result.diff.details:
        for d in result.diff.details:
            console.print(f"    - {d}")
    console.print(f"  undo snapshot: {result.snapshot_ref or 'n/a (midi_export)'}")
    _print_moves(result.next_moves)


@app.command("templates")
def templates_cmd() -> None:
    """List genre structure templates."""
    table = Table(title="Genre templates")
    table.add_column("ID")
    table.add_column("BPM")
    table.add_column("Density")
    table.add_column("Notes")
    for t in list_templates():
        table.add_row(t.id, f"{t.default_bpm:g}", f"{t.groove_density:.2f}", t.notes or "")
    console.print(table)


@app.command("recipe-save")
def recipe_save(
    project_id: str = typer.Argument(..., help="Project UUID to snapshot as a recipe"),
    name: str | None = typer.Option(None, help="Recipe display name"),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Save a recipe stub (groove fingerprint + locks) from a project CIR tip."""
    from backend.app.music.recipes import recipe_from_project, save_recipe
    from backend.app.services.revise import _load_cir

    settings = _settings(None, workspace)
    assets = AssetStore(settings)
    project = _load_cir(assets, UUID(project_id), None)
    if project is None:
        raise typer.BadParameter(f"no CIR found for project {project_id}")
    recipe = recipe_from_project(project, name=name)
    path = save_recipe(recipe, assets)
    console.print(f"[bold green]Recipe[/] {recipe.id}")
    console.print(f"  name: {recipe.name}")
    console.print(f"  locks: {recipe.locked_roles or '—'}")
    console.print(f"  path: {path}")


@app.command("recipe-list")
def recipe_list(workspace: Path | None = typer.Option(None)) -> None:
    """List saved recipe stubs."""
    from backend.app.music.recipes import list_recipes

    settings = _settings(None, workspace)
    assets = AssetStore(settings)
    recipes = list_recipes(assets)
    if not recipes:
        console.print("No recipes saved yet.")
        return
    table = Table(title="Recipes")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("BPM")
    table.add_column("Locks")
    for r in recipes:
        table.add_row(
            str(r.id),
            r.name,
            str(r.groove_fingerprint.get("bpm", "—")),
            ", ".join(r.locked_roles) or "—",
        )
    console.print(table)


@app.command("import-ref")
def import_ref(
    path: Path = typer.Argument(..., help="WAV/MP3/FLAC/M4A reference file"),
    license_class: str = typer.Option("unknown", help="owned | licensed | unknown"),
    use_mode: str = typer.Option("analysis", help="inspiration | analysis | direct-sample"),
    notes: str | None = typer.Option(None, help="Permission / rights notes"),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Import a reference into the immutable workspace store (hash + rights)."""
    from backend.app.services.reference import run_import

    settings = _settings(None, workspace)
    setup_logging(settings.log_level)
    asset = run_import(
        path,
        settings=settings,
        license_class=license_class,
        permission_notes=notes,
        use_mode=use_mode,
    )
    console.print(f"[bold green]Reference[/] {asset.id}")
    console.print(f"  file: {asset.original_filename}")
    console.print(f"  sha256: {asset.immutable_sha256[:16]}…")
    console.print(f"  license: {asset.license_class.value}  use: {asset.use_mode.value}")
    console.print(f"  duration: {asset.duration_sec:.2f}s  sr: {asset.sample_rate}")
    console.print(f"  store: {asset.source_uri_or_local_path}")


@app.command()
def analyse(
    reference_id: str = typer.Argument(..., help="Reference UUID"),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Estimate BPM/key/groove for an imported reference (marked as estimates)."""
    from backend.app.services.reference import run_analyse

    settings = _settings(None, workspace)
    setup_logging(settings.log_level)
    asset, profile = run_analyse(UUID(reference_id), settings=settings)
    console.print(f"[bold green]Analysed[/] {asset.id}")
    console.print(
        f"  BPM: {profile.bpm_estimate} (conf {profile.bpm_confidence})  "
        f"key: {profile.key_estimate} (conf {profile.key_confidence})"
    )
    gf = profile.groove_features
    console.print(
        f"  groove: swing≈{gf.swing_estimate} sync≈{gf.syncopation} "
        f"onsets={len(gf.onset_grid)} density={gf.onset_density}"
    )
    console.print(f"  limitations: {profile.limitations[0] if profile.limitations else '—'}")


@app.command()
def separate(
    reference_id: str = typer.Argument(..., help="Reference UUID"),
    separator: str | None = typer.Option(None, help="simulation (default) | demucs"),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Separate stems (default: simulation band-split; Demucs optional/manual)."""
    from backend.app.services.reference import run_separate

    settings = _settings(None, workspace)
    setup_logging(settings.log_level)
    asset, stems, _profile = run_separate(
        UUID(reference_id), settings=settings, separator_name=separator
    )
    console.print(f"[bold green]Separated[/] {asset.id} → {len(stems)} stems")
    table = Table(title="Stems")
    table.add_column("Type")
    table.add_column("Role")
    table.add_column("Model")
    table.add_column("Path")
    table.add_column("Flags")
    for s in stems:
        table.add_row(
            s.stem_type,
            (s.mapped_role.value if s.mapped_role else "—"),
            f"{s.separation_model}@{s.separation_version}",
            s.file_path,
            ",".join(s.confidence_or_quality_flags) or "—",
        )
    console.print(table)
    if stems and stems[0].bleed_notes:
        console.print(f"[yellow]Note:[/] {stems[0].bleed_notes}")


@app.command()
def transcribe(
    reference_id: str = typer.Argument(..., help="Reference UUID"),
    stem: str = typer.Option("bass", help="Stem type to transcribe"),
    transcriber: str | None = typer.Option(None, help="stub (default) | basic_pitch"),
    lock: bool = typer.Option(False, help="Role-lock the mapped track after transcription"),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Transcribe a pitched stem → editable MIDI candidate."""
    from backend.app.services.reference import run_transcribe

    settings = _settings(None, workspace)
    setup_logging(settings.log_level)
    asset, stem_asset, notes, midi_path = run_transcribe(
        UUID(reference_id),
        stem_type=stem,
        settings=settings,
        transcriber_name=transcriber,
        lock_role=lock,
    )
    console.print(f"[bold green]Transcribed[/] {asset.id} / {stem_asset.stem_type}")
    console.print(f"  notes: {len(notes)}  role: {stem_asset.mapped_role}  locked: {stem_asset.role_locked}")
    console.print(f"  midi: {midi_path}")
    if notes:
        preview = ", ".join(f"p{n.pitch}@{n.onset_beats:.2f}" for n in notes[:8])
        console.print(f"  preview: {preview}{'…' if len(notes) > 8 else ''}")


@app.command()
def profile(
    reference_id: str = typer.Argument(..., help="Reference UUID"),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Show reference profile + tempo/groove summary + stem→role map + borrows."""
    from backend.app.audio.ingest import load_reference_asset
    from backend.app.services.reference import load_profile

    settings = _settings(None, workspace)
    asset = load_reference_asset(UUID(reference_id), settings)
    prof = load_profile(UUID(reference_id), settings)
    console.print(f"[bold green]Profile[/] {asset.id}  status={asset.analysis_status}")
    console.print(f"  file: {asset.original_filename}  rights: {asset.license_class.value}")
    console.print(
        f"  BPM≈{prof.bpm_estimate} (c={prof.bpm_confidence})  "
        f"key≈{prof.key_estimate} (c={prof.key_confidence})  meter={prof.meter}"
    )
    gf = prof.groove_features
    console.print(
        f"  groove: swing≈{gf.swing_estimate} sync≈{gf.syncopation} "
        f"density≈{gf.onset_density} onsets={len(gf.onset_grid)}"
    )
    console.print(f"  borrow traits: {', '.join(prof.available_borrow_traits)}")
    if prof.transcription_summary:
        console.print(f"  transcription: {prof.transcription_summary}")
    if asset.stem_role_mappings:
        table = Table(title="Stem → role")
        table.add_column("Stem")
        table.add_column("Role")
        table.add_column("Locked")
        for m in asset.stem_role_mappings:
            table.add_row(m.stem_type, m.role.value, "yes" if m.locked else "no")
        console.print(table)
    if prof.limitations:
        console.print("[yellow]Limitations:[/]")
        for lim in prof.limitations:
            console.print(f"  - {lim}")


@app.command("ref-pipeline")
def ref_pipeline(
    path: Path = typer.Argument(..., help="Reference audio file"),
    license_class: str = typer.Option("owned"),
    use_mode: str = typer.Option("analysis"),
    separator: str | None = typer.Option(None, help="simulation | demucs"),
    transcriber: str | None = typer.Option(None, help="stub | basic_pitch"),
    borrow: list[str] | None = typer.Option(
        None, help="Borrow traits (repeatable), e.g. bass_bounce"
    ),
    lock_bass: bool = typer.Option(False, help="Role-lock transcribed bass"),
    prompt: str | None = typer.Option(None, help="Optional NL brief to attach borrows to"),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Run import → analyse → separate → transcribe → show profile (Phase 2 exit)."""
    from backend.app.services.reference import run_pipeline

    settings = _settings(None, workspace)
    setup_logging(settings.log_level)
    result = run_pipeline(
        path,
        settings=settings,
        license_class=license_class,
        use_mode=use_mode,
        separator_name=separator,
        transcriber_name=transcriber,
        borrow_traits=list(borrow) if borrow else None,
        lock_bass=lock_bass,
        prompt_for_brief=prompt,
    )
    console.print(f"[bold green]Pipeline complete[/] reference={result.asset.id}")
    console.print(
        f"  BPM≈{result.profile.bpm_estimate}  key≈{result.profile.key_estimate}  "
        f"stems={len(result.stems)}  midi_notes={len(result.transcription_notes)}"
    )
    console.print(f"  midi: {result.transcription_midi}")
    console.print(
        f"  simulated: separator={result.simulated.get('separator')} "
        f"transcriber={result.simulated.get('transcriber')}"
    )
    if result.brief_with_borrows:
        chips = result.brief_with_borrows.borrow_chips
        console.print(
            f"  borrow chips: {', '.join(f'{c.trait}@{c.weight}' for c in chips)}"
        )
    gf = result.profile.groove_features
    console.print(
        f"  groove summary: swing≈{gf.swing_estimate} sync≈{gf.syncopation} "
        f"onsets={len(gf.onset_grid)}"
    )


@app.command()
def doctor() -> None:
    """Inspect local environment (safe checks only)."""
    from backend.app.core.doctor import run_doctor

    console.print_json(json.dumps(run_doctor(), indent=2, default=str))


@app.command("probe-daw")
def probe_daw() -> None:
    """Probe DAW bridge availability."""
    import platform
    from pathlib import Path as P

    settings = get_settings()
    setup_logging(settings.log_level)
    report: dict = {
        "configured_mode": settings.daw_mode.value,
        "platform": platform.platform(),
        "live_bridge": False,
        "adapters": {},
    }
    fake = FakeDawAdapter()
    fake.connect()
    report["adapters"]["fake"] = fake.probe_capabilities().as_dict()
    midi = MidiExportAdapter()
    midi.connect()
    report["adapters"]["midi_export"] = midi.probe_capabilities().as_dict()
    markers = []
    if platform.system() == "Darwin":
        for c in (
            P("/Applications/FL Studio 2024.app"),
            P("/Applications/FL Studio 2025.app"),
            P("/Applications/FL Studio.app"),
        ):
            if c.exists():
                markers.append(str(c))
    report["macos_markers"] = markers
    report["note"] = (
        "Cloud/Linux CI: FL Studio, PostFader, and IAC MIDI are N/A. "
        "Use simulation or midi_export mode."
    )
    console.print_json(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    app()
