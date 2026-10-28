"""CLI entrypoint: music-ai compose / revise / critique / revise-loop / ref-compose / …"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
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
    help="Private AI Music Producer — Phase 0–7 CLI (refs, critic, taste, full-length, research)",
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
    """Resolve DAW via registry — postfader/ableton stubs refuse honestly (no FakeDaw mask)."""
    from backend.app.daw.registry import adapter_for_settings

    return adapter_for_settings(settings)


def _print_moves(moves) -> None:
    if not moves:
        return
    console.print("[bold]Next moves (typed PatchOps):[/]")
    for i, op in enumerate(moves, 1):
        console.print(
            f"  {i}. {op.action_type} → {op.target_role} — {op.predicted_impact or op.explanation}"
        )


def _print_candidate_table(candidates) -> None:
    table = Table(title="Candidates")
    table.add_column("#")
    table.add_column("Seed")
    table.add_column("Version")
    table.add_column("One-line diff")
    for c in candidates:
        table.add_row(
            str(c.index),
            str(c.seed),
            str(c.version.id),
            c.candidate.one_line_diff[:80],
        )
    console.print(table)


@app.command()
def compose(
    prompt: str = typer.Argument(..., help="Creative brief / NL request"),
    seed: int | None = typer.Option(None, help="Explicit RNG seed"),
    bars: int = typer.Option(8, help="Loop length in bars (8–16)"),
    mode: str | None = typer.Option(
        None, help="simulation | midi_export | postfader (postfader refuses until live probe)"
    ),
    workspace: Path | None = typer.Option(None, help="Override workspace directory"),
    lock: list[str] | None = typer.Option(None, help="Roles to lock (repeatable)"),
    recipe_id: str | None = typer.Option(None, help="Attach existing recipe UUID metadata"),
) -> None:
    """NL/brief → 8–16-bar drum/bass/chord MIDI + candidate package."""
    if bars < 8 or bars > 16:
        raise typer.BadParameter("bars must be 8–16")
    settings = _settings(mode, workspace)
    setup_logging(settings.log_level)
    try:
        result = compose_from_prompt(
            prompt,
            seed=seed,
            bars=bars,
            settings=settings,
            adapter=_adapter(settings),
            locked_roles=list(lock or []),
            recipe_id=UUID(recipe_id) if recipe_id else None,
        )
    except Exception as exc:  # noqa: BLE001 — surface DawWriteError / specialist refuse
        from backend.app.daw.base import DawWriteError

        if isinstance(exc, DawWriteError):
            console.print(f"[bold red]DAW write failed[/] ({settings.daw_mode.value})")
            console.print(f"  {exc}")
            if exc.daw_result.user_action_required:
                console.print(f"[yellow]User action:[/] {exc.daw_result.user_action_required}")
            raise typer.Exit(code=1) from exc
        raise
    console.print(f"[bold green]Project[/] {result.project.id}")
    console.print(f"  brief: {result.brief.title} ({result.brief.genre_template_id})")
    console.print(
        f"  seed: {result.project.seed}  bpm: {result.project.bpm}  "
        f"key: {result.project.key_estimate}  bars: {result.project.length_bars}"
    )
    console.print(
        f"  specialist: {result.specialist_name or '—'} "
        f"(mode={result.specialist_mode or '—'})"
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


@app.command("ref-compose")
def ref_compose(
    prompt: str = typer.Argument(..., help="Creative brief (novelty encouraged)"),
    trait: list[str] | None = typer.Option(
        None,
        help=(
            "Borrow traits (repeatable). Canonical: bass_bounce, drums, "
            "percussion_texture, atmosphere, chords, arrangement, bass_rhythm, "
            "groove, energy. Aliases: chord_feel→chords, groove_swing→groove, …"
        ),
    ),
    fixture: str = typer.Option(
        "afrobeats",
        help="Fixture genre profile (demo without a live file; Phase 2 pipeline also available)",
    ),
    n: int = typer.Option(2, help="Number of candidates (seeds)"),
    seed: int | None = typer.Option(None, help="Base seed (candidates use seed..seed+n-1)"),
    bars: int = typer.Option(8, help="Loop length 8–16"),
    mode: str | None = typer.Option(None),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Reference (fixture profile) → borrow chips → N novel CandidatePackages."""
    if bars < 8 or bars > 16:
        raise typer.BadParameter("bars must be 8–16")
    from backend.app.services.reference_compose import compose_from_reference

    settings = _settings(mode, workspace)
    setup_logging(settings.log_level)
    result = compose_from_reference(
        prompt,
        traits=trait,
        fixture_genre=fixture,
        n=n,
        seed=seed,
        bars=bars,
        settings=settings,
        adapter=_adapter(settings),
    )
    project_id = result.multi.baseline.project.id
    console.print(f"[bold green]Project[/] {project_id}")
    console.print(f"  analyzer: {result.analyzer}")
    console.print(f"  profile: {result.profile.id} bpm≈{result.profile.bpm_estimate}")
    console.print(f"  borrow traits: {result.traits}")
    console.print(f"  conditioning: {result.multi.conditioning.get('notes')}")
    console.print(f"  session: {result.multi.session_id}")
    console.print(f"[yellow]Phase 2 note:[/] {result.phase2_note}")
    _print_candidate_table(result.multi.candidates)
    tip = result.multi.candidates[-1]
    console.print(f"  tip version: {tip.version.id}")
    console.print(f"  MIDI tip: {tip.midi_paths.get('combined')}")


