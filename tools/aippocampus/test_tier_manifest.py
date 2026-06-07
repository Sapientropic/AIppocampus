from __future__ import annotations

from typing import NamedTuple


class TestModuleClassification(NamedTuple):
    primary_tier: str
    tags: tuple[str, ...] = ()


TEST_MODULE_STEMS = frozenset(
    {
        "test_aar_v2_action_time_nudges",
        "test_activation_payload_compaction",
        "test_activation_surface_authority",
        "test_active_recall",
        "test_active_recall_lock",
        "test_active_recall_lock_compaction",
        "test_active_path_packet",
        "test_agency_affordance",
        "test_agency_host_timing",
        "test_agent_fallback_executor",
        "test_agent_fallback_materializer",
        "test_agent_discovery_release_check",
        "test_agent_self_notes",
        "test_aippocampus_cli",
        "test_aippocampus_health",
        "test_aippocampus_lifecycle_hook",
        "test_aippocampus_maintenance",
        "test_aippocampus_mcp_server",
        "test_aippocampus_prompt_hook",
        "test_aippocampuslib",
        "test_ambient_recall_cards",
        "test_ambient_recall_policy",
        "test_ambient_source_reopen",
        "test_ambient_thread_cache",
        "test_architecture_boundaries",
        "test_benchmark_coding_decision_shadow",
        "test_benchmark_amemgym",
        "test_benchmark_amemgym_official",
        "test_benchmark_cognitive_portrait",
        "test_benchmark_compaction_continuity",
        "test_benchmark_continuous_memory_arms",
        "test_benchmark_codex_desktop_amemgym",
        "test_benchmark_corpus_converter",
        "test_benchmark_conversational_media_ingest_recall",
        "test_benchmark_e2e50_silent_constraint",
        "test_benchmark_field_continuity",
        "test_benchmark_fresh_thread_recall_demo",
        "test_benchmark_fts5_recall",
        "test_benchmark_hippocampal_hard_negatives",
        "test_benchmark_hippocampal_recall",
        "test_benchmark_knowledge_pollution",
        "test_benchmark_live_semantic_gate",
        "test_benchmark_locomo_answer_usefulness",
        "test_benchmark_locomo_public_users",
        "test_benchmark_longmemeval",
        "test_benchmark_longmemeval_v2_context",
        "test_benchmark_memory_decision_gate",
        "test_benchmark_memoryagentbench",
        "test_benchmark_multimodal_corpus_retrieval",
        "test_benchmark_multimodal_niah_evidence_pool",
        "test_benchmark_payload_fidelity",
        "test_benchmark_prompt_hot_path_funnel",
        "test_benchmark_public_longitudinal_users",
        "test_benchmark_published_reports",
        "test_benchmark_question_aware_real_history",
        "test_benchmark_question_tracking_calibration",
        "test_benchmark_run_history_diff",
        "test_benchmark_segmented_merge_policy",
        "test_benchmark_semantic_robustness",
        "test_benchmark_source_evidence_retrieval",
        "test_benchmark_statistics",
        "test_benchmark_suite",
        "test_benchmark_vcs_future_event_recall",
        "test_benchmark_warm_ambient_recall",
        "test_benchmark_warm_ambient_sweep",
        "test_browser_memory_companion",
        "test_build_associations",
        "test_build_clean_source",
        "test_build_cognitive_map",
        "test_build_concept_graph",
        "test_build_index",
        "test_build_project_timeline",
        "test_build_segments",
        "test_build_vcs_future_event_fixture",
        "test_capture_consolidation_boundary",
        "test_checkpoint",
        "test_cli_json_contract",
        "test_codex_long_session_smoke",
        "test_coding_decision_events",
        "test_coding_rejected_route_probes",
        "test_coding_ticket_host_contract",
        "test_episode_arcs",
        "test_compat_shim_inventory",
        "test_compensatory_dream",
        "test_correction_reconsolidation",
        "test_cognitive_load_sidecar",
        "test_cognitive_observatory",
        "test_cognitive_worker_mode",
        "test_cross_agent_continuity_smoke",
        "test_deepseek_model_routing",
        "test_diagnose_hooks",
        "test_docs_health",
        "test_dream_delivery_eligibility",
        "test_dream_input_pack",
        "test_dream_live_shadow_ab",
        "test_dream_one_sidedness",
        "test_dream_precision_policy",
        "test_dream_queue",
        "test_dream_real_history_eval",
        "test_dream_retrospective_lifecycle",
        "test_dream_sleep_cycle",
        "test_dream_worker",
        "test_dream_working_memory",
        "test_dream_working_memory_compaction",
        "test_e2e50_seed_candidates",
        "test_encrypted_sync_bundle",
        "test_emergency_snapshot",
        "test_export_bundle",
        "test_fresh_thread_action_policy",
        "test_fresh_thread_activation_state",
        "test_fresh_thread_demo",
        "test_fresh_thread_real_history_smoke",
        "test_fresh_thread_scent_packet",
        "test_frontier_probe",
        "test_generic_jsonl_integration_smoke",
        "test_global_storage_defaults",
        "test_import_bundle",
        "test_import_coupling",
        "test_install_lifecycle_hook",
        "test_install_prompt_hook",
        "test_journey_tracking",
        "test_knowledge_answer_gate",
        "test_knowledge_capability_conflicts",
        "test_knowledge_capability_manifest",
        "test_knowledge_source_schema",
        "test_legacy_aliases",
        "test_life_wide_registry_smoke",
        "test_living_cue_cache",
        "test_log_retention",
        "test_long_thread_segment_soak",
        "test_magic_activation_policy",
        "test_macos_install_smoke_workflow",
        "test_memory_candidate_router",
        "test_memory_pain_prompt_hook_smoke",
        "test_model_client",
        "test_multilingual_prompt_hook_smoke",
        "test_multimodal_answer_gate",
        "test_multimodal_provider_routing",
        "test_multimodal_source_manifest",
        "test_navigation_potential",
        "test_object_storage_sync",
        "test_onboard_codex",
        "test_openai_agents_sdk_smoke",
        "test_operation_claim_gate",
        "test_operation_integrity",
        "test_package_windows_binary",
        "test_path_identity",
        "test_planning_audit",
        "test_plugin_distribution",
        "test_prewarm_planner",
        "test_project_triage",
        "test_prompt_context_render",
        "test_prompt_hot_path_funnel",
        "test_prompt_recall_decision_boundaries",
        "test_prompt_recall_policy",
        "test_prompt_recall_threshold",
        "test_provider_doctor",
        "test_provider_key_bridge",
        "test_public_output",
        "test_question_confirmation_live",
        "test_question_confirmation_live_smoke",
        "test_question_feedback_policy",
        "test_question_health",
        "test_question_index_sidecar",
        "test_question_prefilter_parity",
        "test_question_resolution",
        "test_question_tracking",
        "test_question_tracking_scale_smoke",
        "test_question_vector_index",
        "test_query_profile",
        "test_recall_funnel_smoke",
        "test_recall_navigation_comparison",
        "test_recall_scoring_policy",
        "test_recall_structure_time_features",
        "test_recall_why_diagnostics",
        "test_reflection_space",
        "test_registry_register_rollout",
        "test_registry_search",
        "test_registry_store",
        "test_repo_familiarity",
        "test_repo_familiarity_foreground_experiment",
        "test_retrieval_query_policy",
        "test_retrieval_score_fusion",
        "test_routing_boundaries",
        "test_runtime_contracts_and_config_registry",
        "test_run_tests_tiers",
        "test_schema_profiles",
        "test_search_clean_source",
        "test_search_decision_adapter",
        "test_search_segments",
        "test_semantic_cue_cache",
        "test_semantic_paraphrase_reuse_smoke",
        "test_semantic_recall_gate",
        "test_semantic_scope_labels",
        "test_semantic_scope_real_history_smoke",
        "test_semantic_scope_source_review",
        "test_semantic_scope_suppressed_recovery",
        "test_semantic_trigger_compaction",
        "test_semantic_trigger_router",
        "test_simulate_prompt_hook",
        "test_spend_doctor",
        "test_source_evidence_recall_eval",
        "test_source_texture",
        "test_stage_0_5_smoke",
        "test_storage_capacity_report",
        "test_storage_governance",
        "test_subconscious_agent",
        "test_subconscious_jobs",
        "test_subconscious_review",
        "test_subconscious_scheduler",
        "test_subconscious_staging_maintenance",
        "test_subconscious_worker",
        "test_sync_bundle",
        "test_synthetic_scale_capacity_smoke",
        "test_theme_emergence",
        "test_thread_story_packet",
        "test_time_driven_maintenance",
        "test_topology_anchor_policy",
        "test_update_sync",
        "test_vault_dashboard_assets",
        "test_warm_ambient_privacy_policy",
        "test_warm_ambient_recall",
        "test_warm_ambient_scheduler_policy",
        "test_warm_ambient_topic_epoch_policy",
    }
)

