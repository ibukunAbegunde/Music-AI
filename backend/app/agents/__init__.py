"""Agent helpers: critic (typed PatchOps), future planner/composer."""

from backend.app.agents.critic import critique_project, propose_next_moves

__all__ = ["critique_project", "propose_next_moves"]
