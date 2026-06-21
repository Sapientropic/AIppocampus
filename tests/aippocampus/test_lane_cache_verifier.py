from __future__ import annotations

import unittest

from aippocampus_runtime.recall import lane_cache_verifier


class LaneCacheVerifierTests(unittest.TestCase):
    def test_valid_cached_lane_is_accepted_as_reopenable_navigation_only(self) -> None:
        proposal = {
            "lane_id": "semantic_expander",
            "candidate_refs": ["route:alpha"],
            "source_fingerprint": "src-a",
            "topic_epoch": "epoch-a",
            "policy_version": "policy-v1",
            "action_scope": "read",
            "expires_unix": 2_000.0,
            "terms": ["semantic", "cache"],
        }
        context = {
            "source_fingerprint": "src-a",
            "topic_epoch": "epoch-a",
            "policy_version": "policy-v1",
            "action_scope": "read",
            "now_unix": 1_000.0,
        }

        verification = lane_cache_verifier.verify_lane_cache_proposal(
            proposal,
            current_context=context,
        )
        token = lane_cache_verifier.route_token_from_accepted_lane_proposal(
            proposal,
            verification,
        )
        report = lane_cache_verifier.build_lane_cache_verifier_report(
            [proposal],
            current_context=context,
        )

        self.assertEqual(verification["decision"], "accept")
        self.assertEqual(verification["action_grammar"], "reopenable_route")
        self.assertEqual(verification["claim_permission"], "no_claim_before_reopen")
        self.assertTrue(verification["cache_output_is_not_evidence"])
        self.assertIsNotNone(token)
        self.assertEqual(token["authority_level"], "navigation_only")
        self.assertTrue(token["source_reopen_required_before_claim"])
        self.assertEqual(report["metrics"]["accepted_cache_count"], 1)
        self.assertEqual(report["metrics"]["accepted_cache_avoided_lane_regeneration_count"], 1)

    def test_stale_blocked_or_dismissed_proposals_are_rejected(self) -> None:
        context = {
            "source_fingerprint": "src-current",
            "topic_epoch": "epoch-a",
            "policy_version": "policy-v1",
            "now_unix": 1_000.0,
        }
        cases = [
            {
                "lane_id": "source_changed",
                "candidate_refs": ["route:a"],
                "source_fingerprint": "src-old",
            },
            {
                "lane_id": "expired",
                "candidate_refs": ["route:b"],
                "source_fingerprint": "src-current",
                "expires_unix": 999.0,
            },
            {
                "lane_id": "dismissed",
                "candidate_refs": ["route:c"],
                "source_fingerprint": "src-current",
                "feedback_state": "wrong_route",
            },
            {
                "lane_id": "privacy",
                "candidate_refs": ["route:d"],
                "source_fingerprint": "src-current",
                "privacy_state": "privacy_blocked",
            },
        ]

        rows = [
            lane_cache_verifier.verify_lane_cache_proposal(case, current_context=context)
            for case in cases
        ]

        self.assertTrue(all(row["decision"] == "reject" for row in rows))
        joined = " ".join(reason for row in rows for reason in row["reason_codes"])
        self.assertIn("source_fingerprint_mismatch", joined)
        self.assertIn("expired_lane_cache_proposal", joined)
        self.assertIn("feedback_wrong_route", joined)
        self.assertIn("privacy_or_boundary_blocked", joined)

    def test_partial_context_mismatch_requests_selective_rerun(self) -> None:
        proposal = {
            "lane_id": "key_line_hunter",
            "candidate_refs": ["route:beta"],
            "source_fingerprint": "src-a",
            "topic_epoch": "epoch-old",
            "policy_version": "policy-v1",
            "action_scope": "read",
        }
        context = {
            "source_fingerprint": "src-a",
            "topic_epoch": "epoch-new",
            "policy_version": "policy-v2",
            "action_scope": "release",
        }

        verification = lane_cache_verifier.verify_lane_cache_proposal(
            proposal,
            current_context=context,
        )

        self.assertEqual(verification["decision"], "rerun")
        self.assertTrue(verification["selective_regeneration_requested"])
        self.assertIn("topic_epoch_mismatch", verification["reason_codes"])
        self.assertIn("policy_version_mismatch", verification["reason_codes"])
        self.assertIn("high_cost_action_scope_changed", verification["reason_codes"])

    def test_report_metrics_surface_false_accepts_without_overclaiming(self) -> None:
        report = lane_cache_verifier.build_lane_cache_verifier_report(
            [
                {
                    "lane_id": "bad_expected",
                    "candidate_refs": ["route:gamma"],
                    "source_fingerprint": "src-a",
                    "expected_decision": "reject",
                }
            ],
            current_context={"source_fingerprint": "src-a", "now_unix": 1_000.0},
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["metrics"]["false_accept_count"], 1)
        self.assertIn("cached_lane_output_as_source_truth", report["cannot_claim"])
        self.assertTrue(report["boundary"]["accepted_proposals_remain_navigation_only"])

    def test_source_fingerprint_policy_and_lifecycle_boundaries_fail_closed(self) -> None:
        proposal = {
            "lane_id": "codebook_route",
            "candidate_refs": ["spc:manifest:entry_0001"],
            "source_fingerprint": "srcfp-old",
            "privacy_partition": "public",
            "policy_version": "public-v1",
            "lifecycle_state": "current",
            "manifest_version": "source-objects-v1",
        }
        context = {
            "source_fingerprint": "srcfp-new",
            "privacy_partition": "private_blocked",
            "policy_version": "public-v2",
            "lifecycle_state": "deleted_no_recall",
            "manifest_version": "source-objects-v2",
            "now_unix": 1_000.0,
        }

        verification = lane_cache_verifier.verify_lane_cache_proposal(
            proposal,
            current_context=context,
        )
        report = lane_cache_verifier.build_lane_cache_verifier_report(
            [proposal],
            current_context=context,
        )

        self.assertEqual(verification["decision"], "reject")
        self.assertTrue(verification["deterministic_hot_path"])
        self.assertEqual(verification["external_model_calls"], 0)
        self.assertIn("source_fingerprint_mismatch", verification["reason_codes"])
        self.assertIn("lifecycle_state_blocked", verification["reason_codes"])
        self.assertIn("privacy_partition_mismatch", verification["reason_codes"])
        self.assertEqual(report["metrics"]["fingerprint_rejected_reuse"], 1)
        self.assertEqual(report["metrics"]["privacy_bypass_count"], 0)
        self.assertEqual(report["metrics"]["masked_source_resurrection_count"], 0)
        self.assertEqual(report["metrics"]["source_backed_claim_without_reopen"], 0)
        self.assertEqual(report["metrics"]["stale_as_current_count"], 0)

if __name__ == "__main__":
    unittest.main()