QUICK_STEMS = frozenset(
    {
        "test_active_recall",
        "test_active_recall_lock",
        "test_active_path_packet",
        "test_agent_fallback_executor",
        "test_agent_fallback_materializer",
        "test_agent_self_notes",
        "test_aippocampuslib",
        "test_ambient_recall_cards",
        "test_architecture_boundaries",
        "test_build_clean_source",
        "test_build_index",
        "test_capture_consolidation_boundary",
        "test_cli_json_contract",
        "test_cognitive_load_sidecar",
        "test_cognitive_observatory",
        "test_docs_health",
        "test_dream_delivery_eligibility",
        "test_magic_activation_policy",
        "test_navigation_potential",
        "test_path_identity",
        "test_prewarm_planner",
        "test_prompt_context_render",
        "test_public_output",
        "test_question_tracking",
        "test_query_profile",
        "test_recall_why_diagnostics",
        "test_runtime_contracts_and_config_registry",
        "test_run_tests_tiers",
        "test_semantic_recall_gate",
        "test_source_texture",
        "test_topology_anchor_policy",
    }
)

SMOKE_STEMS = frozenset(
    {
        "test_aippocampus_lifecycle_hook",
        "test_codex_long_session_smoke",
        "test_cross_agent_continuity_smoke",
        "test_diagnose_hooks",
        "test_e2e50_seed_candidates",
        "test_fresh_thread_real_history_smoke",
        "test_frontier_probe",
        "test_generic_jsonl_integration_smoke",
        "test_install_lifecycle_hook",
        "test_install_prompt_hook",
        "test_long_thread_segment_soak",
        "test_macos_install_smoke_workflow",
        "test_memory_pain_prompt_hook_smoke",
        "test_multilingual_prompt_hook_smoke",
        "test_openai_agents_sdk_smoke",
        "test_question_confirmation_live_smoke",
        "test_question_tracking_scale_smoke",
        "test_recall_funnel_smoke",
        "test_semantic_paraphrase_reuse_smoke",
        "test_simulate_prompt_hook",
        "test_synthetic_scale_capacity_smoke",
    }
)

