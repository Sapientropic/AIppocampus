# Recall Owner Map

Role: inventory.
Status: current architecture inventory.

Use this map before adding or moving files under
`skills/aippocampus/scripts/aippocampus_runtime/recall/`. The goal is
navigability: a new agent should know which owner family a file belongs to
before editing it. Source truth, privacy, and foreground output contracts still
live in their existing owner docs; this file only maps the runtime terrain.

Docs health treats the flat module inventory below as a sealed legacy
classification, not a permission slip for more flat files. New recall runtime
files must use an owner subpackage by default. A new flat `recall/*.py` file is
accepted only when it is a true entrypoint or temporary compatibility wrapper
listed in `Flat File Exceptions` with owner, removal condition, and default
import guidance.

Legacy flat inventory seal:

- sealed_count: 150
- sealed_sha256: b498a407a7a73a0a77226ce2fc93743cbb7436b0684aefaabbe3fa959114eacc

Do not update this seal to admit a normal new module; move the file under the
owning package instead.

## Flat File Exceptions

No new flat exceptions are currently allowed.

| File | Kind | Owner | Removal condition | Default import guidance |
| --- | --- | --- | --- | --- |

## Owner Families

### Prompt Recall

Owner boundary: prompt interpretation, recall-channel selection, prompt budget,
and prompt-side route projection. Do not change
`prompt_recall_decision.py` without the prompt recall owner.

Current flat files:

- `prompt_concept_graph_bridge.py`
- `prompt_context_diagnostics.py`
- `prompt_context_dream.py`
- `prompt_context_render.py`
- `prompt_cue_catalog.py`
- `prompt_cues.py`
- `prompt_foreground_budget.py`
- `prompt_recall_ambient.py`
- `prompt_recall_ambiguity.py`
- `prompt_recall_budget.py`
- `prompt_recall_channels.py`
- `prompt_recall_context.py`
- `prompt_recall_core.py`
- `prompt_recall_decision.py`
- `prompt_recall_evidence.py`
- `prompt_recall_feedback_filter.py`
- `prompt_recall_hot_path.py`
- `prompt_recall_hot_path_debug.py`
- `prompt_recall_policy.py`
- `prompt_recall_projection.py`
- `prompt_recall_result_tiers.py`
- `prompt_recall_route_context.py`
- `prompt_recall_semantic.py`
- `prompt_recall_semantic_routes.py`
- `prompt_recall_threshold.py`
- `prompt_route_blocks.py`

### Ambient

Owner boundary: ambient cards, cache hygiene, signal accumulation, prompt-hook
affordance, and low-friction fresh-thread nudges.

Current owner package:

- `ambient/__init__.py`
- `ambient/card_ranking.py`
- `ambient/ref_counts.py`

Current flat files:

- `ambient_cache.py`
- `ambient_cache_compaction.py`
- `ambient_card_hygiene.py`
- `ambient_cards.py`
- `ambient_policy.py`
- `ambient_signal_accumulator.py`
- `ambient_source_reopen.py`
- `fresh_thread_action.py`
- `fresh_thread_activation.py`
- `fresh_thread_demo.py`
- `fresh_thread_demo_fixtures.py`
- `fresh_thread_scent.py`
- `hook_agent_affordance.py`
- `living_cue_cache.py`

### Active Recall And Locks

Owner boundary: active recall CLI/runtime, lock lifecycle, public lock shape,
authority conflicts, and cross-agent isolation.

Current flat files:

- `active_recall.py`
- `active_recall_lock.py`
- `active_recall_lock_compaction.py`
- `active_recall_lock_lifecycle.py`
- `active_recall_lock_public.py`
- `active_recall_public.py`
- `authority.py`
- `cross_agent_isolation.py`

### APW And Route Walking

Owner boundary: Active Path Packets, APW route identity, fallback/walker inputs,
source-shaped APW candidates, and pathlet routing. Feedback events for this
family now live under the feedback owner package.

Current flat files:

- `active_path_packet.py`
- `apw_anchor_coverage.py`
- `apw_route_identity.py`
- `associative_path_fallback.py`
- `associative_path_fallback_policy.py`
- `associative_path_foreground_gate.py`
- `associative_path_inputs.py`
- `associative_path_source_shape.py`
- `associative_path_walker.py`
- `clean_source_apw_candidates.py`
- `continuity_pathlets.py`
- `registry_source_apw_candidates.py`
- `route_notes.py`

### Semantic

Owner boundary: semantic trigger/gate/cache behavior, semantic bridge maps,
candidate effectiveness, and semantic diagnostics. Semantic findings remain
navigation until source is reopened.

Current owner package:

- `semantic/__init__.py`
- `semantic/confidence_policy.py`
- `semantic/cue_learning.py`

Current flat files:

