# Architecture Debt Register

Role: implementation map.

This is the lightweight action board for oversized runtime scripts and
repo-owned test / benchmark / tool harnesses. It is not a scorecard and it does
not replace source-backed design decisions.

Full budget metadata lives in
[`docs/evidence/architecture-debt-snapshot-2026-06-04.md`](../evidence/architecture-debt-snapshot-2026-06-04.md).
Generate the current count/status report with:

```powershell
python tools\aippocampus\docs\debt_report.py --json
```

For contributor onboarding, dependency flow, maintenance/core-recall separation,
and recall test visibility, use
[`runtime-script-map.md`](./runtime-script-map.md). This register only answers
"which large files need attention next?"

The enforcing tests are:

- `tests/aippocampus/test_architecture_boundaries.py::ArchitectureBoundaryTests.test_large_runtime_scripts_have_debt_register_budgets`
- `tests/aippocampus/test_architecture_boundaries.py::ArchitectureBoundaryTests.test_large_tests_benchmarks_and_tools_have_debt_register_budgets`

If a file grows past its budget, either split a real responsibility out or raise
the budget with a concrete owner-boundary reason. Do not raise budgets as a
routine way to make tests pass.

## Near-Budget Split Priority Queue

Last counted: 2026-06-10.
Counting method: `script_line_count()` from
`tests/aippocampus/test_architecture_boundaries.py`: nonblank lines excluding
lines whose first non-space character is `#`.

This queue is intentionally small. It ranks modules that are at or near their
guard budgets by product/runtime risk and next owner boundary, not by LOC alone.
Closed or fully stable inventory rows belong in the evidence snapshot, not in
this main action queue.