INTEGRATION_STEMS = frozenset(
    {
        "test_aippocampus_mcp_server",
        "test_browser_memory_companion",
        "test_deepseek_model_routing",
        "test_dream_live_shadow_ab",
        "test_encrypted_sync_bundle",
        "test_export_bundle",
        "test_import_bundle",
        "test_cognitive_worker_mode",
        "test_model_client",
        "test_multimodal_provider_routing",
        "test_package_windows_binary",
        "test_project_triage",
        "test_provider_doctor",
        "test_question_confirmation_live",
        "test_sync_bundle",
    }
)

SLOW_STEMS = frozenset(
    {
        "test_aippocampus_prompt_hook",
        "test_dream_real_history_eval",
        "test_life_wide_registry_smoke",
        "test_object_storage_sync",
        "test_onboard_codex",
        "test_plugin_distribution",
        "test_semantic_scope_real_history_smoke",
        "test_stage_0_5_smoke",
    }
)

BENCHMARK_STEMS = frozenset(
    {
        "test_benchmark_coding_decision_shadow",
        "test_benchmark_amemgym",
        "test_benchmark_amemgym_official",
        "test_benchmark_cognitive_portrait",
        "test_benchmark_compaction_continuity",
        "test_benchmark_continuous_memory_arms",
        "test_benchmark_codex_desktop_amemgym",
        "test_benchmark_conversational_media_ingest_recall",
        "test_benchmark_e2e50_silent_constraint",
        "test_benchmark_field_continuity",
        "test_benchmark_fresh_thread_recall_demo",
        "test_benchmark_fts5_recall",
        "test_benchmark_hippocampal_hard_negatives",
        "test_benchmark_hippocampal_recall",
        "test_benchmark_knowledge_pollution",
        "test_benchmark_live_semantic_gate",
        "test_benchmark_locomo_answer_usefulness",
        "test_benchmark_locomo_public_users",
        "test_benchmark_longmemeval",
        "test_benchmark_longmemeval_v2_context",
        "test_benchmark_memory_decision_gate",
        "test_benchmark_memoryagentbench",
        "test_benchmark_multimodal_corpus_retrieval",
        "test_benchmark_multimodal_niah_evidence_pool",
        "test_benchmark_payload_fidelity",
        "test_benchmark_prompt_hot_path_funnel",
        "test_benchmark_public_longitudinal_users",
        "test_benchmark_published_reports",
        "test_benchmark_question_aware_real_history",
        "test_benchmark_question_tracking_calibration",
        "test_benchmark_run_history_diff",
        "test_benchmark_segmented_merge_policy",
        "test_benchmark_semantic_robustness",
        "test_benchmark_source_evidence_retrieval",
        "test_benchmark_statistics",
        "test_benchmark_suite",
        "test_benchmark_vcs_future_event_recall",
        "test_benchmark_warm_ambient_recall",
        "test_benchmark_warm_ambient_sweep",
    }
)

