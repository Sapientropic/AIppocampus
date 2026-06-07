from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.cli import facade  # noqa: E402
from aippocampus_runtime.ops import cognitive_observatory  # noqa: E402
from aippocampus_runtime.ops.route_readiness import route_readiness_report  # noqa: E402


class RouteReadinessObservatoryTests(unittest.TestCase):
    def test_route_readiness_keeps_ready_rows_navigation_only(self) -> None:
        report = route_readiness_report(
            [
                {
                    "route_id": "ready-route",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 100,
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "source_refs": [{"source_id": "clean:1", "message_id": "m1"}],
                }
            ],
            active_lock_roi={
                "lock_pull_count": 1,
                "lock_reopen_attempt_count": 1,
                "source_backed_hit_count": 1,
            },
            now_unix=1_010,
        )

        self.assertEqual(report["kind"], "aippocampus_route_readiness_report")
        self.assertEqual(report["metrics"]["ready_count"], 1)
        row = report["rows"][0]
        self.assertEqual(row["status"], "ready")
        self.assertTrue(row["navigation_only"])
        self.assertTrue(row["source_reopen_required_before_claim"])
        self.assertIn("prewarm_route_is_source_backed_evidence", report["cannot_claim"])
        self.assertEqual(
            report["metrics"]["rates"]["source_reopen_after_prewarm_rate"],
            1.0,
        )

    def test_route_readiness_suppresses_stale_privacy_low_roi_and_missing_refs(self) -> None:
        report = route_readiness_report(
            [
                {
                    "route_id": "stale",
                    "freshness": "stale",
                    "created_unix": 1_000,
                    "ttl_seconds": 100,
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "source_refs": [{"source_id": "clean:stale"}],
                },
                {
                    "route_id": "privacy",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 100,
                    "privacy_action": "hard_block",
                    "privacy_reason_codes": ["secret_like"],
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "source_refs": [{"source_id": "clean:private"}],
                },
                {
                    "route_id": "low-roi",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 100,
                    "expected_value": 0.2,
                    "estimated_cost": 1,
                    "source_refs": [{"source_id": "clean:weak"}],
                },
                {
                    "route_id": "no-refs",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 100,
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "source_refs": [],
                },
            ],
            now_unix=1_010,
        )

        self.assertEqual(report["metrics"]["ready_count"], 0)
        self.assertEqual(report["metrics"]["suppressed_count"], 4)
        self.assertEqual(report["metrics"]["stale_suppression_count"], 1)
        self.assertEqual(report["metrics"]["privacy_suppression_count"], 1)
        self.assertEqual(report["metrics"]["secret_or_property_risk_suppression_count"], 1)
        self.assertEqual(report["metrics"]["low_value_suppression_count"], 1)
        self.assertEqual(report["metrics"]["no_source_refs_suppression_count"], 1)
        self.assertIn("secret_or_property_risk_blocked", report["suppression_counts"])
        for row in report["rows"]:
            self.assertEqual(row["readiness_class"], "silent")
            self.assertTrue(row["navigation_only"])

    def test_route_readiness_keeps_local_privacy_route_handles_ready(self) -> None:
        report = route_readiness_report(
            [
                {
                    "route_id": "same-user-cross-domain",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 100,
                    "privacy_action": "private_route",
                    "privacy_reason_codes": ["ordinary_personal_conversation"],
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "source_refs": [{"source_id": "clean:relationship"}],
                }
            ],
            now_unix=1_010,
        )

        row = report["rows"][0]
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["readiness_class"], "source_reopen_ready")
        self.assertIn("local_route_handle_only", row["reason_codes"])
        self.assertEqual(report["metrics"]["ready_count"], 1)
        self.assertEqual(report["metrics"]["privacy_suppression_count"], 0)

    def test_route_readiness_hard_reason_overrides_local_route_action(self) -> None:
        report = route_readiness_report(
            [
                {
                    "route_id": "mixed-privacy-route",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 100,
                    "privacy_action": "private_route",
                    "privacy_reason_codes": ["external_payload"],
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "source_refs": [{"source_id": "clean:relationship"}],
                }
            ],
            now_unix=1_010,
        )

        row = report["rows"][0]
        self.assertEqual(row["status"], "suppressed")
        self.assertIn("external_payload_blocked", row["reason_codes"])
        self.assertNotIn("local_route_handle_only", row["reason_codes"])
        self.assertEqual(report["metrics"]["privacy_suppression_count"], 1)
        self.assertEqual(report["metrics"]["external_payload_suppression_count"], 1)

    def test_observatory_fixture_is_public_safe_and_read_only(self) -> None:
        report = cognitive_observatory.fixture_cognitive_observatory_readout()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["kind"], "aippocampus_cognitive_observatory_readout")
        self.assertTrue(report["ok"])
        self.assertTrue(report["no_write"])
        self.assertTrue(report["contract"]["read_only_report"])
        self.assertTrue(report["contract"]["not_control_plane"])
        self.assertTrue(report["contract"]["source_reopen_required_before_claim"])
        self.assertGreater(report["metrics"]["route_ready_count"], 0)
        self.assertGreater(report["metrics"]["route_suppressed_count"], 0)
        self.assertIn("route_readiness", report["surfaces"])
        self.assertIn("activation_authority", report["surfaces"])
        self.assertIn("recall_diagnostic", report["surfaces"])
        self.assertIn("sleep_cycle", report["surfaces"])
        self.assertNotIn("this field must never be serialized", encoded)
        self.assertNotIn("private\\thread", encoded)
        self.assertNotIn(str(REPO_ROOT), encoded)
        self.assertIn("complete_cognitive_observatory_ui_exists", report["cannot_claim"])
        self.assertFalse(report["privacy_boundary"]["sensitive_values_serialized"])

    def test_observatory_public_output_redacts_sensitive_values(self) -> None:
        sensitive_key = "api" + "_key"
        sensitive_value = "fixture-" + "credential-value"
        assignment_value = "token=" + sensitive_value

        report = cognitive_observatory.cognitive_observatory_readout(
            recall_diagnostic={
                "kind": "fixture_recall_diagnostic",
                sensitive_key: sensitive_value,
                "public_note": assignment_value,
            }
        )
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertIn("<sensitive-value-redacted>", encoded)
        self.assertNotIn(sensitive_value, encoded)

    def test_observatory_reports_query_pattern_routes_without_alias_text(self) -> None:
        private_alias = "内部 canonical 海马体预热"
        report = cognitive_observatory.cognitive_observatory_readout(
            query_pattern_routes=[
                {
                    "query_aliases": [private_alias, "E:\\private\\query-pattern\\source.jsonl"],
                    "source_generation_digest": "gen-alpha-v2",
                    "thread_key_hash": "thread_alpha_hash",
                    "source_refs": [
                        {
                            "source_id": "clean:qp:m7",
                            "thread_key": "session:test-old",
                            "message_id": "m7",
                            "line": 14,
                            "path": "E:\\private\\query-pattern\\source.jsonl",
                        }
                    ],
                    "created_unix": 1_800_000_000,
                    "ttl_seconds": 600,
                    "confidence": 0.92,
                },
                {
                    "query_aliases": ["stale canonical 海马体预热"],
                    "source_generation_digest": "gen-alpha-v1",
                    "thread_key_hash": "thread_alpha_hash",
                    "source_refs": [{"thread_key": "session:test-old", "message_id": "msg-old"}],
                    "state": "stale",
                    "confidence": 0.92,
                },
                {
                    "query_aliases": ["blocked canonical 海马体预热"],
                    "source_generation_digest": "gen-alpha-v2",
                    "thread_key_hash": "thread_alpha_hash",
                    "source_refs": [{"thread_key": "session:test-old", "message_id": "msg-blocked"}],
                    "privacy_blocked": True,
                    "confidence": 0.92,
                },
            ],
            now_unix=1_800_000_120,
        )
        query_routes = report["query_pattern_routes"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertIn("query_pattern_routes", report["surfaces"])
        self.assertEqual(query_routes["kind"], "aippocampus_query_pattern_routes_report")
        self.assertEqual(query_routes["metrics"]["route_count"], 3)
        self.assertEqual(query_routes["metrics"]["active_route_count"], 1)
        self.assertEqual(query_routes["metrics"]["stale_suppressed_count"], 1)
        self.assertEqual(query_routes["metrics"]["privacy_suppressed_count"], 1)
        self.assertEqual(report["metrics"]["query_pattern_active_route_count"], 1)
        self.assertTrue(query_routes["contract"]["query_aliases_omitted"])
        self.assertIn("query_pattern_route_is_source_truth", query_routes["cannot_claim"])
        self.assertNotIn(private_alias, encoded)
        self.assertNotIn("stale canonical", encoded)
        self.assertNotIn("blocked canonical", encoded)
        self.assertNotIn("E:\\", encoded)
        self.assertNotIn("source.jsonl", encoded)

    def test_observatory_static_html_is_public_safe_and_read_only(self) -> None:
        report = cognitive_observatory.fixture_cognitive_observatory_readout()
        html = cognitive_observatory.render_html(report)

        self.assertIn("<!doctype html>", html.casefold())
        self.assertIn("Cognitive Observatory", html)
        self.assertIn("route_readiness", html)
        self.assertIn("navigation_only", html)
        self.assertIn("not a control plane", html)
        self.assertIn("source reopen", html.casefold())
        self.assertNotIn("<script", html.casefold())
        self.assertNotIn("this field must never be serialized", html)
        self.assertNotIn("private\\thread", html)
        self.assertNotIn(str(REPO_ROOT), html)

    def test_observatory_keeps_pruning_as_activation_eligibility_not_truth(self) -> None:
        report = cognitive_observatory.fixture_cognitive_observatory_readout()
        authority = report["activation_authority"]

        self.assertTrue(authority["contract"]["pruning_changes_activation_eligibility_only"])
        self.assertTrue(
            report["contract"]["activation_pruning_changes_activation_eligibility_only"]
        )
        self.assertEqual(
            authority["metrics"]["activation_truth_status_mutation_attempt_count"],
            0,
        )
        self.assertEqual(
            authority["metrics"]["activation_clean_source_mutation_attempt_count"],
            0,
        )

    def test_observatory_control_authority_audit_blocks_control_attempts(self) -> None:
        report = cognitive_observatory.cognitive_observatory_readout(
            activation_surfaces=[
                {
                    "surface_id": "attempted-activation",
                    "surface_kind": "ambient_card",
                    "freshness": "current",
                    "source_refs": [{"source_id": "clean:control", "message_id": "m-control"}],
                    "requested_control_action": "activate_foreground",
                    "owner_surface_mutation": True,
                    "foreground_hook_mutation": True,
                    "clean_source_mutation": True,
                    "truth_status_changed": True,
                    "raw_source_text": "PRIVATE_OBSERVATORY_CONTROL_SENTINEL",
                }
            ]
        )
        audit = report["control_authority_audit"]

        self.assertEqual(audit["kind"], "aippocampus_observatory_control_authority_audit")
        self.assertEqual(audit["mode"], "deterministic_public_safe")
        self.assertEqual(audit["authority"], "diagnostic_only")
        self.assertEqual(audit["decision"], "blocked_control_attempts_present")
        self.assertFalse(audit["mutation_allowed"]["clean_source"])
        self.assertFalse(audit["mutation_allowed"]["owner_surfaces"])
        self.assertFalse(audit["mutation_allowed"]["foreground_hook"])
        self.assertEqual(audit["metrics"]["control_action_attempt_count"], 1)
        self.assertEqual(audit["metrics"]["blocked_control_action_count"], 1)
        self.assertEqual(audit["metrics"]["owner_surface_mutation_attempt_count"], 1)
        self.assertEqual(audit["metrics"]["foreground_hook_mutation_attempt_count"], 1)
        self.assertEqual(audit["metrics"]["activation_truth_status_mutation_attempt_count"], 1)
        self.assertEqual(audit["issue_readouts"]["github_576"]["control_authority"], "diagnostic_only_not_control_plane")
        self.assertFalse(audit["issue_readouts"]["github_576"]["closeout_eligible"])
        self.assertIn("observatory_control_plane", audit["cannot_claim"])

        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("PRIVATE_OBSERVATORY_CONTROL_SENTINEL", encoded)

    def test_cli_facade_exposes_observatory_fixture_json(self) -> None:
        result = facade.run_command(["observatory", "--fixture", "--json"], capture_output=True)

        self.assertTrue(result.ok, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["kind"], "aippocampus_cognitive_observatory_readout")
        self.assertTrue(payload["contract"]["read_only_report"])
        self.assertTrue(payload["route_readiness"]["navigation_only"])

    def test_cli_facade_exposes_observatory_fixture_html(self) -> None:
        result = facade.run_command(["observatory", "--fixture", "--html"], capture_output=True)

        self.assertTrue(result.ok, result.stderr)
        self.assertIn("<!doctype html>", result.stdout.casefold())
        self.assertIn("Cognitive Observatory", result.stdout)
        self.assertIn("navigation_only", result.stdout)
        self.assertNotIn("<script", result.stdout.casefold())

    def test_cli_facade_exposes_query_pattern_routes_jsonl_report(self) -> None:
        routes_path = REPO_ROOT / ".tmp" / "test-query-pattern-routes-observatory.jsonl"
        try:
            routes_path.parent.mkdir(exist_ok=True)
            routes_path.write_text(
                json.dumps(
                    {
                        "query_aliases": ["内部 canonical 海马体预热"],
                        "source_generation_digest": "gen-alpha-v2",
                        "thread_key_hash": "thread_alpha_hash",
                        "source_refs": [{"thread_key": "session:test-old", "message_id": "msg-a"}],
                        "created_unix": 1_800_000_000,
                        "ttl_seconds": 600,
                        "confidence": 0.92,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = facade.run_command(
                ["observatory", "--query-pattern-routes", str(routes_path), "--json"],
                capture_output=True,
            )
        finally:
            try:
                routes_path.unlink()
            except FileNotFoundError:
                pass

        self.assertTrue(result.ok, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("query_pattern_routes", payload["surfaces"])
        self.assertEqual(payload["query_pattern_routes"]["metrics"]["active_route_count"], 1)
        self.assertNotIn("内部 canonical", result.stdout)


if __name__ == "__main__":
    unittest.main()
