from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall.associative_path_walker import (  # noqa: E402
    walk_associative_paths,
)


class AssociativePathWalkerTests(unittest.TestCase):
    def test_distinctive_unsupported_anchor_does_not_select_generic_route(self) -> None:
        report = walk_associative_paths(
            query="slime mold exploratory recall",
            candidates=[
                {
                    "route_id": "route:generic",
                    "route_terms": ["memory", "recall", "search"],
                    "thread_key": "thread:generic",
                }
            ],
        )

        self.assertEqual(report["decision"], "abstain")
        self.assertEqual(report["candidate_count"], 0)
        self.assertIn("path_abstained_tighten_cue", report["reason_codes"])
        self.assertIn("generic_only_path_evaporated", report["reason_codes"])

    def test_source_backed_bridge_rescues_cross_vocabulary_cue(self) -> None:
        report = walk_associative_paths(
            query="slime mold exploratory recall",
            candidates=[
                {
                    "route_id": "route:apw",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "thread_key": "thread:apw",
                }
            ],
            bridge_rows=[
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["slime mold", "exploratory recall"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [{"thread_key": "thread:apw", "source_id": "src"}],
                    "scope_bucket": "project",
                }
            ],
        )

        self.assertEqual(report["decision"], "route_candidates")
        candidate = report["candidates"][0]
        self.assertIn("path_found_reopenable", candidate["reason_codes"])
        self.assertIn("source_backed_semantic_bridge", candidate["reason_codes"])
        self.assertEqual(candidate["authority_level"], "navigation_only")
        self.assertEqual(candidate["claim_permission"], "no_claim_before_reopen")
        self.assertNotIn("src_apw_private_text", json.dumps(report, ensure_ascii=False))

    def test_generic_query_is_not_overexpanded(self) -> None:
        report = walk_associative_paths(
            query="memory recall search",
            candidates=[{"route_id": "route:any", "route_terms": ["memory"], "thread_key": "t"}],
        )

        self.assertEqual(report["decision"], "abstain")
        self.assertIn("path_low_specificity", report["reason_codes"])

    def test_private_stale_source_free_and_negative_paths_do_not_expand(self) -> None:
        base_candidate = {
            "route_id": "route:apw",
            "candidate_id": "bridge:apw",
            "route_terms": ["associative path walker"],
            "thread_key": "thread:apw",
        }
        private = walk_associative_paths(
            query="slime mold exploratory recall",
            candidates=[base_candidate],
            bridge_rows=[
                {
                    "candidate_id": "bridge:private",
                    "from_terms": ["slime mold"],
                    "to_terms": ["associative path walker"],
                    "source_refs": [{"source_id": "src"}],
                    "scope_bucket": "user_private",
                }
            ],
        )
        negative = walk_associative_paths(
            query="slime mold exploratory recall",
            candidates=[base_candidate],
            bridge_rows=[
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["slime mold"],
                    "to_terms": ["associative path walker"],
                    "source_refs": [{"source_id": "src"}],
                    "scope_bucket": "project",
                }
            ],
            feedback_rows=[{"candidate_id": "bridge:apw", "signal": "wrong_route_drag"}],
        )

        self.assertEqual(private["candidate_count"], 0)
        self.assertIn("path_blocked_private_or_stale", private["reason_codes"])
        self.assertEqual(negative["candidate_count"], 0)
        self.assertIn("negative_feedback_evaporated", negative["reason_codes"])


if __name__ == "__main__":
    unittest.main()
