from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.learning_loop import (  # noqa: E402
    adapt_behavior_events_to_review_signals,
    build_learning_action_time_packet,
    build_learning_loop_dogfood_fixture_report,
    build_semantic_learning_hypotheses,
    detect_recurring_failure_findings,
    detect_workflow_order_findings,
    extract_learning_activations,
    extract_workflow_candidates,
    project_action_time_guidance,
)


def source_ref(name: str) -> dict[str, object]:
    return {
        "thread_key": "public-fixture-thread",
        "source_id": f"source:{name}",
        "message_id": f"msg:{name}",
        "line": 10,
    }


def behavior_event(
    event_id: str,
    *,
    status: str = "failed",
    command_family: str = "python_pytest",
    target_class: str = "test_suite",
    failure_family: str = "assertion_failure",
    target_fingerprint: str = "target:tests:a",
    path_category_fingerprint: str = "path:test:a",
    sequence_index: int = 1,
    source: str | None = None,
    expected_local_red: bool = False,
) -> dict[str, object]:
    return {
        "kind": "behavior_event",
        "event_id": event_id,
        "status": status,
        "hard_event_kind": "tool_call_failed" if status == "failed" else "tool_call_succeeded",
        "command_family": command_family,
        "command_class": "test" if "test" in command_family or "pytest" in command_family else "check",
        "target_class": target_class,
        "failure_family": failure_family if status == "failed" else "none",
        "target_fingerprint": target_fingerprint,
        "path_category_fingerprint": path_category_fingerprint,
        "workspace_or_environment_profile": "public-ci-windows",
        "scope": "project:AIppocampus",
        "freshness_window": "recent",
        "source_refs": [source_ref(source or event_id)],
        "sequence_index": sequence_index,
        "expected_local_red": expected_local_red,
        "path_fingerprints": [path_category_fingerprint],
        "output": "PUBLIC_FIXTURE_PAYLOAD_MARKER raw stack should not be copied",
        "command": "pytest tests/private_path.py",
    }