| Path | Current `script_line_count()` | Guard budget | Priority | Next split boundary | Current split status / deferral reason |
| --- | ---: | ---: | --- | --- | --- |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/ambient_cache.py` | 792 | 820 | P0 foreground-cache-risk | Split signal accumulator helpers or residue/dead-letter cache maintenance before adding another ambient lifecycle surface. | #821 added a hash-only topic signal accumulator to the existing thread-cache owner because it shares the same privacy/storage boundary. Do not add more foreground cache policy here without extracting a focused helper. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_decision.py` | 776 | 836 | P0 foreground-risk | Remaining staged foreground decision pipeline: semantic-gate invocation/skip diagnostics, final hook-result projection, and ambient/dream sidecar projection. | #500 froze golden foreground projection fixtures and moved source-evidence/final skip-scent-evidence projection into `prompt_recall_projection.py`; #602 moved hot-path route indexing/merge logic into `prompt_recall_hot_path.py`; #821 moved route-context preparation into `prompt_recall_route_context.py`; #938 moved fast/deep channel diagnostics into `prompt_recall_channels.py`; and #281 kept living-cue default-hook consumption in that hot-path owner while `assess_prompt` stayed at the 255-line orchestration guard. Next splits should target semantic-gate skip diagnostics or hook-result projection only with fixture coverage. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/semantic_recall_gate.py` | 968 | 1200 | P1 foreground-budget-risk | Separate prompt/catalog payload construction or foreground-budget arbitration from the semantic gate coordinator if either grows again. | #580 froze focused skip/scent/evidence fixtures and moved worker response parsing, unavailable classification, and public projection into `semantic_gate_response.py`; #820 adds prompt-term trigger suppression inside the existing foreground relevance coordinator. The next split should not re-inline provider diagnostics or source/evidence truth into the coordinator. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_cues.py` | 417 | 740 | P1 foreground-cue-risk | Future growth should split current-checkout, secret-surface, memory-boundary, or semantic-gate intent helpers only when one of those policy owners grows again. | #1145 split static cue term/pattern catalogs into `prompt_cue_catalog.py` while keeping legacy `prompt_cues` imports stable; `prompt_cues.py` now owns prompt intent, gating, and source-boundary helper behavior. |
| `skills/aippocampus/scripts/aippocampus_runtime/ops/spend_doctor.py` | 722 | 760 | P2 ops-observability-risk | Split route artifact scanners or the model telemetry normalizer before adding another model-backed lane, artifact family, or cost model. | #1207 keeps the first shared `model_telemetry` shape in the spend doctor because it owns cross-lane operator reporting. Do not add provider-specific pricing or another lane scanner here without extracting the telemetry normalization helper. |
| `skills/aippocampus/scripts/aippocampus_runtime/subconscious/scheduler.py` | 847 | 860 | P2 hook-scheduler-risk | Split agent-fallback enqueue wrapping or detached worker command assembly before adding another scheduler mode, worker lane, or lifecycle policy. | #1205 split due-project diagnostics into `scheduler_due_diagnostics.py`; the scheduler still owns hook-safe orchestration and public CLI result assembly. Do not add another no-due/freshness branch here without extracting a second helper. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/continuity_domain_producer.py` | 600 | 680 | P2 registry-producer-risk | Split producer-specific label-quality policy or registry/source scanning from candidate scoring before adding another language policy, signal source, or promotion heuristic. | #973 kept low-information label suppression inside the existing producer because it owns domain-promotion eligibility; do not keep piling linguistic deny/allow policy here if another issue extends it. |
| `skills/aippocampus/scripts/aippocampus_runtime/reflection/retrieval_lifecycle.py` | 640 | 700 | P2 reflection-entrypoint-risk | Keep lifecycle ingestion, adapters, and CLI thin; split future review-window, outcome-projection, or adapter-family growth into sibling reflection modules. | #1081 split retrieval reconsolidation review-window logic into `retrieval_reconsolidation.py`; the remaining lifecycle file is the append-only event/adapter entrypoint. Do not add more reconsolidation policy here. |
| `skills/aippocampus/scripts/aippocampus_runtime/journey/live.py` | 606 | 660 | P2 journey-replay-risk | Split public replay fixture catalog or report projection into a sibling helper before adding another Journey replay source family, live-host adapter, or foreground policy branch. | #310 keeps live-row conversion, foreground hint timing, and the small public replay cohort together because they share the same no-write / no-raw-source / navigation-only boundary. The next expansion should extract the public replay cohort catalog or report projection instead of raising this budget again. |
| `skills/aippocampus/scripts/aippocampus_runtime/dream/input_pack.py` | 815 | 840 | P2 dream-seed-owner-risk | Split seed adapters into a focused helper before adding another Dream seed family, public feedback source, or CLI projection. | #942 kept recall-miss feedback ingestion in the input-pack owner because it shares the same source-ref audit/readiness boundary. The next seed-family expansion should extract the adapter chain instead of raising this budget again. |
| `skills/aippocampus/scripts/aippocampus_runtime/warm_ambient/recall.py` | 1437 | 1438 | P2 background-runtime-risk | Split batch/quorum bookkeeping or job/cache summary projection before adding more warm runtime orchestration. | Recent helper splits moved config, scout attribution, privacy action result policy, and topic-epoch write policy out; another extraction would be speculative unless the next warm-runtime growth touches batch/quorum bookkeeping or job/cache summary projection. Split one of those before any further budget raise. |
| `skills/aippocampus/scripts/aippocampus_runtime/dream/live_shadow_ab.py` | 1252 | 1340 | P3 opt-in-eval-risk | Split replay adapters, semantic relevance gating, delivery policy, or model-route binding before adding richer live outcome analysis. | It is below budget and opt-in/evaluation-facing. #605 added shared route-contract consumption but did not change the next split boundary. Split when a live-shadow feature touches one of those boundaries. |

## Test, Benchmark, And Tool Debt Budgets

Last counted: 2026-06-11.
Counting method: `script_line_count()` from
`tests/aippocampus/test_architecture_boundaries.py`: nonblank lines excluding
lines whose first non-space character is `#`.

Thresholds:

- test modules: 1500
- benchmark runners: 1200
- repo tools and smokes: 1100

This is not a scorecard. A large test can be the right shape when it owns one
coherent behavior surface, but it must say what should split next so review
pressure does not become invisible.

At least one real boundary split has landed for this register: the shared
AST/import graph helpers from `tests/aippocampus/test_import_coupling.py` now
live in `tests/aippocampus/import_coupling_helpers.py`. Keep future
`test_import_coupling.py` work focused on compatibility/public-entrypoint
contract assertions rather than rebuilding generic import-analysis helpers
inside the assertion file.

Current non-runtime action rows:

