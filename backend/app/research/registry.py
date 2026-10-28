"""Research capability registry — honest status for Phase 7 hooks."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.app.core.config import Settings, get_settings
from backend.app.daw.registry import list_daw_adapters


class ResearchCapability(BaseModel):
    id: str
    name: str
    status: str  # shipped | stub | refused | blocked
    verification: str  # mock-tested | manual-fallback | blocked
    notes: str = ""
    config_key: str | None = None


def research_status(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    caps = [
        ResearchCapability(
            id="midi_specialist",
            name="Specialist MIDI composition hooks",
            status="shipped",
            verification="mock-tested",
            notes="Default = deterministic generators; optional neural refuses without approval.",
            config_key="midi_specialist",
        ),
        ResearchCapability(
            id="action_effect",
            name="Action-effect / revision outcome scaffolding",
            status="shipped",
            verification="mock-tested",
            notes="Logs RevisionOutcome; HeuristicActionEffectPredictor (not trained).",
            config_key=None,
        ),
        ResearchCapability(
            id="advanced_mix",
            name="Advanced mix / mastering heuristics",
            status="stub",
            verification="mock-tested",
            notes="Simulation proxies (sidechain/stereo/master/sub/DR) — not a mastering AI.",
            config_key=None,
        ),
        ResearchCapability(
            id="vocal_workflow",
            name="Optional vocal workflow",
            status="stub",
            verification="mock-tested",
            notes="Guide-MIDI stub; neural vocal refuses without MUSIC_AI_ALLOW_VOCAL_MODEL_DOWNLOAD.",
            config_key="vocal_workflow",
        ),
        ResearchCapability(
            id="multi_daw",
            name="Multi-DAW adapter interface",
            status="shipped",
            verification="mock-tested",
            notes="Registry beyond FakeDaw/MidiExport; other DAWs are honest refuse stubs.",
            config_key="daw_mode",
        ),
        ResearchCapability(
            id="dual_path",
            name="Neural audio dual-path (CIR SoR)",
            status="shipped",
            verification="mock-tested",
            notes="Policy + side-artifact helper; no foundation model download.",
            config_key=None,
        ),
        ResearchCapability(
            id="blind_eval_harness",
            name="Blind listening eval harness vs Phase 6",
            status="shipped",
            verification="mock-tested",
            notes="Simulation proxy + BlindListeningHarness scaffold; real listening not run in CI.",
            config_key=None,
        ),
    ]
    return {
        "phase": 7,
        "schema_version": settings.schema_version,
        "allow_specialist_download": bool(
            getattr(settings, "music_ai_allow_specialist_download", False)
        ),
        "allow_vocal_model_download": bool(
            getattr(settings, "music_ai_allow_vocal_model_download", False)
        ),
        "midi_specialist": getattr(settings, "midi_specialist", "deterministic"),
        "vocal_workflow": getattr(settings, "vocal_workflow", "stub"),
        "capabilities": [c.model_dump() for c in caps],
        "daw_adapters": list_daw_adapters(),
        "non_claims": [
            "No foundation models downloaded or trained from scratch.",
            "Simulation preference_proxy ≠ blind listening win.",
            "Advanced mix heuristics ≠ radio-ready mastering.",
            "Vocal guide MIDI ≠ synthesized vocals.",
        ],
    }
