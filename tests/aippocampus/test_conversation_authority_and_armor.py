from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import authority  # noqa: E402
from aippocampus_runtime.recall.foreground_armor import (  # noqa: E402
    compact_surface_armor_report,
    foreground_armor_budget,
)


class ConversationAuthorityAndArmorTests(unittest.TestCase):
    def test_working_orientation_is_allowed_without_source_truth(self) -> None:
        contract = authority.conversation_authority_contract(
            {
                "support_level": "scent",
                "authority_level": "navigation_only",
                "source_reopen_required": False,
            }
        )

        self.assertEqual(contract["conversation_authority_level"], "working_orientation")
        self.assertEqual(contract["action_grammar"], "direction_only")
        self.assertTrue(contract["working_orientation_allowed"])
        self.assertFalse(contract["fact_claim_allowed"])

    def test_high_risk_conversation_surface_requires_source_reachable(self) -> None:
        contract = authority.conversation_authority_contract(
            {
                "support_level": "scent",
                "risk_flags": ["code_change", "exact_quote"],
            }
        )

        self.assertEqual(contract["conversation_authority_level"], "source_reachable")
        self.assertEqual(contract["action_grammar"], "reopenable_route")
        self.assertTrue(contract["source_reopen_required_for_claims"])

    def test_compact_armor_budget_rewards_guidance_not_cannot_claim_stack(self) -> None:
        budget = foreground_armor_budget("compact")
        self.assertFalse(budget["cannot_claim_visible"])

        useful = compact_surface_armor_report(
            {
                "situation": "Fresh-thread reentry for recall quality work.",
                "load_bearing_unknown": "Need to reopen the current issue only before closeout.",
                "next_action": "Run focused recall tests.",
            },
            surface="agent_orient",
        )
        armored = compact_surface_armor_report(
            {
                "claim_permission": "no_claim_before_reopen",
                "cannot_claim": ["source_truth", "currentness", "exact_quote"],
                "source_reopen_required_before_claim": True,
                "must_reopen": True,
            },
            surface="agent_recall",
        )

        self.assertTrue(useful["ok"], useful)
        self.assertFalse(armored["ok"], armored)
        self.assertEqual(armored["red_lines"]["cannot_claim_visible_in_compact"], 1)
        self.assertEqual(armored["red_lines"]["guidance_signal_deficit"], 1)


if __name__ == "__main__":
    unittest.main()
