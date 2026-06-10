# Benchmark Priority And Run-Profile Map

This registry answers the operational question that the broader evidence map
does not try to answer: which benchmark or smoke surface should a future agent
prioritize, run, trust, or treat as diagnostic only?

It is not a leaderboard, a numeric claim table, or another runner index. Keep
current metric values, confirmed scope boundaries, remediation issues, and
supersession rules in [`../../current-claims.md`](../../current-claims.md),
dated command evidence in
[`../../readiness/public-readiness-verification.md`](../../readiness/public-readiness-verification.md),
and the full runner/smoke directory in
[`../../benchmark-evidence-map.md`](../../benchmark-evidence-map.md).

## What To Run When

Use the highest-priority surface that matches the question you are trying to
answer. Do not average unrelated layers into one score: gate decisions,
source-evidence retrieval, payload fidelity, compaction continuity, answer
generation, private-history lift, and live host behavior are separate proof
surfaces.

| Need | Start with | Escalate only when |
| --- | --- | --- |
| Ordinary PR confidence after benchmark-adjacent changes | `python tools/aippocampus/run_tests.py --tier benchmark-smoke --benchmark-suite-profile public-fast` | You changed benchmark runner code, reports, profiles, or claim-boundary helpers. |
| Full deterministic benchmark mirror | `python tools/aippocampus/run_tests.py --tier benchmark` | You need broad runner parity before a release/public-readiness claim. |
| Public evidence update | The owning dated report plus `release-evidence` or the owning runner command | The result changes what `current-claims.md` or stage readiness can honestly say. |
| Live/provider calibration | The track-owned optional command | A local deterministic surface already isolates the risk, and provider setup/privacy boundaries are documented. |
| Private real-history or life-wide evidence | The owning private/sanitized protocol | The public fixture cannot answer the question, and the output remains aggregate/hash-only. |

## Classification Keys

Priority:

- `P0`: keep readable and green by default; regression here confuses nearly all
  benchmark work.
- `P1`: high proof value after P0 is clean; usually the next useful public or
  source-backed evidence slice.
- `P2`: important diagnostic or future-proofing surface, but not first-order
  proof for current public claims.
- `P3`: candidate, optional, expensive, blocked, or comparison-oriented; keep
  visible without making it headline work.

Status:

- `implemented`: executable runner/helper exists.
- `dated_evidence`: a report or current-claims row exists; rerun only if the
  owning question changes.
- `contract_smoke`: fixture/report contract exists but cannot support broad
  quality claims.
- `diagnostic_only`: useful for calibration or root-cause work, not a gate.
- `scaffold`: shape exists; representative data or scoring is incomplete.
- `planned_or_blocked`: source map exists but implementation or fair scoring is
  intentionally deferred.

Claim level:

- `public_safe_claim`: public-safe fixture or dated evidence can support the
  narrow claim named by its owner.
- `contract_smoke`: verifies report/scorer semantics only.
- `diagnostic_proxy`: helps calibrate or compare but is not product-quality
  evidence.
- `selected_private_diagnostic`: sanitized aggregate private-history result.
- `cannot_claim`: no score or quality claim should be made from this surface.

## Runner Registry