BENCHMARK_SMOKE_STEMS = frozenset(
    {
        "test_benchmark_field_continuity",
        "test_benchmark_amemgym",
        "test_benchmark_amemgym_official",
        "test_benchmark_codex_desktop_amemgym",
        "test_benchmark_e2e50_silent_constraint",
        "test_benchmark_hippocampal_recall",
        "test_benchmark_knowledge_pollution",
        "test_benchmark_locomo_public_users",
        "test_benchmark_longmemeval_v2_context",
        "test_benchmark_memoryagentbench",
        "test_benchmark_public_longitudinal_users",
        "test_benchmark_published_reports",
        "test_benchmark_segmented_merge_policy",
        "test_benchmark_statistics",
        "test_benchmark_suite",
        "test_benchmark_vcs_future_event_recall",
        "test_e2e50_seed_candidates",
    }
)

TAG_OVERRIDES = {
    "test_aippocampus_mcp_server": ("mcp", "subprocess"),
    "test_browser_memory_companion": ("browser",),
    "test_codex_long_session_smoke": ("host", "filesystem"),
    "test_cognitive_worker_mode": ("provider",),
    "test_cross_agent_continuity_smoke": ("cross_agent", "host"),
    "test_deepseek_model_routing": ("provider",),
    "test_diagnose_hooks": ("hook", "subprocess"),
    "test_dream_live_shadow_ab": ("host",),
    "test_e2e50_seed_candidates": ("benchmark", "public_fixture"),
    "test_encrypted_sync_bundle": ("sync", "filesystem"),
    "test_export_bundle": ("filesystem",),
    "test_import_bundle": ("filesystem",),
    "test_install_lifecycle_hook": ("install", "hook"),
    "test_install_prompt_hook": ("install", "hook"),
    "test_life_wide_registry_smoke": ("smoke", "registry", "slow"),
    "test_macos_install_smoke_workflow": ("install", "macos"),
    "test_model_client": ("provider",),
    "test_multimodal_provider_routing": ("provider", "multimodal"),
    "test_object_storage_sync": ("sync", "provider", "slow"),
    "test_onboard_codex": ("install", "onboarding", "slow"),
    "test_openai_agents_sdk_smoke": ("provider", "optional_dependency"),
    "test_package_windows_binary": ("windows", "packaging"),
    "test_plugin_distribution": ("packaging", "release", "slow"),
    "test_project_triage": ("github",),
    "test_provider_doctor": ("provider",),
    "test_provider_key_bridge": ("hook", "install", "provider"),
    "test_question_confirmation_live": ("live_contract",),
    "test_semantic_scope_real_history_smoke": ("real_history", "slow"),
    "test_simulate_prompt_hook": ("hook",),
    "test_stage_0_5_smoke": ("release", "slow"),
    "test_sync_bundle": ("sync", "filesystem"),
    "test_update_sync": ("install", "filesystem", "hook", "packaging"),
}


