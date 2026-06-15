from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops.issue_work_guard import (  # noqa: E402
    build_issue_active_pull_packet,
    build_issue_work_guard_fixture_report,
    render_issue_work_guard_text,
)


class IssueWorkGuardTests(unittest.TestCase):
    def test_benchmark_source_side_issue_requires_active_pull_before_manual_search(self) -> None:
        packet = build_issue_active_pull_packet(
            title="Fix LongMemEval source-side semantic cache benchmark",
            body="Agent must verify whether source-side warming uses existing semantic scope design.",
        )

        self.assertTrue(packet["should_pull"])
        self.assertEqual(packet["output_mode"], "reopenable_route")
        self.assertEqual(packet["suggested_agent_action"], "agent_recall")
        self.assertIn("benchmark_capability_provenance", packet["lead_kinds"])
        self.assertIn("semantic_scope_builder", packet["existing_owner_ref_ids"])
        self.assertIn("subconscious_jobs", packet["existing_owner_ref_ids"])
        self.assertIn("check_existing_routes_before_manual_benchmark_scaffold", packet["constraints"])

    def test_trivial_issue_stays_silent(self) -> None:
        packet = build_issue_active_pull_packet(
            title="Fix typo in README",
            body="One spelling correction.",
        )

        self.assertFalse(packet["should_pull"])
        self.assertEqual(packet["output_mode"], "silence")
        self.assertEqual(packet["suggested_agent_action"], "continue_without_recall")

    def test_fixture_report_covers_ignored_scent_and_trivial_silence(self) -> None:
        report = build_issue_work_guard_fixture_report()

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["metrics"]["active_pull_required_count"], 2)
        self.assertEqual(report["metrics"]["trivial_silence_count"], 1)
        self.assertEqual(report["red_lines"]["broad_manual_search_before_route_count"], 0)

    def test_human_card_renders_pull_and_continue_decisions_without_raw_json(self) -> None:
        pull = build_issue_active_pull_packet(
            title="Fix LongMemEval source-side semantic cache benchmark",
            body="Use existing warm ambient owners.",
        )
        quiet = build_issue_active_pull_packet(title="Fix typo in README")

        pull_text = render_issue_work_guard_text(pull)
        quiet_text = render_issue_work_guard_text(quiet)

        self.assertIn("AIppocampus work guard", pull_text)
        self.assertIn("decision: pull continuity first", pull_text)
        self.assertIn("aippocampus agent recall", pull_text)
        self.assertIn("boundary:", pull_text)
        self.assertFalse(pull_text.strip().startswith("{"))
        self.assertIn("decision: continue", quiet_text)
        self.assertIn("continue without an AIppocampus recall pull", quiet_text)


if __name__ == "__main__":
    unittest.main()
