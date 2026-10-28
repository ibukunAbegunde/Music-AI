# Phase 5 report — Personal taste model

Date: 2026-10-28  
Spec: **v1.1** (`ai-music-producer-build-spec.md` §10 + §16 Phase 5 + `product-upgrades-v1.1.md` §10)  
Mode: **simulation** (CIR feature projection as frozen encoder; synthetic pairwise OK). No CLAP/MERT download.

## Exit criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Pairwise comparison collection | ✅ | `taste/dataset.py`; A/B `--choice` also appends features |
| Listening journal | ✅ | `journal-add` / `journal-list`; `ListeningJournalEntry` persisted |
| Retrieval-based baseline | ✅ | `taste/retrieval.py` nearest-neighbour on preferred embeds |
| Frozen-encoder ranking head | ✅ | `SimulationFrozenEncoder` + logistic pairwise head (`P(B>A)=sigmoid(sB−sA)`) |
| Style vectors from approved recipes | ✅ | `taste/style_vectors.py` — only when approved CIR exists |
| Held-out evaluation (by project) | ✅ | `taste/evaluation.py` project holdout + calibration bins |
| Model registry / rollback | ✅ | `taste/registry.py`; activate only if better than retrieval |
| Honest calibration / deploy gate | ✅ | `train_and_evaluate` refuses activation if holdout ≤ retrieval |
| No large model downloads | ✅ | optional encoder refuses without `MUSIC_AI_ALLOW_ENCODER_DOWNLOAD` |
| Tests + status docs | ✅ | unit + integration; this report; `IMPLEMENTATION_STATUS.md` |

## What is real vs stub

| Piece | Reality |
|-------|---------|
| Pairwise dataset + journal store | **Real** (JSON under `workspace/taste/`) |
| CIR → 32-d musical feature vector | **Real** deterministic proxies (BPM, density, syncopation, …) |
| Frozen encoder | **Honest stub interface**: `SimulationFrozenEncoder` = fixed seeded projection of CIR features. Optional CLAP/MERT path **refuses** unless flag + install (not bundled). |
| Pairwise logistic ranking head | **Real** numpy SGD on frozen embeds |
| Retrieval baseline | **Real** cosine NN heuristic |
| Holdout-by-project eval | **Real** (pair-fraction fallback only if single project) |
| Deploy gate + registry/rollback | **Real** |
| Style vectors | **Real** embeddings from approved recipe CIR via simulation encoder |
| Simulated pairwise generator | **Synthetic** planted preference for CI (`taste-simulate`) |
| Pretrained audio embeddings (CLAP/MERT) | **Not installed** — deferred behind approval flag |

## What shipped

- `backend/app/taste/` — features, encoder, dataset, retrieval, ranking, training, evaluation, registry, style_vectors, simulate, pipeline
- Schemas: extended `PreferenceComparison`; `StyleVector`, `TasteModelCheckpoint`, `TasteProfileSummary`
- CLI: `taste-simulate`, `taste-train`, `taste-eval`, `taste-registry`, `taste-rollback`, `taste-profile`, `journal-add`, `journal-list`, `style-vectors`
- A/B compare writes into taste dataset when `--choice` is set

## Non-claims

- No claim of >70% pairwise accuracy as a product guarantee.
- Simulation encoder ≠ pretrained audio embedding quality.
- Style vectors are not invented when no approved recipes exist.
- Phase 6 autonomous full-length **not started**.

## How to demo

```bash
pip install -e ".[dev]"
pytest tests/unit/test_taste_*.py tests/integration/test_phase5_taste.py

music-ai taste-simulate --n-projects 8 --pairs 4
music-ai taste-train
music-ai taste-eval
music-ai taste-registry
music-ai taste-profile
music-ai journal-add <project-id> "liked the bass bounce" --rating 4 --tag bass
music-ai style-vectors   # no-op until an approved recipe exists

# live A/B → taste dataset:
music-ai compose "Afrobeats 110 BPM" --seed 42 --n 2
music-ai ab <project-id> --choice b --reason "prefer B"
```

## Verification labels

| Path | Label |
|------|-------|
| Pairwise / journal / registry / eval | `mock-tested` (simulation) |
| Ranking head train/eval | `mock-tested` (synthetic + CIR features) |
| Optional audio encoder | `blocked` until approved download |
| Live listening preference studies | `manual-fallback` / not run in CI |