@app.command()
def candidates(
    prompt: str = typer.Argument(..., help="Brief text"),
    n: int = typer.Option(3, help="Candidate count"),
    seed: int | None = typer.Option(None),
    bars: int = typer.Option(8),
    mode: str | None = typer.Option(None),
    workspace: Path | None = typer.Option(None),
    fixture: str | None = typer.Option(None, help="Optional fixture profile to condition on"),
    trait: list[str] | None = typer.Option(None),
) -> None:
    """Generate N seeded candidates (optionally reference-conditioned)."""
    from backend.app.audio.reference import bind_borrow_chips, load_fixture_profile
    from backend.app.services.candidates import generate_candidates

    if bars < 8 or bars > 16:
        raise typer.BadParameter("bars must be 8–16")
    settings = _settings(mode, workspace)
    setup_logging(settings.log_level)
    brief = parse_brief(prompt, seed=seed, bars=bars)
    profile = None
    if fixture:
        profile = load_fixture_profile(fixture)
        if trait:
            brief.borrow_chips.extend(bind_borrow_chips(profile, list(trait)))
    multi = generate_candidates(
        brief,
        n=n,
        base_seed=seed,
        settings=settings,
        adapter=_adapter(settings),
        profile=profile,
    )
    console.print(f"[bold green]Project[/] {multi.baseline.project.id}")
    console.print(f"  session: {multi.session_id}")
    _print_candidate_table(multi.candidates)


@app.command("ab")
def ab_cmd(
    project_id: str = typer.Argument(...),
    index_a: int = typer.Option(0, help="Candidate index A"),
    index_b: int = typer.Option(1, help="Candidate index B"),
    choice: str | None = typer.Option(None, help="a|b|tie|skip"),
    reason: str | None = typer.Option(None),
    workspace: Path | None = typer.Option(None),
) -> None:
    """A/B two candidates (MIDI preview proxies when no render)."""
    from backend.app.services.ab_compare import compare_session_pair

    settings = _settings(None, workspace)
    result = compare_session_pair(
        UUID(project_id),
        index_a=index_a,
        index_b=index_b,
        choice=choice,  # type: ignore[arg-type]
        reason=reason,
        settings=settings,
    )
    console.print(f"[bold green]A/B[/] mode={result.path_mode} id={result.comparison_id}")
    console.print(f"  A seed={result.side_a.seed} midi={result.side_a.midi_proxy_path}")
    console.print(f"  B seed={result.side_b.seed} midi={result.side_b.midi_proxy_path}")
    console.print(f"  musical diff: {result.musical_diff.one_line_summary}")
    console.print(f"  roles changed: {result.musical_diff.roles_changed}")
    console.print(
        f"  loudness target: {result.side_a.loudness_notes.target_lufs} LUFS "
        f"({result.side_a.loudness_notes.normalization_status})"
    )
    if result.preference:
        console.print(f"  preference: {result.preference.user_choice}")
    console.print(f"  saved: {result.session_path}")


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
        help="e.g. 'keep the drums, replace bass' or 'soften bass and add a fill'",
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


