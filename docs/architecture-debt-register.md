# Architecture Debt Register

This is the lightweight guardrail for oversized runtime scripts. It is not a
scorecard and it should not replace source-backed design decisions. Its job is
only to keep large-file debt visible: every `skills/aippocampus/scripts/*.py`
file at or above 600 non-comment LOC must be listed here with a guard budget
and a next plausible boundary.

The enforcing test is
`tests/aippocampus/test_architecture_boundaries.py::ArchitectureBoundaryTests.test_large_runtime_scripts_have_debt_register_budgets`.
If a file grows past its budget, either split a real responsibility out or raise
the budget here with a concrete reason. Do not raise budgets as a routine way to
make tests pass.

| Path | Guard budget | Primary responsibility | Next boundary to consider |
| --- | ---: | --- | --- |
| `skills/aippocampus/scripts/warm_ambient_recall.py` | 1300 | Warm scout runtime orchestration, model calls, result merging, cache writes, and CLI/job entrypoints | Split cache/job execution helpers only after the runtime API stabilizes further; source validation, scout profiles, and prompt rendering already have modules. |
| `skills/aippocampus/scripts/retrieval.py` | 740 | Hybrid SQLite/RAG-lite retrieval execution, result ranking, and recall result assembly | Split ranking diversification from SQLite execution if retrieval tuning keeps growing; query expansion and anchor policy already live in `retrieval_query_policy.py`. |
| `skills/aippocampus/scripts/registry.py` | 710 | Thread registry schema normalization, path handling, and artifact bookkeeping | Move path repair/export compatibility into a registry maintenance helper if sync-specific cases keep accumulating; search/ranking now lives in `registry_search.py`. |
| `skills/aippocampus/scripts/semantic_recall_gate.py` | 840 | Semantic recall gating, candidate judgement, and evidence-aware suppression | Separate prompt construction/model response parsing from deterministic gate decisions if more providers are added. |
| `skills/aippocampus/scripts/build_concept_graph.py` | 720 | Concept graph extraction and graph artifact construction | Separate graph schema/write layer from extraction heuristics if graph consumers multiply. |
| `skills/aippocampus/scripts/subconscious_scheduler.py` | 720 | Background job scheduling, queue eligibility, and lifecycle timing | Split eligibility policy from scheduler IO when additional job classes land. |
