from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import source_joined_routing_decision  # noqa: E402


class SourceJoinedRoutingDecisionTests(unittest.TestCase):
    def test_decision_report_closes_consumer_and_default_policy_slices(self) -> None:
        report = source_joined_routing_decision.build_source_joined_routing_decision()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        metrics = report["measured_consumer_metrics"]
        decision = report["default_policy_decision"]
        readouts = report["issue_readouts"]

        self.assertEqual(
            report["kind"],
            source_joined_routing_decision.DECISION_KIND,
        )
        self.assertTrue(report["ok"])
        self.assertEqual(
            report["selected_consumer_path"]["path"],
            "recall_context -> recall_deepen plus foreground packet source reopen",
        )
        self.assertGreaterEqual(metrics["case_count"], 5)
        self.assertEqual(metrics["progressive_source_reopen_follow_through_rate"], 1.0)
        self.assertEqual(metrics["source_ref_rejoin_rate"], 1.0)
        self.assertGreaterEqual(metrics["semantic_bridge_lift_count"], 1)
        self.assertEqual(metrics["wrong_stance_collision_count"], 0)
        self.assertEqual(metrics["wrong_route_drag_from_sentinel_count"], 0)
        self.assertGreaterEqual(metrics["source_join_gate_reject_count"], 1)
        self.assertGreaterEqual(metrics["vectors_disabled_fallback_count"], 1)
        self.assertFalse(metrics["default_vector_prefilter_enabled"])
        self.assertFalse(metrics["local_embedding_adapter_enabled"])

        self.assertEqual(decision["normal_recall"], "text_first_lexical_structural")
        self.assertEqual(decision["vector_prefilter"], "disabled_by_default")
        self.assertIn(
            "missing_source_join_reject_before_ranking",
            decision["fallbacks"],
        )
        self.assertTrue(readouts["github_1370"]["closeout_eligible"])
        self.assertTrue(readouts["github_1372"]["closeout_eligible"])
        self.assertTrue(readouts["github_309"]["closeout_eligible"])
        self.assertEqual(
            readouts["github_309"]["owner_resolution"],
            "decision_closeout_not_feature_promotion",
        )
        self.assertEqual(
            report["latency_and_cost_notes"]["provider_calls"],
            0,
        )
        self.assertFalse(report["source_truth_guardrails"]["raw_source_text_serialized"])
        self.assertFalse(report["source_truth_guardrails"]["absolute_paths_serialized"])
        self.assertIn("default_vector_prefilter_safety", report["cannot_claim"])
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn(str(REPO_ROOT), encoded)

    def test_markdown_report_states_defer_decision_and_boundaries(self) -> None:
        report = source_joined_routing_decision.build_source_joined_routing_decision()
        text = source_joined_routing_decision.render_markdown(report)
        source_joined_routing_decision.assert_public_report_text(text)

        self.assertIn("keep_text_first_source_joined_defaults", text)
        self.assertIn("#1370 can close", text)
        self.assertIn("#1372 can close", text)
        self.assertIn("#309 can close as a decision issue", text)
        self.assertIn("default_vector_prefilter_safety", text)

    def test_public_json_output_rejects_sensitive_route_fields(self) -> None:
        report = source_joined_routing_decision.build_source_joined_routing_decision()
        report["debug_model_route"] = {
            "provider": "fixture",
            "api_key_env": "DEEPSEEK_API_KEY",
        }

        with self.assertRaises(ValueError):
            source_joined_routing_decision.encode_public_json(report)

    def test_public_json_output_rejects_raw_refs_and_local_paths(self) -> None:
        report = source_joined_routing_decision.build_source_joined_routing_decision()
        report["source_refs"] = [
            {
                "source_id": "private-source",
                "message_id": "message",
                "path": r"C:\Users\Name\private.txt",
            }
        ]

        with self.assertRaises(ValueError):
            source_joined_routing_decision.encode_public_json(report)

    def test_default_public_json_excludes_codeql_sensitive_fragments(self) -> None:
        report = source_joined_routing_decision.build_source_joined_routing_decision()
        encoded = source_joined_routing_decision.encode_public_json(report)

        self.assertNotIn("api_key_env", encoded)
        self.assertNotIn("DEEPSEEK_API_KEY", encoded)
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn('"source_refs": [', encoded)
        self.assertNotIn(str(REPO_ROOT), encoded)


if __name__ == "__main__":
    unittest.main()
