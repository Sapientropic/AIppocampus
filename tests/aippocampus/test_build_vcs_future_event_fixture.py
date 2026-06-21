from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"

from benchmarks.aippocampus.builders import build_vcs_future_event_fixture as builder

recall = import_benchmark_module("benchmark_vcs_future_event_recall")

class VcsFutureEventFixtureBuilderTests(unittest.TestCase):
    def test_builds_grouped_fixture_from_nested_and_flat_rows(self) -> None:
        rows = [
            {
                "project_id": "repo-a",
                "project_label": "Repo A",
                "past_source": {
                    "source_id": "review-1",
                    "kind": "pull_request_review",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "text": "Reject the cache daemon until multi-process support exists.",
                },
                "future_event": {
                    "event_id": "pr-9-merged",
                    "family": "reopen_condition",
                    "hard_event_kind": "pull_request_merged",
                    "timestamp": "2026-03-01T00:00:00Z",
                    "flag_worthy": True,
                    "text": "Merged multi-process cache daemon.",
                    "required_past_source_ids": ["review-1"],
                    "expected_signal": "Reopen the old cache-daemon route.",
                },
                "candidate_discovery": {
                    "source_surfaces": ["title", "body"],
                    "query_terms": ["revert", "rollback"],
                    "manual_decision": "included",
                    "manual_reason_code": "gold_future_event",
                    "sampled_miss": False,
                },
            },
            {
                "project_id": "repo-a",
                "past_source_id": "review-2",
                "past_kind": "satd_comment",
                "past_timestamp": "2026-01-02T00:00:00Z",
                "past_text": "TODO keep debounce_epoch until watcher batching is fixed.",
                "behavior_backed": True,
                "tool_name": "pytest",
                "event_id": "commit-10-reverted",
                "family": "workaround_rationale",
                "hard_event_kind": "commit_reverted",
                "event_timestamp": "2026-03-02T00:00:00Z",
                "flag_worthy": "true",
                "event_text": "Reverted removal of debounce_epoch after watcher batching regressed.",
                "required_past_source_ids": "review-2",
                "candidate_discovery": {
                    "source_surface": "comment",
                    "query_terms": ["workaround", "patch"],
                    "manual_decision": "included",
                    "manual_reason": "raw reviewer wording must not be emitted",
                    "manual_reason_code": "behavior_backed_route",
                    "sampled_miss": False,
                },
            },
            {
                "project_id": "repo-a",
                "past_source_id": "review-2",
                "past_kind": "satd_comment",
                "past_timestamp": "2026-01-02T00:00:00Z",
                "past_text": "TODO keep debounce_epoch until watcher batching is fixed.",
                "event_id": "pr-11-merged",
                "family": "anti_drift_negative",
                "hard_event_kind": "pull_request_merged",
                "event_timestamp": "2026-03-03T00:00:00Z",
                "flag_worthy": False,
                "event_text": "Merged a doc example with a debounce_epoch variable name.",
                "candidate_discovery": {
                    "source_surfaces": ["label"],
                    "query_terms": ["again"],
                    "manual_decision": "excluded",
                    "manual_reason_code": "lexical_near_miss",
                    "sampled_miss": True,
                },
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "links.jsonl"
            output = Path(tmp) / "fixture.jsonl"
            source.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )

            payload = builder.build_fixture(
                input_path=source,
                output_path=output,
                dataset_id="unit_vcs_future_events",
                source_family="unit_public_vcs",
            )
            dataset = recall.load_dataset(output)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["metrics"]["project_count"], 1)
        self.assertEqual(payload["metrics"]["flag_worthy_event_count"], 2)
        bias = payload["candidate_discovery_bias"]
        self.assertTrue(bias["available"])
        self.assertEqual(bias["source_surface_mix"]["title"]["count"], 1)
        self.assertEqual(bias["source_surface_mix"]["body"]["count"], 1)
        self.assertEqual(bias["source_surface_mix"]["comment"]["count"], 1)
        self.assertEqual(bias["query_term_hit_mix_by_family"]["revert"], 1)
        self.assertEqual(bias["query_term_hit_mix_by_family"]["rollback"], 1)
        self.assertEqual(bias["query_term_hit_mix_by_family"]["workaround"], 1)
        self.assertEqual(bias["manual_decision_counts"]["included"], 2)
        self.assertEqual(bias["manual_decision_counts"]["excluded"], 1)
        self.assertEqual(bias["manual_reason_code_counts"]["lexical_near_miss"], 1)
        self.assertEqual(bias["sampled_miss_rate"]["sample_count"], 3)
        self.assertEqual(bias["sampled_miss_rate"]["miss_count"], 1)
        self.assertEqual(bias["synonym_coverage"]["missing_required_families"], ["reland"])
        self.assertNotIn("raw reviewer wording", json.dumps(bias, ensure_ascii=False))
        self.assertEqual(dataset.dataset_id, "unit_vcs_future_events")
        self.assertIn("candidate_discovery_bias", dataset.rows[0])
        self.assertEqual(len(dataset.rows[0]["past_window"]), 2)
        self.assertEqual(len(dataset.events_by_id), 3)
        self.assertIn("pr-11-merged", dataset.non_flag_event_ids)
        review_2 = {
            source["source_id"]: source for source in dataset.rows[0]["past_window"]
        }["review-2"]
        self.assertTrue(review_2["behavior_backed"])
        self.assertEqual(review_2["tool_name"], "pytest")

    def test_non_cc0_output_requires_explicit_local_opt_in(self) -> None:
        rows = [
            {
                "project_id": "repo-a",
                "past_source_id": "review-1",
                "past_text": "Reject route.",
                "event_id": "pr-1-merged",
                "family": "reopen_condition",
                "hard_event_kind": "pull_request_merged",
                "flag_worthy": True,
                "event_text": "Merged route later.",
                "required_past_source_ids": ["review-1"],
            }
        ]

        with self.assertRaisesRegex(ValueError, "non-CC0"):
            builder.build_fixture_rows(rows, license_id="see-source-dataset")

        built = builder.build_fixture_rows(
            rows,
            license_id="see-source-dataset",
            allow_non_cc0_output=True,
        )
        self.assertEqual(built[0]["license"], "see-source-dataset")

    def test_builds_fixture_from_clean_source_behavior_events_and_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean_events = root / "events.jsonl"
            links = root / "links.jsonl"
            output = root / "fixture.jsonl"
            clean_events.write_text(
                "\n".join(
                    json.dumps(row, ensure_ascii=False)
                    for row in [
                        {
                            "event_id": "evt_failed_test",
                            "timestamp": "2026-05-01T00:00:00Z",
                            "hard_event_kind": "tool_call_failed",
                            "event_kind": "tool_call_observed",
                            "tool_name": "functions.shell_command",
                            "command_class": "test",
                            "tool_intent": "test_check",
                            "command_family": "python_pytest",
                            "test_target_class": "focused_test_path",
                            "failure_family": "assertion_failure",
                            "path_categories": ["test", "source"],
                            "path_fingerprints": ["sha256:abc123def4567890"],
                            "generated_file": False,
                            "exit_code": 1,
                            "behavior_backed": True,
                            "source_ref": "codex:session:test#L12",
                            "text": "functions.shell_command failed; command_class=test",
                            "observation_sha256": "abc123",
                            "raw_command": "python tests\\aippocampus\\test_secret.py",
                            "stdout": "SECRET_TOKEN=abc123",
                            "path": "C:\\Users\\Administrator\\secret\\test_secret.py",
                        },
                        {
                            "event_id": "evt_narrative_only",
                            "timestamp": "2026-05-01T00:01:00Z",
                            "hard_event_kind": "assistant_message",
                            "behavior_backed": False,
                            "text": "Assistant said the route was bad.",
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            links.write_text(
                json.dumps(
                    {
                        "project_id": "rollout-unit",
                        "past_event_ids": ["evt_failed_test"],
                        "future_event": {
                            "event_id": "evt_failed_again",
                            "family": "rejected_route",
                            "hard_event_kind": "test_failed",
                            "timestamp": "2026-05-02T00:00:00Z",
                            "flag_worthy": True,
                            "text": "The same route failed tests again.",
                            "expected_signal": "Surface the behavior-backed rejected route.",
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            payload = builder.build_fixture_from_clean_events(
                clean_source_events_path=clean_events,
                links_path=links,
                output_path=output,
                dataset_id="unit_rollout_events",
            )
            dataset = recall.load_dataset(output)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["metrics"]["clean_source_event_count"], 2)
        self.assertFalse(payload["candidate_discovery_bias"]["available"])
        self.assertEqual(dataset.dataset_id, "unit_rollout_events")
        event = dataset.events_by_id["evt_failed_again"]
        self.assertEqual(event["required_past_source_ids"], ["evt_failed_test"])
        source = dataset.rows[0]["past_window"][0]
        self.assertTrue(source["behavior_backed"])
        self.assertEqual(source["command_class"], "test")
        self.assertEqual(source["command_family"], "python_pytest")
        self.assertEqual(source["test_target_class"], "focused_test_path")
        self.assertEqual(source["failure_family"], "assertion_failure")
        self.assertEqual(source["path_categories"], ["test", "source"])
        self.assertEqual(source["path_fingerprints"], ["sha256:abc123def4567890"])
        self.assertEqual(source["generated_file"], False)
        self.assertEqual(source["exit_code"], 1)
        serialized = json.dumps(dataset.rows, ensure_ascii=False)
        self.assertNotIn("raw_command", serialized)
        self.assertNotIn("stdout", serialized)
        self.assertNotIn("SECRET_TOKEN", serialized)
        self.assertNotIn("C:\\Users", serialized)
        self.assertNotIn("test_secret.py", serialized)

if __name__ == "__main__":
    unittest.main()
