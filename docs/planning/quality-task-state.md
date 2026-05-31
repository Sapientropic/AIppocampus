state: active
goal_anchor: "Codex Goal: refine AIppocampus open issues with Claude Code MCP live smoke, Windows binary packaging, and verified issue closeout"
mode: Standard
run_shape: continuous_until_stop
slice_id: issues-mcp-binary-refinement
slice_goal: "Close evidence-backed provider/MCP/binary issues, then continue only the remaining issue tracks that still have real implementation gaps"
source_goal: "User request: configure local Claude Code MCP for real smoke, start Windows standalone binary first, skip #148/#163/#168, and refine remaining issues without clearing for its own sake"
stop_condition: "Each targeted issue is implemented with evidence, explicitly deferred with blocker/risk, or reduced to a smaller verified follow-up; final closeout separates Can Claim and Cannot Claim"
handoff_policy: after_deadline_closeout
continuation_policy: continue_after_initial_plan_until_stop_condition
intake_status: inferred_from_user_request
gate_status: in_progress
artifact_index:
  - docs/planning/quality-task-state.md
  - README.md
  - docs/guides/install-guide.md
  - docs/guides/public-api.md
  - docs/guides/claude-code-mcp.md
  - docs/architecture/runtime-script-map.md
  - docs/evidence/readiness/public-readiness-verification.md
  - docs/planning/standalone-binary-packaging.md
  - skills/aippocampus/scripts/conversation_sources/
  - skills/aippocampus/scripts/build_clean_source.py
  - skills/aippocampus/scripts/onboard.py
  - tools/aippocampus/package_windows_binary.py
  - tests/aippocampus/
worker_plan: "subagents used for Claude MCP audit, Windows binary packaging, and issue evidence audit"
recovery_status: normal
blockers: []
needs_human:
  - "Final product acceptance and any remote publishing/PR decision"
residual_risk: "Claude Code MCP host/tool-call smoke passes on this Windows host, explicit Claude Code onboarding dry-run has been previewed without writing, Windows x64 PyInstaller artifact smoke passes, and the standalone binary has been re-smoked after the #144 package-layout slices through commit d1b8617. #104 still needs real provider credentials and an ephemeral object-store target; #148/#163/#168 are intentionally skipped for this pass; #158/#164 remain dependent on the skipped Dream/coding-continuity evidence tracks."
next_action: "Continue only evidence-backed slices: either run #104 after a real provider target is available, or take another narrow #144/Dream package boundary only when the ownership seam is clear."
candidate_slices:
  - "issues-113-116-120-provider-mainline: provider contract, normalized clean source, Claude/generic import, onboarding status"
  - "issue-112-cli-facade: aippocampus command wrapper over existing scripts"
  - "issues-117-118-host-smoke-docs: Claude Code MCP/onboarding docs and cross-agent continuity smoke"
  - "issue-119-source-identity-privacy: source id/ref policy and redaction tests"
  - "issue-121-windows-binary: PyInstaller packaging script, private-data guard, and Windows artifact smoke"
  - "issues-122-124-host-boundary: Codex-specific surface inventory, registry-home precedence, and Claude host-native adapter decision"
  - "issues-158-162-dream-mainline: dream queue, policies, one-sidedness gate, and parked lifecycle validation"
  - "issues-164-170-coding-memory: coding decision terrain/weather split, thin-evidence gating, probes, benchmark runner, and host affordance simulator"
last_update: "2026-05-31T13:52:00+08:00"
deadline: null
time_budget_remaining: null
checkpoint_ready: true
