state: handed-off
goal_anchor: "Codex Goal: refine and implement GitHub issues #112-#120 for AIppocampus with verification and closeout"
mode: Standard
run_shape: continuous_until_stop
slice_id: issues-112-120-provider-mainline
slice_goal: "Stabilize the provider-normalized ingestion/onboarding mainline that #113-#116 and #120 depend on"
source_goal: "User request: [$quality-iteration] /goal 精细化落地 issues #112-#120"
stop_condition: "Each issue is either implemented with evidence, explicitly deferred with blocker/risk, or reduced to a smaller verified follow-up; final closeout separates Can Claim and Cannot Claim"
handoff_policy: after_deadline_closeout
continuation_policy: continue_after_initial_plan_until_stop_condition
intake_status: inferred_from_user_request
gate_status: degraded
artifact_index:
  - docs/planning/quality-task-state.md
  - README.md
  - docs/guides/install-guide.md
  - docs/guides/public-api.md
  - docs/architecture/runtime-script-map.md
  - skills/aippocampus/scripts/conversation_sources/
  - skills/aippocampus/scripts/build_clean_source.py
  - skills/aippocampus/scripts/onboard.py
  - tests/aippocampus/
worker_plan: none
recovery_status: normal
blockers: []
needs_human:
  - "Final product acceptance and any remote publishing/PR decision"
residual_risk: "Claude Code host MCP probe is blocked by local host configuration; real local Claude Code history parser smoke passed with counts-only output, but live Claude MCP tool-call reachability remains unproven"
next_action: "Configure Claude Code MCP server named aippocampus, then rerun the host probe before claiming live Claude Code MCP tool-call success"
candidate_slices:
  - "issues-113-116-120-provider-mainline: provider contract, normalized clean source, Claude/generic import, onboarding status"
  - "issue-112-cli-facade: aippocampus command wrapper over existing scripts"
  - "issues-117-118-host-smoke-docs: Claude Code MCP/onboarding docs and cross-agent continuity smoke"
  - "issue-119-source-identity-privacy: source id/ref policy and redaction tests"
last_update: "2026-05-30T22:10:00+08:00"
deadline: null
time_budget_remaining: null
checkpoint_ready: true
