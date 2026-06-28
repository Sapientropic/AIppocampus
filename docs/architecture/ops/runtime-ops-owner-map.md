# Runtime Ops Owner Map

Role: implementation map.
Status: current guard-backed owner map.

This is the owner map for `aippocampus_runtime/ops/`. The flat directory is a
legacy compatibility surface: do not add a new flat `ops/*.py` module unless
this map names its owner and explains why it cannot start inside a subpackage.
The architecture boundary test parses the allowlist below.

## Owner Packages

| Package | Owner scope | Rule |
| --- | --- | --- |
| `aippocampus_runtime/ops/doctors/` | provider/preflight/spend diagnostics, provider credential-source discovery, compact provider/spend cards | new doctor code must not be added as flat `ops/*.py`. Put implementation here and expose only reviewed public wrappers when needed. |

Compatibility wrappers:

- `aippocampus_runtime/ops/provider_doctor.py`
- `aippocampus_runtime/ops/spend_doctor.py`

These wrappers preserve public direct module imports. Their sunset condition is
to remove them when the next public-API review removes direct module
entrypoints from the release contract; until then, new implementation imports
should use `aippocampus_runtime.ops.doctors.*`.

Compatibility wrappers sunset when the next public-API review removes direct module entrypoints.

Planned owner groups for future slices:

- `ops/governance/`: storage, retention, capacity, eviction, cold archive, log retention.
- `ops/observatory/`: Cognitive Observatory, route-readiness, foreground-output, topology, and load readouts.
- `ops/recovery/`: interrupted writes, activation dead letters, activation compaction, trust-horizon recovery.
- `ops/experiments/`: recall funnel, macro timing, repo-familiarity, and fixture-only experiments.
- `ops/handoffs/`: Telepathy, worker hook handoff, provider-key bridge.

## Flat Ops Allowlist

The files below are the currently reviewed flat modules. Adding to this list is
an architecture decision, not a routine way to make a test pass.

- `aippocampus_runtime/ops/__init__.py`
- `aippocampus_runtime/ops/activation_authority_audit.py`
- `aippocampus_runtime/ops/activation_compaction_cli.py`
- `aippocampus_runtime/ops/activation_dead_letter.py`
- `aippocampus_runtime/ops/activation_lifecycle_manifest.py`
- `aippocampus_runtime/ops/activation_payload_compaction.py`
- `aippocampus_runtime/ops/attention_router_auto_gate.py`
- `aippocampus_runtime/ops/capture_consolidation_boundary.py`
- `aippocampus_runtime/ops/cognitive_observatory.py`
- `aippocampus_runtime/ops/cognitive_observatory_actions.py`
- `aippocampus_runtime/ops/cognitive_observatory_summary.py`
- `aippocampus_runtime/ops/cold_archive.py`
- `aippocampus_runtime/ops/coordination_topology.py`
- `aippocampus_runtime/ops/foreground_output_audit.py`
- `aippocampus_runtime/ops/generation_eviction.py`
- `aippocampus_runtime/ops/graphify_corpus.py`
- `aippocampus_runtime/ops/interrupted_write_recovery.py`
- `aippocampus_runtime/ops/issue_route_quality.py`
- `aippocampus_runtime/ops/issue_work_guard.py`
- `aippocampus_runtime/ops/log_retention.py`
- `aippocampus_runtime/ops/macro_timing_recheck_experiment.py`
- `aippocampus_runtime/ops/maintenance.py`
- `aippocampus_runtime/ops/maintenance_projection.py`
- `aippocampus_runtime/ops/map_rot_maintenance.py`
- `aippocampus_runtime/ops/near_user_semantic_classifier_audit.py`
- `aippocampus_runtime/ops/observatory_boundary.py`
- `aippocampus_runtime/ops/observatory_cognitive_load.py`
- `aippocampus_runtime/ops/observatory_completeness.py`
- `aippocampus_runtime/ops/observatory_control_authority.py`
- `aippocampus_runtime/ops/observatory_inputs.py`
- `aippocampus_runtime/ops/packet_topology_diagnostic.py`
- `aippocampus_runtime/ops/presence_first_matrix_fixtures.py`
- `aippocampus_runtime/ops/provider_doctor.py`
- `aippocampus_runtime/ops/provider_key_bridge.py`
- `aippocampus_runtime/ops/recall_funnel_live_agent_gate.py`
- `aippocampus_runtime/ops/recall_funnel_smoke.py`
- `aippocampus_runtime/ops/recall_navigation_attention.py`
- `aippocampus_runtime/ops/recall_navigation_comparison.py`
- `aippocampus_runtime/ops/recall_navigation_comparison_fixtures.py`
- `aippocampus_runtime/ops/recall_navigation_macro_fixture.py`
- `aippocampus_runtime/ops/recall_navigation_promotion.py`
- `aippocampus_runtime/ops/recall_navigation_promotion_projection.py`
- `aippocampus_runtime/ops/reopen_follow_through.py`
- `aippocampus_runtime/ops/repo_familiarity_foreground_experiment.py`
- `aippocampus_runtime/ops/repo_familiarity_foreground_experiment_fixtures.py`
- `aippocampus_runtime/ops/retention_report.py`
- `aippocampus_runtime/ops/rollout_size_audit.py`
- `aippocampus_runtime/ops/route_readiness.py`
- `aippocampus_runtime/ops/source_joined_routing_decision.py`
- `aippocampus_runtime/ops/spend_doctor.py`
- `aippocampus_runtime/ops/storage_capacity_report.py`
- `aippocampus_runtime/ops/storage_eviction.py`
- `aippocampus_runtime/ops/storage_governance.py`
- `aippocampus_runtime/ops/storage_governance_actions.py`
- `aippocampus_runtime/ops/storage_governance_contract.py`
- `aippocampus_runtime/ops/storage_governance_projection.py`
- `aippocampus_runtime/ops/successor_evidence.py`
- `aippocampus_runtime/ops/successor_closeout_evidence.py`
- `aippocampus_runtime/ops/successor_issue_state.py`
- `aippocampus_runtime/ops/telepathy_coordination_packet.py`
- `aippocampus_runtime/ops/telepathy_handoff_store.py`
- `aippocampus_runtime/ops/topology_anchor_policy.py`
- `aippocampus_runtime/ops/uninstall.py`
- `aippocampus_runtime/ops/worker_hook_handoff.py`
