# Architecture Debt Register

Role: implementation map.

This is the lightweight action board for oversized runtime scripts and
repo-owned test / benchmark / tool harnesses. It is not a scorecard and it does
not replace source-backed design decisions.

Full budget metadata lives in
[`docs/evidence/reports/architecture-debt-snapshot-2026-06-04.md`](../evidence/reports/architecture-debt-snapshot-2026-06-04.md).
Generate the current count/status report with:

```powershell
python tools\aippocampus\docs\debt_report.py --json
```

For contributor onboarding, dependency flow, maintenance/core-recall separation,
and recall test visibility, use
[`runtime-script-map.md`](./runtime-script-map.md). This register only answers
"which large files need attention next?"

## System-Weight Plan

`debt_report.py --json` now includes a `system_weight` block that groups the
tracked surface into runtime, tests, benchmarks, docs, and tools. Treat that as
fresh-agent load guidance, not as a new scorecard: runtime is product pressure,
tests and benchmarks are proof pressure, docs are architecture/research context,
and tools are operator audit or maintenance pressure. The detailed owner row
below remains the authority for a file-specific split decision.

Use `archive_or_split_targets` from the report when pruning stale support
material or deciding the next focused helper extraction. Do not mirror this
section into benchmark reports; link back here.

The enforcing tests are:

- `tests/aippocampus/test_architecture_boundaries.py::ArchitectureBoundaryTests.test_large_runtime_scripts_have_debt_register_budgets`
- `tests/aippocampus/test_architecture_boundaries.py::ArchitectureBoundaryTests.test_large_tests_benchmarks_and_tools_have_debt_register_budgets`

If a file grows past its budget, either split a real responsibility out or raise
the budget with a concrete owner-boundary reason. Do not raise budgets as a
routine way to make tests pass.

## Near-Budget Split Priority Queue

