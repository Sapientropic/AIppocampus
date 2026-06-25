from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "aippocampus"
    / "github"
    / "closeout_audit.py"
)
SPEC = importlib.util.spec_from_file_location("closeout_audit", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
closeout_audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = closeout_audit
SPEC.loader.exec_module(closeout_audit)

class CloseoutAuditTests(unittest.TestCase):
    def test_simple_bugfix_closeout_passes_without_extra_ceremony(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Fixes the negated numeric answer gate.

            Closes #1304.
            """
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["findings"], [])

    def test_unchecked_template_options_do_not_make_closeout_risky(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Adds the closeout audit.

            Closes #1308.

            Closeout class:

            - [x] `complete` - acceptance criteria are satisfied.
            - [ ] `complete_with_followups` - any remaining gaps are linked below.
            - [ ] `blocker_recorded` - useful blocker evidence landed.
            - [ ] `narrow_slice_only` - use relates-to wording.
            """
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["closeout_class"], "complete")
        self.assertEqual(report["risk_terms"], [])

    def test_failure_report_closeout_requires_followup_issue(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Adds a useful failure report, but this is diagnostic-only and not default.

            Closes #1193.
            """
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["findings"][0]["kind"], "risky_closeout_missing_followup")

    def test_empty_template_followup_heading_cannot_borrow_closing_ref(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Adds a useful failure report, but this is diagnostic-only and not default.

            Closes #1193.

            Closeout class:

            - [ ] `complete` - acceptance criteria are satisfied.
            - [ ] `complete_with_followups` - any remaining gaps are linked below.
            - [ ] `blocker_recorded` - useful blocker evidence landed; do not use a
                  closing keyword unless a follow-up issue owns the remaining work.
            - [ ] `narrow_slice_only` - use relates-to wording, not `Closes #...`.

            Remaining gap / follow-up issue:
            """
        )

        self.assertFalse(report["ok"], report)
        self.assertFalse(report["has_followup_pointer"], report)
        self.assertEqual(report["findings"][0]["kind"], "risky_closeout_missing_followup")

    def test_checked_source_boundary_cannot_claim_text_is_not_closeout_risk(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Fixes a straightforward bug.

            Closes #1304.

            ## Source And Privacy Boundary

            - [x] Any public benchmark or readiness claim states what it cannot claim.
            """
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["risk_terms"], [])

    def test_complete_with_followups_accepts_remaining_gap_issue(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Adds a useful failure report, but this is diagnostic-only and not default.

            Closeout class: complete_with_followups
            remaining_gap: #1305 owns semantic/source-side cache measurement.

            Closes #1193.
            """
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["closeout_class"], "complete_with_followups")

    def test_narrow_slice_only_cannot_use_closing_keyword(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Implements one adapter slice.

            Closeout class: narrow_slice_only
            Relates to #1188.
            Closes #1188.
            """
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["findings"][0]["kind"], "narrow_slice_closes_issue")

    def test_scripted_proxy_cannot_close_model_backed_behavior_issue(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Adds a deterministic scripted proxy for the bounded resonance prompt pilot.

            Evidence level: scripted_proxy
            Issue intent: model-backed behavior

            Closes #1319.
            """
        )

        self.assertFalse(report["ok"], report)
        finding = report["findings"][0]
        self.assertEqual(finding["kind"], "evidence_level_mismatch")
        self.assertEqual(finding["declared_evidence_level"], "scripted_proxy")
        self.assertIn("model_pilot", finding["required_evidence_levels"])
        self.assertIn("behavior_run", finding["required_evidence_levels"])

    def test_contract_pack_cannot_close_live_behavior_issue_without_followup(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Lands the public E2E50 contract pack.

            Evidence level: contract_fixture
            Issue intent: live behavior validation

            Closes #279.
            """
        )

        self.assertFalse(report["ok"], report)
        self.assertEqual(report["findings"][0]["kind"], "evidence_level_mismatch")

    def test_lower_evidence_level_passes_with_complete_followup(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Lands the public E2E50 contract pack.

            Closeout class: complete_with_followups
            Evidence level: contract_fixture
            Issue intent: live behavior validation
            remaining_gap: #1322 owns model-backed behavior validation.

            Closes #279.
            """
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["evidence_level"], "contract_fixture")
        self.assertIn("behavior_run", report["required_evidence_levels"])

    def test_runtime_default_change_requires_benchmark_outcome_or_rationale(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Runtime/default policy change: make the new route ranking default.

            Closes #2379.
            """
        )

        self.assertFalse(report["ok"], report)
        self.assertEqual(
            report["findings"][0]["kind"],
            "missing_benchmark_adoption_outcome",
        )
        self.assertTrue(report["default_runtime_change_signal"])

    def test_runtime_default_change_accepts_passing_adoption_outcome(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Runtime/default policy change: make the new route ranking default.
            Benchmark outcome card: runtime_policy_adoption_gate_ok: true.

            Closes #2379.
            """
        )

        self.assertTrue(report["ok"], report)
        self.assertTrue(report["has_benchmark_adoption_outcome"])

    def test_diagnostic_only_outcome_cannot_authorize_default_change(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Runtime/default policy change: make the new route ranking default.
            Benchmark outcome card: diagnostic-only result approves default adoption.

            Closes #2379.
            """
        )

        self.assertFalse(report["ok"], report)
        kinds = [finding["kind"] for finding in report["findings"]]
        self.assertIn("diagnostic_outcome_authorizes_default", kinds)

    def test_runtime_default_change_accepts_explicit_non_benchmark_override(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Runtime/default policy change: keep the CLI status wording default.
            Non-benchmark rationale: small internal refactor; no routing,
            hook, ranking, or policy gate behavior changed.

            Closes #2379.
            """
        )

        self.assertTrue(report["ok"], report)
        self.assertTrue(report["has_non_benchmark_adoption_rationale"])

    def test_blank_runtime_default_template_field_does_not_trigger_guard(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Small CLI wording fix.

            Runtime/default policy change:
            Benchmark outcome card or gate:
            Non-benchmark rationale / override:

            Closes #2379.
            """
        )

        self.assertTrue(report["ok"], report)
        self.assertFalse(report["default_runtime_change_signal"])

    def test_benchmark_source_side_closeout_requires_aippocampus_orientation(
        self,
    ) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Adds a LongMemEval source-side semantic cache result.

            Evidence level: scale_run

            Closes #1323.
            """
        )

        self.assertFalse(report["ok"], report)
        self.assertEqual(
            report["findings"][0]["kind"],
            "missing_aippocampus_orientation",
        )

    def test_benchmark_local_provider_prompt_cannot_close_source_side_warming(
        self,
    ) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Uses a temporary provider prompt to label source route text for a
            LongMemEval source-side warming result.

            Evidence level: scale_run
            AIppocampus orientation: checked semantic_scope_builder.

            Closes #1323.
            """
        )

        self.assertFalse(report["ok"], report)
        self.assertEqual(
            report["findings"][0]["kind"],
            "benchmark_local_scaffold_closes_source_side",
        )

    def test_benchmark_local_provider_prompt_passes_as_isolated_experiment_with_followup(
        self,
    ) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Uses a temporary provider prompt as an isolated_experiment for
            LongMemEval source-side semantic cache research.

            Closeout class: complete_with_followups
            Evidence level: scale_run
            AIppocampus orientation: checked semantic_scope_builder and warm_ambient.
            remaining_gap: #1323 owns canonical source-side semantic materialization.

            Closes #1328.
            """
        )

        self.assertTrue(report["ok"], report)

    def test_issue_metadata_file_can_supply_intent_when_pr_body_omits_it(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Lands the public E2E50 contract pack.

            Evidence level: contract_fixture

            Closes #279.
            """,
            issue_metadata={
                279: {
                    "title": "Run model-backed public E2E50 behavior validation",
                    "body": "Need live/model-backed behavior evidence, not only a contract pack.",
                }
            },
        )

        self.assertFalse(report["ok"], report)
        self.assertEqual(report["issue_intent_levels"]["279"], ["model_pilot", "behavior_run"])

    def test_high_risk_recall_closeout_requires_real_source_followthrough(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Wires MCP recall and says selector exists; route_count is nonzero.
            JSON snapshot updated.

            Closes #2600.
            """,
            issue_metadata={
                2600: {
                    "title": "Fix MCP agent recall source-open foreground action",
                    "body": "Recall/MCP/source-open work must prove useful source anchor hits.",
                }
            },
        )

        self.assertFalse(report["ok"], report)
        kinds = {finding["kind"] for finding in report["findings"]}
        self.assertIn("missing_recall_source_followthrough", kinds)
        self.assertIn("field_only_evidence_closes_high_risk", kinds)

    def test_high_risk_closeout_accepts_followthrough_and_debt_removed_shape(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Fixes compact MCP recall projection and removes duplicate helper debt.

            Evidence level: behavior_run
            agent recall -> agent deepen/open -> opened source anchor hits:
            `aippocampus agent recall "old handoff cue" --json`
            `aippocampus agent deepen --request 1 --recall-selector sel_public --json`
            opened source anchor hits=3.

            Compact/default output: compact card shows one next action.
            Detail/operator output: detail JSON keeps diagnostics behind full view.

            Debt removed: deleted helper copy and migrated callers.
            Before/after inventory: duplicate helper count 2 -> 0.

            Closes #2601.
            """,
            issue_metadata={
                2601: {
                    "title": "Cleanup MCP recall compact/detail projection debt",
                    "body": "Recall/MCP/source-open, compact/detail, and cleanup/test-debt work.",
                }
            },
        )

        self.assertTrue(report["ok"], report)
        self.assertIn("2601", report["high_risk_issue_families"])
        self.assertTrue(report["evidence_shape"]["has_recall_deepen_open_anchor_chain"])
        self.assertTrue(report["evidence_shape"]["has_debt_removed_evidence"])

    def test_guard_tooling_contract_closeout_does_not_require_runtime_proof(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            - Add runtime owner-layer contracts for MCP projection, source IO,
              registry writer, local lock, and follow-through test surfaces.
            - Add changed-surface red lights for registry writer copies and
              ad hoc local locks.

            Closes #2689.

            ## Verification
            - `python tools/aippocampus/agent_slop_guard.py --all --json --fail-on-violations`
            """,
            issue_metadata={
                2689: {
                    "title": "Add runtime owner-layer import boundary checks",
                    "body": (
                        "Need repo-native import/ownership tests for MCP projection, "
                        "source IO, registry/sync, locks, compact foreground surfaces, "
                        "fixtures, and architecture cleanup."
                    ),
                    "labels": [{"name": "readiness:guard-tooling"}],
                }
            },
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["high_risk_issue_families"]["2689"], ["guard_tooling_contract"])
        self.assertTrue(report["evidence_shape"]["has_guard_contract_list_evidence"])
        self.assertTrue(report["evidence_shape"]["has_guard_command_evidence"])
        kinds = {finding["kind"] for finding in report["findings"]}
        self.assertNotIn("missing_recall_source_followthrough", kinds)
        self.assertNotIn("missing_compact_detail_evidence_split", kinds)
        self.assertNotIn("missing_debt_removed_evidence", kinds)

    def test_guard_tooling_contract_closeout_requires_contracts_and_command(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Improves the ownership guard.

            Closes #2689.
            """,
            issue_metadata={
                2689: {
                    "title": "Add runtime owner-layer import boundary checks",
                    "body": "Add owner-layer guard-tooling contracts.",
                    "labels": [{"name": "readiness:guard-tooling"}],
                }
            },
        )

        self.assertFalse(report["ok"], report)
        finding = report["findings"][0]
        self.assertEqual(finding["kind"], "missing_guard_tooling_closeout_evidence")
        self.assertEqual(finding["missing_evidence"], ["contract_list", "guard_command"])

    def test_non_guard_labeled_issue_is_not_masked_by_guard_words(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Touches the owner-layer around MCP source-open recall.

            Closes #2690.
            """,
            issue_metadata={
                2690: {
                    "title": "Fix MCP source-open recall follow-through",
                    "body": "MCP/source-open work needs real recall/deepen/open source anchor hits.",
                    "labels": [{"name": "bug"}],
                }
            },
        )

        self.assertFalse(report["ok"], report)
        self.assertEqual(report["high_risk_issue_families"]["2690"], ["recall_mcp_apw_source_open"])
        self.assertIn(
            "missing_recall_source_followthrough",
            {finding["kind"] for finding in report["findings"]},
        )

    def test_followthrough_phrase_without_commands_does_not_pass_high_risk_closeout(
        self,
    ) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Fixes MCP recall projection.

            Evidence level: behavior_run
            agent recall -> agent deepen/open -> opened source anchor hits:
            public cue selector sel_public, opened source anchor hits=3.

            Compact/default output: compact card shows one next action.
            Detail/operator output: detail JSON keeps diagnostics behind full view.

            Closes #2601.
            """,
            issue_metadata={
                2601: {
                    "title": "Cleanup MCP recall compact/detail projection debt",
                    "body": "Recall/MCP/source-open and compact/detail work.",
                }
            },
        )

        self.assertFalse(report["ok"], report)
        self.assertTrue(report["evidence_shape"]["has_recall_deepen_open_phrase"])
        self.assertFalse(report["evidence_shape"]["has_recall_deepen_open_anchor_chain"])
        self.assertIn(
            "missing_recall_source_followthrough",
            {finding["kind"] for finding in report["findings"]},
        )

    def test_compact_detail_closeout_cannot_use_json_snapshot_only(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Updates compact projection. JSON snapshot updated.

            Closes #2602.
            """,
            issue_metadata={
                2602: {
                    "title": "Split MCP compact/detail projection",
                    "body": "Compact/default output and detail/operator output must be shown separately.",
                }
            },
        )

        self.assertFalse(report["ok"], report)
        kinds = {finding["kind"] for finding in report["findings"]}
        self.assertIn("missing_compact_detail_evidence_split", kinds)

    def test_cleanup_closeout_requires_debt_removed_not_guard_added_only(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Adds a new guard for field-only tests.

            Closes #2603.
            """,
            issue_metadata={
                2603: {
                    "title": "Clean up test-debt and guard-debt around field-only tests",
                    "body": "Debt cleanup needs deleted or migrated paths and before/after inventory.",
                }
            },
        )

        self.assertFalse(report["ok"], report)
        self.assertEqual(report["findings"][0]["kind"], "missing_debt_removed_evidence")

    def test_build_incrementality_closeout_does_not_inherit_non_goal_recall_noise(
        self,
    ) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Implements changed-slice concept graph ingress updates.

            Evidence level: scale_run
            Closeout class: complete
            Real local graph run: full rebuild concepts=101766, edges=1274418;
            changed association slice build_mode=incremental_update and reset_graph_called=false.

            Closes #2711.
            """,
            issue_metadata={
                2711: {
                    "title": "Implement changed-ingress incremental concept graph updates after no-op skip",
                    "body": """
                    ## Problem
                    Changed inputs still take the conservative full_rebuild path.
                    The next scale step is real changed-ingress incrementality.

                    ## Scope
                    Track stale/deleted labels and edges explicitly.
                    Keep the operator report honest.

                    ## Acceptance
                    Add synthetic fixtures for each changed ingress family.
                    A real/local graph run may report counts only.

                    ## Non-goals
                    Do not change live expansion semantics; another issue owns
                    recall query/read latency and foreground output.
                    """,
                }
            },
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["required_evidence_levels"], ["scale_run"])
        self.assertEqual(report["high_risk_issue_families"]["2711"], ["benchmark_or_synthetic"])

    def test_synthetic_fixture_only_cannot_claim_ready_useful_high_risk(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Ready and useful after synthetic fixture passed; scripted proxy is green.

            Closes #2604.
            """,
            issue_metadata={
                2604: {
                    "title": "Verify agent recall source-open readiness",
                    "body": "Recall/source-open readiness must not rely only on synthetic fixtures.",
                }
            },
        )

        self.assertFalse(report["ok"], report)
        kinds = {finding["kind"] for finding in report["findings"]}
        self.assertIn("missing_recall_source_followthrough", kinds)
        self.assertIn("synthetic_only_evidence_overclaims_high_risk", kinds)

    def test_performance_closeout_rejects_internal_metrics_without_user_visible_shape(
        self,
    ) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Improves the SQL query plan for graph expansion.

            Evidence level: behavior_run
            Internal performance: EXPLAIN QUERY PLAN no longer uses a temp b-tree.
            Build elapsed before=245ms after=18ms on a synthetic hub fixture.

            Closes #2713.
            """,
            issue_metadata={
                2713: {
                    "title": "Require user-visible before/after metrics for performance closeouts",
                    "body": (
                        "Performance and latency issues need recall/deepen/open follow-through, "
                        "useful source hits, wrong-route drag, manual-search fallback, and "
                        "graph/cache freshness when relevant."
                    ),
                }
            },
        )

        self.assertFalse(report["ok"], report)
        kinds = {finding["kind"] for finding in report["findings"]}
        self.assertIn("missing_performance_user_visible_metrics", kinds)
        performance = next(
            finding
            for finding in report["findings"]
            if finding["kind"] == "missing_performance_user_visible_metrics"
        )
        self.assertIn("recall_deepen_open_anchor_chain", performance["missing_metrics"])
        self.assertIn("useful_source_hit_or_anchor_count", performance["missing_metrics"])
        self.assertIn("wrong_route_drag_or_hard_negative", performance["missing_metrics"])
        self.assertIn("manual_search_fallback", performance["missing_metrics"])
        self.assertIn("graph_cache_freshness", performance["missing_metrics"])

    def test_performance_closeout_accepts_internal_metrics_with_user_visible_followthrough(
        self,
    ) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Improves hub-node graph expansion without changing the foreground surface.

            Evidence level: behavior_run
            Internal performance: EXPLAIN QUERY PLAN uses idx_concept_edges_expand;
            synthetic hub fixture latency before=245ms after=18ms.

            User-visible before/after metrics:
            agent recall -> agent deepen/open -> opened source anchor hits:
            `aippocampus agent recall "hub-node slowdown cue" --json`
            `aippocampus agent deepen --request 1 --recall-selector sel_perf --json`
            opened source anchor hits=3.
            agent recall wall time before=1800ms after=420ms.
            useful source hit count before=1 after=3.
            wrong-route-drag count before=2 after=0.
            manual-search-fallback count before=1 after=0.
            stale-route/stale-graph freshness metric: stale_route_count before=1 after=0.

            Closes #2713.
            """,
            issue_metadata={
                2713: {
                    "title": "Require user-visible before/after metrics for performance closeouts",
                    "body": (
                        "Performance and latency issues involving graph/cache freshness need "
                        "recall/deepen/open follow-through and user-visible before/after metrics."
                    ),
                }
            },
        )

        self.assertTrue(report["ok"], report)
        self.assertTrue(report["performance_freshness_required"])
        self.assertTrue(report["performance_evidence_shape"]["has_latency_before_after_metric"])
        self.assertTrue(report["performance_evidence_shape"]["has_useful_source_hit_metric"])

    def test_github_metadata_fetch_falls_back_to_gh_cli_on_rest_failure(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["gh", "issue", "view"],
            returncode=0,
            stdout=json.dumps(
                {
                    "title": "Performance closeout",
                    "body": "latency and graph expansion",
                    "labels": [{"name": "readiness:guard-tooling"}],
                }
            ),
            stderr="",
        )

        with (
            mock.patch.object(
                closeout_audit.urllib.request,
                "urlopen",
                side_effect=closeout_audit.urllib.error.URLError("rate limit"),
            ),
            mock.patch.object(closeout_audit.subprocess, "run", return_value=completed) as run,
        ):
            metadata = closeout_audit._fetch_github_issue_metadata(
                repo="Sapientropic/AIppocampus",
                issue_numbers=[2713],
            )

        self.assertEqual(metadata[2713]["title"], "Performance closeout")
        self.assertEqual(metadata[2713]["body"], "latency and graph expansion")
        self.assertEqual(metadata[2713]["labels"], [{"name": "readiness:guard-tooling"}])
        run.assert_called_once()

    def test_cli_reads_body_file_and_returns_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            body = Path(tmp) / "body.md"
            body.write_text(
                "Closes #1193\n\nfailure report without follow-up\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--body-file",
                    str(body),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])

    def test_closed_issue_traceability_flags_malformed_and_missing_evidence(self) -> None:
        report = closeout_audit.audit_closed_issue_traceability(
            [
                {
                    "number": 1401,
                    "closedByPullRequestsReferences": {"nodes": []},
                    "comments": {
                        "nodes": [
                            {
                                "body": (
                                    "Closeout: fixed on $branch at ^[cf754d8. "
                                    "Verification passed."
                                )
                            }
                        ]
                    },
                },
                {
                    "number": 1402,
                    "closedByPullRequestsReferences": {"nodes": []},
                    "comments": {"nodes": [{"body": "Thanks."}]},
                },
            ],
            window_start="2026-06-13T18:33:49Z",
            window_end="2026-06-14T06:33:49Z",
        )

        self.assertFalse(report["ok"], report)
        self.assertEqual(report["summary"]["closed_issue_count"], 2)
        kinds = [finding["kind"] for finding in report["findings"]]
        self.assertIn("malformed_closeout_comment", kinds)
        self.assertIn("missing_pr_or_commit_reference", kinds)
        self.assertIn("missing_closeout_comment", kinds)
        self.assertTrue(report["policy"]["do_not_rewrite_existing_comments"])

    def test_closed_issue_traceability_accepts_pr_linked_closeout_comment(self) -> None:
        report = closeout_audit.audit_closed_issue_traceability(
            {
                "issues": [
                    {
                        "number": 1403,
                        "closedByPullRequestsReferences": {
                            "nodes": [{"number": 1436, "url": "https://example.test/pull/1436"}]
                        },
                        "comments": {
                            "nodes": [
                                {
                                    "body": (
                                        "Closeout: PR #1436 merged. "
                                        "Verification: docs health and PR gate passed. "
                                        "Cannot claim live/private quality."
                                    )
                                }
                            ]
                        },
                    }
                ]
            }
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["summary"]["issues_with_closed_pr_count"], 1)
        self.assertEqual(report["findings"], [])

    def test_cli_reads_closed_issue_file_and_returns_traceability_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "closed.json"
            payload_path.write_text(
                json.dumps(
                    [
                        {
                            "number": 1404,
                            "closedByPullRequestsReferences": {"nodes": []},
                            "comments": {"nodes": []},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--closed-issues-file",
                    str(payload_path),
                    "--closed-window-start",
                    "2026-06-13T18:33:49Z",
                    "--closed-window-end",
                    "2026-06-14T06:33:49Z",
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["kind"], "aippocampus_closed_issue_traceability_audit")
        self.assertEqual(payload["window"]["start"], "2026-06-13T18:33:49Z")

if __name__ == "__main__":
    unittest.main()
