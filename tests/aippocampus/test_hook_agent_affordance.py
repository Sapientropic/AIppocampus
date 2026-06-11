from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import hook_agent_affordance as affordance  # noqa: E402


class HookAgentAffordanceTests(unittest.TestCase):
    def test_fixture_report_covers_active_pull_path_without_context_delivery(self) -> None:
        report = affordance.build_hook_agent_affordance_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["schema_version"], "hook-agent-affordance-v0")
        self.assertEqual(report["metrics"]["usable_lead_emitted_count"], 2)
        self.assertEqual(report["metrics"]["agent_pull_suggested_count"], 2)
        self.assertEqual(report["metrics"]["agent_pull_follow_through_rate"], 1.0)
        self.assertEqual(report["metrics"]["hook_full_context_delivery_count"], 0)
        self.assertEqual(report["metrics"]["manual_search_fallback_count"], 0)
        self.assertEqual(report["metrics"]["blind_deepen_required_count"], 0)
        self.assertEqual(report["metrics"]["false_activation_count"], 0)
        self.assertEqual(report["metrics"]["read_current_repo_first_count"], 1)

        self.assertEqual(
            by_id["work_task_aippo_available"]["affordance"]["suggested_agent_action"],
            "agent_aippo",
        )
        self.assertEqual(
            by_id["vague_old_route_source_required"]["affordance"]["suggested_agent_action"],
            "agent_deepen",
        )
        self.assertEqual(
            by_id["current_code_question_no_pull"]["affordance"][
                "suggested_agent_action"
            ],
            "read_current_repo_first",
        )

    def test_fixture_report_is_public_safe_and_source_non_authoritative(self) -> None:
        report = affordance.build_hook_agent_affordance_fixture_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertFalse(report["privacy_boundary"]["raw_prompt_text_emitted"])
        self.assertFalse(report["privacy_boundary"]["raw_source_text_emitted"])
        self.assertFalse(report["privacy_boundary"]["local_paths_emitted"])
        self.assertFalse(report["privacy_boundary"]["source_refs_emitted"])
        self.assertEqual(report["privacy_boundary"]["forbidden_payload_marker_count"], 0)
        self.assertNotIn("PRIVATE_PROMPT_SENTINEL", encoded)
        self.assertNotIn("PRIVATE_SOURCE_SENTINEL", encoded)
        self.assertNotIn("C:\\", encoded)
        for case in report["cases"]:
            packet = case["affordance"]
            self.assertTrue(packet["not_enough_for_claim"])
            self.assertEqual(
                packet["privacy_boundary"],
                "no raw source, no local paths, no source refs in hook",
            )


if __name__ == "__main__":
    unittest.main()
