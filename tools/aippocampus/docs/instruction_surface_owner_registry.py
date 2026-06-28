"""Central owner classifications for instruction-surface scans."""

from __future__ import annotations

INSTRUCTION_SURFACE_CLASSIFIED_FILES = {
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py": {
        "classification": "compact_projection_owner",
        "owner": "#2636/#2651",
        "why": (
            "owns the compact recall card translation boundary; proof remains in "
            "detail/operator/tests, not default MCP payload expansion"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_apw_meta_echo.py": {
        "classification": "apw_meta_echo_compact_action_owner",
        "owner": "#2775/#2651",
        "why": (
            "owns compact recall action selection when APW finds a memory-product "
            "quote echo; proof stays in recall/search/open follow-through and tests"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_result_assembly.py": {
        "classification": "compact_projection_result_owner",
        "owner": "#2679/#2636/#2651",
        "why": (
            "owns final compact recall payload assembly and debug-field stripping; "
            "route proof remains in deepen/open follow-through and detail output"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_action_menu.py": {
        "classification": "agent_recall_foreground_action_menu_owner",
        "owner": "#2880/#2876/#2651",
        "why": (
            "owns the full/detail foreground-compatible action menu; compact may "
            "signal operator details exist, but proof and gates stay in "
            "deepen/open follow-through, tests, or detail output"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_recovery_projection.py": {
        "classification": "agent_recall_recovery_projection_owner",
        "owner": "#2877/#2876/#2651",
        "why": (
            "owns APW and recovery-action projection gating; source_anchor_gate "
            "fields are used to prevent bad foreground actions, not to expand "
            "default compact proof"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_route_projection.py": {
        "classification": "compact_route_receipt_owner",
        "owner": "#2679/#2636/#2651",
        "why": (
            "owns compact route receipt labels and low-confidence navigation; "
            "source proof and ranking diagnostics stay out of default MCP output"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_deepen_projection.py": {
        "classification": "mcp_deepen_projection_owner",
        "owner": "#2679/#2686/#2651",
        "why": (
            "owns MCP agent_deepen compact-vs-detail source-open and recovery "
            "cards; operator/source diagnostics remain in detail/full output"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_explain_projection.py": {
        "classification": "mcp_explain_projection_owner",
        "owner": "#2679/#2686/#2651",
        "why": (
            "owns MCP and CLI agent_explain compact-vs-detail recovery cards; "
            "policy/operator diagnostics remain behind detail/full output"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_compact_choices.py": {
        "classification": "compact_route_choice_owner",
        "owner": "#2663/#2651",
        "why": (
            "owns compact recall route-choice and source-search affordance wording; "
            "route proof remains in deepen/open follow-through and tests"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/compact_profile.py": {
        "classification": "mcp_compact_profile_owner",
        "owner": "#2679/#2685/#2686/#2651",
        "why": (
            "owns MCP structuredContent/text compact filtering; debug and proof "
            "fields stay behind detail/operator profiles"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/contracts.py": {
        "classification": "mcp_compact_contract_boundary_owner",
        "owner": "#2788/#2795/#2651",
        "why": (
            "owns typed MCP compact-card boundary checks; foreground action proof "
            "must stay in deepen/open follow-through, conformance smoke, or detail"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/protocol.py": {
        "classification": "mcp_protocol_conformance_owner",
        "owner": "#2795/#2788/#2651",
        "why": (
            "owns deterministic MCP stdio protocol/version policy while SDK "
            "migration remains parked behind parity checks"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/foreground_recovery.py": {
        "classification": "mcp_foreground_recovery_owner",
        "owner": "#2685/#2651",
        "why": (
            "owns missing-input recovery card wording and safe next actions for "
            "MCP tools; detailed source/operator payload stays in full profile"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/memory_health_recovery.py": {
        "classification": "mcp_memory_health_recovery_owner",
        "owner": "#2629/#2651",
        "why": (
            "owns memory_health recovery-card split state; compact may choose "
            "recall vs setup actions, while probe evidence stays in full/detail "
            "and compact filtering"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/public_projection.py": {
        "classification": "mcp_public_projection_owner",
        "owner": "#2666/#2651",
        "why": (
            "owns MCP default-vs-full public projection and redaction text; raw "
            "diagnostics stay in full/detail surfaces"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/runtime_provenance.py": {
        "classification": "mcp_runtime_provenance_detail_owner",
        "owner": "#2629/#2651",
        "why": (
            "owns sanitized MCP runtime provenance for full/detail profiles; "
            "compact projection must keep this diagnostic family stripped"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/runtime_recovery.py": {
        "classification": "mcp_runtime_recovery_card_owner",
        "owner": "#2765/#2651",
        "why": (
            "owns stale foreground-MCP runtime recovery cards; compact output may "
            "name reload/CLI fallback actions, but source proof and runtime "
            "diagnostics must stay in follow-through or detail surfaces"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/server.py": {
        "classification": "mcp_server_dispatch_boundary_owner",
        "owner": "#2765/#2651",
        "why": (
            "owns MCP request dispatch and error-boundary routing; user-facing "
            "tool failures must delegate compact/detail shaping to focused "
            "projection or recovery helpers"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/continuity_routes.py": {
        "classification": "mcp_continuity_route_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns MCP continuity-domain route handles and route-count diagnostics; "
            "compact proof must stay in follow-through, not foreground field dumps"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/relationship_origin_routes.py": {
        "classification": "relationship_origin_route_owner",
        "owner": "#2635/#2651",
        "why": (
            "owns the canonical relationship-origin route labels and handoff "
            "wording; routes remain navigation until deepen/source-open follow-through"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/recall_navigation.py": {
        "classification": "mcp_recall_navigation_owner",
        "owner": "#2628/#2636/#2651",
        "why": (
            "owns MCP progressive recall handles and blocked-source messages; "
            "handles guide deepen/open but must not become remembered facts"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/tool_handlers.py": {
        "classification": "mcp_tool_handler_owner",
        "owner": "#2666/#2651",
        "why": (
            "owns MCP handler tool-error and renderer-routing text; handlers must "
            "delegate compact/detail cleanup to the shared profile layer"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/tool_catalog.py": {
        "classification": "mcp_tool_catalog_schema_owner",
        "owner": "#2716/#2651",
        "why": (
            "owns MCP tool descriptions and schemas; any source-open parameter "
            "claim must be backed by handler tests and compact/detail projection"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/tool_readiness.py": {
        "classification": "mcp_tool_readiness_projection_owner",
        "owner": "#2685/#2686/#2651",
        "why": (
            "owns MCP tool-readiness compact actions and CLI fallbacks; tool visibility "
            "is not source evidence and compact output must stay action-sized"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/thread_list_projection.py": {
        "classification": "mcp_thread_list_foreground_action_owner",
        "owner": "#2814/#2651",
        "why": (
            "owns list_threads compact foreground actions and registry-detail "
            "diagnostic affordances; ordinary routing must prefer agent_recall "
            "while legacy recall stays compat/detail-only"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity.py": {
        "classification": "runtime_prompt_and_route_owner",
        "owner": "#2636/#2651",
        "why": (
            "owns recall route/action selection text that later projections render"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_recall_primitives.py": {
        "classification": "recall_route_primitive_owner",
        "owner": "#2631/#2651",
        "why": (
            "owns shared route-to-packet boundary wording and local invariant "
            "comments for the thin facade and staged recall pipeline; source "
            "proof still belongs in deepen/open or detail/operator surfaces"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity_cli.py": {
        "classification": "recall_cli_dispatch_owner",
        "owner": "#2676/#2530/#2651",
        "why": (
            "owns agent recall CLI parser/help and compact-vs-full output dispatch; "
            "error recovery must delegate projection to focused helpers"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity_cli_dispatch.py": {
        "classification": "recall_cli_execution_owner",
        "owner": "#2631/#2676/#2651",
        "why": (
            "owns parsed agent CLI command execution branches split out of the "
            "parser; foreground text must remain compact and source-boundary aware"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/foreground_action_card.py": {
        "classification": "recall_foreground_action_card_owner",
        "owner": "#2716/#2651",
        "why": (
            "owns compact recall next-action wording; route proof must stay in "
            "search/open follow-through rather than foreground diagnostics"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/active_path_packet.py": {
        "classification": "active_path_packet_owner",
        "owner": "#2628/#2636/#2651",
        "why": (
            "owns Active Path Packet foreground route hints; packet text is "
            "navigation guidance and source reopening remains the truth boundary"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity_cli_support.py": {
        "classification": "recall_cli_render_boundary_owner",
        "owner": "#2636/#2651",
        "why": (
            "owns agent recall/deepen compact-vs-detail CLI rendering; source proof "
            "and diagnostics must stay in detail/operator surfaces"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_recall_cache.py": {
        "classification": "last_recall_cache_navigation_owner",
        "owner": "#2676/#2629/#2651",
        "why": (
            "owns same-machine last-recall selector/cache navigation text and "
            "typed cache-read recovery; local handles stay private and source "
            "claims require deepen/open follow-through"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_fallback.py": {
        "classification": "apw_fallback_projection_owner",
        "owner": "#2678/#2651",
        "why": (
            "owns APW fallback cards and deepen-request projection; policy gating "
            "lives in the focused sibling helper after the #2678 split"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_fallback_policy.py": {
        "classification": "apw_fallback_policy_owner",
        "owner": "#2678/#2651",
        "why": (
            "owns APW fallback promotion and candidate-input gating; source-open "
            "proof remains in fallback/deepen follow-through, not policy text"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_inputs.py": {
        "classification": "apw_input_sidecar_owner",
        "owner": "#2635/#2636/#2651",
        "why": (
            "owns APW sidecar input-status and diagnostic wording; sidecars guide "
            "navigation only and source-open proof stays in deepen/open probes"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/background_findings.py": {
        "classification": "background_findings_projection_owner",
        "owner": "#2742/#2752/#2651",
        "why": (
            "owns reviewed background compact/detail cards and recovery wording; "
            "background findings are navigation until recall/deepen reopens source"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/background_finding_actions.py": {
        "classification": "background_finding_action_owner",
        "owner": "#2742/#2752/#2651",
        "why": (
            "owns executable background-finding action labels, commands, and "
            "detail-only source-boundary wording; compact callers should surface "
            "only the smallest behavior-bearing action"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/ambient_cards.py": {
        "classification": "ambient_recall_card_owner",
        "owner": "#2628/#2636/#2651",
        "why": (
            "owns compact ambient-card guidance and its source-boundary warnings; "
            "cards may orient attention but cannot assert source-open facts"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/ambient_policy.py": {
        "classification": "ambient_policy_owner",
        "owner": "#2636/#2651",
        "why": (
            "owns ambient anti-nag and dismissal policy strings for the foreground "
            "hot path; policy state quiets or reopens hints without becoming evidence"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/ambient_cache.py": {
        "classification": "ambient_thread_cache_owner",
        "owner": "#2674/#2676/#2651",
        "why": (
            "owns local ambient-cache persistence and related-cache boundary text; "
            "cached cards remain navigation until clean source is reopened"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/semantic_result_cache.py": {
        "classification": "semantic_result_cache_owner",
        "owner": "#2681/#2629/#2651",
        "why": (
            "owns semantic-gate cache value classes and lock behavior; cached "
            "aliases remain routing hints and cannot replace source reopening"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/cognitive_load_private_calibration.py": {
        "classification": "private_calibration_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns public-safe cognitive-load calibration wording from private "
            "history; private detail stays out of foreground output"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/continuity_domain_cli.py": {
        "classification": "continuity_domain_operator_cli_owner",
        "owner": "#2668/#2651",
        "why": (
            "owns explicit continuity-domain preview/operator wording; default "
            "foreground recall still has to reopen source before claims"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/continuity_domain_cue_quality.py": {
        "classification": "continuity_domain_cue_quality_owner",
        "owner": "#2668/#2651",
        "why": (
            "owns continuity-domain foreground cue quality and suppression labels; "
            "broad route words may stay diagnostic but must not become recall commands"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/clean_source_apw_candidates.py": {
        "classification": "clean_source_apw_candidate_filter_owner",
        "owner": "#2775/#2543/#2651",
        "why": (
            "owns current clean-source APW candidate filtering, including product-meta "
            "quote echo demotion; foreground proof belongs in source-open follow-through"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/registry_source_apw_candidates.py": {
        "classification": "registry_source_apw_candidate_filter_owner",
        "owner": "#2877/#2543/#2651",
        "why": (
            "owns registry APW candidate filtering and low-signal cue-anchor "
            "discounting; registry hits are navigation only until source-open "
            "follow-through confirms the target evidence"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/continuity_domain_producer.py": {
        "classification": "continuity_domain_producer_owner",
        "owner": "#2668/#2631/#2651",
        "why": (
            "owns deterministic registry-to-domain candidate wording and "
            "low-information label filtering; append/publish remains operator-owned"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/evidence_drawer.py": {
        "classification": "evidence_drawer_projection_owner",
        "owner": "#2628/#2636/#2651",
        "why": (
            "owns optional evidence-drawer explanation text; drawer/detail output "
            "can explain proof without expanding default compact recall"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/hook_agent_affordance.py": {
        "classification": "hook_agent_affordance_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns prompt-hook affordance text and quieting rules; broad agent words "
            "must not become unsolicited foreground recall nudges"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_context_render.py": {
        "classification": "prompt_hook_context_render_owner",
        "owner": "#2676/#2651",
        "why": (
            "owns prompt-hook compact context and operator debug projection; cache "
            "read diagnostics stay in debug/detail output instead of foreground "
            "additionalContext"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_foreground_budget.py": {
        "classification": "prompt_foreground_budget_owner",
        "owner": "#2794/#2632/#2651",
        "why": (
            "owns prompt-hook foreground packet width/source-boundary projection; "
            "sidecar diagnostics remain in detail/operator result tiers"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_decision.py": {
        "classification": "prompt_recall_decision_owner",
        "owner": "#2794/#2631/#2651",
        "why": (
            "owns prompt-recall orchestration and final result assembly; compact "
            "output should route action without leaking diagnostics"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_hot_path.py": {
        "classification": "prompt_recall_hot_path_owner",
        "owner": "#2794/#2632/#2651",
        "why": (
            "owns local-only prompt-hook hot-path route hints and stage diagnostics; "
            "instruction-like strings document runtime invariants, not foreground proof"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_result_tiers.py": {
        "classification": "prompt_recall_result_tier_owner",
        "owner": "#2794/#2651",
        "why": (
            "owns compact/detail/trace result-tier envelopes for prompt recall so "
            "foreground packets stay small without losing operator diagnostics"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_core.py": {
        "classification": "prompt_recall_policy_owner",
        "owner": "#2629/#2651",
        "why": (
            "owns prompt-recall scoring, gate, and latency-bound local invariant "
            "text; explicit deepen/search remains the source-backed path"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_ambient.py": {
        "classification": "prompt_hook_ambient_coordinator_owner",
        "owner": "#2676/#2629/#2651",
        "why": (
            "owns prompt-hook ambient cache coordination, policy filtering, active "
            "locks, and warm scheduling; degraded cache state is diagnostic, not "
            "foreground proof"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_cues.py": {
        "classification": "prompt_cue_policy_owner",
        "owner": "#2651",
        "why": (
            "owns prompt-intent and cue-detection strings used before recall "
            "routing; broad product doctrine belongs in canonical docs"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/semantic_trigger_router.py": {
        "classification": "semantic_trigger_router_owner",
        "owner": "#2793/#2651",
        "why": (
            "owns reviewed semantic trigger fixture phrases and activation/suppression "
            "boundary text; triggers are navigation candidates until source-open "
            "follow-through proves the cue"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/route_notes.py": {
        "classification": "route_note_extraction_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns process-note extraction wording; notes are route context and must "
            "be source-reopened before becoming factual evidence"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/score_fusion.py": {
        "classification": "score_fusion_policy_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns retrieval score-fusion contract text; score richness is ranking "
            "metadata, not source eligibility"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/retrieval.py": {
        "classification": "recall_retrieval_policy_owner",
        "owner": "#2635/#2651",
        "why": (
            "owns dependency-free recall retrieval and source-route expansion "
            "comments; lexical sidecars guide search and cannot replace source-open proof"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/task_orientation.py": {
        "classification": "task_orientation_projection_owner",
        "owner": "#2670/#2651",
        "why": (
            "owns Task Orientation compact/detail projection text; compact route "
            "guidance must stay distinct from callable source evidence"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/task_orientation_fixtures.py": {
        "classification": "task_orientation_fixture_owner",
        "owner": "#2670/#2651",
        "why": (
            "owns deterministic Task Orientation fixture wording used to guard "
            "source-guidance boundaries without becoming live source evidence"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/segment_search_extras.py": {
        "classification": "source_sidecar_boundary_owner",
        "owner": "#2635/#2651",
        "why": (
            "owns source sidecar/read-model boundary strings; sidecars may guide "
            "search, while source-open proof stays in detail/tests/issue closeout"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/registry_search_actions.py": {
        "classification": "registry_search_action_owner",
        "owner": "#2660/#2662/#2651",
        "why": (
            "owns registry search foreground actions for exact identifiers and "
            "useful-target gating; diagnostic hits must not become source-open proof"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/artifact_role.py": {
        "classification": "registry_search_artifact_role_owner",
        "owner": "#2775/#2651",
        "why": (
            "owns local invariant marker strings for demoting validation, issue, "
            "and memory-product quote echoes during recall/search ranking; these "
            "markers are scoring guards, not foreground instructions"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/agent_self_note_cli.py": {
        "classification": "agent_self_note_cli_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns low-authority foreground-agent self-note text and current-thread "
            "route hints; self-notes remain atmosphere, not evidence"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py": {
        "classification": "source_io_trust_boundary_owner",
        "owner": "#2635/#2675/#2651",
        "why": (
            "owns JSONL/source-ref loss-accounting boundary text; diagnostics "
            "belong in detail/operator surfaces, not compact foreground proof"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/clean_source.py": {
        "classification": "clean_source_boundary_owner",
        "owner": "#2628/#2636/#2651",
        "why": (
            "owns clean-source normalization diagnostics and redaction labels; clean "
            "source is authority, while provider loss/profiles stay explicit"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/multimodal_manifest.py": {
        "classification": "multimodal_manifest_policy_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns media-origin validation text for source manifests; policy strings "
            "guard source eligibility rather than foreground recall proof"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/registry_search_pipeline.py": {
        "classification": "registry_search_projection_owner",
        "owner": "#2660/#2662/#2651",
        "why": (
            "owns registry-wide search projection wording; exact/source usefulness "
            "state must drive actions instead of generic familiarity fallbacks"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/registry_search_duplicates.py": {
        "classification": "registry_search_match_projection_owner",
        "owner": "#2715/#2651",
        "why": (
            "owns duplicate/usefulness projection cleanup; private ranking "
            "haystacks may affect ordering but must be stripped from public output"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/last_recall_recovery.py": {
        "classification": "last_recall_recovery_action_owner",
        "owner": "#2665/#2651",
        "why": (
            "owns invalid-selector recovery actions for last-recall source search; "
            "fallback commands must stay explicit and non-mutating"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/last_recall_actions.py": {
        "classification": "last_recall_foreground_action_owner",
        "owner": "#2716/#2651",
        "why": (
            "owns last-recall search/open action text; fallback deepen actions "
            "must never be presented as exact source-open proof"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/search.py": {
        "classification": "clean_source_search_cli_owner",
        "owner": "#2715/#2716/#2651",
        "why": (
            "owns source-search CLI argument and help text; foreground commands "
            "must execute exact source-open follow-through without path leakage"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/search_output.py": {
        "classification": "clean_source_search_output_owner",
        "owner": "#2715/#2716/#2651",
        "why": (
            "owns human search/open rendering; source-open proof remains in the "
            "opened window and detail payload rather than compact debug fields"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/action_hint_cache.py": {
        "classification": "action_hint_cache_owner",
        "owner": "#2635/#2651",
        "why": (
            "owns prepared action-hint cache path, recovery, and operator refresh "
            "wording; compact hook output stays action-sized"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/diagnose.py": {
        "classification": "hook_diagnostic_operator_owner",
        "owner": "#2629/#2651",
        "why": (
            "owns operator-only hook host emulation, latency, and timeout diagnostics; "
            "diagnostic command strings must not become foreground memory guidance"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py": {
        "classification": "prompt_hook_entrypoint_owner",
        "owner": "#2629/#2651",
        "why": (
            "owns prompt-hook CLI/help and fail-open telemetry warnings; foreground "
            "additionalContext stays compact while degraded warnings stay detail/debug"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt_fallbacks.py": {
        "classification": "prompt_hook_fallback_owner",
        "owner": "#2629/#2651",
        "why": (
            "owns optional prompt-hook fallback glue kept off the hot entrypoint; "
            "missing optional foreground material fails open with detail/debug "
            "diagnostics rather than blocking prompt submission"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/scheduler.py": {
        "classification": "lifecycle_scheduler_boundary_owner",
        "owner": "#2635/#2651",
        "why": (
            "owns hook-safe scheduler boundary text; lifecycle foreground must "
            "stay fail-open and must not become a proof or job-output surface"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/candidate_router.py": {
        "classification": "subconscious_candidate_route_owner",
        "owner": "#2742/#2752/#2636/#2651",
        "why": (
            "owns subconscious candidate route reasons and trigger filtering "
            "contracts; wording can guide navigation but source claims still "
            "require recall/deepen/open follow-through"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/shell_selection.py": {
        "classification": "subconscious_shell_selection_owner",
        "owner": "#2636/#2651",
        "why": (
            "owns dry-run shell-selection policy wording for subconscious work; "
            "private queue-shape signals stay diagnostic and do not start work alone"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/staging_maintenance.py": {
        "classification": "subconscious_staging_maintenance_owner",
        "owner": "#2843/#2839/#2651",
        "why": (
            "owns bounded staging-maintenance and operator-only cache refresh "
            "wording; maintenance receipts must not become foreground proof or "
            "implicit background-work claims"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/foreground_status.py": {
        "classification": "foreground_hook_status_owner",
        "owner": "#2611/#2651",
        "why": (
            "owns foreground hook/action-hint status wording and latency readiness; "
            "status output is operational guidance, not source proof"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/lifecycle.py": {
        "classification": "lifecycle_hook_runtime_owner",
        "owner": "#2859/#2631/#2651",
        "why": (
            "owns Codex lifecycle maintenance wording, fail-open budget text, and "
            "detached-work diagnostics; hook status must not become foreground "
            "source proof or block prompt responsiveness"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/install_lifecycle.py": {
        "classification": "lifecycle_hook_install_owner",
        "owner": "#2674/#2651",
        "why": (
            "owns lifecycle hook install/status text and private command redaction; "
            "hook wiring is operational state, not foreground source evidence"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/install_prompt.py": {
        "classification": "prompt_hook_install_owner",
        "owner": "#2674/#2651",
        "why": (
            "owns prompt hook install/status text, latency-budget wording, and "
            "private command redaction for hook setup surfaces"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/skip_telemetry.py": {
        "classification": "prompt_skip_telemetry_owner",
        "owner": "#2674/#2651",
        "why": (
            "owns aggregate prompt-hook skip/latency telemetry wording; telemetry "
            "is local operational signal and must not log prompt/source text"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/update/agent_status_summary.py": {
        "classification": "update_status_compact_projection_owner",
        "owner": "#2661/#2651",
        "why": (
            "owns compact update/readiness card text; acceptance-bearing warnings "
            "must stay actionable without being reported as ready"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/update/agent_status_summary_core.py": {
        "classification": "update_status_projection_primitive_owner",
        "owner": "#2628/#2631/#2651",
        "why": (
            "owns shared update/readiness projection wording and action ordering "
            "primitives so staged modules do not recreate helper copies or cycles"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/update/capability_ladder.py": {
        "classification": "capability_ladder_status_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns capability/readiness ladder wording; ambient states must stay to "
            "installed/callable/active/useful without mixed ready claims"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/update/agent_status_summary_stages.py": {
        "classification": "update_status_staged_projection_owner",
        "owner": "#2631/#2651",
        "why": (
            "owns staged compact update/readiness projection after the mega-function "
            "split; proof and raw diagnostics remain in operator/detail output"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/update/status_actions.py": {
        "classification": "update_status_action_owner",
        "owner": "#2661/#2669/#2651",
        "why": (
            "owns update/readiness foreground action cards and mutation-risk labels "
            "for CLI and MCP follow-through"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/update/cli.py": {
        "classification": "update_cli_operator_owner",
        "owner": "#2629/#2651",
        "why": (
            "owns update/install/status operator command wording and key-safety "
            "warnings; readiness claims must still come from status projections"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/update/plugin_cache.py": {
        "classification": "plugin_cache_host_setup_owner",
        "owner": "#2715/#2716/#2669/#2651",
        "why": (
            "owns Codex plugin cache and host-setup repair receipts; host setup "
            "proof is operational state and must not be projected as source evidence"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/update/plugin_installer.py": {
        "classification": "plugin_install_host_probe_owner",
        "owner": "#2715/#2716/#2669/#2651",
        "why": (
            "owns plugin install, rollback, and Codex host-probe user-facing text; "
            "host proof stays in structured probe payloads and reports rather than "
            "compact foreground copy"
        ),
    },
    "tests/aippocampus/frontstage_assertions.py": {
        "classification": "test_contract_owner",
        "owner": "#2632/#2651",
        "why": (
            "owns reusable compact-vs-detail assertions instead of duplicating "
            "foreground doctrine in payload tests"
        ),
    },
    "tests/aippocampus/test_architecture_boundaries.py": {
        "classification": "architecture_guard_test_owner",
        "owner": "#2636/#2651",
        "why": "owns repository-level architecture boundary tests.",
    },
    "tests/aippocampus/test_build_clean_source.py": {
        "classification": "clean_source_builder_test_contract_owner",
        "owner": "#2698/#2636/#2651",
        "why": (
            "owns clean-source builder redaction and source-ref fixture strings; "
            "fixtures protect source authority instead of acting as runtime instructions"
        ),
    },
    "tests/aippocampus/test_aippocampus_cli.py": {
        "classification": "cli_frontdoor_test_contract_owner",
        "owner": "#2664/#2651",
        "why": "owns executable CLI frontdoor contracts for operator/detail actions.",
    },
    "tests/aippocampus/test_aippocampus_health.py": {
        "classification": "health_status_test_contract_owner",
        "owner": "#1868/#1890/#2178/#2651",
        "why": (
            "owns health/status compact-vs-detail, storage-pressure, host-state, "
            "and readiness text contracts; strings are test fixtures, not hidden policy"
        ),
    },
    "tests/aippocampus/test_aippocampus_maintenance.py": {
        "classification": "maintenance_recovery_test_contract_owner",
        "owner": "#1868/#2197/#2632/#2651",
        "why": (
            "owns maintenance status/plan/apply recovery-card behavior tests; "
            "wording asserts read-only and explicit-mutation contracts"
        ),
    },
    "tests/aippocampus/test_aippocampus_mcp_server_catalog.py": {
        "classification": "mcp_catalog_test_contract_owner",
        "owner": "#2685/#2686/#2651",
        "why": (
            "owns MCP tool catalog and missing-input compact/detail regression "
            "tests so payload assertions do not re-freeze JSON-wall text"
        ),
    },
    "tests/aippocampus/test_ambient_recall_cards.py": {
        "classification": "ambient_recall_card_test_contract_owner",
        "owner": "#2628/#2632/#2651",
        "why": (
            "owns ambient card trust/action-grammar behavior tests; identity checks "
            "must exercise public card output rather than private helper aliases"
        ),
    },
    "tests/aippocampus/test_cli_recovery_cards.py": {
        "classification": "cli_recovery_card_test_contract_owner",
        "owner": "#2632/#2651",
        "why": (
            "owns broad CLI recovery-card wording assertions; shared helpers keep "
            "the subprocess runner centralized while compact/detail doctrine stays in tests"
        ),
    },
    "tests/aippocampus/test_docs_health.py": {
        "classification": "docs_health_test_contract_owner",
        "owner": "#672/#1837/#1845/#1846/#1887/#2079/#2087/#2276/#2277/#2791/#2793",
        "why": (
            "owns repository docs-health fixture strings and cross-doc guard "
            "contracts; strings are test inputs, not hidden runtime instructions"
        ),
    },
    "tests/aippocampus/test_closeout_audit.py": {
        "classification": "closeout_audit_test_contract_owner",
        "owner": "#2692/#2636/#2651",
        "why": (
            "owns PR-body and issue-closeout fixture text for the closeout audit; "
            "these strings are test inputs, not runtime foreground instructions"
        ),
    },
    "tests/aippocampus/test_run_tests_tiers.py": {
        "classification": "test_runner_contract_owner",
        "owner": "#2764/#2544/#2691/#2651",
        "why": (
            "owns test-runner operator diagnostics, tier-budget wording, shard "
            "errors, and tempdir preflight fixtures; strings are CLI/test "
            "contracts, not hidden agent instructions"
        ),
    },
    "tests/aippocampus/test_agent_recall_compact_projection.py": {
        "classification": "recall_compact_projection_test_contract_owner",
        "owner": "#2741/#2742/#2743/#2636/#2651",
        "why": (
            "owns compact-vs-full recall projection fixture text and executable "
            "foreground-action assertions; tests should guard behavior, not "
            "promote diagnostics into compact output"
        ),
    },
    "tests/aippocampus/test_agent_deepen_compact_projection.py": {
        "classification": "agent_deepen_compact_projection_test_contract_owner",
        "owner": "#2860/#2686/#2651",
        "why": (
            "owns CLI/MCP deepen compact-vs-detail source-open fixture text and "
            "cue-learning follow-through assertions; fixture strings are test "
            "contracts, not runtime foreground policy"
        ),
    },
    "tests/aippocampus/test_question_tracking.py": {
        "classification": "question_source_ref_test_contract_owner",
        "owner": "#2667/#2651",
        "why": "owns question source-ref reopen contracts instead of title-search fallbacks.",
    },
    "tests/aippocampus/test_prompt_hook_latency_status.py": {
        "classification": "prompt_hook_latency_status_test_contract_owner",
        "owner": "#2732/#2632/#2651",
        "why": (
            "owns prompt-hook current-vs-historical latency status fixtures; "
            "strings are operator/status contracts, not foreground policy payloads"
        ),
    },
    "tests/aippocampus/test_prompt_recall_decision_boundaries.py": {
        "classification": "prompt_recall_decision_test_contract_owner",
        "owner": "#2794/#2631/#2651",
        "why": (
            "owns prompt-recall compact/detail boundary fixtures and source-route "
            "examples; wording asserts behavior rather than becoming runtime policy"
        ),
    },
    "tests/aippocampus/test_agent_opt_in_recall_routes.py": {
        "classification": "agent_opt_in_recall_route_test_contract_owner",
        "owner": "#2636/#2651",
        "why": (
            "owns opt-in recall route, foreground action, and macro navigation "
            "fixture strings as test contracts; these are expected outputs, not "
            "runtime instructions"
        ),
    },
    "tests/aippocampus/test_search_clean_source.py": {
        "classification": "clean_source_search_test_contract_owner",
        "owner": "#2720/#2632/#2651",
        "why": (
            "owns clean-source search/source-open follow-through fixtures; "
            "source-like strings are test evidence, not hidden agent instructions"
        ),
    },
    "tests/aippocampus/test_relationship_origin_recall.py": {
        "classification": "relationship_origin_recall_test_contract_owner",
        "owner": "#2636/#2651",
        "why": (
            "owns relationship-origin CLI/MCP source-follow-through fixtures; "
            "origin cue strings are test contracts, not runtime instructions"
        ),
    },
    "tests/aippocampus/test_semantic_trigger_router.py": {
        "classification": "semantic_trigger_router_test_contract_owner",
        "owner": "#2793/#2651",
        "why": (
            "owns semantic trigger activation/suppression fixture strings as test "
            "contracts; they verify routing behavior without becoming live prompt "
            "instructions"
        ),
    },
    "tests/aippocampus/test_task_orientation_packet.py": {
        "classification": "task_orientation_test_contract_owner",
        "owner": "#2670/#2651",
        "why": "owns Task Orientation compact/detail boundary tests.",
    },
    "tests/aippocampus/test_update_agent_status.py": {
        "classification": "update_status_test_contract_owner",
        "owner": "#2661/#2651",
        "why": "owns compact update-status readiness semantics for foreground agents.",
    },
    "tests/aippocampus/test_update_sync.py": {
        "classification": "update_sync_test_contract_owner",
        "owner": "#2661/#2669/#2651",
        "why": "owns update/sync foreground action and mutation-risk regression contracts.",
    },
    "tests/aippocampus/test_warm_ambient_recall.py": {
        "classification": "warm_ambient_test_contract_owner",
        "owner": "#2632/#2651",
        "why": (
            "owns warm ambient recall compact/detail and private-boundary tests; "
            "fixtures should guard product semantics instead of freezing debug noise"
        ),
    },
}