class LearningLoopTests(unittest.TestCase):
    def test_behavior_adapter_outputs_review_rows_without_raw_payloads(self) -> None:
        rows = [
            behavior_event("fail_assert"),
            behavior_event("pass_after", status="succeeded", sequence_index=2),
            behavior_event(
                "timeout",
                failure_family="timeout",
                command_family="repo_test_runner",
                target_class="repo_pr_suite",
            ),
            behavior_event(
                "missing_dep",
                failure_family="dependency_missing",
                command_family="python_pytest",
            ),
            behavior_event(
                "no_tests",
                failure_family="no_tests_collected",
                command_family="python_pytest",
            ),
        ]

        signals = adapt_behavior_events_to_review_signals(rows)
        encoded = json.dumps(signals, ensure_ascii=False, sort_keys=True)

        self.assertEqual(len(signals), 5)
        self.assertEqual(signals[0]["kind"], "aippocampus_learning_review_signal")
        self.assertEqual(signals[0]["event_refs"][0]["event_id"], "fail_assert")
        self.assertEqual(signals[0]["command_family"], "python_pytest")
        self.assertEqual(signals[0]["target_class"], "test_suite")
        self.assertEqual(signals[0]["failure_family"], "assertion_failure")
        self.assertTrue(signals[0]["navigation_only"])
        self.assertFalse(signals[0]["foreground_eligible"])
        self.assertIn("grouping_fingerprint", signals[0])
        self.assertIn("success_after_failure", {row["signal_type"] for row in signals})
        self.assertIn("failure:timeout", {row["learning_signal"] for row in signals})
        self.assertIn("failure:dependency_missing", {row["learning_signal"] for row in signals})
        self.assertIn("failure:no_tests_collected", {row["learning_signal"] for row in signals})
        self.assertNotIn("PUBLIC_FIXTURE_PAYLOAD_MARKER", encoded)
        self.assertNotIn("pytest tests/private_path.py", encoded)
        self.assertNotIn("private_path.py", encoded)

    def test_tool_failure_activation_requires_source_refs_and_downweights_expected_red(self) -> None:
        signals = adapt_behavior_events_to_review_signals(
            [
                behavior_event("activation_timeout", failure_family="timeout"),
                {**behavior_event("missing_source"), "source_refs": []},
                behavior_event("expected_red", expected_local_red=True),
            ]
        )

        activations = extract_learning_activations(signals)
        by_event = {row["event_refs"][0]["event_id"]: row for row in activations}

        self.assertIn("activation_timeout", by_event)
        self.assertTrue(by_event["activation_timeout"]["durable_activation"])
        self.assertEqual(by_event["activation_timeout"]["activation_status"], "open")
        self.assertNotIn("missing_source", by_event)
        self.assertFalse(by_event["expected_red"]["durable_activation"])
        self.assertEqual(by_event["expected_red"]["activation_status"], "review_only_expected_red")

    def test_recurring_failure_detector_groups_narrowly_and_retires_resolved_patterns(self) -> None:
        signals = adapt_behavior_events_to_review_signals(
            [
                behavior_event("fail_1", sequence_index=1),
                behavior_event("fail_2", sequence_index=2),
                behavior_event("expected_red", sequence_index=3, expected_local_red=True),
                behavior_event("one_off", target_fingerprint="target:other", sequence_index=4),
                behavior_event("success_1", status="succeeded", sequence_index=5),
                behavior_event("success_2", status="succeeded", sequence_index=6),
            ]
        )

        findings = detect_recurring_failure_findings(signals)
        by_status = {row["status"]: row for row in findings}
        encoded = json.dumps(findings, ensure_ascii=False, sort_keys=True)

        self.assertIn("resolved", by_status)
        self.assertGreaterEqual(by_status["resolved"]["occurrence_count"], 2)
        self.assertEqual(by_status["resolved"]["target_fingerprint"], "target:tests:a")
        self.assertIn("path_category_fingerprint", by_status["resolved"]["signature"])
        self.assertFalse(by_status["resolved"]["foreground_eligible"])
        self.assertNotIn("one_off", encoded)
        self.assertNotIn("expected_red", encoded)

    def test_workflow_order_detector_requires_causal_guard_and_preserves_order(self) -> None:
        rows = [
            behavior_event("broad_failed", command_family="repo_test_runner", target_class="repo_pr_suite", sequence_index=1),
            behavior_event("ruff_fixed", status="succeeded", command_family="python_ruff", target_class="lint", sequence_index=2),
            behavior_event("broad_succeeded", status="succeeded", command_family="repo_test_runner", target_class="repo_pr_suite", sequence_index=3),
            behavior_event("wrong_success", status="succeeded", command_family="repo_test_runner", target_class="repo_pr_suite", sequence_index=4, target_fingerprint="target:wrong"),
            behavior_event("wrong_ruff", status="succeeded", command_family="python_ruff", target_class="lint", sequence_index=5, target_fingerprint="target:wrong"),
            behavior_event("wrong_failed", command_family="repo_test_runner", target_class="repo_pr_suite", sequence_index=6, target_fingerprint="target:wrong"),
        ]
        signals = adapt_behavior_events_to_review_signals(rows)

        findings = detect_workflow_order_findings(signals)
        guidance = project_action_time_guidance(findings, query_terms=["repo", "test", "ruff"])
        encoded = json.dumps(findings, ensure_ascii=False, sort_keys=True)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["finding_kind"], "workflow_order_finding")
        self.assertEqual(findings[0]["workflow_order"], ["repo_test_runner", "python_ruff", "repo_test_runner"])
        self.assertIn("cheap_preflight_before_broad_test", findings[0]["reason_codes"])
        self.assertIn("same_target_window", findings[0]["reason_codes"])
        self.assertNotIn("target:wrong", encoded)
        self.assertEqual(guidance[0]["next_action"], "run_preflight_before_broad_test")
        self.assertTrue(guidance[0]["source_reopen_required_before_claim"])

    def test_workflow_order_detector_covers_environment_and_context_recovery(self) -> None:
        rows = [
            behavior_event(
                "env_failed",
                failure_family="dependency_missing",
                command_family="python_pytest",
                target_fingerprint="target:env",
                path_category_fingerprint="path:env",
                sequence_index=1,
            ),
            behavior_event(
                "env_fixed",
                status="succeeded",
                command_family="environment_workaround",
                target_class="environment_setup",
                target_fingerprint="target:env",
                path_category_fingerprint="path:env",
                sequence_index=2,
            ),
            behavior_event(
                "env_success",
                status="succeeded",
                command_family="python_pytest",
                target_fingerprint="target:env",
                path_category_fingerprint="path:env",
                sequence_index=3,
            ),
            behavior_event(
                "context_failed",
                command_family="python_pytest",
                target_fingerprint="target:context",
                path_category_fingerprint="path:context",
                sequence_index=4,
            ),
            behavior_event(
                "context_reopened",
                status="succeeded",
                command_family="ripgrep",
                target_class="source_search",
                target_fingerprint="target:context",
                path_category_fingerprint="path:context",
                sequence_index=5,
            ),
            behavior_event(
                "context_success",
                status="succeeded",
                command_family="python_pytest",
                target_fingerprint="target:context",
                path_category_fingerprint="path:context",
                sequence_index=6,
            ),
        ]

        findings = detect_workflow_order_findings(adapt_behavior_events_to_review_signals(rows))
        families = {row["workflow_family"] for row in findings}
        candidate_families = {row["candidate_family"] for row in findings}

        self.assertIn("environment_workaround_before_retry", families)
        self.assertIn("context_reopen_before_retry", families)
        self.assertIn("environment_workaround_candidate", candidate_families)
        self.assertIn("context_reopen_candidate", candidate_families)

    def test_action_time_guidance_feeds_active_path_packet_and_suppresses_visible_refs(self) -> None:
        rows = [
            behavior_event("broad_failed", command_family="repo_test_runner", target_class="repo_pr_suite", sequence_index=1),
            behavior_event("ruff_fixed", status="succeeded", command_family="python_ruff", target_class="lint", sequence_index=2),
            behavior_event("broad_succeeded", status="succeeded", command_family="repo_test_runner", target_class="repo_pr_suite", sequence_index=3),
        ]
        findings = detect_workflow_order_findings(adapt_behavior_events_to_review_signals(rows))

        packet = build_learning_action_time_packet(findings, query_terms=["repo", "test"])
        suppressed = build_learning_action_time_packet(
            findings,
            query_terms=["repo", "test"],
            visible_source_refs=[source_ref("broad_failed")],
        )

        self.assertEqual(packet["kind"], "aippocampus_active_path_packet")
        self.assertEqual(packet["learning_guidance"]["guidance_count"], 1)
        self.assertEqual(packet["paths"][0]["origin"], "learning_loop_action_guidance")
        self.assertEqual(packet["paths"][0]["route"], "reopen")
        self.assertTrue(packet["paths"][0]["source_boundary"]["source_reopen_required"])
        self.assertEqual(suppressed["learning_guidance"]["guidance_count"], 0)
        self.assertEqual(suppressed["path_count"], 0)

    def test_workflow_candidates_choose_smallest_package_or_skip(self) -> None:
        findings = [
            {
                "kind": "aippocampus_learning_finding",
                "finding_kind": "workflow_order_finding",
                "workflow_family": "cheap_preflight_before_broad_test",
                "occurrence_count": 3,
                "source_refs": [source_ref("skill")],
                "scope": "project:AIppocampus",
                "confidence": "high",
            },
            {
                "kind": "aippocampus_learning_finding",
                "finding_kind": "workflow_order_finding",
                "workflow_family": "automation_candidate",
                "occurrence_count": 4,
                "source_refs": [source_ref("automation")],
                "scope": "machine:local",
                "confidence": "high",
            },
            {
                "kind": "aippocampus_learning_finding",
                "finding_kind": "semantic_context_miss",
                "occurrence_count": 2,
                "source_refs": [source_ref("subagent")],
                "scope": "project:AIppocampus",
                "confidence": "medium",
            },
            {
                "kind": "aippocampus_learning_finding",
                "finding_kind": "workflow_order_finding",
                "workflow_family": "already_covered",
                "occurrence_count": 4,
                "source_refs": [source_ref("existing")],
                "scope": "project:AIppocampus",
                "confidence": "high",
            },
            {
                "kind": "aippocampus_learning_finding",
                "finding_kind": "workflow_order_finding",
                "workflow_family": "stable_repeated_manual_workflow",
                "occurrence_count": 3,
                "source_refs": [source_ref("narrow_skill")],
                "scope": "project:AIppocampus",
                "confidence": "high",
            },
            {
                "kind": "aippocampus_learning_finding",
                "finding_kind": "workflow_order_finding",
                "workflow_family": "thin",
                "occurrence_count": 1,
                "source_refs": [source_ref("thin")],
                "scope": "project:AIppocampus",
                "confidence": "low",
            },
        ]

        candidates = extract_workflow_candidates(
            findings,
            existing_assets={"skills": ["cheap_preflight_before_broad_test"]},
        )
        forms = {row["recommended_form"] for row in candidates}

        self.assertIn("extend_existing_skill", forms)
        self.assertIn("create_narrow_skill", forms)
        self.assertIn("create_automation", forms)
        self.assertIn("create_subagent", forms)
        self.assertIn("add_checklist", forms)
        self.assertIn("skip", forms)
        self.assertTrue(all(row["auto_create_asset"] is False for row in candidates))
        self.assertTrue(any(row["skip_reason"] == "thin_or_one_off_evidence" for row in candidates))

    def test_semantic_learning_hypotheses_are_candidate_only_and_retire_when_stale(self) -> None:
        hypotheses = build_semantic_learning_hypotheses(
            [
                {
                    "finding_kind": "blind_spot",
                    "source_refs": [source_ref("blind")],
                    "source_thickness": "usable",
                    "freshness": "current",
                    "model_summary": "this smells like the same trap",
                },
                {
                    "finding_kind": "workflow_packaging",
                    "source_refs": [],
                    "source_thickness": "thin",
                    "freshness": "current",
                    "model_summary": "invent a global rule",
                },
                {
                    "finding_kind": "one_sided_route",
                    "source_refs": [source_ref("stale")],
                    "source_thickness": "usable",
                    "freshness": "stale",
                },
            ]
        )
        by_status = {row["status"]: row for row in hypotheses}

        self.assertEqual(by_status["candidate"]["candidate_kind"], "blind_spot_candidate")
        self.assertFalse(by_status["candidate"]["foreground_eligible"])
        self.assertFalse(by_status["candidate"]["model_output_is_evidence"])
        self.assertEqual(by_status["review_only"]["candidate_kind"], "workflow_packaging_candidate")
        self.assertEqual(by_status["retired"]["candidate_kind"], "one_sided_route_candidate")

    def test_dogfood_fixture_report_tracks_effectiveness_without_causality_claim(self) -> None:
        report = build_learning_loop_dogfood_fixture_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], report)
        metrics = report["metrics"]
        self.assertGreaterEqual(metrics["surfaced_count"], 1)
        self.assertGreaterEqual(metrics["success_after_surface_count"], 1)
        self.assertEqual(metrics["repeat_failure_after_surface_count"], 0)
        self.assertGreaterEqual(metrics["no_overpromotion_count"], 2)
        self.assertGreaterEqual(metrics["stale_or_superseded_count"], 1)
        self.assertGreaterEqual(metrics["environment_workaround_count"], 1)
        self.assertGreaterEqual(metrics["context_reopen_count"], 1)
        self.assertGreaterEqual(metrics["one_off_suppressed_count"], 1)
        self.assertEqual(report["truth_boundary"], "effectiveness_is_diagnostic_not_causal_proof")
        self.assertEqual(report["effectiveness_status"], "useful_signal")
        self.assertIn("fixture_only_runtime_capability", report["claim_boundary"])
        self.assertNotIn("PUBLIC_FIXTURE_PAYLOAD_MARKER", encoded)
        self.assertNotIn("source_audit_payload_bytes", encoded)
        self.assertNotIn("tool_transcript_stream", encoded)


if __name__ == "__main__":
    unittest.main()
