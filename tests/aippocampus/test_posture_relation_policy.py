from __future__ import annotations

import hashlib
import json
import unittest

from aippocampus_runtime.subconscious import (
    posture_relation_calibration,
    posture_relation_policy,
)


class PostureRelationPolicyTests(unittest.TestCase):
    def test_candidate_producer_counts_sequences_and_counterexamples(self) -> None:
        observations = [
            {"posture_id": "seed_probe", "scope": "project", "source_refs": [{"source_id": "s1"}]},
            {"posture_id": "archivist_boundary", "scope": "project", "source_refs": [{"source_id": "s2"}]},
            {"posture_id": "seed_probe", "scope": "project", "source_refs": [{"source_id": "s3"}]},
            {"posture_id": "archivist_boundary", "scope": "project", "source_refs": [{"source_id": "s4"}]},
        ]

        report = posture_relation_calibration.posture_relation_calibration_candidates(observations)
        candidate = next(
            item
            for item in report["candidates"]
            if item["from_posture_id"] == "seed_probe" and item["to_posture_id"] == "archivist_boundary"
        )

        self.assertEqual(candidate["observed_sequence_count"], 2)
        self.assertEqual(candidate["counterexample_count"], 1)
        self.assertFalse(candidate["foreground_eligible"])
        self.assertFalse(candidate["policy_mutation_allowed"])

    def test_promotion_gate_accepts_project_local_and_rejects_risky_rows(self) -> None:
        accepted = posture_relation_policy.promotion_gate(
            {
                "candidate_id": "c1",
                "relation": "seed_needs_source_boundary",
                "from_posture_id": "seed_probe",
                "to_posture_id": "archivist_boundary",
                "scope": "project",
                "observed_sequence_count": 4,
                "counterexample_count": 0,
                "source_refs": [{"source_id": "s1"}],
                "suggested_lift": 0.2,
            }
        )
        rejected = posture_relation_policy.promotion_gate(
            {
                "candidate_id": "c2",
                "relation": "seed_needs_source_boundary",
                "scope": "public",
                "observed_sequence_count": 2,
                "counterexample_count": 2,
                "source_refs": [{"source_id": "s1"}],
            }
        )

        self.assertTrue(accepted["accepted"])
        self.assertEqual(accepted["lift"], 0.12)
        self.assertFalse(accepted["may_satisfy_glue"])
        self.assertFalse(accepted["may_transfer_fact"])
        self.assertFalse(rejected["accepted"])
        self.assertIn("counterexample_ratio_too_high", rejected["rejection_reasons"])
        self.assertIn("public_default_requires_separate_evidence", rejected["rejection_reasons"])

    def test_policy_id_uses_sha256_fingerprint_for_stable_non_secret_ids(self) -> None:
        candidate = {
            "candidate_id": "candidate-id",
            "relation": "seed_needs_source_boundary",
            "from_posture_id": "seed_probe",
            "to_posture_id": "archivist_boundary",
            "scope": "project",
            "observed_sequence_count": 4,
            "counterexample_count": 0,
            "source_refs": [{"source_id": "s1"}],
        }

        row = posture_relation_policy.promotion_gate(candidate)
        raw = "\n".join(
            json.dumps(part, ensure_ascii=False, sort_keys=True)
            for part in (
                candidate["candidate_id"],
                candidate["relation"],
                candidate["scope"],
            )
        )
        sha1_id = f"posture_policy_{hashlib.sha1(raw.encode('utf-8', errors='replace')).hexdigest()[:18]}"
        sha256_id = f"posture_policy_{hashlib.sha256(raw.encode('utf-8', errors='replace')).hexdigest()[:18]}"

        self.assertEqual(row["policy_id"], sha256_id)
        self.assertNotEqual(row["policy_id"], sha1_id)

if __name__ == "__main__":
    unittest.main()