| Path | Current `script_line_count()` | Guard budget | Owner issue | Next split boundary |
| --- | ---: | ---: | --- | --- |
| `tests/aippocampus/test_subconscious_jobs.py` | 2655 | 2700 | #153 / #248 | Split deterministic question-tracking fixtures or shared model-route/job-output assertions before adding more job families; keep runner semantics visible. |
| `benchmarks/aippocampus/benchmark_memory_decision_gate.py` | 2216 | 2250 | #378 / #996 | Split scenario catalog or report projection from runner orchestration before adding another decision family or residual taxonomy. |
| `tests/aippocampus/test_continuity_domains.py` | 1607 | 1750 | #973 / #926 | Split continuity-domain producer fixtures or route-projection assertions before adding another domain family, source-opening surface, or MCP handle contract. |
| `tests/aippocampus/test_import_coupling.py` | 107 | 2500 | #658 / #659 | Continue moving reusable analysis helpers into `import_coupling_helpers.py`; invert remaining shim-preservation assertions toward explicit public allowlists. |
| `benchmarks/aippocampus/benchmark_amemgym_official.py` | 1570 | 1650 | #742 / #1052 / #1229 | #1052 split public execution-state, checkpoint, runner-plan, and protocol projection into `amemgym_official_public_state.py`; #1229 kept shared provider-budget preflight and timeout handling inside the official-bridge owner because it guards the same `openrouter --run` execution surface. Split score-output discovery, provider-budget/openrouter surface orchestration, or provider-specific usage parsing before adding more AMemGym arms, raw cost/latency extraction, or provider metadata extraction. |
| `benchmarks/aippocampus/benchmark_locomo_qa.py` | 1310 | 1400 | #1158 / #1229 | Keep the fixed-reader text-QA adapter, provider-budget preflight, static dry-run path, citation scoring, and sanitized report projection together while this remains one opt-in LoCoMo answer harness. Split provider/report projection helpers or LoCoMo answer-scoring taxonomy before adding more reader arms, multimodal LoCoMo behavior, or raw provider usage extraction. |
| `benchmarks/aippocampus/benchmark_longmemeval_answer.py` | 1272 | 1400 | #1157 / #1229 | Keep the fixed-reader answer/latency adapter, provider-budget preflight, static dry-run path, source-evidence input projection, and sanitized report projection together while this remains one LongMemEval-S answer harness. Split provider/report projection helpers or reader-metric taxonomy before adding more reader arms, official-judge integration, V2 execution, or raw provider usage extraction. |
| `benchmarks/aippocampus/benchmark_continuous_memory_arms.py` | 1751 | 1800 | #378 | Preregistered repeat readout and registration projection live in `continuous_memory_preregistered_slices.py`; split arm fixture catalog or cost/harm scoring before adding more arms or private-history adapters. |
| `tools/aippocampus/docs/check_docs_health.py` | 1372 | 1400 | #672 | Product profile guards now live in `tools/aippocampus/docs/product_profile_guard.py`; split another focused check group or shared markdown/path scanner before adding more public-readiness domains; keep single CLI output stable. |

The complete test / benchmark / tool inventory is in the evidence snapshot and
the deterministic report output.

## Claim-Boundary Duplication Pressure

This queue tracks runner and smoke files that define local `cannot_claim` or
`claim_boundary` helpers. These helpers are often legitimate active-run
boundaries, but they are also the easiest place for caveat lists to multiply
without improving source-backed behavior.