- `agent_semantic_diagnostics.py`
- `semantic_bridge_map.py`
- `semantic_cue_cache.py`
- `semantic_effectiveness.py`
- `semantic_gate_response.py`
- `semantic_recall_gate.py`
- `semantic_result_cache.py`
- `semantic_trigger_compaction.py`
- `semantic_trigger_router.py`

### Source Open And Deepen

Owner boundary: deepen requests, last-recall cache handles, source-anchor gate,
source-gate context, source reopen budgets, and exact source-search support.

Current owner package:

- `source_open/__init__.py`
- `source_open/cue_learning.py`

Current flat files:

- `agent_deepen_requests.py`
- `agent_recall_cache.py`
- `evidence_drawer.py`
- `local_reopen_token.py`
- `rollout_search.py`
- `segment_deep_recall.py`
- `source_anchor_gate.py`
- `source_gate_context.py`
- `source_reopen_budget.py`

### Foreground Projection

Owner boundary: agent facade/continuity output, CLI dispatch/support, compact
foreground action cards, macro foreground surfaces, and user-facing confidence
translation. Keep proof/debug fields out of compact foreground output.

Current owner package:

- `foreground/__init__.py`
- `foreground/route_quality.py`

Current flat files:

- `agent_continuity.py`
- `agent_continuity_cli.py`
- `agent_continuity_cli_dispatch.py`
- `agent_continuity_cli_support.py`
- `agent_facade_contract.py`
- `agent_packet_compaction.py`
- `agent_pull_gesture.py`
- `agent_recall_pipeline.py`
- `agent_recall_primitives.py`
- `agent_surface_intent.py`
- `continuity_route_projection.py`
- `foreground_action_card.py`
- `foreground_armor.py`
- `foreground_confidence.py`
- `human_actions.py`
- `macro_field_live.py`
- `macro_foreground.py`
- `macro_live_recall.py`

### Scoring And Retrieval

Owner boundary: retrieval/search indexes, query policy, score fusion,
segment-search shape, candidate survival/planning, result diversity, and cache
read diagnostics. Scoring is route ordering, not source truth.

Current flat files:

- `cache_read_diagnostics.py`
- `candidate_planning.py`
- `candidate_survival.py`
- `index_builder.py`
- `lane_cache_verifier.py`
- `query_expansion.py`
- `query_policy.py`
- `query_profile.py`
- `result_diversity.py`
- `retrieval.py`
- `score_fusion.py`
- `score_fusion_calibration.py`
- `scoring_policy.py`
- `search_decision_adapter.py`
- `segment_builder.py`
- `segment_merge.py`
- `segment_metadata.py`
- `segment_search.py`
- `segment_search_extras.py`

### Feedback

Owner boundary: low-authority route/outcome feedback, APW follow-through
feedback, calibration reports, and capture receipts. Feedback rows can guide
future navigation but cannot mutate source truth or create source-open claims.

Current owner package:

- `feedback/__init__.py`
- `feedback/associative_path.py`
- `feedback/capture.py`
- `feedback/events.py`
- `feedback/outcome.py`

No flat compatibility wrappers belong here. Production callers, tests, and docs
must import `aippocampus_runtime.recall.feedback.*` directly so feedback remains
owned by one package instead of drifting back into parallel flat modules.

### Continuity And Life Cues

Owner boundary: continuity-domain production, life cues, narrative packets,
orientation sidecars, cognitive-load sidecars, source-backed lessons, and
time/understanding state used as recall context.

Current flat files:

- `cognitive_load_private_calibration.py`
- `cognitive_load_sidecar.py`
- `continuity_domain_cli.py`
- `continuity_domain_cue_quality.py`
- `continuity_domain_producer.py`
- `continuity_domain_salience_adapter.py`
- `continuity_domain_scan.py`
- `continuity_domains.py`
- `continuity_situation_glyphs.py`
- `continuity_usefulness.py`
- `life_cues.py`
- `narrative_packet.py`
- `orientation_sidecars.py`
- `source_backed_lessons.py`
- `structure_time.py`
- `understanding_state.py`

### Background Findings

Owner boundary: background finding payloads, recovery, and foreground-safe
projection of reviewed background material.

Current flat files:

- `background_finding_actions.py`
- `background_finding_projection.py`
- `background_findings.py`
- `background_recovery.py`

### Diagnostics And Recovery

Owner boundary: why/explain surfaces, recovery policy/layers, strategy planning,
nudges, attention-router policy, task orientation, and architecture navigation.

Current flat files:

- `architecture_navigation_affordance.py`
- `attention_router_policy.py`
- `before_commitment.py`
- `nudge_policy.py`
- `recall_recovery_layers.py`
- `recall_recovery_policy.py`
- `repo_familiarity_fallback.py`
- `strategy_planner.py`
- `task_orientation.py`
- `task_orientation_fixtures.py`
- `why_cli.py`
- `why_diagnostics.py`
- `why_reason_codes.py`
- `why_surfaces.py`