def _module_name(stem: str) -> str:
    return f"tests.aippocampus.{stem}"


ALL_TEST_MODULES = frozenset(_module_name(stem) for stem in TEST_MODULE_STEMS)
QUICK_MODULES = frozenset(_module_name(stem) for stem in QUICK_STEMS)
SMOKE_MODULES = frozenset(_module_name(stem) for stem in SMOKE_STEMS)
INTEGRATION_MODULES = frozenset(_module_name(stem) for stem in INTEGRATION_STEMS)
SLOW_MODULES = frozenset(_module_name(stem) for stem in SLOW_STEMS)
BENCHMARK_MODULES = frozenset(_module_name(stem) for stem in BENCHMARK_STEMS)
BENCHMARK_SMOKE_MODULES = frozenset(_module_name(stem) for stem in BENCHMARK_SMOKE_STEMS)

TIER_ALIASES = {"fast": "pr", "deterministic": "pr", "ci": "pr"}
PR_PRIMARY_TIERS = frozenset({"quick", "pr", "smoke", "integration"})
PRIMARY_TIER_ORDER = ("quick", "pr", "smoke", "integration", "slow", "benchmark")
TEST_TIERS = (
    "quick",
    "pr",
    "smoke",
    "integration",
    "slow",
    "benchmark-smoke",
    "benchmark",
    "full",
    "fast",
)

TIER_DESCRIPTIONS = {
    "quick": "Small local inner loop for core source, CLI, docs, and tier-contract guards.",
    "pr": "Broad deterministic PR lane; includes quick plus local-safe contract, smoke, and integration modules.",
    "smoke": "Focused deterministic smoke lane for hooks, install workflows, host/cross-agent probes, and scale smokes.",
    "integration": "Focused local integration lane for MCP, browser companion, provider routing, sync bundles, and packaging contracts.",
    "slow": "Deterministic but expensive or readiness-heavy tests kept out of normal PR loops.",
    "benchmark-smoke": "Curated public benchmark/support smoke lane.",
    "benchmark": "Full checked-in benchmark test mirror.",
    "full": "Composition of all explicitly classified tests.",
    "fast": "Deprecated compatibility alias for pr.",
}


def _primary_tier_for_stem(stem: str) -> str:
    if stem in QUICK_STEMS:
        return "quick"
    if stem in SMOKE_STEMS:
        return "smoke"
    if stem in INTEGRATION_STEMS:
        return "integration"
    if stem in SLOW_STEMS:
        return "slow"
    if stem in BENCHMARK_STEMS:
        return "benchmark"
    return "pr"


def _tags_for_stem(stem: str, primary_tier: str) -> tuple[str, ...]:
    tags = {primary_tier}
    if primary_tier in {"quick", "pr"}:
        tags.add("deterministic")
    if stem.startswith("test_benchmark_"):
        tags.add("benchmark")
    if "smoke" in stem:
        tags.add("smoke")
    if "hook" in stem:
        tags.add("hook")
    if "sync" in stem or "bundle" in stem:
        tags.add("sync")
    if "install" in stem:
        tags.add("install")
    if "provider" in stem or "model" in stem:
        tags.add("provider")
    if "host" in stem:
        tags.add("host")
    tags.update(TAG_OVERRIDES.get(stem, ()))
    return tuple(sorted(tags))


TEST_MODULE_CLASSIFICATIONS = {
    _module_name(stem): TestModuleClassification(
        primary_tier=_primary_tier_for_stem(stem),
        tags=_tags_for_stem(stem, _primary_tier_for_stem(stem)),
    )
    for stem in sorted(TEST_MODULE_STEMS)
}


def validate_manifest(discovered_modules: set[str]) -> None:
    unclassified = sorted(discovered_modules - ALL_TEST_MODULES)
    stale = sorted(ALL_TEST_MODULES - discovered_modules)
    if unclassified or stale:
        details = []
        if unclassified:
            details.append(f"unclassified test modules: {', '.join(unclassified)}")
        if stale:
            details.append(f"stale manifest modules: {', '.join(stale)}")
        raise ValueError("test tier manifest is out of sync; " + "; ".join(details))