@app.command()
def versions(
    project_id: str = typer.Argument(...),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Show version timeline + one-line musical diffs."""
    from backend.app.services.versions import list_version_timeline

    settings = _settings(None, workspace)
    entries = list_version_timeline(UUID(project_id), settings=settings)
    if not entries:
        console.print("No versions.")
        return
    table = Table(title=f"Versions — {project_id}")
    table.add_column("Version")
    table.add_column("Parent")
    table.add_column("Seed")
    table.add_column("Diff")
    for e in entries:
        table.add_row(
            str(e.version_id),
            str(e.parent_version_id or "—"),
            str(e.seed if e.seed is not None else "—"),
            (e.one_line_diff or "")[:72],
        )
    console.print(table)


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


@app.command("structure-templates")
def structure_templates_cmd() -> None:
    """List Phase 6 full-song structure templates."""
    from backend.app.music.structure_templates import list_structure_templates

    table = Table(title="Full-song structure templates")
    table.add_column("ID")
    table.add_column("Genre")
    table.add_column("Bars")
    table.add_column("Sections")
    table.add_column("Notes")
    for t in list_structure_templates():
        table.add_row(
            t.id,
            t.genre_template_id,
            str(t.length_bars),
            str(len(t.section_map)),
            (t.notes or "")[:48],
        )
    console.print(table)


@app.command("full-compose")
def full_compose_cmd(
    prompt: str = typer.Argument(..., help="Creative brief / NL request"),
    seed: int | None = typer.Option(None, help="Explicit RNG seed"),
    bars: int | None = typer.Option(
        None, help="Full-song length in bars (32–256; default from structure template)"
    ),
    structure: str | None = typer.Option(
        None, "--structure", help="Structure template id (e.g. afrobeats_full)"
    ),
    scratch: bool = typer.Option(True, "--scratch/--release", help="Scratch vs Release mode"),
    autonomy: str = typer.Option(
        "collaborative", help="suggest-only | collaborative | autonomous"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Bypass Release DAW gate when --autonomy autonomous (logged)",
    ),
    ref: bool = typer.Option(False, "--ref", help="Condition on fixture reference profile"),
    fixture: str = typer.Option("afrobeats", help="Fixture genre when --ref"),
    trait: Annotated[
        list[str] | None, typer.Option(help="Borrow traits when --ref (repeatable)")
    ] = None,
    mode: str | None = typer.Option(None, help="simulation | midi_export"),
    workspace: Annotated[
        Path | None, typer.Option(help="Override workspace directory")
    ] = None,
    lock: Annotated[
        list[str] | None, typer.Option(help="Roles to lock (repeatable)")
    ] = None,
) -> None:
    """Brief/reference → full instrumental + MIDI export + versioned editable project."""
    from backend.app.music.arrangement import MAX_FULL_BARS, MIN_FULL_BARS
    from backend.app.services.full_compose import (
        full_compose_from_prompt,
        full_compose_from_reference,
    )

    if bars is not None and (bars < MIN_FULL_BARS or bars > MAX_FULL_BARS):
        raise typer.BadParameter(f"bars must be {MIN_FULL_BARS}–{MAX_FULL_BARS}")
    settings = _settings(mode, workspace)
    setup_logging(settings.log_level)
    scratch_or_release = "scratch" if scratch else "release"
    locked = list(lock or [])
    try:
        if ref:
            result = full_compose_from_reference(
                prompt,
                traits=list(trait or []),
                fixture=fixture,
                seed=seed,
                structure_id=structure,
                bars=bars,
                scratch_or_release=scratch_or_release,
                autonomy_mode=autonomy,
                settings=settings,
                adapter=_adapter(settings),
                locked_roles=locked,
                force=force,
            )
        else:
            result = full_compose_from_prompt(
                prompt,
                seed=seed,
                structure_id=structure,
                bars=bars,
                scratch_or_release=scratch_or_release,
                autonomy_mode=autonomy,
                settings=settings,
                adapter=_adapter(settings),
                locked_roles=locked,
                force=force,
            )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    console.print(f"[bold green]Full project[/] {result.project.id}")
    console.print(
        f"  structure: {result.plan.structure_template_id}  "
        f"genre: {result.project.genre_template_id}  "
        f"bars: {result.project.length_bars}  "
        f"sections: {len(result.project.sections)}"
    )
    console.print(
        f"  seed: {result.project.seed}  bpm: {result.project.bpm}  "
        f"key: {result.project.key_estimate}  "
        f"mode: {result.plan.scratch_or_release}"
    )
    if result.gated:
        console.print("[yellow]Release gate:[/] DAW write skipped — MIDI + plan only")
    console.print(f"  version: {result.version.id}")
    console.print(f"  candidate: {result.candidate.id if result.candidate else '—'}")
    console.print(f"  plan: {result.arrangement_plan_path}")
    console.print(f"  CIR: projects/{result.project.id}/versions/{result.version.id}.json")

    table = Table(title="Sections")
    table.add_column("Name")
    table.add_column("Bars")
    table.add_column("Intensity")
    for s in result.project.sections:
        table.add_row(s.name, f"{s.start_bar}–{s.end_bar}", f"{s.intensity_target:.2f}")
    console.print(table)

    palette = Table(title="Instrument palette (hints)")
    palette.add_column("Role")
    palette.add_column("Suggestion")
    for role, hint in result.plan.instrument_palette.items():
        palette.add_row(role, hint)
    console.print(palette)

    midi_table = Table(title="Exported MIDI (playable)")
    midi_table.add_column("Role")
    midi_table.add_column("Path")
    for role, path in result.midi_paths.items():
        midi_table.add_row(role, str(path))
    console.print(midi_table)

    console.print(
        f"DAW [{settings.daw_mode.value}]: succeeded={result.daw_result.succeeded} "
        f"verified={result.daw_result.verified} arrange_ops={len(result.arrange_results)}"
    )
    if result.daw_result.user_action_required:
        console.print(f"[yellow]User action:[/] {result.daw_result.user_action_required}")
    console.print("[bold]Manual FL steps[/] (also in manual_fl_steps.json):")
    for step in result.manual_steps[:6]:
        console.print(f"  • {step}")
    if len(result.manual_steps) > 6:
        console.print(f"  … +{len(result.manual_steps) - 6} more")
    _print_moves(result.next_moves)


@app.command("recipe-save")
def recipe_save(
    project_id: str = typer.Argument(..., help="Project UUID to snapshot as a recipe"),
    name: str | None = typer.Option(None, help="Recipe display name"),
    approved: bool = typer.Option(False, help="Mark approved (feeds Phase 5 style vectors)"),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Save a recipe (groove fingerprint + locks) from a project CIR tip."""
    from backend.app.music.recipes import recipe_from_project, save_recipe
    from backend.app.services.revise import _load_cir

    settings = _settings(None, workspace)
    assets = AssetStore(settings)
    project = _load_cir(assets, UUID(project_id), None)
    if project is None:
        raise typer.BadParameter(f"no CIR found for project {project_id}")
    recipe = recipe_from_project(project, name=name, approved=approved)
    path = save_recipe(recipe, assets)
    console.print(f"[bold green]Recipe[/] {recipe.id}")
    console.print(f"  name: {recipe.name}")
    console.print(f"  approved: {recipe.approved}")
    console.print(f"  locks: {recipe.locked_roles or '—'}")
    console.print(f"  path: {path}")


@app.command("recipe-list")
def recipe_list(workspace: Path | None = typer.Option(None)) -> None:
    """List saved recipes."""
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


@app.command("recipe-apply")
def recipe_apply(
    recipe_id: str = typer.Argument(...),
    prompt: str | None = typer.Option(None, help="Override brief text"),
    n: int = typer.Option(2),
    seed: int | None = typer.Option(None),
    bars: int | None = typer.Option(None),
    mode: str | None = typer.Option(None),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Apply a recipe → seed brief + locks → N candidates."""
    from backend.app.music.recipes import apply_recipe

    settings = _settings(mode, workspace)
    setup_logging(settings.log_level)
    assets = AssetStore(settings)
    multi = apply_recipe(
        UUID(recipe_id),
        assets,
        prompt=prompt,
        seed=seed,
        bars=bars,
        n=n,
        settings=settings,
        adapter=_adapter(settings),
    )
    console.print(f"[bold green]Recipe applied → project[/] {multi.baseline.project.id}")
    console.print(f"  recipe_id: {multi.recipe_id}")
    console.print(f"  locks on brief: {multi.brief.locked_roles}")
    _print_candidate_table(multi.candidates)


@app.command()
def critique(
    project_id: str = typer.Argument(..., help="Existing project UUID"),
    fixture: str | None = typer.Option(
        None,
        help="Optional render metrics fixture id (e.g. hot_clipping, muddy_sub)",
    ),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Evaluate CIR/render fixtures and emit typed PatchOps (≤3 next moves)."""
    from backend.app.agents.critic import critique_project
    from backend.app.services.revise import _load_cir

    settings = _settings(None, workspace)
    assets = AssetStore(settings)
    project = _load_cir(assets, UUID(project_id), None)
    if project is None:
        raise typer.BadParameter(f"no CIR found for project {project_id}")
    result = critique_project(project, fixture_id=fixture, max_moves=3)
    board = result.scoreboard
    console.print(f"[bold green]Critique[/] {project.id}")
    if board:
        console.print(
            f"  technical={board.technical:.3f} (fails={board.technical_fail_count})  "
            f"musical={board.musical:.3f} (fails={board.musical_fail_count})"
        )
    if result.findings_summary:
        console.print("[bold]Findings (annotations only):[/]")
        for f in result.findings_summary:
            console.print(f"  • {f}")
    console.print("[bold]Actionable deliverable = typed PatchOps:[/]")
    _print_moves(result.next_moves)
    if not result.next_moves:
        console.print("  (none — mix looks healthy or all roles locked)")


@app.command("revise-loop")
def revise_loop_cmd(
    project_id: str = typer.Argument(..., help="Existing project UUID"),
    max_iters: int = typer.Option(3, help="Bounded revision iterations (cap 3 default)"),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply low-risk PatchOps when measured improvement holds (else suggest-only)",
    ),
    fixture: str | None = typer.Option(None, help="Render metrics fixture id"),
    seed: int | None = typer.Option(None),
    mode: str | None = typer.Option(None, help="simulation | midi_export"),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Bounded critic loop: evaluate → ≤3 PatchOps → measure → rollback if worse."""
    from backend.app.services.revision_loop import run_revision_loop

    settings = _settings(mode, workspace)
    setup_logging(settings.log_level)
    result = run_revision_loop(
        UUID(project_id),
        max_iterations=max_iters,
        apply_ops=apply,
        fixture_id=fixture,
        seed=seed,
        settings=settings,
        adapter=_adapter(settings),
    )
    console.print(f"[bold green]Revision loop[/] {result.project.id}")
    console.print(f"  stopped: {result.stopped_reason}")
    console.print(f"  applied: {result.applied}")
    console.print(f"  undo verified: {result.undo_verified}")
    if result.user_confirmation_required:
        console.print("[yellow]Awaiting confirmation[/] — pass --apply to execute low-risk ops")
    if result.initial_scoreboard and result.final_scoreboard:
        b, a = result.initial_scoreboard, result.final_scoreboard
        console.print(
            f"  technical {b.technical:.3f}→{a.technical:.3f}  "
            f"musical {b.musical:.3f}→{a.musical:.3f}"
        )
    for it in result.iterations:
        flag = "✓" if it.accepted else ("↩" if it.rolled_back else "·")
        console.print(f"  [{flag}] iter {it.index}: {it.reason}")
        for op in it.ops:
            console.print(f"      - {op.action_type} → {op.target_role} ({op.verification_status})")
    if result.version:
        console.print(f"  version: {result.version.id}")
        console.print(f"  one-line diff: {result.candidate.one_line_diff if result.candidate else '—'}")
    _print_moves(result.next_moves)


@app.command("restore")
def restore_cmd(
    project_id: str = typer.Argument(..., help="Project UUID"),
    version_id: str = typer.Argument(..., help="Restorable version UUID"),
    mode: str | None = typer.Option(None),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Restore project CIR tip to a prior version (rollback)."""
    from backend.app.services.revision_loop import restore_project_version

    settings = _settings(mode, workspace)
    project = restore_project_version(
        UUID(project_id),
        UUID(version_id),
        settings=settings,
        adapter=_adapter(settings),
    )
    console.print(f"[bold green]Restored[/] {project.id} → version {project.version_id}")


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


# --- Phase 5: personal taste -------------------------------------------------


@app.command("taste-simulate")
def taste_simulate(
    n_projects: int = typer.Option(8, help="Distinct projects for holdout splits"),
    pairs: int = typer.Option(4, help="Pairs per project"),
    seed: int = typer.Option(42),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Generate synthetic pairwise preferences (CI / demo; no listening required)."""
    from backend.app.taste.simulate import build_simulated_dataset

    settings = _settings(None, workspace)
    settings.ensure_workspace()
    pairs_out = build_simulated_dataset(
        n_projects=n_projects,
        pairs_per_project=pairs,
        settings=settings,
        seed=seed,
        persist=True,
    )
    console.print(
        f"[bold green]Simulated[/] {len(pairs_out)} pairwise comparisons "
        f"across {n_projects} projects → workspace/taste/comparisons/"
    )


@app.command("taste-train")
def taste_train(
    version: str = typer.Option("0.1.0"),
    seed: int = typer.Option(0),
    epochs: int = typer.Option(250),
    no_activate: bool = typer.Option(False, help="Register but never activate"),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Train frozen-encoder ranking head; activate only if holdout beats retrieval."""
    from backend.app.taste.pipeline import train_and_evaluate

    settings = _settings(None, workspace)
    settings.ensure_workspace()
    result = train_and_evaluate(
        settings=settings,
        version=version,
        seed=seed,
        epochs=epochs,
        activate_if_better=not no_activate,
    )
    er = result.eval_report
    console.print(f"[bold green]Checkpoint[/] {result.checkpoint.id} v={result.checkpoint.version}")
    console.print(f"  encoder: {result.encoder_name}")
    console.print(f"  decisive pairs: {result.n_decisive}")
    console.print(
        f"  holdout ranking acc={er.ranking['accuracy']:.3f} "
        f"logloss={er.ranking['logloss']:.3f}"
    )
    console.print(
        f"  retrieval baseline acc={er.retrieval['accuracy']:.3f} "
        f"| random≈{er.random['accuracy']:.3f}"
    )
    console.print(
        f"  better_than_retrieval={er.better_than_retrieval} "
        f"activated={result.activated}"
    )
    console.print(f"  saved: {result.checkpoint_path}")
    for n in result.notes:
        console.print(f"  note: {n}")


@app.command("taste-eval")
def taste_eval(
    seed: int = typer.Option(0),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Re-evaluate active (or latest) ranking head on project-held-out pairs."""
    from backend.app.taste.encoder import get_frozen_encoder
    from backend.app.taste.evaluation import evaluate_ranking
    from backend.app.taste.pipeline import _load_pair_matrices
    from backend.app.taste.ranking import PairwiseRankingHead
    from backend.app.taste.registry import get_active_checkpoint, list_checkpoints
    from backend.app.taste.retrieval import RetrievalBaseline

    settings = _settings(None, workspace)
    ckpt = get_active_checkpoint(settings=settings)
    if ckpt is None:
        ckpts = list_checkpoints(settings=settings)
        if not ckpts:
            raise typer.Exit("No taste checkpoints — run taste-simulate && taste-train")
        ckpt = ckpts[-1]
        console.print(f"[yellow]No active model — evaluating latest[/] {ckpt.id}")
    encoder = get_frozen_encoder(settings)
    emb_a, emb_b, labels, project_ids = _load_pair_matrices(settings, encoder)
    head = PairwiseRankingHead.from_checkpoint(ckpt)
    report = evaluate_ranking(
        head, emb_a, emb_b, labels, project_ids, seed=seed, retrieval=RetrievalBaseline()
    )
    console.print_json(
        json.dumps(
            {
                "checkpoint_id": str(ckpt.id),
                "ranking": report.ranking,
                "retrieval": report.retrieval,
                "random": report.random,
                "better_than_retrieval": report.better_than_retrieval,
                "calibration_bins": report.calibration_bins,
                "notes": report.notes,
            },
            indent=2,
        )
    )


@app.command("taste-registry")
def taste_registry(workspace: Path | None = typer.Option(None)) -> None:
    """List taste model checkpoints and active marker."""
    from backend.app.taste.registry import get_active_checkpoint, list_checkpoints

    settings = _settings(None, workspace)
    active = get_active_checkpoint(settings=settings)
    table = Table(title="Taste model registry")
    table.add_column("Active")
    table.add_column("Version")
    table.add_column("ID")
    table.add_column("Holdout acc")
    table.add_column("Better?")
    for c in list_checkpoints(settings=settings):
        acc = c.holdout_metrics.get("accuracy")
        table.add_row(
            "✓" if active and c.id == active.id else "",
            c.version,
            str(c.id),
            f"{acc:.3f}" if isinstance(acc, float) else "—",
            "yes" if c.better_than_baseline else "no",
        )
    console.print(table)


@app.command("taste-activate")
def taste_activate(
    checkpoint_id: str = typer.Argument(..., help="Checkpoint UUID to activate"),
    force: bool = typer.Option(
        False,
        "--force",
        help="Bypass better-than-retrieval gate (logged on checkpoint notes)",
    ),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Activate a taste checkpoint (refuses unless better_than_baseline, unless --force)."""
    from uuid import UUID

    from backend.app.taste.registry import activate_checkpoint

    settings = _settings(None, workspace)
    try:
        ckpt = activate_checkpoint(UUID(checkpoint_id), settings=settings, force=force)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from exc
    suffix = " (forced)" if force and not ckpt.better_than_baseline else ""
    console.print(f"[bold green]Activated[/] → {ckpt.id} v={ckpt.version}{suffix}")


@app.command("taste-rollback")
def taste_rollback(workspace: Path | None = typer.Option(None)) -> None:
    """Roll back to the previously active taste checkpoint."""
    from backend.app.taste.registry import rollback_checkpoint

    settings = _settings(None, workspace)
    prev = rollback_checkpoint(settings=settings)
    if prev is None:
        console.print("[yellow]No previous checkpoint — registry cleared/inactive[/]")
    else:
        console.print(f"[bold green]Rolled back[/] → {prev.id} v={prev.version}")


@app.command("taste-profile")
def taste_profile(workspace: Path | None = typer.Option(None)) -> None:
    """Show transparent taste profile (recorded data only)."""
    from backend.app.taste.dataset import taste_profile_summary

    settings = _settings(None, workspace)
    summary = taste_profile_summary(settings=settings)
    console.print_json(summary.model_dump_json(indent=2))


@app.command("journal-add")
def journal_add(
    project_id: str = typer.Argument(...),
    notes: str = typer.Argument(...),
    rating: float | None = typer.Option(None, min=0, max=5),
    version_id: str | None = typer.Option(None),
    tag: list[str] | None = typer.Option(None),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Append a listening-journal entry tied to a project/version."""
    from backend.app.models.schemas import ListeningJournalEntry
    from backend.app.taste.dataset import record_journal_entry

    settings = _settings(None, workspace)
    entry = ListeningJournalEntry(
        project_id=UUID(project_id),
        version_id=UUID(version_id) if version_id else None,
        notes=notes,
        tags=list(tag or []),
        rating=rating,
    )
    path = record_journal_entry(entry, settings=settings)
    console.print(f"[bold green]Journal[/] {entry.id} → {path}")


@app.command("journal-list")
def journal_list(workspace: Path | None = typer.Option(None)) -> None:
    """List listening-journal entries."""
    from backend.app.taste.dataset import list_journal

    settings = _settings(None, workspace)
    entries = list_journal(settings=settings)
    table = Table(title="Listening journal")
    table.add_column("ID")
    table.add_column("Project")
    table.add_column("Rating")
    table.add_column("Notes")
    for e in entries:
        table.add_row(
            str(e.id)[:8],
            str(e.project_id)[:8],
            "" if e.rating is None else str(e.rating),
            e.notes[:60],
        )
    console.print(table)


@app.command("style-vectors")
def style_vectors_cmd(
    approved_only: bool = typer.Option(True),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Derive style vectors from approved recipes (no-op if none approved)."""
    from backend.app.taste.style_vectors import derive_style_vectors, list_style_vectors

    settings = _settings(None, workspace)
    derived = derive_style_vectors(settings=settings, approved_only=approved_only)
    all_v = list_style_vectors(settings=settings)
    console.print(
        f"[bold green]Style vectors[/] derived={len(derived)} total={len(all_v)} "
        f"(approved_only={approved_only})"
    )
    if not derived and not all_v:
        console.print(
            "  [yellow]No approved recipes with CIR — save+approve a recipe first "
            "(music-ai recipe-save …). Vectors are not invented.[/]"
        )


@app.command("research-status")
def research_status_cmd(
    workspace: Path | None = typer.Option(None),
) -> None:
    """Phase 7 research capability registry (stubs + hooks; no model downloads)."""
    from backend.app.research.registry import research_status

    settings = _settings(None, workspace)
    status = research_status(settings)
    console.print_json(data=status)


@app.command("research-eval")
def research_eval_cmd(
    prompt: Annotated[str, typer.Argument()] = "mellow Afrobeats 110 BPM in A minor",
    seed: int = typer.Option(42),
    bars: int = typer.Option(8, min=8, max=16),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Simulation eval harness: Phase 7 specialist path vs Phase 6 baseline."""
    from backend.app.research.eval_harness import run_phase7_baseline_eval
    from backend.app.storage.assets import AssetStore

    settings = _settings(None, workspace)
    result = run_phase7_baseline_eval(prompt, seed=seed, bars=bars, settings=settings)
    assets = AssetStore(settings)
    out = assets.write_json(
        f"research/eval/{result.id}.json",
        result.model_dump(mode="json"),
    )
    console.print(
        f"[bold green]Research eval[/] preference_proxy={result.preference_proxy} "
        f"Δtech={result.delta_technical:+.4f} Δmus={result.delta_musical:+.4f}"
    )
    console.print(f"  blind_listening_status={result.blind_listening_status} (sim only)")
    console.print(f"  wrote {out}")
    for n in result.notes:
        console.print(f"  · {n}")


@app.command("action-effect-log")
def action_effect_log_cmd(
    project_id: str | None = typer.Option(None, "--project"),
    accepted_only: bool = typer.Option(False),
    workspace: Path | None = typer.Option(None),
) -> None:
    """List logged revision outcomes for action-effect scaffolding."""
    from uuid import UUID

    from backend.app.research.action_effect import list_revision_outcomes

    settings = _settings(None, workspace)
    pid = UUID(project_id) if project_id else None
    rows = list_revision_outcomes(
        settings=settings, project_id=pid, accepted_only=accepted_only
    )
    table = Table(title=f"Revision outcomes ({len(rows)})")
    table.add_column("id")
    table.add_column("project")
    table.add_column("accepted")
    table.add_column("Δtech")
    table.add_column("Δmus")
    table.add_column("ops")
    for r in rows:
        ops = ",".join(o.action_type for o in r.ops)[:40]
        table.add_row(
            str(r.id)[:8],
            str(r.project_id)[:8],
            "yes" if r.accepted else "no",
            "" if r.delta_technical is None else f"{r.delta_technical:+.3f}",
            "" if r.delta_musical is None else f"{r.delta_musical:+.3f}",
            ops or "—",
        )
    console.print(table)


@app.command("mix-heuristics")
def mix_heuristics_cmd(
    project_id: Annotated[str, typer.Argument()],
    workspace: Path | None = typer.Option(None),
) -> None:
    """Run advanced mix heuristic stubs on a CIR project (simulation)."""
    from uuid import UUID

    from backend.app.research.mix_heuristics import run_advanced_mix_heuristics
    from backend.app.services.revise import _load_cir

    settings = _settings(None, workspace)
    assets = AssetStore(settings)
    project = _load_cir(assets, UUID(project_id), None)
    if project is None:
        raise typer.BadParameter(f"project {project_id} not found")
    report = run_advanced_mix_heuristics(project)
    console.print(
        f"[bold green]Advanced mix[/] overall={report.overall_mix_score:.3f} "
        f"source={report.source}"
    )
    for h in report.heuristics:
        console.print(f"  [{h.severity}] {h.name}: {h.score:.2f} — {h.suggestion}")


@app.command("vocal-stub")
def vocal_stub_cmd(
    project_id: Annotated[str, typer.Argument()],
    lyric: str | None = typer.Option(None, "--lyric"),
    apply: bool = typer.Option(False, "--apply", help="Write guide-MIDI vocal track into CIR tip"),
    workspace: Path | None = typer.Option(None),
) -> None:
    """Optional vocal workflow stub — guide MIDI only; no neural singing."""
    from uuid import UUID

    from backend.app.models.db import init_db
    from backend.app.research.vocal import get_vocal_workflow
    from backend.app.services.revise import _load_cir
    from backend.app.storage.repository import ProjectRepository

    settings = _settings(None, workspace)
    assets = AssetStore(settings)
    project = _load_cir(assets, UUID(project_id), None)
    if project is None:
        raise typer.BadParameter(f"project {project_id} not found")
    wf = get_vocal_workflow(settings)
    plan = wf.plan_vocals(project, lyric_hint=lyric)
    console.print(f"[bold green]Vocal plan[/] mode={plan.mode} bars={plan.bars}")
    for n in plan.notes:
        console.print(f"  · {n}")
    if apply:
        updated = wf.apply_guide_melody(project, plan)
        session_factory = init_db(settings)
        ProjectRepository(session_factory).save_project(updated)
        assets.write_json(
            f"projects/{updated.id}/vocal_plan.json",
            plan.model_dump(mode="json"),
        )
        console.print(
            f"  applied guide MIDI vocal track; tracks={len(updated.tracks)} "
            f"(CIR tip updated — re-export MIDI via compose/revise as needed)"
        )


@app.command("list-daws")
def list_daws_cmd() -> None:
    """List multi-DAW adapter registry (FakeDaw / MidiExport + Phase 7 stubs)."""
    from backend.app.daw.registry import list_daw_adapters

    table = Table(title="DAW adapters")
    table.add_column("id")
    table.add_column("live")
    table.add_column("description")
    for row in list_daw_adapters():
        table.add_row(row["id"], "yes" if row["live"] else "no", row["description"])
    console.print(table)


if __name__ == "__main__":
    app()