Last counted: 2026-06-17.
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
| `skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_decision.py` | 819 | 836 | P0 foreground-risk | Remaining staged foreground decision pipeline: semantic-gate invocation/skip diagnostics, final hook-result projection, and ambient/dream sidecar projection. | #500 froze golden foreground projection fixtures and moved source-evidence/final skip-scent-evidence projection into `prompt_recall_projection.py`; #602 moved hot-path route indexing/merge logic into `prompt_recall_hot_path.py`; #821 moved route-context preparation into `prompt_recall_route_context.py`; #938 moved fast/deep channel diagnostics into `prompt_recall_channels.py`; #1456 moved semantic route-agreement/source-reopen promotion into `prompt_recall_semantic_routes.py`; and #281 kept living-cue default-hook consumption in that hot-path owner while `assess_prompt` stayed inside the 255-line orchestration guard. #1468/#1469 moved explicit agent-surface intent and cheap casual-skip helpers into sibling modules; remaining pressure should still split semantic-gate skip diagnostics or hook-result projection only with fixture coverage. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_hot_path.py` | 666 | 720 | P0 foreground-hot-path-risk | Split source-factual-alias artifact loading/matching or bounded FTS fallback before adding another hot-path candidate stage. | #1424-#1426 added local source-side factual alias consumption here because it shares the existing no-provider, navigation-only candidate funnel. Do not add another artifact family or ranking surface to this facade without extracting a focused stage helper first. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/semantic_recall_gate.py` | 978 | 1200 | P1 foreground-budget-risk | Separate prompt/catalog payload construction or foreground-budget arbitration from the semantic gate coordinator if either grows again. | #580 froze focused skip/scent/evidence fixtures and moved worker response parsing, unavailable classification, and public projection into `semantic_gate_response.py`; #820 adds prompt-term trigger suppression inside the existing foreground relevance coordinator. The next split should not re-inline provider diagnostics or source/evidence truth into the coordinator. |
| `skills/aippocampus/scripts/aippocampus_runtime/learning_loop/core.py` | 1065 | 1080 | P1 learning-loop-spine-risk | Split dogfood fixture/report projection or one detector family before adding live hook writes, model-backed review, or another action-time surface. | #1593-#1602 introduced the first source-backed learning-loop spine in one no-write owner so adapter, activation, deterministic detectors, workflow packaging, semantic hypotheses, lesson handoff, and Active Path Packet projection share one privacy/source-boundary contract. #1790/#1799 kept effectiveness-ledger loading and source-backed learning report projection here because they shape the same no-write learning-loop spine. Do not add persistence, live host hooks, or another workflow family here without extracting a focused helper first. |
| `skills/aippocampus/scripts/aippocampus_runtime/learning_loop/semantic_learning.py` | 748 | 780 | P1 semantic-outcome-risk | Split outcome-row fixture catalog or private-replay projection helpers before adding another semantic-failure family or live hook outcome reader. | #1978 intentionally keeps surfaced-guidance, observed outcome, dogfood fixture, and private-replay aggregate projection together so unobserved guidance cannot be misread as prevented repeats. Do not add live telemetry ingestion or another result taxonomy here without extracting the fixture/outcome catalog. |
| `skills/aippocampus/scripts/aippocampus_runtime/hooks/action_hint_cache.py` | 623 | 660 | P1 action-hint-setup-risk | Split semantic-guidance fixture summarization or cache-record projection before adding another learning-source family, provider ledger, or recovery-card branch. | #1995/#2062 kept empty-cache recovery, semantic guidance review, and prepared-cache materialization in one action-time hint cache owner because they form one trusted Codex setup path. Do not add another attribution or scoring layer here; extract the semantic guidance bridge first. |
| `skills/aippocampus/scripts/aippocampus_runtime/hooks/action_hint_replay.py` | 363 | 420 | P1 pretool-replay-risk | Split replay fixture catalog from report projection before adding dogfood/live telemetry ingestion. | #1610 added the first public-safe with/without-hint replay telemetry for #435. It is intentionally fixture-bound and keeps usefulness, cost, and red lines separate. Do not turn this into live telemetry ingestion or promotion policy without extracting a separate outcome reader. |
| `skills/aippocampus/scripts/aippocampus_runtime/hooks/claude_code.py` | 785 | 840 | P1 claude-hook-host-risk | Split settings mutation helpers, event-status projection, or handler-command resolution before adding another Claude Code event family or host-version lane. | #2010 keeps status, dry-run, explicit install/uninstall, synthetic smoke, and fail-open scoped handlers together because they guard the same Claude settings contract. PostToolUse/PostCompact support or real-host firing evidence should extract a focused owner instead of growing this file. |
| `skills/aippocampus/scripts/aippocampus_runtime/mcp/recall_navigation.py` | 994 | 1040 | P1 agent-recall-risk | Split topic-label selection, source-window projection, or malformed-handle diagnostics before adding another route family, handle family, or freshness policy. | #1278 and #1188 deliberately kept display-vs-callable deepen diagnostics and fixed-vocabulary route-topic labels in the progressive MCP recall owner because they directly shape the same `recall_context -> recall_deepen` packet contract. #2026 kept latest-reply reopen in this owner because it is another handle-resolution branch, not a new recall surface. Do not add more route-label or freshness heuristics here without extracting a focused helper. |
| `skills/aippocampus/scripts/aippocampus_runtime/mcp/memory_health_recovery.py` | 336 | 380 | P1 memory-health-foreground-risk | Split recall-capability probing from public recovery-card projection before adding another health, maintenance, or host-readiness branch. | #2129 keeps exception recovery and compact health-card recall-first overlay together because both prevent MCP `memory_health` from hiding a source-backed `agent_recall -> agent_deepen` path. Do not add maintenance planning, indexing policy, or host install status here; keep those in their existing owners and only project the foreground split state. |
| `skills/aippocampus/scripts/aippocampus_runtime/mcp/server.py` | 1137 | 1150 | P1 agent-host-risk | Split tool-family handlers before adding another diagnostic surface, host-specific MCP projection, or write-like setup lane. | #1656-#1676 kept compact `agent_recall`/`recall_context`, request-index `agent_deepen` follow-through, and explicit `register_thread` write consent in the MCP facade because they close one existing foreground contract. #2081 kept compact health exposure here because it is the existing `memory_health` tool family. The 2026-06-18 foreground sweep kept list/readiness action wiring here because it belongs to existing MCP tool dispatch; the next MCP expansion should extract handler families. |
| `skills/aippocampus/scripts/aippocampus_runtime/vault/dashboard.py` | 627 | 660 | P1 dashboard-foreground-risk | Split foreground health-card projection or generated body-node parsing before adding another dashboard pane, card family, or mobile shell behavior. | #2169/#2170 kept mobile reachability, structured generated body nodes, and the first-viewport health action card in the dashboard renderer because they shape one human-visible continuity cockpit. The next dashboard feature should extract the foreground card projection or body-node allowlist/parser instead of growing this renderer. |
| `skills/aippocampus/scripts/aippocampus_runtime/update/cli.py` | 1744 | 1760 | P1 host-readiness-risk | Split another host/plugin readiness lane before adding more package, plugin-cache, foreground-tool status behavior, rollback, or dirty-sync recovery. | #2183 kept rollback JSON, atomic output recovery, and cache-refresh routing in this facade because they share one local update transaction boundary. The next host surface should extract another readiness lane before extending this facade. |
| `skills/aippocampus/scripts/aippocampus_runtime/update/plugin_installer.py` | 943 | 960 | P1 host-install-risk | Split the Codex app-server JSON client, recoverable replacement helper, or host-probe wording helper before adding another host manager, marketplace backend, or install target. | The 2026-06-18 sweep kept atomic owner/marketplace manifest writes and interrupted-install recovery in this installer because it owns local plugin-file mutation. The next expansion should extract the recoverable replacement helper or host-probe client rather than extending the installer. |
| `skills/aippocampus/scripts/aippocampus_runtime/ops/cognitive_observatory.py` | 895 | 920 | P1 observatory-readout-risk | Split static HTML rendering or Campus usefulness panel projection before adding topology, Telepathy, Dream, or ranking/cost drilldowns. | #576 keeps read-only route readiness, activation authority, query-pattern, cognitive-load, sleep-cycle, and Campus usefulness summaries in one no-write observatory report. #1885 kept default no-input explanation and safe panel previews here because they are foreground readout projection over the same diagnostic payload, not a control plane. The next expansion should extract one renderer/projection helper. |
| `skills/aippocampus/scripts/aippocampus_runtime/ops/successor_evidence.py` | 1861 | 1880 | P0 successor-closeout-risk | Split issue manifest data, track-specific metric adapters, or GitHub native-parent loading before adding another successor wave or closeout policy. | The 2026-06-18 issue sweep kept new closeout evidence checks here because issue closure is evidence-bound instead of range-bound. The next successor wave should extract manifest/metric adapters first. |
| `skills/aippocampus/scripts/aippocampus_runtime/ops/provider_doctor.py` | 656 | 700 | P2 provider-onboarding-risk | Split compact card projection or credential-source discovery adapters before adding another provider family, operator mode, or validation lane. | #2172 kept the compact default card beside existing provider doctor detection so first-run users get one safe next action without exposing credential inventory. Full operator JSON still owns discovery/validation. Extract `provider_doctor_card.py` or credential-source adapters before adding another provider/operator branch. |
| `skills/aippocampus/scripts/aippocampus_runtime/macro/loadbearing_fixture.py` | 628 | 660 | P1 macro-topology-replay-risk | Split macro replay fixtures from topology foreground replay fixtures before adding another Macro or packet-topology evidence family. | #1965/#1966 keep Macro and topology load-bearing replay together only because they share the same public-safe fixture, no-authority-upgrade, and no-private-leak boundary. Do not add live hexagram inference, default routing policy, or another replay surface here without extracting separate fixture catalogs. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_cues.py` | 417 | 740 | P1 foreground-cue-risk | Future growth should split current-checkout, secret-surface, memory-boundary, or semantic-gate intent helpers only when one of those policy owners grows again. | #1145 split static cue term/pattern catalogs into `prompt_cue_catalog.py` while keeping legacy `prompt_cues` imports stable; `prompt_cues.py` now owns prompt intent, gating, and source-boundary helper behavior. |
| `skills/aippocampus/scripts/aippocampus_runtime/ops/spend_doctor.py` | 868 | 900 | P2 ops-observability-risk | Split route artifact scanners, warm-queue health projection, or the model telemetry normalizer before adding another model-backed lane, artifact family, queue family, or cost model. | #1207 keeps the first shared `model_telemetry` shape in the spend doctor because it owns cross-lane operator reporting. The 2026-06-16 issue sweep kept value-rate normalization and public usage summaries here because they are the same operator spend report, not a new pricing surface. #2086/#2024 kept blocked warm-queue diagnostics in this report so spend and ambient queue health produce one foreground decision card; the compact card renderer moved to `ops/spend_doctor_card.py`. Do not add provider-specific pricing, another lane scanner, or another queue signal here without extracting the telemetry or warm-queue projection helper. |
| `skills/aippocampus/scripts/aippocampus_runtime/subconscious/scheduler.py` | 847 | 860 | P2 hook-scheduler-risk | Split agent-fallback enqueue wrapping or detached worker command assembly before adding another scheduler mode, worker lane, or lifecycle policy. | #1205 split due-project diagnostics into `scheduler_due_diagnostics.py`; the scheduler still owns hook-safe orchestration and public CLI result assembly. Do not add another no-due/freshness branch here without extracting a second helper. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/continuity_domain_producer.py` | 785 | 820 | P2 registry-producer-risk | Split producer-specific label-quality policy or registry/source scanning from candidate scoring before adding another language policy, signal source, or promotion heuristic. | #973 kept low-information label suppression inside the existing producer because it owns domain-promotion eligibility. #1727/#1728 added foreground-bounded preview metrics and stricter low-information suppression here because both decide whether a domain candidate should exist at all. The next language policy, signal source, or preview scan expansion should extract label-quality policy or registry/source scanning before this owner grows again. |
| `skills/aippocampus/scripts/aippocampus_runtime/source_shape.py` | 625 | 720 | P2 source-shape-spine-risk | Split active-recall priority adaptation or explain/deepen projection before adding another producer family or foreground consumer. | #1417-#1428 introduced the shared source-shape descriptor, guard arbitration, temporal semantics, compact foreground projection, and active-recall priority adapter in one spine so producers share vocabulary and guard order. Do not add another scoring layer or producer-specific policy here. |
| `skills/aippocampus/scripts/aippocampus_runtime/navigation/local_global_compatibility.py` | 539 | 680 | P2 diagnostic-surface-risk | Split report/CLI projection before adding another packet family, overlap basis, or foreground consumer. | #1394-#1406 split typed Section/restriction helpers and public fixtures into sibling modules while keeping the V0 explain/deepen/Campus report owner here. Do not turn it into a router, truth layer, or default foreground drawer. |
| `skills/aippocampus/scripts/aippocampus_runtime/reflection/retrieval_lifecycle.py` | 640 | 700 | P2 reflection-entrypoint-risk | Keep lifecycle ingestion, adapters, and CLI thin; split future review-window, outcome-projection, or adapter-family growth into sibling reflection modules. | #1081 split retrieval reconsolidation review-window logic into `retrieval_reconsolidation.py`; the remaining lifecycle file is the append-only event/adapter entrypoint. Do not add more reconsolidation policy here. |
| `skills/aippocampus/scripts/aippocampus_runtime/journey/live.py` | 606 | 660 | P2 journey-replay-risk | Split public replay fixture catalog or report projection into a sibling helper before adding another Journey replay source family, live-host adapter, or foreground policy branch. | #310 keeps live-row conversion, foreground hint timing, and the small public replay cohort together because they share the same no-write / no-raw-source / navigation-only boundary. The next expansion should extract the public replay cohort catalog or report projection instead of raising this budget again. |
| `skills/aippocampus/scripts/aippocampus_runtime/dream/input_pack.py` | 856 | 860 | P2 dream-seed-owner-risk | Split seed adapters into a focused helper before adding another Dream seed family, public feedback source, or CLI projection. | #942 kept recall-miss feedback ingestion in the input-pack owner because it shares the same source-ref audit/readiness boundary. #1421/#1434 kept runtime-recheck seed consumption inside the same input-pack readiness boundary. #1415 put line-topology seed interpretation in `dream/macro_guidance.py`; the input-pack owner only adapts the sanitized payload into the shared readiness boundary. |
| `skills/aippocampus/scripts/aippocampus_runtime/warm_ambient/recall.py` | 1438 | 1438 | P2 background-runtime-risk | Split batch/quorum bookkeeping or job/cache summary projection before adding more warm runtime orchestration. | Recent helper splits moved config, scout attribution, privacy action result policy, and topic-epoch write policy out; another extraction would be speculative unless the next warm-runtime growth touches batch/quorum bookkeeping or job/cache summary projection. Split one of those before any further budget raise. |
| `skills/aippocampus/scripts/aippocampus_runtime/dream/live_shadow_ab.py` | 1257 | 1340 | P3 opt-in-eval-risk | Split replay adapters, semantic relevance gating, delivery policy, or model-route binding before adding richer live outcome analysis. | It is below budget and opt-in/evaluation-facing. #605 added shared route-contract consumption but did not change the next split boundary. Split when a live-shadow feature touches one of those boundaries. |

