from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import dream_live_shadow_ab as shadow  # noqa: E402


class DreamLiveShadowABTests(unittest.TestCase):
    def test_recall_reminder_classifier_is_strict_about_temporal_noise(self) -> None:
        positives = [
            "你忘了我们之前说过要先回忆旧线程。",
            "回忆一下上次那个 clean source 边界再继续。",
            "As I said before, you forgot the old constraint.",
            "还记得我们之前聊过的 dream hypothesis gate 吗？",
        ]
        negatives = [
            "before calling render, run the tests",
            "保留之前的代码风格，但这里不用查旧对话。",
            "previous commit changed this function name",
            "先把上一段 diff 格式整理一下。",
        ]

        self.assertTrue(all(shadow.classify_recall_reminder(text)["is_reminder"] for text in positives))
        self.assertFalse(any(shadow.classify_recall_reminder(text)["is_reminder"] for text in negatives))

    def test_shadow_event_output_is_hash_only_and_records_both_arms(self) -> None:
        baseline_rows: list[dict[str, object]] = []
        dream_rows = [
            {
                "kind": "aippocampus_working_memory",
                "status": "active",
                "route": "use_with_source",
                "candidate_type": "dream_hypothesis",
                "candidate_key": "wm_dream_continuity",
                "title": "Continuity source-ref bridge",
                "summary": "Use only as a route hint.",
                "trigger_terms": ["continuity"],
                "source_finding_ids": ["dreamfinding_continuity"],
                "confidence": 0.7,
                "project_label": "AIppocampus",
                "review_state": "agent_adjudicated",
                "sensitive_use_gate": {"state": "allowed"},
                "foreground_use": {"strong_claim_requires_source_reopen": True},
            }
        ]

        event = shadow.build_shadow_prompt_event(
            prompt="continuity 这条线下一步怎么收？",
            session_id="session-secret",
            turn_id="turn-secret",
            baseline_rows=baseline_rows,
            dream_rows=dream_rows,
            project_label="AIppocampus",
            salt="unit-test",
        )
        encoded = json.dumps(event, ensure_ascii=False)

        self.assertEqual(event["kind"], "aippocampus_dream_shadow_ab_event")
        self.assertTrue(event["eligible_exposure"])
        self.assertEqual(event["baseline"]["match_count"], 0)
        self.assertEqual(event["dream"]["match_count"], 1)
        self.assertIn(event["assigned_arm"], {"control", "dream"})
        self.assertNotIn("continuity 这条线", encoded)
        self.assertNotIn("session-secret", encoded)
        self.assertNotIn("turn-secret", encoded)

    def test_outcome_attribution_uses_nearest_prior_eligible_exposure_once(self) -> None:
        rows = [
            shadow.test_event(
                index=0,
                arm="control",
                eligible=True,
                reminder=False,
                thread="thread-a",
            ),
            shadow.test_event(
                index=1,
                arm="dream",
                eligible=True,
                reminder=False,
                thread="thread-a",
            ),
            shadow.test_event(
                index=2,
                arm="control",
                eligible=False,
                reminder=True,
                thread="thread-a",
            ),
            shadow.test_event(
                index=0,
                arm="dream",
                eligible=True,
                reminder=False,
                thread="thread-b",
            ),
            shadow.test_event(
                index=1,
                arm="control",
                eligible=False,
                reminder=False,
                thread="thread-b",
            ),
        ]

        metrics = shadow.analyze_shadow_events(rows, window_user_turns=3)

        self.assertEqual(metrics["arms"]["control"]["eligible_exposures"], 1)
        self.assertEqual(metrics["arms"]["control"]["reminder_outcomes"], 0)
        self.assertEqual(metrics["arms"]["dream"]["eligible_exposures"], 2)
        self.assertEqual(metrics["arms"]["dream"]["reminder_outcomes"], 1)
        self.assertEqual(metrics["attribution"]["attributed_reminder_count"], 1)
        self.assertEqual(metrics["attribution"]["unattributed_reminder_count"], 0)

    def test_append_and_analyze_event_log_keeps_report_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shadow.jsonl"
            shadow.append_event(path, shadow.test_event(index=0, arm="control", eligible=True))
            shadow.append_event(path, shadow.test_event(index=1, arm="control", eligible=False, reminder=True))

            payload = shadow.run_shadow_ab_analysis(event_log=path, window_user_turns=2)
            encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["kind"], "aippocampus_dream_live_shadow_ab_analysis")
        self.assertEqual(payload["metrics"]["attribution"]["attributed_reminder_count"], 1)
        self.assertFalse(payload["private_text_emitted"])
        self.assertNotIn("prompt", encoded)
        self.assertNotIn("thread-a", encoded)


if __name__ == "__main__":
    unittest.main()
