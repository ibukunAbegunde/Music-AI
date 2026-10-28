"""Critic lock-awareness + recipe save/load stubs."""

from __future__ import annotations

from backend.app.agents.critic import propose_next_moves
from backend.app.core.config import Settings
from backend.app.music.coedit import apply_role_locks
from backend.app.music.generators import generate_eight_bar_project
from backend.app.music.recipes import list_recipes, load_recipe, recipe_from_project, save_recipe
from backend.app.storage.assets import AssetStore


def test_next_moves_skip_locked_drums() -> None:
    p = apply_role_locks(generate_eight_bar_project("Afrobeats 110", seed=1), ["drums"])
    moves = propose_next_moves(p)
    assert moves
    assert all(m.target_role != "drums" for m in moves)
    assert all(m.target_role in {"bass", "chord"} for m in moves)


def test_recipe_save_load(tmp_settings: Settings) -> None:
    assets = AssetStore(tmp_settings)
    project = generate_eight_bar_project("Amapiano 112", seed=7)
    project = apply_role_locks(project, ["drums"])
    recipe = recipe_from_project(project, name="amapiano-kit")
    path = save_recipe(recipe, assets)
    assert path.exists()
    loaded = load_recipe(recipe.id, assets)
    assert loaded is not None
    assert loaded.name == "amapiano-kit"
    assert "drums" in loaded.locked_roles
    listed = list_recipes(assets)
    assert any(r.id == recipe.id for r in listed)
