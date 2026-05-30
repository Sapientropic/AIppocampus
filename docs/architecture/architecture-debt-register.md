# Architecture Debt Register

This is the lightweight guardrail for oversized runtime scripts. It is not a
scorecard and it should not replace source-backed design decisions. Its job is
only to keep large-file debt visible: every `skills/aippocampus/scripts/*.py`
file at or above 600 non-comment LOC must be listed here with a guard budget
and a next plausible boundary.

For contributor onboarding, dependency flow, maintenance/core-recall separation,
and recall test visibility, use `runtime-script-map.md`. This register only
answers "which large scripts need an explicit split boundary next?"

The enforcing test is
`tests/aippocampus/test_architecture_boundaries.py::ArchitectureBoundaryTests.test_large_runtime_scripts_have_debt_register_budgets`.
If a file grows past its budget, either split a real responsibility out or raise
the budget here with a concrete reason. Do not raise budgets as a routine way to
make tests pass.

| Path | Guard budget | Primary responsibility | Next boundary to consider |
| --- | ---: | --- | --- |
| `skills/aippocampus/scripts/warm_ambient_recall.py` | 1350 | Warm scout runtime orchestration, model calls, result merging, cache writes, route capability metadata, and CLI/job entrypoints | Split provider route binding or cache/job execution helpers only after the runtime API stabilizes further; source validation, scout profiles, and prompt rendering already have modules. |
| `skills/aippocampus/scripts/retrieval.py` | 740 | Hybrid SQLite/RAG-lite retrieval execution, result ranking, and recall result assembly | Split ranking diversification from SQLite execution if retrieval tuning keeps growing; query expansion and anchor policy already live in `retrieval_query_policy.py`. |
| `skills/aippocampus/scripts/registry.py` | 715 | Thread registry schema normalization, path handling, provider-aware scan guardrails, and artifact bookkeeping | Move path repair/export compatibility into a registry maintenance helper if sync-specific cases keep accumulating; search/ranking now lives in `registry_search.py`. |
| `skills/aippocampus/scripts/semantic_recall_gate.py` | 1020 | Semantic recall gating, candidate judgement, provider capability metadata, unavailable-path diagnostics, failure buckets, cue-aware cache keys, and evidence-aware suppression | Separate prompt construction/model response parsing from deterministic gate decisions if more providers are added. |
| `skills/aippocampus/scripts/build_concept_graph.py` | 720 | Concept graph extraction and graph artifact construction | Separate graph schema/write layer from extraction heuristics if graph consumers multiply. |
| `skills/aippocampus/scripts/subconscious_scheduler.py` | 720 | Background job scheduling, queue eligibility, and lifecycle timing | Split eligibility policy from scheduler IO when additional job classes land. |
| `skills/aippocampus/scripts/sync_bundle.py` | 780 | Local-folder sync bundle manifest, chunk copy, conflict preservation, and path repair policy | Split path repair and conflict handling into focused helpers if additional sync backends start copying this policy. |
| `skills/aippocampus/scripts/prompt_recall_decision.py` | 760 | Foreground recall decision orchestration across cues, semantic gate, budget diagnostics, source-ref cue fallback candidates, evidence, and ambient attach | Extract candidate assembly or evidence decision only after adding golden recall-decision fixtures; do not push more policy into the hook glue. |
| `skills/aippocampus/scripts/subconscious_jobs.py` | 710 | Subconscious job circuit runner, tool-loop wiring, provider route metadata, sample ordering, deterministic follow-up ordering, and append-only staging writes | Split semantic runner execution from deterministic follow-up orchestration if more non-model jobs join `--job all`. |
| `skills/aippocampus/scripts/memory_candidate_router.py` | 660 | Promotion-candidate routing, source-strength scoring, working-memory foreground matching, hook-safe stripping, and dream-hypothesis foreground gates | Split foreground match/gate policy from candidate routing if more candidate-specific live-use rules land after the dream-hypothesis gate. |
| `skills/aippocampus/scripts/question_tracking.py` | 1060 | Deterministic Phase 2 question-link tracking over staged question candidates, including salience tags, adaptive separation/completion thresholds, local multi-field scoring, ordering edges, confirmation audit, and CLI output | Split salience/threshold policy into a focused helper before adding live calibration, dormancy detection, or model-confirmation plumbing; source-ref resolution already lives in `question_source_refs.py`. |
| `skills/aippocampus/scripts/correction_reconsolidation.py` | 720 | Correction activation/outcome event builders, privacy-scanned evidence shaping, detached adjudication candidates, active-anchor rendering, and CLI output | Split event sanitization or anchor rendering into focused helpers if live hook capture lands and starts sharing this logic with foreground hooks. |
| `skills/aippocampus/scripts/dream_input_pack.py` | 760 | Source-backed dream input pack assembly, seed adapters for question/Journey/ambient/concept/theme/correction/reflection/agency rows, readiness audit, weak-handle handling, and CLI output | Split seed adapters into a focused helper if more dream seed families land after #132, or if live worker scheduling starts sharing seed normalization. |
| `skills/aippocampus/scripts/dream_real_history_eval.py` | 908 | Selected real-history dream pack selection, deterministic fallback worker, optional bounded model-backed worker handoff, structural and user-visible ablation metrics, sanitized aggregate output, and CLI wiring | Split pack selection and visibility-ablation scoring into focused helpers before adding live smoke orchestration, larger manual source-review slices, or additional eval surfaces. Keep model-backed prompt/validation policy in `dream_worker.py`. |
| `skills/aippocampus/scripts/dream_worker.py` | 660 | Bounded model-backed compensatory/amplification/prospective/active-imagination dream prompt shaping, source-ref-id validation, sandbox risk gates, background adjudication handoff, no-write summaries, and retrospective prospective validation | Split retrospective validation, active-imagination risk gating, or prompt-schema shaping into focused helpers before adding live retry orchestration, provider-specific repair loops, or more creative synthesis surfaces. |
| `skills/aippocampus/scripts/reflection_space.py` | 660 | Journey reflection topology, source-ref-carried feedback adjustments, AAR strategy hints, and collapsed adjudicated dream-hypothesis nodes with source-reopen boundaries | Split dream-hypothesis node shaping or feedback-adjustment policy into focused helpers before adding visual layout, richer topology clustering, or live reflection UI orchestration. |
| `skills/aippocampus/scripts/prompt_cues.py` | 660 | Static cue taxonomy, multilingual recall cues, and query expansion bootstrap tables | Split broad cue catalogs from intent/gating helpers if cue additions keep landing without product-level review. |
| `skills/aippocampus/scripts/sync_object_storage.py` | 650 | Object-storage sync CLI wiring, provider argument resolution, and shared bundle transport orchestration | Split CLI/provider config from transport orchestration if more providers or auth modes are added. |