Do not add new runner-local caveat catalogs by default. Keep active run-level
or track-local `cannot_claim` entries only where a reader could over-read that
specific output; for inherited or inactive caveats, prefer `claim_boundary_ref`
or the parent evidence owner instead of mirroring full lists. The canonical rule
remains [`schema-field-profiles.md#cannot-claim`](./schema-field-profiles.md#cannot-claim).
Runner and smoke pressure files should consume
`benchmarks/aippocampus/claim_boundary_refs.py` unless they are the current
aggregation owner (`benchmark_suite.py`) or a documented successor. That keeps
the canonical pointer movable without turning domain-specific runner caveats
into a new global claim schema.

Current local helper pressure points:

| Path | Local helper(s) | Next pressure boundary |
| --- | --- | --- |
| `benchmarks/aippocampus/benchmark_amemgym.py` | `claim_boundary` | Keep AMemGym protocol/output caveats owned by the AMemGym evidence doc; do not spread official-score caveats into generic benchmark helpers. |
| `benchmarks/aippocampus/benchmark_locomo_qa.py` | `cannot_claim` | Keep LoCoMo fixed-reader text-QA caveats local to the opt-in harness; do not promote answer-run boundaries into same-conversation retrieval-only metrics or generic external-benchmark policy. |
| `benchmarks/aippocampus/benchmark_longmemeval.py` | `cannot_claim` | Keep V1 retrieval-only caveats local unless a shared external-benchmark policy emerges from multiple real adapters. |
| `benchmarks/aippocampus/benchmark_longmemeval_answer.py` | `cannot_claim` | Keep fixed-reader answer/latency caveats local to the opt-in harness; do not promote answer-run boundaries into retrieval-only or generic external-benchmark policy. |
| `benchmarks/aippocampus/benchmark_longmemeval_v2_context.py` | `cannot_claim` | Keep V2 context-mapping pilot caveats local and diagnostic; do not promote pilot status into suite-level quality claims. |
| `benchmarks/aippocampus/benchmark_memoryagentbench.py` | `stage3_claim_boundary` | Keep Stage 3 dry-run boundaries inside MemoryAgentBench until official scoring inputs are wired. |
| `benchmarks/aippocampus/memory_pain_companions.py` | `companion_cannot_claim` | Keep memory-pain companion caveats tied to the memory-pain fixture report; do not turn this helper into a second suite-level claim-boundary layer. |
| `benchmarks/aippocampus/benchmark_segmented_merge_policy.py` | `cannot_claim` | Keep segmented-merge caveats owned by the merge-policy fixture report; split only if another segment runner reuses the same policy. |
| `benchmarks/aippocampus/benchmark_source_evidence_retrieval.py` | `cannot_claim` | Prefer source-evidence track ownership and `cannot_claim_by_track`; avoid copying Track B caveats into unrelated runners. |
| `benchmarks/aippocampus/benchmark_suite.py` | `collect_cannot_claim`, `collect_cannot_claim_by_track`, `suite_level_cannot_claims`, `profile_cannot_claims`, `claim_boundary_policy` | This is the current aggregation owner. Extend this policy before adding a second suite-level caveat layer. |
| `benchmarks/aippocampus/source_evidence/reporting.py` | `claim_boundary` | Keep source-evidence reporting helpers focused on query-origin and track-local summaries. |
| `tools/aippocampus/smoke/simulate_multilingual_prompt_hook.py` | `claim_boundary` | Keep prompt-hook smoke caveats narrow; broad multilingual quality belongs in benchmark/readiness evidence, not this simulator. |
| `tools/aippocampus/smoke/smoke_life_wide_registry.py` | `cannot_claim_for_stage2` | Keep Stage 2 aggregate caveats tied to readiness evidence; avoid adding per-label caveat catalogs here. |
| `tools/aippocampus/smoke/smoke_semantic_scope_real_history.py` | `semantic_cannot_claim` | Split public projection from live-provider orchestration before adding more semantic-readiness caveats. |
| `tools/aippocampus/smoke/smoke_semantic_scope_source_review.py` | `cannot_claim` | Keep source-review caveats local to selected review status; do not turn them into global semantic correctness policy. |
| `tools/aippocampus/smoke/smoke_source_evidence_recall_eval.py` | `cannot_claim` | Keep selected-source eval caveats local and point fallback warnings back to the owner report instead of repeating inherited lists. |

## Guard Budget Change Policy

Raise a guard budget only when the added code is still inside the same owner
boundary, the split candidate would be artificial or duplicate an existing
helper, and the PR records the reason here or in the evidence snapshot with a
follow-up owner if pressure is still rising.

Do not raise budgets as a routine way to make tests pass; budget changes need a
real owner-boundary reason.

Split before raising when a module is at or over budget and the change adds a
new stage, IO surface, CLI projection, provider/host concern, retry policy, or
foreground user-visible behavior that can be extracted behind existing tests.

For #502 specifically, the safe action was debt-governance only: current counts,
priority order, next split boundaries, and extraction deferral were recorded.
The first executable extraction is #500 for `prompt_recall_decision.py`; that
issue froze golden foreground recall-decision fixtures before moving
source-evidence/final projection policy.

## Update Rule

1. Run `python tools\aippocampus\docs\debt_report.py --json`.
2. If a file is missing, add it to the evidence snapshot with a guard budget and
   owner-boundary note, or split a real responsibility out.
3. If a file is over budget, split first unless the owner boundary is still
   coherent and the budget raise reason is recorded.
4. Keep this main document as a short action queue. Move resolved or stable
   inventory rows to the evidence snapshot.
