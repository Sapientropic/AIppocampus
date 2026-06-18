from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import issue_work_guard  # noqa: E402
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
        self.assertEqual(packet["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(packet["foreground_action"], packet["agent_next_action"])
        self.assertEqual(packet["safe_next_actions"][0], packet["foreground_action"])
        self.assertEqual(packet["foreground_action"]["id"], "agent_recall_issue_context")
        self.assertEqual(packet["foreground_action"]["tool_name"], "agent_recall")
        self.assertIn("benchmark_capability_provenance", packet["lead_kinds"])
        self.assertIn("semantic_scope_builder", packet["existing_owner_ref_ids"])
        self.assertIn("subconscious_jobs", packet["existing_owner_ref_ids"])
        self.assertEqual(packet["owner_refs_confidence"], "high")
        self.assertTrue(all("reason" in item for item in packet["existing_owner_refs"]))
        self.assertIn("check_existing_routes_before_manual_benchmark_scaffold", packet["constraints"])

    def test_skill_docs_issue_prefers_bootstrap_and_docs_owners(self) -> None:
        packet = build_issue_active_pull_packet(
            title="Make SKILL.md a foreground continuity bootstrap",
            body=(
                "The installable skill entrypoint should lead with foreground continuity "
                "cards and public docs, not operator fallback maps."
            ),
        )

        self.assertTrue(packet["should_pull"])
        self.assertEqual(packet["owner_refs_confidence"], "high")
        self.assertIn("skill_entrypoint", packet["existing_owner_ref_ids"])
        self.assertIn("public_docs", packet["existing_owner_ref_ids"])
        self.assertIn("docs_health_guard", packet["existing_owner_ref_ids"])
        self.assertNotIn("attention_router", packet["existing_owner_ref_ids"])
        self.assertNotIn("semantic_scope_builder", packet["existing_owner_ref_ids"])
        self.assertIn("skill_or_docs_surface_owner", packet["lead_kinds"])
        self.assertIn("check_foreground_surface_owner_before_runtime_patch", packet["constraints"])

    def test_cli_foreground_card_issue_prefers_card_contract_owners(self) -> None:
        packet = build_issue_active_pull_packet(
            title="Make doctor spend default JSON a compact decision card",
            body=(
                "The foreground JSON card should lead with safe_next_actions and a "
                "compact claim_boundary instead of cannot_claim noise."
            ),
        )

        self.assertTrue(packet["should_pull"])
        self.assertEqual(packet["owner_refs_confidence"], "high")
        self.assertIn("foreground_cli_facade", packet["existing_owner_ref_ids"])
        self.assertIn("foreground_output_projection", packet["existing_owner_ref_ids"])
        self.assertIn("agent_continuity_cards", packet["existing_owner_ref_ids"])
        self.assertNotIn("attention_router", packet["existing_owner_ref_ids"])
        self.assertIn("foreground_card_contract", packet["lead_kinds"])

    def test_task_orientation_issue_prefers_card_contract_owners(self) -> None:
        packet = build_issue_active_pull_packet(
            title="Build Task Orientation Packets for understanding state",
            body="External source anchors and learning-loop constraints should guide fresh-thread issue starts.",
        )

        self.assertTrue(packet["should_pull"])
        self.assertEqual(packet["owner_refs_confidence"], "high")
        self.assertIn("foreground_cli_facade", packet["existing_owner_ref_ids"])
        self.assertIn("foreground_output_projection", packet["existing_owner_ref_ids"])
        self.assertIn("agent_continuity_cards", packet["existing_owner_ref_ids"])
        self.assertIn("foreground_card_contract", packet["lead_kinds"])

    def test_repeating_mistakes_issue_prefers_learning_loop_owners(self) -> None:
        packet = build_issue_active_pull_packet(
            title="Fix repeating mistakes learning loop",
            body=(
                "Agent feedback, do-not-use-here events, and source-backed lessons should "
                "drive action-time guidance before another generic router patch."
            ),
        )

        self.assertTrue(packet["should_pull"])
        self.assertEqual(packet["owner_refs_confidence"], "high")
        self.assertIn("learning_loop_cli", packet["existing_owner_ref_ids"])
        self.assertIn("feedback_events", packet["existing_owner_ref_ids"])
        self.assertIn("source_backed_lessons", packet["existing_owner_ref_ids"])
        self.assertIn("action_hint_cache", packet["existing_owner_ref_ids"])
        self.assertNotIn("attention_router", packet["existing_owner_ref_ids"])
        self.assertNotIn("semantic_scope_builder", packet["existing_owner_ref_ids"])
        self.assertIn("learning_feedback_owner", packet["lead_kinds"])
        self.assertIn("check_learning_feedback_and_lesson_owner_before_router_patch", packet["constraints"])

    def test_trivial_issue_stays_silent(self) -> None:
        packet = build_issue_active_pull_packet(
            title="Fix typo in README",
            body="One spelling correction.",
        )

        self.assertFalse(packet["should_pull"])
        self.assertEqual(packet["output_mode"], "silence")
        self.assertEqual(packet["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(packet["foreground_action"], packet["agent_next_action"])
        self.assertEqual(packet["safe_next_actions"][0], packet["foreground_action"])
        self.assertEqual(packet["foreground_action"]["id"], "continue_without_recall")
        self.assertIn("no benchmark", packet["reason"])
        self.assertEqual(packet["suggested_agent_action"], "continue_without_recall")
        self.assertIn("continue normally", packet["fallback_action"])

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

    def test_cli_help_is_issue_work_orientation_card(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "work-guard",
                "--help",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Issue-work orientation card:", proc.stdout)
        self.assertIn("pull continuity/source owners before broad manual search", proc.stdout)
        self.assertIn("aippocampus work-guard --title", proc.stdout)

    def test_issue_number_input_fetches_title_body_and_comments(self) -> None:
        with mock.patch(
            "aippocampus_runtime.ops.issue_work_guard.fetch_issue_context",
            return_value={
                "number": 1802,
                "url": "https://github.com/Sapientropic/AIppocampus/issues/1802",
                "title": "Fix LongMemEval source-side cache",
                "body": "Use the existing semantic scope owner.",
                "comments": ["Comment mentions architecture routing."],
            },
        ) as fetch:
            from aippocampus_runtime.cli import facade

            proc = facade.run_command(["work-guard", "1802", "--json"], capture_output=True)

        self.assertEqual(proc.exit_code, 0, proc.stderr)
        fetch.assert_called_once_with("1802")
        self.assertIn('"should_pull": true', proc.stdout)
        self.assertIn('"issue_number": 1802', proc.stdout)
        self.assertIn("comments_included", proc.stdout)

    def test_issue_reference_parser_accepts_number_and_url(self) -> None:
        issue_reference_from_text = issue_work_guard.issue_reference_from_text
        self.assertEqual(issue_reference_from_text("1776"), "1776")
        self.assertEqual(
            issue_reference_from_text("https://github.com/Sapientropic/AIppocampus/issues/1776"),
            "https://github.com/Sapientropic/AIppocampus/issues/1776",
        )


if __name__ == "__main__":
    unittest.main()