## Test, Benchmark, And Tool Debt Budgets

Last counted: 2026-06-17.
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
| `benchmarks/aippocampus/benchmark_compaction_continuity.py` | 1695 | 1800 | #1351 | Split Track D scenario catalog or sequence-diagnostic fixtures before adding another hook/state/status family; keep runner scoring and public report projection together until the #1351 coverage closeout is stable. |
| `benchmarks/aippocampus/benchmark_memoryagentbench.py` | 1351 | 1360 | #608 / #614 / #995 / #1644 / #2190 | Split Stage 3 runtime-arm projection or dataset/parquet observation helpers before adding another MemoryAgentBench competency arm; provider artifact receipts stay hashes/counts-only until official runner compatibility exists. |
| `tests/aippocampus/test_continuity_domains.py` | 1607 | 1750 | #973 / #926 | Split continuity-domain producer fixtures or route-projection assertions before adding another domain family, source-opening surface, or MCP handle contract. |
| `tests/aippocampus/test_aippocampus_mcp_server.py` | 2307 | 2320 | #1450 / #1451 / #1656-#1676 / #1813 / #1817 / #1712 / #1889 / #1890 / #1982 / #2066-#2089 / #2013 / #2173 / #2174 / #2181 / #2203-#2226 / #2228-#2252 | Split JSON-RPC request builders, source-window privacy fixtures, tool-catalog assertion helpers, or readiness-repair payload fixtures before adding another tool family; keep host-facing compact/full/error contracts visible together while the MCP surface stabilizes. The 2026-06-18 foreground sweep kept list/readiness/template-action checks here because they guard the same compact/default MCP contract. `latest_reply` MCP closeout semantics now live in `tests/aippocampus/test_mcp_latest_reply.py`. |
| `tests/aippocampus/test_update_sync.py` | 2273 | 2290 | #1307 / #1335 / #1431 / #1563 / #1748 / #1755 / #1810 / #1982 / #2078 / #2183 / #2203-#2226 | Split Codex config/cache fixture builders, plugin apply/status assertion helpers, rollback fixtures, or dirty-worktree fixture setup before adding another host install/sync lane; keep one local-update contract suite until marketplace/cache/rollback/no-write status behavior stabilizes. |
| `tests/aippocampus/test_agent_opt_in_continuity.py` | 2278 | 2300 | #1507 / #1620 / #1808 / #1814 / #2069 / #2013 / #2021 / #2184 | Split shared CLI/MCP fixture builders, last-recall cache fixtures, or returned-packet shape assertion helpers before adding another foreground recall surface; keep opt-in recall, AIppo, macro, compact/full recall boundary, last-recall privacy, and action-card JSON contracts visible together while the agent-facing packet shape is stabilizing. |
| `tests/aippocampus/test_aippocampus_cli.py` | 2259 | 2280 | #1756 / #1843 / #1838 / #1845 / #1774-#1823 / #2066-#2078 / #1986-#1996 / #2014-#2015 / #2173 / #2183 / #2203-#2226 | Split subprocess runner helpers or command-family smoke tests into focused modules before adding more top-level facade, personal-control, learning, package-facade, or MCP command discovery cases; keep the first-five-minutes path visible in one smoke owner. Command-family recovery/help contracts live in `tests/aippocampus/test_cli_recovery_cards.py`; only facade-owned first-use smoke should stay here. The foreground-continuity sweep kept parent-command and CLI JSON recovery smoke here because the public facade owns those entrypoints. |
| `tests/aippocampus/test_aippocampus_health.py` | 1925 | 1960 | #248 / #1809 / #1782 / #1890 / #2081 / #2178 | Split storage-pressure fixture builders, host-state fixture builders, exit-code policy fixtures, or compact/full projection assertion helpers before adding another health lane; keep generated-cache pressure advisory, host-state confound separation, compact agent cards, first-recall-blocked exit semantics, and live-delta readiness together until that contract stabilizes. |
| `tests/aippocampus/test_docs_health.py` | 1632 | 1680 | #672 / #1837 / #1845 / #1846 / #1887 / #2079 / #2087 | Split public-doc command lint, executable memory-card examples, evidence-ledger guards, diagnostic-prerequisite guards, or product-profile guards into focused helpers before adding another docs-health domain; keep one repository health smoke owner for cross-doc drift. #2079/#2087 kept visible-env-key onboarding and SKILL bootstrap posture guards here because both catch public first-use documentation drift. |
| `tests/aippocampus/test_benchmark_longmemeval.py` | 1578 | 1650 | #1323 / #1424 / #1426 | Split source-index fixture builders or factual-alias hot-path assertions before adding another source-window, alias, or LongMemEval rerank family. |
| `tests/aippocampus/test_import_coupling.py` | 107 | 2500 | #658 / #659 | Continue moving reusable analysis helpers into `import_coupling_helpers.py`; invert remaining shim-preservation assertions toward explicit public allowlists. |
| `benchmarks/aippocampus/benchmark_amemgym_official.py` | 1672 | 1700 | #742 / #1052 / #1229 / #2190 | #2190 kept public-safe provider artifact receipts here because they describe AMemGym execution evidence without raw provider payloads. Split score-output discovery, provider-budget/openrouter surface orchestration, or provider-specific usage parsing before adding more AMemGym arms, raw cost/latency extraction, or provider metadata extraction. |
| `benchmarks/aippocampus/benchmark_locomo_qa.py` | 1310 | 1400 | #1158 / #1229 | Keep the fixed-reader text-QA adapter, provider-budget preflight, static dry-run path, citation scoring, and sanitized report projection together while this remains one opt-in LoCoMo answer harness. Split provider/report projection helpers or LoCoMo answer-scoring taxonomy before adding more reader arms, multimodal LoCoMo behavior, or raw provider usage extraction. |
| `benchmarks/aippocampus/benchmark_longmemeval_answer.py` | 1358 | 1400 | #1157 / #1229 / #1282 | Keep the fixed-reader answer/latency adapter, provider-budget preflight, static dry-run path, source-evidence input projection, and sanitized report projection together while this remains one LongMemEval-S answer harness. #1282 moved privacy-safe failure review and expansion gating into `longmemeval_answer_review.py`; split provider/report projection helpers before adding more reader arms, official-judge integration, V2 execution, or raw provider usage extraction. |
| `benchmarks/aippocampus/benchmark_longmemeval_rerank_analysis.py` | 1476 | 1480 | #1092 / #1327 / #1437 / #2230 | Keep semantic-rerank budget projection, source-cache replay analysis, and the #1437 post-factual-alias closeout together while they explain the same LongMemEval exact-line rerank boundary. #2230 kept closed-owner/no-open-followup classification here because this runner owns the #1437 closeout report shape. Split post-factual-alias closeout projection or source-window coverage diagnostics before adding another reranker family, provider protocol, or candidate-builder decision lane. |
| `benchmarks/aippocampus/benchmark_continuous_memory_arms.py` | 1954 | 2000 | #378 / #1968 | Preregistered repeat readout and registration projection live in `continuous_memory_preregistered_slices.py`; #1968 added the public context-loss cohort in the same comparative-arm runner so no extra scoring layer was introduced. Split arm fixture catalog, context-loss cohort construction, or cost/harm scoring before adding more arms or private-history adapters. |
| `benchmarks/aippocampus/benchmark_hippocampal_hard_negatives.py` | 1364 | 1400 | #517 / #1972 | Split currentness/supersession fixture catalog or source-open scoring projection before adding another hard-negative family, LoCoMo adapter, or answer-time currentness claim. |
| `tests/aippocampus/test_warm_ambient_recall.py` | 2273 | 2300 | #657 / #1281 / #2009 | Keep warm ambient hook, registry reconciliation, cache, scout, detached-job, and optional queue-status tests together while stale queue recovery stays part of the scheduler contract. Split hook-seen ledger fixtures, queue-status fixtures, or scout-card assertion helpers before adding another scheduler/lifecycle lane. |
| `tools/aippocampus/docs/check_docs_health.py` | 1454 | 1460 | #672 / #1887 / #2203-#2226 | Product profile guards now live in `tools/aippocampus/docs/product_profile_guard.py`; foreground continuity/report-router/currentness guards now live in `tools/aippocampus/docs/foreground_continuity_guard.py`; evidence-ledger payload line checks and diagnostic-prerequisite wording guards stayed here because they are repository docs-health invariants. Split another focused check group or shared markdown/path scanner before adding more public-readiness domains; keep single CLI output stable. |

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
remains [`schema-field-profiles.md#cannot-claim`](runtime/schema-field-profiles.md#cannot-claim).
Runner and smoke pressure files should consume
`benchmarks/aippocampus/shared/claim_boundary_refs.py` unless they are the current
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
| `benchmarks/aippocampus/shared/benchmark_report_contract.py` | `_cannot_claim_count` | Keep report-contract lint counting tied to canonical `claim_boundary_ref`; do not turn high-signal follow-up detection into a second caveat catalog. |
| `benchmarks/aippocampus/shared/memory_pain_companions.py` | `companion_cannot_claim` | Keep memory-pain companion caveats tied to the memory-pain fixture report; do not turn this helper into a second suite-level claim-boundary layer. |
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
