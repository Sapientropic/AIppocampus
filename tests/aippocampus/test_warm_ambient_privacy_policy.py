from __future__ import annotations

import unittest

from aippocampus_runtime.warm_ambient import recall as warm


class WarmAmbientPrivacyPolicyTests(unittest.TestCase):
    def test_private_route_preserves_supported_fallback_as_degraded_handle(self) -> None:
        rows = [
            warm.parse_scout_output(
                {
                    "decision": "skip",
                    "confidence": 0.92,
                    "block": True,
                    "privacy_action": "private_route",
                    "privacy_reason_codes": ["ordinary_personal_conversation"],
                    "raw_external_projection_allowed": True,
                    "negative_contexts": ["keep ordinary same-user context private"],
                    "reason": "ordinary same-user relationship source should stay private",
                },
                "privacy_boundary_guard:direct",
            )
        ]
        fallback = [
            {
                "theme": "same-user relationship context",
                "support_level": warm.EVIDENCE,
                "visibility": warm.SOURCE_BACKED_RECALL_CARD,
                "key_line": "Keep the route private until source is reopened.",
                "matched_terms": ["relationship"],
                "source_refs": [
                    {"thread_key": "session:old", "message_id": "msg-1", "line": 4}
                ],
            }
        ]
        source_index = {
            "session:old": {
                "by_id": {"msg-1": {"text": "Keep the route private until source is reopened."}},
                "by_line": {},
            }
        }

        result = warm.merge_scouts(rows, fallback_cards=fallback, source_index=source_index)

        self.assertEqual(result["blocked_by"], [])
        self.assertEqual(result["privacy_actions"], ["private_route"])
        self.assertEqual(result["privacy_reason_codes"], ["ordinary_personal_conversation"])
        self.assertFalse(result["raw_external_projection_allowed"])
        self.assertEqual(len(result["cards"]), 1)
        card = result["cards"][0]
        self.assertEqual(card["support_level"], warm.EVIDENCE)
        self.assertEqual(card["visibility"], warm.ACTIVE_GENTLE_NUDGE)
        self.assertEqual(card["privacy_action"], "private_route")
        self.assertFalse(card["raw_external_projection_allowed"])
        self.assertIn("ordinary_personal_conversation", card["privacy_reason_codes"])

    def test_hard_block_action_suppresses_supported_fallback(self) -> None:
        rows = [
            warm.parse_scout_output(
                {
                    "decision": "skip",
                    "confidence": 0.97,
                    "privacy_action": "hard_block",
                    "privacy_reason_codes": ["secret_like"],
                    "raw_external_projection_allowed": False,
                    "negative_contexts": ["secret-like material removed"],
                    "reason": "credential-like content",
                },
                "privacy_boundary_guard:direct",
            )
        ]
        fallback = [
            {
                "theme": "token-bearing source",
                "support_level": warm.EVIDENCE,
                "visibility": warm.SOURCE_BACKED_RECALL_CARD,
                "key_line": "Never surface secret-like material.",
                "matched_terms": ["token"],
                "source_refs": [
                    {"thread_key": "session:old", "message_id": "msg-2", "line": 8}
                ],
            }
        ]
        source_index = {
            "session:old": {
                "by_id": {"msg-2": {"text": "Never surface secret-like material."}},
                "by_line": {},
            }
        }

        result = warm.merge_scouts(rows, fallback_cards=fallback, source_index=source_index)

        self.assertEqual(result["cards"], [])
        self.assertEqual(result["blocked_by"], ["privacy_boundary_guard:direct"])
        self.assertEqual(result["privacy_actions"], ["hard_block"])
        self.assertEqual(result["privacy_reason_codes"], ["secret_like"])
        self.assertFalse(result["raw_external_projection_allowed"])

    def test_privacy_diagnostics_distinguish_route_handles_from_hard_blocks(self) -> None:
        route_handle = {
            "cards": [{"theme": "same-user route"}],
            "blocked_by": [],
            "privacy_actions": ["private_route"],
            "privacy_reason_codes": ["ordinary_personal_conversation"],
        }
        secret_block = {
            "cards": [],
            "blocked_by": ["privacy_boundary_guard:direct"],
            "privacy_actions": ["hard_block"],
            "privacy_reason_codes": ["secret_like"],
        }
        external_block = {
            "cards": [],
            "blocked_by": ["privacy_boundary_guard:direct"],
            "privacy_actions": ["external_projection_block"],
            "privacy_reason_codes": ["external_payload"],
        }
        mixed_route_with_external_payload = {
            "cards": [],
            "blocked_by": ["privacy_boundary_guard:direct"],
            "privacy_actions": ["private_route"],
            "privacy_reason_codes": ["external_payload"],
        }

        self.assertEqual(warm.suppression_reason_buckets(route_handle), ["local_route_handle_only"])
        self.assertEqual(
            warm.suppression_reason_buckets(secret_block),
            ["secret_or_property_risk_blocked", "no_supported_cards"],
        )
        self.assertEqual(
            warm.suppression_reason_buckets(external_block),
            ["external_payload_blocked", "no_supported_cards"],
        )
        self.assertEqual(
            warm.suppression_reason_buckets(mixed_route_with_external_payload),
            ["external_payload_blocked", "no_supported_cards"],
        )

    def test_purpose_check_keeps_cross_domain_source_private_until_reopened(self) -> None:
        rows = [
            warm.parse_scout_output(
                {
                    "decision": "skip",
                    "confidence": 0.81,
                    "block": True,
                    "privacy_action": "purpose_check",
                    "privacy_reason_code": "cross-domain sensitive use",
                    "reason": "relationship source may need explicit purpose before reuse",
                },
                "privacy_boundary_guard:direct",
            )
        ]
        fallback = [
            {
                "theme": "cross-domain relationship echo",
                "support_level": warm.EVIDENCE,
                "visibility": warm.DEEP_ARCHIVAL_RECALL,
                "key_line": "Ask for purpose before reusing this source in another domain.",
                "source_refs": [
                    {"thread_key": "session:old", "message_id": "msg-3", "line": 12}
                ],
            }
        ]
        source_index = {
            "session:old": {
                "by_id": {
                    "msg-3": {
                        "text": "Ask for purpose before reusing this source in another domain."
                    }
                },
                "by_line": {},
            }
        }

        result = warm.merge_scouts(rows, fallback_cards=fallback, source_index=source_index)

        self.assertEqual(result["blocked_by"], [])
        self.assertEqual(result["privacy_actions"], ["purpose_check"])
        self.assertEqual(result["privacy_reason_codes"], ["cross_domain_sensitive_use"])
        card = result["cards"][0]
        self.assertEqual(card["privacy_action"], "purpose_check")
        self.assertEqual(card["visibility"], warm.ACTIVE_GENTLE_NUDGE)
        self.assertIn("reopen clean source", card["suggested_use"])

if __name__ == "__main__":
    unittest.main()
