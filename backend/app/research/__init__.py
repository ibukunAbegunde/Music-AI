"""Phase 7 research upgrades — interfaces, honest stubs, eval harnesses.

No large foundation models are downloaded or trained from scratch here.
Real specialist / vocal / mix models plug in later behind explicit user approval.
CIR/MIDI remains the system of record (neural dual-path refinements welcome).
"""

from backend.app.research.action_effect import (
    ActionEffectPredictor,
    HeuristicActionEffectPredictor,
    RevisionOutcome,
    append_revision_outcome,
    list_revision_outcomes,
    predict_effect,
)
from backend.app.research.eval_harness import (
    BlindListeningHarness,
    ResearchEvalResult,
    run_phase7_baseline_eval,
)
from backend.app.research.midi_specialist import (
    DeterministicMidiSpecialist,
    MidiSpecialist,
    MidiSpecialistRequest,
    MidiSpecialistResult,
    OptionalNeuralMidiSpecialist,
    get_midi_specialist,
)
from backend.app.research.mix_heuristics import (
    AdvancedMixReport,
    MixHeuristic,
    StubAdvancedMixHeuristics,
    run_advanced_mix_heuristics,
)
from backend.app.research.registry import ResearchCapability, research_status
from backend.app.research.vocal import (
    StubVocalWorkflow,
    VocalPlan,
    VocalWorkflow,
    get_vocal_workflow,
)

__all__ = [
    "ActionEffectPredictor",
    "AdvancedMixReport",
    "BlindListeningHarness",
    "DeterministicMidiSpecialist",
    "HeuristicActionEffectPredictor",
    "MidiSpecialist",
    "MidiSpecialistRequest",
    "MidiSpecialistResult",
    "MixHeuristic",
    "OptionalNeuralMidiSpecialist",
    "ResearchCapability",
    "ResearchEvalResult",
    "RevisionOutcome",
    "StubAdvancedMixHeuristics",
    "StubVocalWorkflow",
    "VocalPlan",
    "VocalWorkflow",
    "append_revision_outcome",
    "get_midi_specialist",
    "get_vocal_workflow",
    "list_revision_outcomes",
    "predict_effect",
    "research_status",
    "run_advanced_mix_heuristics",
    "run_phase7_baseline_eval",
]
