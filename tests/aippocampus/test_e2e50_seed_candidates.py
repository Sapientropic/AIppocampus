from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke"
if str(TOOLS_SMOKE) not in sys.path:
    sys.path.insert(0, str(TOOLS_SMOKE))

import smoke_e2e50_seed_candidates as scanner  # noqa: E402


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


class E2E50SeedCandidateScannerTests(unittest.TestCase):
    def test_scanner_selects_long_compacted_thread_without_leaking_source_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "registry" / "threads.json"
            clean_dir = root / "clean-source" / "thread-a"
            messages_path = clean_dir / "messages.jsonl"
            events_path = clean_dir / "events.jsonl"

            messages = [
                {
                    "message_id": "msg-001-private",
                    "turn_id": "turn-001-private",
                    "turn_index": 1,
                    "role": "user",
                    "source_line": 10,
                    "text": (
                        "Do not use the generated fallback route again; "
                        "the previous attempt failed tests."
                    ),
                },
                *[
                    {
                        "message_id": f"msg-{index:03d}-private",
                        "turn_id": f"turn-{index:03d}-private",
                        "turn_index": index,
                        "role": "user" if index % 2 else "assistant",
                        "source_line": 10 + index,
                        "text": f"Ordinary topic drift turn {index} with unrelated implementation work.",
                    }
                    for index in range(2, 59)
                ],
            ]
            events = [
                {
                    "event_id": "evt-failed-private",
                    "turn_index": 2,
                    "hard_event_kind": "tool_call_failed",
                    "event_kind": "tool_call_observed",
                    "command_class": "test",
                    "failure_family": "assertion_failure",
                    "status": "failed",
                    "behavior_backed": True,
                    "source_ref": "thread:private#L12",
                    "raw_command": "python secret_test.py",
                },
                {"event_id": "evt-precompact-private", "hook_stage": "PreCompact"},
                {"event_id": "evt-postcompact-private", "hook_stage": "PostCompact"},
            ]
            write_jsonl(messages_path, messages)
            write_jsonl(events_path, events)
            registry_path.parent.mkdir(parents=True)
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "threads": [
                            {
                                "thread_key": "session:private-e2e50-thread",
                                "paths": {
                                    "clean_source_messages_jsonl": str(messages_path),
                                    "clean_source_events_jsonl": str(events_path),
                                },
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = scanner.run_seed_scan(
                registry_path=registry_path,
                min_turns=50,
                max_turns=70,
                min_candidates=1,
            )
            encoded = json.dumps(payload, ensure_ascii=False)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "sufficient_candidate_seeds")
        self.assertEqual(payload["candidate_count"], 1)
        candidate = payload["candidates"][0]
        self.assertEqual(candidate["turn_count"], 58)
        self.assertTrue(candidate["compaction_evidence"]["observed"])
        self.assertGreater(candidate["early_window"]["signal_counts"]["binding_constraint"], 0)
        self.assertGreater(candidate["behavior_evidence"]["behavior_event_count"], 0)
        self.assertIn("binding_constraint_survival", candidate["case_family_guesses"])
        self.assertIn("behavior_backed_rejected_route", candidate["case_family_guesses"])
        self.assertNotIn("generated fallback", encoded)
        self.assertNotIn("session:private-e2e50-thread", encoded)
        self.assertNotIn("msg-001-private", encoded)
        self.assertNotIn("secret_test.py", encoded)
        self.assertNotIn(str(root), encoded)

    def test_scanner_reports_insufficient_candidates_without_false_benchmark_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "registry" / "threads.json"
            messages_path = root / "clean-source" / "short" / "messages.jsonl"
            events_path = root / "clean-source" / "short" / "events.jsonl"
            write_jsonl(
                messages_path,
                [
                    {
                        "message_id": "short-msg",
                        "turn_index": 1,
                        "role": "user",
                        "text": "Do not repeat this route.",
                    }
                ],
            )
            write_jsonl(events_path, [])
            registry_path.parent.mkdir(parents=True)
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "threads": [
                            {
                                "thread_key": "session:short",
                                "paths": {
                                    "clean_source_messages_jsonl": str(messages_path),
                                    "clean_source_events_jsonl": str(events_path),
                                },
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = scanner.run_seed_scan(registry_path=registry_path, min_candidates=1)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "insufficient_candidate_seeds")
        self.assertIn("e2e50_behavior_benchmark_result", payload["cannot_claim"])

    def test_annotation_summary_reports_retained_blocker_without_leaking_rows(self) -> None:
        annotation = {
            "kind": "local_private_annotation",
            "review_status": "private local note rollout secret marker",
            "private_text_exported": False,
            "annotations": [
                {
                    "case_index": 1,
                    "thread_hash": "sha256:private-a",
                    "label": "gold_seed_candidate",
                    "reason": "binding_constraint_survival",
                    "gold_seed": True,
                },
                {
                    "case_index": 2,
                    "thread_hash": "sha256:private-b",
                    "label": "calibration_seed",
                    "reason": "timeboxed_quality_iteration_constraint",
                },
                {
                    "case_index": 3,
                    "thread_hash": "sha256:private-c",
                    "label": "negative_control",
                    "reason": "source_visible_browser_report_should_not_be_remembered",
                },
                {
                    "case_index": 4,
                    "thread_hash": "sha256:private-d",
                    "label": "reject_duplicate",
                    "reason": "duplicate_conceptual_thread_not_behavior_gold",
                },
                {
                    "case_index": 5,
                    "thread_hash": "sha256:private-e",
                    "label": "reject",
                    "reason": "subagent_goal_context_noise_and_high_later_remention",
                },
            ],
        }

        summary = scanner.summarize_annotation_pack(
            annotation,
            min_retained_cases=20,
            min_negative_controls=1,
        )
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(summary["status"], "private_annotation_blocked")
        self.assertEqual(summary["reviewed_candidate_count"], 5)
        self.assertEqual(summary["retained_case_count"], 3)
        self.assertEqual(summary["behavior_seed_count"], 2)
        self.assertEqual(summary["annotation_category_counts"]["gold"], 1)
        self.assertEqual(summary["annotation_category_counts"]["calibration"], 1)
        self.assertEqual(summary["annotation_category_counts"]["negative_control"], 1)
        self.assertEqual(summary["annotation_category_counts"]["duplicate"], 1)
        self.assertEqual(summary["annotation_category_counts"]["rejected"], 1)
        self.assertEqual(summary["blocker_status"]["retained_case_shortfall"], 17)
        self.assertEqual(summary["blocker_status"]["negative_control_shortfall"], 0)
        self.assertEqual(summary["review_status"], "local_annotation_summary")
        self.assertIn("subagent_or_goal_context_noise", summary["blocker_class_counts"])
        self.assertNotIn("sha256:private-a", encoded)
        self.assertNotIn("binding_constraint_survival", encoded)
        self.assertNotIn("private local note", encoded)

    def test_annotation_summary_marks_twenty_retained_with_negative_control(self) -> None:
        annotations = [
            {"case_index": index, "label": "gold_seed_candidate", "gold_seed": True}
            for index in range(1, 20)
        ]
        annotations.append({"case_index": 20, "label": "negative_control"})

        summary = scanner.summarize_annotation_pack(
            {"annotations": annotations, "private_text_exported": False},
            min_retained_cases=20,
            min_negative_controls=1,
        )

        self.assertEqual(summary["status"], "private_annotation_retained")
        self.assertEqual(summary["retained_case_count"], 20)
        self.assertEqual(summary["annotation_category_counts"]["negative_control"], 1)
        self.assertEqual(summary["blocker_status"]["retained_case_shortfall"], 0)


if __name__ == "__main__":
    unittest.main()