Every repository-level benchmark runner currently listed in
[`../../benchmark-evidence-map.md`](../../benchmark-evidence-map.md#benchmark-runners)
is assigned below. Builders and shared helpers are included because they change
what future agents can safely generate or compare.

| Family | Surface / runner | Measures | Status | Priority | Default run profile | Claim level | Main risk caught | Not for | Related issues |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Core regression | `benchmark_suite.py` | Track A/C/D profile ladder, thresholds, cannot-claim metadata | implemented | P0 | `benchmark-smoke` with `public-fast`; `benchmark` for full mirror | public_safe_claim for profile/report semantics | Mixed profile comparisons and hidden claim-surface drift | Track B, private-history, or live quality under `public-fast` | #171 |
| Core regression | `benchmark_memory_decision_gate.py` | skip/scent/evidence routing choices | implemented | P0 | benchmark-smoke / full benchmark | contract_smoke | Overactive memory, missed source-evidence escalation | Broad real-history gate quality | #27 |
| Core regression | `benchmark_payload_fidelity.py` | final payload source fidelity, privacy and parked-memory protection | implemented | P0 | benchmark-smoke / full benchmark | contract_smoke | Source-free payloads and private/parked payload leakage | Retrieval quality or answer quality | #27 |
| Core regression | `benchmark_compaction_continuity.py` | correction and rejected-route continuity across simulated compaction states | implemented | P0 | benchmark-smoke / full benchmark | contract_smoke | Lost adopted corrections or resurfaced refuted anchors | Live hook capture or private-history continuity | #65, #378 |
| Core regression | `benchmark_run_history_diff.py` | comparable benchmark report diffing | implemented | P0 | full benchmark or release evidence review | diagnostic_proxy | Treating incomparable profiles as metric regressions | Product quality proof | none |
| Core regression | `benchmark_statistics.py` | Wilson interval reporting helper | implemented | P0 | helper via owning runners | diagnostic_proxy | Over-reading tiny samples without uncertainty | Representative sampling proof | none |
| Source-evidence retrieval | `benchmark_source_evidence_retrieval.py` | Track B source/session/source-line retrieval and public adapters | implemented | P0/P1 | full benchmark; deterministic Track B profiles | public_safe_claim for bounded retrieval slices | Stale index, wrong source, source-label confusion | Answer generation or natural user-query quality | #309, #963 |
| Semantic robustness diagnostics | `benchmark_semantic_robustness.py` | Track S no-live-judge S1-S3 diagnostics over gate perturbation, retrieval invariance, and hard-negative suppression | implemented | P1/P2 | full benchmark / direct runner | diagnostic_proxy | Semantic paraphrase drift, negative-constraint failures, and equivalent-query retrieval brittleness | Human-level semantic understanding or Track A/B replacement | #747 |
| Public reliability | `benchmark_public_reliability_gauntlet.py` | Public aggregate gate over runtime stability, mis-recall quality, and pollution hygiene | dated_evidence | P1 | benchmark-smoke / direct runner; optional `--segment-soak` | public_safe_claim for gate coverage and boundary separation | Over-reading partial runtime, retrieval, or pollution slices as a broad reliability proof | Single aggregate score, LongMemEval QA, real GB/TB runtime, private-history quality, exact-line solved, or live hook-write quality | #1102 |
| Attention router | `benchmark_attention_navigation_quality.py` | selected attention-router navigation and red-line fixtures across route, mask, stale/currentness, conflict, action-time, anti-nag, and evidence-packaging families | implemented | P1 | benchmark-smoke / direct runner | contract_smoke; `quality_gate_ok=false` until public/external cohort, floor, uncertainty, holdout, and no-tuning-leak promotion pass | Navigation red-line drift and average-rate overclaim | Representative public route quality, answer generation, private-history quality, live host lift, or default foreground adoption | #1111, #1165 |
| Agent continuity loop | `benchmark_agent_continuity_loop.py` | Integrated public-safe route loop across semantic warming, hot router, facade packets, AIppo, source-reopen budget, foreground budget, deepen/explain, blocked/stale/conflict, and anti-nag cases | implemented | P1 | benchmark-smoke / full benchmark | contract_smoke; `quality_gate_ok=false` until public/external cohort, floor, uncertainty, holdout, and no-tuning-leak promotion pass | Integration drift where individually green contracts compose into overclaim, provenance leak, stale-as-current, or forgotten deepen | Live host behavior lift, private-history quality, answer generation, default foreground adoption, or public benchmark quality lift | #1163, #1165 |
| Source-evidence retrieval | `benchmark_fts5_recall.py` | selected real-history FTS5 and production-hybrid recall | dated_evidence | P0 | optional local / readiness ledger | selected_private_diagnostic | Lexical/source-index regressions | Public benchmark score or private text disclosure | none |
| Benchmark infrastructure | `benchmark_maturity.py` | shared maturity/sample-size metadata helper for separating contract gates from public-quality gates | implemented | P1 | imported by runners / unit tests | policy_helper | Accidental promotion of small deterministic fixtures into quality claims | Benchmark score, evidence owner, or public-quality proof by itself | #1165 |
| Benchmark infrastructure | `sharegpt_sampling.py` | public-corpus seeded sampling | implemented | P2 | optional local when Track B public-corpus work changes | diagnostic_proxy | Biased or unreproducible public-corpus samples | Private-history quality | none |
| Hippocampal | `benchmark_hippocampal_hard_negatives.py` | H1/H2 near-neighbor, unsupported speech, superseded-currentness controls | implemented | P1 | benchmark-smoke / full benchmark | contract_smoke | Wrong-twin and stale/currentness false positives | Live recall quality or full P1 corpus | #244 |
| Hippocampal | `benchmark_hippocampal_recall.py` | recall-discrimination diagnostic seed and local-arm comparison | implemented | P1 | full benchmark; optional local comparison | diagnostic_proxy | Source-reopen failure, scent/fact layer collapse | External memory-system scores | #229, #230, #231, #238 |
| Hippocampal | `build_hippocampal_fixture.py` | public-safe H-series fixture construction | implemented | P1 | optional local when fixture schema changes | contract_smoke | Fixture drift before scoring | Quality score by itself | #229 |
| Field/demo continuity | `benchmark_field_continuity.py` | public-safe magic-moment scenario contracts plus bounded #281 fixture-quality proxy | implemented | P0/P1 | benchmark-smoke / full benchmark | contract_smoke | Demo overclaim, wrong-family route persistence | Live/private field quality proof, #281 live fresh-thread quality | #454, #281 |
| Host/ecosystem | `benchmark_provider_conformance.py` | provider/session, cross-provider route, MCP affordance, real normalizer, and failure-example contracts | implemented | P1 | benchmark-smoke / full benchmark | contract_smoke | Provider identity conflation, copied-summary evidence promotion, injected-content pollution, missing source refs, malformed-row drift, and MCP blob-only recall | Live multi-client quality, all-client drop-in support, AgentMemory behavior, or real cross-host continuity quality | #981, #988 |
| Fresh-thread recall | `benchmark_fresh_thread_recall_demo.py` | fresh-thread public-safe recall/demo flows | implemented | P1 | full benchmark; dated report owner | public_safe_claim for fixture flow | Source-reopen boundary regressions in demos | Default hook first-turn live lift | #490 |
| Prompt hook hot path | `benchmark_prompt_hot_path_funnel.py` | local hook route funnel, cue/cache fallback, latency counters | implemented | P1 | full benchmark or focused smoke | contract_smoke | Hot-path overwork, wrong scent, latency regression | Semantic paraphrase or live recall quality | #602 |
| Warm ambient | `benchmark_warm_ambient_recall.py` | warm ambient recall fixtures | implemented | P2 | full benchmark / optional local | diagnostic_proxy | Warm-scent routing regressions | Broad ambient quality | none |
| Warm ambient | `benchmark_warm_ambient_sweep.py` | parameter sweep for warm ambient tuning | implemented | P3 | optional local | diagnostic_proxy | Hidden threshold brittleness | Default PR gate or claim upgrade | none |
| Warm ambient | `build_warm_ambient_trace_cases.py` | warm ambient case-pack builder | implemented | P3 | optional local | contract_smoke | Case-pack generation drift | Quality evidence alone | none |
| Coding-agent continuity | `benchmark_coding_decision_shadow.py` | deterministic coding decision-shadow Tracks A-E | implemented | P1 | full benchmark / focused benchmark | contract_smoke | Repeating rejected routes, stale authority, visible-source nagging | Live host timing or private-history behavior lift | #164 |
| Continuous-agent continuity | `benchmark_continuous_memory_arms.py` | no-memory, host-native, sham, stale, oracle, true-memory arms, and preregistered slice readouts | implemented | P1 | full benchmark / optional local | diagnostic_proxy | Unfair fresh-context baselines, stale-memory harm, hidden cost, missing slice gates | Public superiority without repeated preregistered evidence | #378, #406, #407, #408, #409, #410, #960 |
| E2E50 | `benchmark_e2e50_silent_constraint.py` | silent-constraint scorer scaffold plus ordered sequence/load sidecar contract | scaffold | P0/P1 | benchmark-smoke support guard | contract_smoke | Scorer/report drift, order-insensitive route evidence, load overclaim before representative cases exist | Closing #279 quality, #663 Episode/Arc layer, #575 load-routing quality, or 20/50-case result | #279/#663/#575 |
| Knowledge/privacy | `benchmark_knowledge_pollution.py` | governed knowledge, source-reopen, privacy partition, capability-contract smoke | implemented | P1 | full benchmark / direct runner | contract_smoke | Source-looking fake authority, stale source, privacy bleed | Real legal/medical/contract quality | #517 |
| Cold navigation maps | `benchmark_map_rot_lifecycle_debt.py` | selected lifecycle-debt fixtures for stale, challenged, quarantined, superseded, missing-middle, deleted/no-recall, dead-lettered, repeated-wrong, and current route objects | implemented | P1 | benchmark-smoke / direct runner | contract_smoke; `quality_gate_ok=false` until public/external cohort, floor, uncertainty, holdout, and no-tuning-leak promotion pass | Stale/current leakage, masked resurrection, wrong-route revival, deletion/quarantine regressions | Representative map-rot distribution, automatic cleanup proof, private-history map-rot quality, or live current-route quality | #1126, #1165 |
| Multimodal | `benchmark_multimodal_corpus_retrieval.py` | public-safe corpus-style multimodal retrieval contract | implemented | P2 | full benchmark / direct runner | contract_smoke | Treating text hints as visual/source truth | ATM-Bench score or conversational upload recall | #531 |
| Multimodal | `benchmark_conversational_media_ingest_recall.py` | conversational media-ingest recall contract | implemented | P2 | full benchmark / direct runner | contract_smoke | Media anchors detached from user turns | Product media privacy or visual model quality | #532 |
| Multimodal | `benchmark_multimodal_niah_evidence_pool.py` | supplied-pool answer-synthesis contract | implemented | P2 | full benchmark / direct runner | contract_smoke | Confusing supplied-pool synthesis with retrieval | ATM-Bench retrieval score | #533, #964 |
| External memory benchmark | `benchmark_longmemeval.py` / `benchmark_longmemeval_rerank_analysis.py` | LongMemEval V1 retrieval-only source/session evidence plus optional line-reranker analysis | dated_evidence | P1 | optional local with dataset download; analysis over ignored generated report | public_safe_claim for bounded V1 retrieval and diagnostic_proxy for reranker analysis | External long-memory retrieval regressions, exact-line ranking gaps, and provider-assisted rerank budget drift | QA answer quality, V2 quality, SOTA, default semantic reranker adoption, or 500Q LLM reranker quality without an explicit full run | #259, #1092 |
| External memory benchmark | `benchmark_longmemeval_v2_context.py` | LongMemEval-V2 context-mapping pilot | diagnostic_only | P1 | optional local with dataset files | diagnostic_proxy | Claiming V2 score without evidence labels | R@K/MRR, LAFS, answer accuracy | #259 |
| External memory benchmark | `benchmark_amemgym.py` / `benchmark_amemgym_official.py` | AMemGym metadata, source-backed overlay smoke, official bridge, full `local-scripted` official-output protocol run, and dated live-provider blocker note | protocol_evidence_blocked_live | P1 | benchmark-smoke; optional public JSON download; optional local official bridge | diagnostic_proxy | Collapsing native accuracy, diagnosis, utilization, source fidelity, and protocol-only output values into one score | Live-model official AMemGym score or baseline parity until bounded live-provider execution and cost extraction exist | #733 / #742 |
| External memory benchmark | `benchmark_state_bench_agent_learning.py` | STATE-Bench Agent Learning feasibility, train-only learning extraction, read-only retrieval hook adapter, and no-score submission boundary | scaffold | P1 | benchmark-smoke missing-checkout guard; optional local upstream checkout | diagnostic_proxy | Test-oracle leakage, raw trajectory leakage, or claiming official lift before a matched task run exists | Official STATE-Bench score, Agent Learning Track lift, leaderboard readiness, held-out quality, or cost/UX improvement | #1043 |
| External memory benchmark | `benchmark_memoryagentbench.py` | MemoryAgentBench metadata, case-pack, Stage 3 dry-run, and local apply-instrumented write/update controls | scaffold | P1 | deterministic smoke; optional local dataset | diagnostic_proxy | Collapsing incremental memory into static retrieval | Official score or compatibility claim | #608, #614, #694, #995 |
| External memory benchmark | `benchmark_locomo_public_users.py` | LoCoMo same-conversation evidence retrieval control | implemented | P2 | optional local dataset | diagnostic_proxy | Same-conversation evidence-id scorer drift | Cross-thread/life-wide memory proof | none |
| External memory benchmark | `benchmark_locomo_answer_usefulness.py` | LoCoMo answer-usefulness prototype layers | scaffold | P2 | optional local with fixed answer model | diagnostic_proxy | Blending retrieval, generation, citation, and judge layers | SOTA or broad answer quality | #400 |
| Public longitudinal | `benchmark_public_longitudinal_users.py` | pseudo-user coding implicit-knowledge contract | implemented | P1 | full benchmark / optional predictions | contract_smoke | Unsupported drift and missing source-event attribution | Private continuity quality or single headline moat | #172 |
| Public longitudinal | `benchmark_vcs_future_event_recall.py` | VCS future-event recall, source disambiguation, and route-chain actionability | implemented | P1 | optional local / dated report owner | diagnostic_proxy | Future-event false negatives, closed-book contamination, source-vs-stale confusion, incomplete multi-source chains, and foreground route-drag from successful current events | Live model quality or wild VCS quality | #309, #378, #454, #961 |
| Public longitudinal | `build_vcs_future_event_fixture.py` | VCS/rollout fixture construction from curated links/events | implemented | P1 | optional local | contract_smoke | Soft-label or narrative-only fixture contamination | Scraping or inferring labels by itself | #378 |
| Dream/consolidation | `benchmark_cognitive_portrait.py` | compact source-backed cognitive portrait smoke | implemented | P2 | full benchmark / direct runner | contract_smoke | Over-personalized or source-loose portrait artifacts | Empirical portrait quality | #70 |
| Dream/consolidation | `benchmark_question_aware_real_history.py` | question/frontier/link structural private-history packs | diagnostic_only | P2 | private-only / sanitized reports | selected_private_diagnostic | Source-fidelity loss in question-aware packs | Answer-quality or token-saving claim | #248 |
| Dream/consolidation | `benchmark_question_tracking_calibration.py` | selected-fixture question tracking calibration | diagnostic_only | P2 | optional local | diagnostic_proxy | Question-axis drift | Broad question-tracking quality | #248 |
| Scale/storage | `benchmark_segmented_merge_policy.py` | segmented merge policy calibration | implemented | P2 | full benchmark / direct runner | contract_smoke | Cross-segment merge and stale/currentness policy drift | Real long-thread recall quality | #375 |
| Live/provider | `benchmark_live_semantic_gate.py` | optional live semantic-gate calibration | implemented | P3 | live/provider only | diagnostic_proxy | Provider/prompt availability or source-review drift | Deterministic CI gate or provider-independent quality | none |

## Smoke And Live Surface Registry

These surfaces are stronger or broader than unit tests. They are not all
benchmark runners, but they often become evidence owners or release gates. Run
them when their owner changed, when a release/public-readiness claim depends on
them, or when the registry above points to an unresolved live/private gap.

| Family | Surface / entrypoint | Status | Priority | Default run profile | Claim level | Main risk caught | Not for | Related issues |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Public readiness | `run_stage_0_5_smoke.py` | implemented | P0 | manual release smoke | public_safe_claim for readiness ledger scope | Broken end-to-end public-readiness path | Benchmark metric replacement | none |
| Prompt hook | `simulate_prompt_hook.py` | implemented | P0 | focused smoke | contract_smoke | Prompt-hook regression | Live recall quality | none |
| Prompt hook | `smoke_prompt_hook_latency.py` | implemented | P1 | focused smoke | diagnostic_proxy | Latency budget drift | Quality proof | none |
| Cognitive Observatory | `smoke_route_readiness_observatory.py` plus query-pattern route observability tests | implemented | P1 | focused smoke | contract_smoke | Route-readiness/prewarm/query-pattern diagnostics leaking into control or source-evidence territory, alias-source counts leaking alias text, or alias text appearing in public Observatory output | Complete observatory UI, live prewarm quality, or live query-pattern alias quality | #574, #576 |
| Prompt hook | `simulate_multilingual_prompt_hook.py` | implemented | P2 | focused smoke | contract_smoke | Multilingual hook regressions | Broad multilingual recall quality | none |
| Prompt hook | `smoke_semantic_paraphrase_reuse.py` | implemented | P2 | focused smoke | diagnostic_proxy | Semantic paraphrase reuse drift | Default quality gate | none |
| Warm ambient | `smoke_living_cue_cache.py` | implemented | P1 | focused smoke | contract_smoke | Learned cue/cache regression | Fresh-thread quality proof | #281 |
| Warm ambient | `aippocampus_runtime.warm_ambient.query_pattern_enrichment --fixture --json` plus query-pattern route/hot-path unit coverage | implemented | P1 | focused smoke | contract_smoke | Registry/import query-pattern planning, idempotency, invalidation, provider/privacy gate drift, sidecar write drift, alias-source diagnostics, or hot-path consumption drift | Live DeepSeek quality, scheduler adoption, or latency savings | #574 |
| Warm ambient | `smoke_worker_hook_handoff.py` | implemented | P1 | focused smoke | contract_smoke | Background/worker cache hits failing to become foreground routes, or stale/blocked worker artifacts becoming actionable | Live second-user helpfulness, background worker quality, or default prewarm ROI lift | #574, #909 |
| Host/ecosystem | `smoke_codex_long_session_continuity.py` | implemented | P1 | optional local host smoke | diagnostic_proxy | Long-session host continuity regression | Cross-host proof | none |
| Host/ecosystem | `smoke_provider_key_bridge_os_store.py` | implemented | P1 | optional local host smoke | diagnostic_proxy | OS credential-store adapter drift, cleanup failure, or public output leaking hook credential locators | Provider-key correctness, already-running hook visibility, or cross-host proof from one machine | #784 |
| E2E50 | `smoke_e2e50_seed_candidates.py` | implemented | P1 | benchmark-smoke support guard | diagnostic_proxy | Candidate-seed scanner drift | Representative E2E50 quality | #279 |
| Host/ecosystem | `smoke_claude_code_mcp_host.py` | implemented | P2 | optional local host smoke | diagnostic_proxy | MCP host integration drift | General MCP support proof | none |
| Host/ecosystem | `smoke_claude_code_history.py` | implemented | P2 | optional local host smoke | diagnostic_proxy | Local-history parser drift | Cross-agent quality | none |
| Host/ecosystem | `smoke_cross_agent_continuity.py` | implemented | P2 | optional local smoke | diagnostic_proxy | Synthetic cross-agent continuity regression | Real cross-agent product proof | none |
| Host/ecosystem | `smoke_generic_jsonl_integration.py` | implemented | P2 | optional local smoke | contract_smoke | Generic JSONL adapter drift | All ecosystem support | none |
| Host/ecosystem | `smoke_openai_agents_sdk_tool_contract.py` | implemented | P2 | optional local smoke | contract_smoke | Tool-contract compatibility drift | Official SDK endorsement | none |
| Life-wide registry | `smoke_life_wide_registry.py` | implemented | P1 | optional local smoke | selected_private_diagnostic | Life-wide aggregate/source-label drift | Private text disclosure or label correctness proof | none |
| Source-evidence retrieval | `smoke_memory_pain_prompt_hook.py` | implemented | P2 | focused smoke | diagnostic_proxy | Real-history memory-pain hook regression | Public quality claim | none |
| Fresh-thread recall | `smoke_fresh_thread_real_history.py` | implemented | P1 | private/sanitized smoke | selected_private_diagnostic | Ready-lock and source-reopen boundary drift | Recall-quality benchmark | #302, #490 |
| Recall navigation | `smoke_recall_navigation_comparison.py` | implemented | P1 | focused smoke | public_safe_claim for deterministic proxy | Manual-query invention, route-follow-through, source-ref rejoin, and sentinel wrong-route-drag regressions | Live #201 closure, #248 default prefilter safety, #309 vector/source-reranker quality, or #281 live fresh-thread quality | #201, #281, #309, #248, #465, #962 |
| Semantic source review | `smoke_semantic_scope_real_history.py` | implemented | P1 | private/sanitized smoke | selected_private_diagnostic | Real-history semantic sidecar drift | Public quality proof | none |
| Semantic source review | `smoke_semantic_scope_source_review.py` | implemented | P1 | private/sanitized, public shadow, or live provider smoke | selected_private_diagnostic | Source-review availability, failure-taxonomy drift, public-shadow regression, and label drift | Human-reviewed global semantic quality | #993 |
| Source-evidence retrieval | `smoke_source_evidence_recall_eval.py` | implemented | P1 | private/sanitized smoke | selected_private_diagnostic | Candidate-space and selected-source recall drift | Public benchmark score | #458 |
| Question tracking | `smoke_question_confirmation_live.py` | implemented | P3 | live/provider optional | diagnostic_proxy | Live confirmation path drift | Deterministic gate | #248 |
| Question tracking | `smoke_question_prefilter_parity.py` | implemented | P1 | focused smoke | contract_smoke | Prefilter/runtime mismatch | Answer quality | #248 |
| Agency/host timing | `smoke_agency_host_timing.py` | implemented | P1 | focused replay smoke | contract_smoke | Annoyance/duplicate-suppression policy drift on the Codex Desktop hidden-route surface | Live host timing lift or real annoyance calibration | #312, #763 |
| Dream/consolidation | `dream_real_history_eval.py` | dated_evidence | P2 | private-only / provider optional | selected_private_diagnostic | Dream structural lift/noise calibration drift | Causal user-visible lift | #163 |
| Scale/storage | `smoke_synthetic_scale_capacity.py` | implemented | P2 | optional local smoke | diagnostic_proxy | Synthetic capacity/regression drift | Real GB/TB readiness | none |
| Question tracking | `smoke_question_tracking_scale.py` | implemented | P2 | optional local smoke | diagnostic_proxy | Question-scale policy drift | Real-history quality | none |
| Repo familiarity | `smoke_repo_familiarity.py` | implemented | P2 | focused smoke | contract_smoke | Source-backed repo map adapter drift | Broad codebase intelligence | none |
| Repo familiarity | `smoke_repo_familiarity_foreground_experiment.py` | implemented | P3 | optional local experiment | diagnostic_proxy | Foreground experiment policy drift | Default product behavior | #250 |
| Sync/scale | `smoke_cross_device_sync.py` | implemented | P1 | optional local smoke | diagnostic_proxy | Single-machine cross-device sync drift | Real multi-device production sync | none |
| Sync/scale | `smoke_object_storage_sync.py` | implemented | P2 | optional local smoke | diagnostic_proxy | HTTP object-storage sync drift | Provider-grade sync proof | none |
| Sync/scale | `smoke_alternate_runtime_sync.py` | implemented | P2 | optional Docker/WSL smoke | diagnostic_proxy | Alternate runtime path drift | Universal platform support | none |
| Sync/scale | `smoke_real_provider_encrypted_sync.py` | implemented | P3 | real-provider optional | diagnostic_proxy | Provider encryption/sync path drift | Default PR gate or broad provider support | none |
| Distribution | `smoke_plugin_install.py` | implemented | P1 | manual release smoke | diagnostic_proxy | Plugin package install drift | Marketplace readiness by itself | none |
| Distribution | `smoke_real_codex_host.py` | implemented | P1 | manual release smoke | diagnostic_proxy | Real Codex app-server plugin drift | Cross-host support by itself | none |

## External Candidate Parking Lot

Keep these visible as candidates, not headline work, until their blockers are
resolved in the owning docs.

| Candidate | Current status | Priority | Boundary |
| --- | --- | --- | --- |
| PersonaMem / PersonaMem-v2 | staged_readiness_gate | P2 | Full benchmark run is deferred until AIppo/Ficus profile-readiness exists; use [`../personamem-readiness.md`](../personamem-readiness.md) for required profile, lifecycle, privacy, adaptation, and metric boundaries. |
| Mem0 | planned_or_blocked | P3 | Missing-config diagnostic slot only; no adapter parity or competitor superiority claim. |
| Zep / Graphiti | planned_or_blocked | P3 | Missing-config graph-memory comparison candidate; live adapters need install/license/fairness review. |
| Letta | planned_or_blocked | P3 | Missing-config compaction comparison candidate; static retrieval must not stand in for agent-memory behavior. |
| LangMem | planned_or_blocked | P3 | Candidate external memory stack only; no score or compatibility claim until source-evidence/fairness boundaries are documented. |

## Cannot-Claim Guardrails

- Do not call `public-fast` a full benchmark. It intentionally excludes Track
  B, live semantic calls, private text, and optional public-corpus adapters.
- Do not treat diagnostic/context-mapping pilots as quality scores.
- Do not merge external benchmark layers into one score. Dataset metadata,
  source retrieval, answer generation, update/write behavior, judge quality,
  and cost/latency must stay separate.
- Do not use private real-history or live/provider runs as public claims unless
  a sanitized aggregate owner updates `current-claims.md` or stage readiness.
- Do not run expensive live/provider or large-dataset sweeps just because a
  docs link exists. Run them when they answer a named claim-boundary question.
- Do not run PersonaMem as a low-signal retrieval benchmark before the
  AIppo/Ficus profile-readiness gate exists; source retrieval is not
  personalization quality.
