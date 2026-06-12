from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall.source_backed_lessons import (  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
