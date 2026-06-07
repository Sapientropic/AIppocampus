from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.warm_ambient.query_pattern_enrichment import (  # noqa: E402
    fixture_query_pattern_enrichment_report,
    query_pattern_enrichment_report,
)


class QueryPatternEnrichmentTests(unittest.TestCase):
    def test_report_plans_only_changed_generations_and_reuses_current_cache(self) -> None:
        local_path = "E:" + "\\private\\query-pattern\\source.jsonl"
        source_generations = [
            {
                "thread_key": "thread-alpha",
                "source_generation_digest": "gen-alpha-v2",
                "previous_generation_digest": "gen-alpha-v1",
                "refresh_reason": "registry_import_refresh",
                "changed": True,
                "source_row_count": 12,
                "query_alias_seeds": ["last time alpha", "continue alpha"],
                "source_refs": [{"thread_key": "thread-alpha", "message_id": "msg-a"}],
                "provider_policy": {
                    "external_model_allowed": True,
                    "local_offline_allowed": True,
                },
                "raw_source_text": f"private source text at {local_path}",
            },
            {
                "thread_key": "thread-beta",
                "source_generation_digest": "gen-beta-v1",
                "changed": False,
                "source_row_count": 8,
                "query_alias_seeds": ["continue beta"],
                "source_refs": [{"thread_key": "thread-beta", "message_id": "msg-b"}],
                "provider_policy": {"external_model_allowed": True},
            },
            {
                "thread_key": "thread-gamma",
                "source_generation_digest": "gen-gamma-v1",
                "changed": True,
                "source_row_count": 5,
                "query_alias_seeds": ["sensitive gamma"],
                "source_refs": [{"thread_key": local_path, "message_id": "msg-g"}],
                "provider_policy": {
                    "external_model_allowed": False,
                    "local_offline_allowed": False,
                    "privacy_blocked": True,
                },
            },
            {
                "thread_key": "thread-delta",
                "source_generation_digest": "gen-delta-v1",
                "changed": True,
                "source_row_count": 4,
                "query_alias_seeds": ["offline delta"],
                "source_refs": [{"thread_key": "thread-delta", "message_id": "msg-d"}],
                "provider_policy": {
                    "external_model_allowed": False,
                    "local_offline_allowed": True,
                },
            },
        ]
        existing_routes = [
            {
                "thread_key": "thread-alpha",
                "source_generation_digest": "gen-alpha-v1",
                "route_count": 2,
                "route_ids": ["old-alpha-route"],
            },
            {
                "thread_key": "thread-beta",
                "source_generation_digest": "gen-beta-v1",
                "route_count": 3,
                "route_ids": ["current-beta-route"],
            },
        ]
        consumption = {
            "query_pattern_route_seen_count": 4,
            "foreground_route_hit_from_query_pattern_count": 2,
            "source_reopen_attempt_count": 2,
            "source_reopen_success_count": 1,
            "wasted_query_pattern_count": 1,
            "materialized_query_pattern_route_count": 4,
        }

        report = query_pattern_enrichment_report(
            source_generations,
            existing_query_pattern_routes=existing_routes,
            consumption_metrics=consumption,
        )

        self.assertEqual(report["kind"], "aippocampus_query_pattern_enrichment_report")
        self.assertTrue(report["no_write"])
        self.assertTrue(report["navigation_only"])
        self.assertFalse(report["contract"]["live_deepseek_call_allowed"])
        self.assertFalse(report["contract"]["foreground_hook_consumption_wired"])
        self.assertTrue(report["contract"]["generated_aliases_are_navigation_only"])

        metrics = report["metrics"]
        self.assertEqual(metrics["source_generation_count"], 4)
        self.assertEqual(metrics["query_pattern_job_count"], 2)
        self.assertEqual(metrics["changed_source_rows_analyzed"], 2)
        self.assertEqual(metrics["cache_reuse_count"], 1)
        self.assertEqual(metrics["cache_reuse_rate"], 0.25)
        self.assertEqual(metrics["invalidated_query_pattern_route_count"], 1)
        self.assertEqual(metrics["privacy_blocked_source_row_count"], 1)
        self.assertEqual(metrics["live_deepseek_call_count"], 0)
        self.assertEqual(metrics["foreground_route_hit_from_query_pattern"], 0.5)
        self.assertEqual(metrics["wasted_query_pattern_rate"], 0.25)
        self.assertEqual(metrics["source_reopen_after_query_pattern_rate"], 0.5)

        job_modes = {job["thread_key_hash"]: job["execution_mode"] for job in report["planned_jobs"]}
        alpha_hash = report["source_rows"][0]["thread_key_hash"]
        delta_hash = report["source_rows"][3]["thread_key_hash"]
        self.assertEqual(job_modes[alpha_hash], "deferred_external_model")
        self.assertEqual(job_modes[delta_hash], "local_offline")

        beta = report["source_rows"][1]
        gamma = report["source_rows"][2]
        self.assertEqual(beta["status"], "cache_reused")
        self.assertEqual(gamma["status"], "suppressed")
        self.assertEqual(gamma["suppression_reason"], "privacy_or_provider_blocked")
        self.assertEqual(len(report["invalidated_routes"]), 1)
        self.assertEqual(report["invalidated_routes"][0]["previous_generation_digest"], "gen-alpha-v1")

        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("private source text", encoded)
        self.assertNotIn("query-pattern\\source", encoded)
        self.assertNotIn("E:\\", encoded)
        self.assertNotIn("answer text", encoded)

    def test_existing_work_item_makes_repeated_refresh_idempotent(self) -> None:
        source_generations = [
            {
                "thread_key": "thread-alpha",
                "source_generation_digest": "gen-alpha-v2",
                "changed": True,
                "source_row_count": 12,
                "query_alias_seeds": ["last time alpha"],
                "source_refs": [{"thread_key": "thread-alpha", "message_id": "msg-a"}],
                "provider_policy": {"external_model_allowed": True},
            }
        ]
        first = query_pattern_enrichment_report(source_generations)
        second = query_pattern_enrichment_report(
            source_generations,
            existing_work_items=first["planned_jobs"],
        )

        self.assertEqual(first["metrics"]["query_pattern_job_count"], 1)
        self.assertEqual(second["metrics"]["query_pattern_job_count"], 0)
        self.assertEqual(second["metrics"]["existing_work_item_reuse_count"], 1)
        self.assertEqual(second["source_rows"][0]["status"], "work_item_reused")
        self.assertEqual(
            second["source_rows"][0]["query_pattern_work_fingerprint"],
            first["planned_jobs"][0]["query_pattern_work_fingerprint"],
        )

    def test_unchanged_generation_without_cache_does_not_enqueue_work(self) -> None:
        report = query_pattern_enrichment_report(
            [
                {
                    "thread_key": "thread-unchanged",
                    "source_generation_digest": "gen-unchanged-v1",
                    "changed": False,
                    "source_row_count": 9,
                    "query_alias_seeds": ["continue unchanged"],
                    "source_refs": [{"thread_key": "thread-unchanged", "message_id": "msg-u"}],
                    "provider_policy": {"external_model_allowed": True},
                }
            ]
        )

        self.assertEqual(report["metrics"]["query_pattern_job_count"], 0)
        self.assertEqual(report["metrics"]["changed_source_rows_analyzed"], 0)
        self.assertEqual(report["source_rows"][0]["status"], "unchanged_skipped")
        self.assertEqual(report["source_rows"][0]["suppression_reason"], "source_generation_unchanged")
        self.assertEqual(report["metrics"]["live_deepseek_call_count"], 0)

    def test_fixture_is_public_safe_and_names_cannot_claim_boundaries(self) -> None:
        report = fixture_query_pattern_enrichment_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["kind"], "aippocampus_query_pattern_enrichment_report")
        self.assertGreater(report["metrics"]["query_pattern_job_count"], 0)
        self.assertGreater(report["metrics"]["invalidated_query_pattern_route_count"], 0)
        self.assertIn("query_pattern_enrichment_is_no_write", report["can_claim"])
        self.assertIn("foreground_hook_consumes_query_pattern_routes", report["cannot_claim"])
        self.assertIn("live_latency_savings_are_proven", report["cannot_claim"])
        self.assertFalse(report["privacy_boundary"]["raw_source_text_serialized"])
        self.assertFalse(report["privacy_boundary"]["local_paths_serialized"])
        self.assertNotIn("private\\query-pattern", encoded)


if __name__ == "__main__":
    unittest.main()
