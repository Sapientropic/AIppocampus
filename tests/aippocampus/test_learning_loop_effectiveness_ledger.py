from __future__ import annotations

import json
import unittest

from aippocampus_runtime.learning_loop import effectiveness_ledger as ledger


def source_ref(name: str) -> dict[str, str]:
    return {"source_id": f"source:{name}", "message_id": f"msg:{name}"}

class LearningLoopEffectivenessLedgerTests(unittest.TestCase):
    def test_effectiveness_rows_cover_useful_ignored_stale_and_self_report_only(self) -> None:
        guidance = [
            {"guidance_id": "useful", "source_refs": [source_ref("useful")]},
            {"guidance_id": "ignored", "source_refs": [source_ref("ignored")]},
            {"guidance_id": "stale", "source_refs": [source_ref("stale")]},
            {"guidance_id": "self-report", "source_refs": [source_ref("self")]},
        ]
        rows = ledger.ledger_rows_from_guidance_outcomes(
            guidance,
            [
                {"lesson_id": "useful", "outcome": "prevented_repeat", "source_refs": [source_ref("useful")]},
                {"lesson_id": "ignored", "outcome": "repeated_failure_after_surface", "source_refs": [source_ref("ignored")]},
                {"lesson_id": "stale", "outcome": "stale_superseded", "source_refs": [source_ref("stale")]},
                {"lesson_id": "self-report", "outcome": "prevented_repeat", "self_report_only": True},
            ],
            surface="action_hint",
        )
        summary = ledger.summarize_effectiveness_ledger(rows)
        projected = ledger.apply_effectiveness_to_guidance(guidance, rows)
        encoded = json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False)
        statuses = {row["lesson_id"]: row["effectiveness_status"] for row in rows}

        self.assertEqual(statuses["useful"], "useful_signal")
        self.assertEqual(statuses["ignored"], "ineffective")
        self.assertEqual(statuses["stale"], "archived")
        self.assertEqual(statuses["self-report"], "unproven")
        self.assertEqual(summary["repeat_failure_after_hint_count"], 1)
        self.assertTrue(all(row["navigation_only"] for row in rows))
        self.assertFalse(any(row["supports_factual_claim"] for row in rows))
        self.assertEqual({row["guidance_id"]: row.get("status") for row in projected}["stale"], "archived")
        self.assertNotIn("pytest tests/private", encoded)
        self.assertNotIn("C:/", encoded)

if __name__ == "__main__":
    unittest.main()
