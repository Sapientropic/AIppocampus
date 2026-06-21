from __future__ import annotations

import unittest

from aippocampus_runtime.recall.source_backed_lessons import (
    apply_lesson_constraints_to_packet,
    build_source_backed_lesson_fixture_report,
    extract_source_backed_lesson_candidates,
    promote_lesson_candidate,
)


class SourceBackedLessonsTests(unittest.TestCase):
    def test_user_correction_about_bypassed_architecture_becomes_growing_candidate(self) -> None:
        candidates = extract_source_backed_lesson_candidates(
            [
                {
                    "event_type": "agent_failed_route",
                    "source_ref": "source:turn-agent-provider-prompt",
                    "text": "I used a benchmark-local provider prompt for source route labels.",
                },
                {
                    "event_type": "user_correction",
                    "source_ref": "source:turn-user-stop",
                    "text": (
                        "You should have used existing semantic_scope_builder, "
                        "subconscious jobs, and warm ambient design first."
                    ),
                },
                {
                    "event_type": "agent_ack",
                    "source_ref": "source:turn-agent-ack",
                    "text": "I will stop the temporary prompt and inspect the existing route.",
                },
            ]
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["kind"], "source_backed_lesson_candidate")
        self.assertEqual(candidate["status"], "growing")
        self.assertEqual(candidate["claim_permission"], "working_guidance_only_not_fact")
        self.assertIn("benchmark_local_provider_prompt", candidate["failed_route"])
        self.assertIn("active_pull_route_constraint", candidate["promotes_to"])

    def test_single_correction_does_not_ripen_without_confirmation(self) -> None:
        candidate = extract_source_backed_lesson_candidates(
            [
                {
                    "event_type": "user_correction",
                    "source_ref": "source:turn-user-stop",
                    "text": "Use existing semantic_scope_builder before source-side benchmark scaffolding.",
                }
            ]
        )[0]

        promoted = promote_lesson_candidate(candidate)

        self.assertEqual(promoted["status"], "growing")
        self.assertFalse(promoted["foreground_activation_allowed"])

    def test_confirmed_lesson_changes_future_issue_packet_without_becoming_fact(self) -> None:
        candidate = extract_source_backed_lesson_candidates(
            [
                {
                    "event_type": "user_correction",
                    "source_ref": "source:turn-user-stop",
                    "text": "Use existing semantic_scope_builder before source-side benchmark scaffolding.",
                },
                {
                    "event_type": "user_confirmation",
                    "source_ref": "source:turn-user-confirm",
                    "text": "Yes, make that a standing lesson.",
                },
            ]
        )[0]
        promoted = promote_lesson_candidate(candidate, explicit_confirmation=True)
        packet = {"constraints": [], "lead_kinds": ["memory_route"]}

        updated = apply_lesson_constraints_to_packet(packet, [promoted])

        self.assertEqual(promoted["status"], "ripe")
        self.assertTrue(promoted["foreground_activation_allowed"])
        self.assertIn("do_not_repeat_benchmark_local_provider_prompt", updated["constraints"])
        self.assertIn("source_backed_lesson", updated["lead_kinds"])
        self.assertEqual(promoted["claim_permission"], "working_guidance_only_not_fact")

    def test_fixture_report_has_zero_lesson_red_lines(self) -> None:
        report = build_source_backed_lesson_fixture_report()

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["red_lines"]["candidate_only_promoted_as_fact_count"], 0)
        self.assertEqual(report["red_lines"]["single_correction_ripened_without_confirmation_count"], 0)

    def test_structured_learning_findings_create_multiple_candidate_families(self) -> None:
        findings = [
            {
                "kind": "aippocampus_learning_finding",
                "finding_kind": "recurring_failure_finding",
                "failure_family": "assertion_failure",
                "command_family": "python_pytest",
                "candidate_family": "verification_preflight_candidate",
                "status": "open",
                "occurrence_count": 2,
                "source_refs": [{"thread_key": "thread", "message_id": "msg1"}],
                "source_ref_count": 1,
                "scope": "project:AIppocampus",
                "freshness": "current",
            },
            {
                "kind": "aippocampus_learning_finding",
                "finding_kind": "workflow_order_finding",
                "workflow_family": "cheap_preflight_before_broad_test",
                "candidate_family": "workflow_order_candidate",
                "status": "open",
                "occurrence_count": 2,
                "source_refs": [{"thread_key": "thread", "message_id": "msg2"}],
                "source_ref_count": 1,
                "scope": "project:AIppocampus",
                "freshness": "current",
            },
            {
                "kind": "aippocampus_learning_finding",
                "finding_kind": "environment_workaround_finding",
                "candidate_family": "environment_workaround_candidate",
                "status": "open",
                "occurrence_count": 2,
                "source_refs": [{"thread_key": "thread", "message_id": "msg3"}],
                "source_ref_count": 1,
                "scope": "machine:local",
                "freshness": "current",
            },
            {
                "kind": "aippocampus_learning_finding",
                "finding_kind": "context_miss_finding",
                "candidate_family": "context_reopen_candidate",
                "status": "open",
                "occurrence_count": 2,
                "source_refs": [{"thread_key": "thread", "message_id": "msg4"}],
                "source_ref_count": 1,
                "scope": "project:AIppocampus",
                "freshness": "current",
            },
            {
                "kind": "aippocampus_learning_finding",
                "finding_kind": "do_not_repeat_finding",
                "candidate_family": "do_not_repeat_candidate",
                "status": "open",
                "occurrence_count": 2,
                "source_refs": [{"thread_key": "thread", "message_id": "msg5"}],
                "source_ref_count": 1,
                "scope": "project:AIppocampus",
                "freshness": "current",
            },
        ]

        candidates = extract_source_backed_lesson_candidates(findings)
        kinds = {row["candidate_kind"] for row in candidates}
        ripe = promote_lesson_candidate(candidates[0], independent_trail_count=2)
        updated = apply_lesson_constraints_to_packet({"constraints": [], "lead_kinds": []}, [ripe])

        self.assertGreaterEqual(len(kinds), 4)
        self.assertIn("verification_preflight_candidate", kinds)
        self.assertIn("workflow_order_candidate", kinds)
        self.assertIn("environment_workaround_candidate", kinds)
        self.assertIn("context_reopen_candidate", kinds)
        self.assertIn("do_not_repeat_candidate", kinds)
        self.assertEqual(ripe["status"], "ripe")
        self.assertIn("source_backed_lesson", updated["lead_kinds"])
        self.assertTrue(all(candidate["structured_lesson"]["source_reopen_required"] for candidate in candidates))

    def test_thin_stale_or_local_only_candidates_do_not_promote(self) -> None:
        candidates = extract_source_backed_lesson_candidates(
            [
                {
                    "kind": "aippocampus_learning_finding",
                    "finding_kind": "recurring_failure_finding",
                    "candidate_family": "route_constraint_candidate",
                    "status": "stale",
                    "occurrence_count": 1,
                    "source_refs": [{"thread_key": "thread", "message_id": "msg"}],
                    "scope": "local-only",
                    "freshness": "stale",
                }
            ]
        )

        self.assertEqual(candidates[0]["status"], "backstage")
        self.assertFalse(promote_lesson_candidate(candidates[0], independent_trail_count=3)["foreground_activation_allowed"])

if __name__ == "__main__":
    unittest.main()
