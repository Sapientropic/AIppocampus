from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.question import feedback_policy as feedback  # noqa: E402


class QuestionFeedbackPolicyTests(unittest.TestCase):
    def write_rows(self, path: Path, rows: list[dict]) -> None:
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def event(self, action: str, created_at: str) -> dict:
        return {
            "kind": "aippocampus_ambient_policy_event",
            "created_at": created_at,
            "action": action,
            "target_key": "wm_context_question",
            "target_kind": "question_link",
            "source_finding_ids": ["sf_question_1", "sf_question_2"],
        }

    def test_loads_latest_dismissal_for_source_backed_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ambient_policy.jsonl"
            self.write_rows(
                path,
                [
                    self.event("dismiss", "2026-05-01T00:00:00Z"),
                    self.event("surface", "2026-05-02T00:00:00Z"),
                ],
            )

            rows = feedback.load_question_pair_feedback(path)

        self.assertEqual(len(rows), 1)
        self.assertTrue(
            feedback.pair_feedback_matches(rows[0], ["sf_question_1", "sf_question_2"])
        )

    def test_later_reopen_clears_dismissal_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ambient_policy.jsonl"
            self.write_rows(
                path,
                [
                    self.event("dismiss", "2026-05-01T00:00:00Z"),
                    self.event("reopen", "2026-05-02T00:00:00Z"),
                ],
            )

            rows = feedback.load_question_pair_feedback(path)

        self.assertEqual(rows, ())

    def test_unsourced_dismissal_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ambient_policy.jsonl"
            self.write_rows(
                path,
                [
                    {
                        "kind": "aippocampus_ambient_policy_event",
                        "created_at": "2026-05-01T00:00:00Z",
                        "action": "dismiss",
                        "target_key": "wm_context_question",
                        "target_kind": "question_link",
                    }
                ],
            )

            rows = feedback.load_question_pair_feedback(path)

        self.assertEqual(rows, ())

    def test_non_question_link_dismissal_does_not_create_pair_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ambient_policy.jsonl"
            row = self.event("dismiss", "2026-05-01T00:00:00Z")
            row["target_kind"] = "theme_candidate"
            self.write_rows(path, [row])

            rows = feedback.load_question_pair_feedback(path)

        self.assertEqual(rows, ())


if __name__ == "__main__":
    unittest.main()
