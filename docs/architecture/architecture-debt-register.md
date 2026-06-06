# Architecture Debt Register

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

Last counted: 2026-06-06.
Counting method: `script_line_count()` from
`tests/aippocampus/test_architecture_boundaries.py`: nonblank lines excluding
lines whose first non-space character is `#`.

This queue is intentionally small. It ranks modules that are at or near their
guard budgets by product/runtime risk and next owner boundary, not by LOC alone.
Closed or fully stable inventory rows belong in the evidence snapshot, not in
this main action queue.

| Path | Current `script_line_count()` | Guard budget | Priority | Next split boundary | Current split status / deferral reason |
| --- | ---: | ---: | --- | --- | --- |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/ambient_cache.py` | 791 | 820 | P0 foreground-cache-risk | Split signal accumulator helpers or residue/dead-letter cache maintenance before adding another ambient lifecycle surface. | #821 added a hash-only topic signal accumulator to the existing thread-cache owner because it shares the same privacy/storage boundary. Do not add more foreground cache policy here without extracting a focused helper. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_decision.py` | 751 | 836 | P0 foreground-risk | Remaining staged foreground decision pipeline: semantic-gate invocation/skip diagnostics, final hook-result projection, and ambient/dream sidecar projection. | #500 froze golden foreground projection fixtures and moved source-evidence/final skip-scent-evidence projection into `prompt_recall_projection.py`; #602 moved hot-path route indexing/merge logic into `prompt_recall_hot_path.py`, #821 moved route-context preparation into `prompt_recall_route_context.py`, and #281 kept living-cue default-hook consumption in that hot-path owner while `assess_prompt` stayed at the 255-line orchestration guard. Next splits should target semantic-gate skip diagnostics or hook-result projection only with fixture coverage. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/semantic_recall_gate.py` | 961 | 1200 | P1 foreground-budget-risk | Separate prompt/catalog payload construction or foreground-budget arbitration from the semantic gate coordinator if either grows again. | #580 froze focused skip/scent/evidence fixtures and moved worker response parsing, unavailable classification, and public projection into `semantic_gate_response.py`; #820 adds prompt-term trigger suppression inside the existing foreground relevance coordinator. The next split should not re-inline provider diagnostics or source/evidence truth into the coordinator. |
| `skills/aippocampus/scripts/aippocampus_runtime/warm_ambient/recall.py` | 1437 | 1438 | P2 background-runtime-risk | Split batch/quorum bookkeeping or job/cache summary projection before adding more warm runtime orchestration. | Recent helper splits moved config, scout attribution, privacy action result policy, and topic-epoch write policy out; another extraction would be speculative unless the next warm-runtime growth touches batch/quorum bookkeeping or job/cache summary projection. Split one of those before any further budget raise. |
| `skills/aippocampus/scripts/aippocampus_runtime/dream/live_shadow_ab.py` | 1260 | 1340 | P3 opt-in-eval-risk | Split replay adapters, semantic relevance gating, delivery policy, or model-route binding before adding richer live outcome analysis. | It is below budget and opt-in/evaluation-facing. #605 added shared route-contract consumption but did not change the next split boundary. Split when a live-shadow feature touches one of those boundaries. |

## Test, Benchmark, And Tool Debt Budgets

Last counted: 2026-06-05.
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
| `tests/aippocampus/test_import_coupling.py` | 107 | 2500 | #658 / #659 | Continue moving reusable analysis helpers into `import_coupling_helpers.py`; invert remaining shim-preservation assertions toward explicit public allowlists. |
| `benchmarks/aippocampus/benchmark_amemgym_official.py` | 1234 | 1400 | #742 | Split official adapter overlay/protocol generation or score-output discovery into a sibling helper before adding more AMemGym arms, provider metadata extraction, or cost/latency parsing. |
| `tools/aippocampus/docs/check_docs_health.py` | 1372 | 1400 | #672 | Product profile guards now live in `tools/aippocampus/docs/product_profile_guard.py`; split another focused check group or shared markdown/path scanner before adding more public-readiness domains; keep single CLI output stable. |

The complete test / benchmark / tool inventory is in the evidence snapshot and
the deterministic report output.

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
