from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import compensatory_dream as dream  # noqa: E402
import memory_candidate_router as router  # noqa: E402


class CompensatoryDreamTests(unittest.TestCase):
    def assert_findings_are_audited(self, payload: dict) -> None:
        for finding in payload["findings"]:
            self.assertEqual(finding["finding_kind"], "dream_synthesized")
            self.assertEqual(finding["dream_function"], "compensatory")
            self.assertEqual(finding["support_level"], "candidate")
            self.assertEqual(finding["review_state"], "needs_review")
            self.assertFalse(finding["foreground_eligible"])
            self.assertTrue(finding["source_refs"])
            self.assertEqual(finding["source_ref_audit"]["status"], "structural_thread_scoped")
            self.assertEqual(finding["source_ref_audit"]["clean_source_resolution"], "not_checked_without_registry_index")
            self.assertTrue(finding["bridge_claims"])
            for claim in finding["bridge_claims"]:
                self.assertTrue(claim["source_refs"])
            self.assertNotIn("question_text", finding)
            self.assertNotIn("frontier_type", finding)

    def test_empty_thread_emits_no_dream_pattern(self) -> None:
        thread_key, rows = dream.fixture_rows("empty")

        payload = dream.run_compensatory_dream(thread_key=thread_key, extraction_rows=rows)

        self.assertEqual(payload["status"], "no_source_backed_pattern")
        self.assertEqual(payload["findings"], [])
        self.assertFalse(payload["foreground_eligible"])
        self.assertFalse(payload["trigger_policy"]["foreground_hooks"])
        self.assertEqual(payload["trigger_policy"]["default_frequency"], "lower_than_extraction")

    def test_technical_thread_gets_review_only_approach_bias_candidate(self) -> None:
        thread_key, rows = dream.fixture_rows("technical")

        payload = dream.run_compensatory_dream(thread_key=thread_key, extraction_rows=rows)

        self.assertEqual(payload["status"], "candidate_emitted")
        self.assertEqual(payload["findings"][0]["compensatory_kind"], "approach_bias")
        self.assertIn("verification", payload["findings"][0]["summary"])
        self.assertIn("frontier_marker", payload["findings"][0]["source_extraction_kinds"])
        self.assert_findings_are_audited(payload)

    def test_personal_life_wide_thread_gets_silently_recurring_candidate(self) -> None:
        thread_key, rows = dream.fixture_rows("personal")

        payload = dream.run_compensatory_dream(thread_key=thread_key, extraction_rows=rows)

        self.assertEqual(payload["status"], "candidate_emitted")
        self.assertEqual(payload["findings"][0]["compensatory_kind"], "silently_recurring")
        self.assertIn("dream-synthesized candidate", payload["findings"][0]["summary"])
        self.assertEqual(payload["input"]["source_backed_row_count"], 2)
        self.assert_findings_are_audited(payload)

    def test_unsourced_rows_are_discarded_before_dream_synthesis(self) -> None:
        payload = dream.run_compensatory_dream(
            thread_key="session:bad",
            extraction_rows=[
                {
                    "fingerprint": "sf_unsourced",
                    "finding_kind": "question_candidate",
                    "thread_key": "session:bad",
                    "question_text": "Why does this keep returning?",
                    "scope_labels": ["personal_reflection", "open_question"],
                    "source_refs": [],
                }
            ],
        )

        self.assertEqual(payload["status"], "no_source_backed_pattern")
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["input"]["source_backed_row_count"], 0)

    def test_source_refs_must_belong_to_requested_thread(self) -> None:
        payload = dream.run_compensatory_dream(
            thread_key="session:current",
            extraction_rows=[
                {
                    "fingerprint": "sf_cross_thread",
                    "finding_kind": "frontier_marker",
                    "thread_key": "session:current",
                    "summary": "A blocked runtime edge.",
                    "frontier_type": "blocked",
                    "source_refs": [{"thread_key": "session:other", "message_id": "msg-other"}],
                }
            ],
        )

        self.assertEqual(payload["status"], "no_source_backed_pattern")
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["input"]["source_backed_row_count"], 0)

    def test_source_backed_rows_do_not_force_a_dream_story(self) -> None:
        payload = dream.run_compensatory_dream(
            thread_key="session:ordinary",
            extraction_rows=[
                {
                    "fingerprint": "sf_note",
                    "finding_kind": "concept_note",
                    "thread_key": "session:ordinary",
                    "summary": "The thread mentions a stable implementation detail.",
                    "concepts": ["implementation"],
                    "source_refs": [{"thread_key": "session:ordinary", "message_id": "msg-note"}],
                }
            ],
        )

        self.assertEqual(payload["status"], "no_source_backed_pattern")
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["input"]["source_backed_row_count"], 1)

    def test_existing_dream_rows_are_not_reingested_as_extraction(self) -> None:
        payload = dream.run_compensatory_dream(
            thread_key="session:dream",
            extraction_rows=[
                {
                    "fingerprint": "dream_old",
                    "finding_kind": "dream_synthesized",
                    "thread_key": "session:dream",
                    "summary": "Old dream output should not seed itself.",
                    "source_refs": [{"thread_key": "session:dream", "message_id": "msg-old"}],
                }
            ],
        )

        self.assertEqual(payload["status"], "no_source_backed_pattern")
        self.assertEqual(payload["input"]["source_backed_row_count"], 0)

    def test_report_declares_non_claims_and_review_boundary(self) -> None:
        thread_key, rows = dream.fixture_rows("technical")

        payload = dream.run_compensatory_dream(thread_key=thread_key, extraction_rows=rows)

        self.assertIn("formal_memory_promotion_without_review", payload["cannot_claim"])
        self.assertIn("clean_source_ref_resolution_without_registry_index", payload["cannot_claim"])
        self.assertIn("foreground_hook_eligibility", payload["cannot_claim"])
        self.assertTrue(payload["trigger_policy"]["requires_review_before_recall_or_reflection"])

    def test_generator_input_and_string_fields_remain_source_audited(self) -> None:
        rows = (
            row
            for row in [
                {
                    "fingerprint": "sf_question_string_1",
                    "finding_kind": "question_candidate",
                    "thread_key": "session:string",
                    "question_text": "Why does continuity keep returning?",
                    "scope_labels": "personal_reflection",
                    "concepts": "continuity",
                    "source_ref": "clean-source/messages.jsonl:1",
                },
                {
                    "fingerprint": "sf_question_string_2",
                    "finding_kind": "question_candidate",
                    "thread_key": "session:string",
                    "question_text": "Continuity returns as a different open question.",
                    "scope_labels": ["open_question"],
                    "concepts": ["continuity"],
                    "source_ref": "clean-source/messages.jsonl:2",
                },
            ]
        )

        payload = dream.run_compensatory_dream(thread_key="session:string", extraction_rows=rows)

        self.assertEqual(payload["status"], "candidate_emitted")
        self.assertEqual(payload["input"]["source_backed_row_count"], 2)
        self.assertEqual(payload["input"]["missing_source_row_count"], 0)
        self.assertEqual(payload["findings"][0]["compensatory_kind"], "silently_recurring")
        self.assertEqual(len(payload["findings"][0]["source_refs"]), 2)
        self.assert_findings_are_audited(payload)

    def test_unadjudicated_dream_findings_do_not_project_to_working_memory(self) -> None:
        thread_key, rows = dream.fixture_rows("personal")
        payload = dream.run_compensatory_dream(thread_key=thread_key, extraction_rows=rows)

        working_rows = dream.adjudicated_dream_findings_to_working_memory(payload["findings"])

        self.assertEqual(working_rows, [])

    def test_background_adjudicated_dream_findings_project_without_user_review(self) -> None:
        thread_key, rows = dream.fixture_rows("personal")
        payload = dream.run_compensatory_dream(thread_key=thread_key, extraction_rows=rows)
        adjudicated = {
            **payload["findings"][0],
            "review_state": "agent_adjudicated",
            "adjudication_source": "detached_dream_worker",
            "confidence": 0.74,
            "downstream_use": ["review_queue", "working_memory", "ambient_recall_card", "reflection_space"],
        }

        working_rows = dream.adjudicated_dream_findings_to_working_memory([adjudicated])

        self.assertEqual(len(working_rows), 1)
        row = working_rows[0]
        self.assertEqual(row["kind"], "aippocampus_working_memory")
        self.assertEqual(row["candidate_type"], "dream_hypothesis")
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["route"], router.USE_WITH_SOURCE)
        self.assertEqual(row["truth_boundary"], "adjudicated_dream_hypothesis_not_fact")
        self.assertEqual(row["adjudication_source"], "detached_dream_worker")
        self.assertFalse(row["human_review_required"])
        self.assertTrue(row["source_refs"])
        self.assertIn("reflection_space", row["downstream_use"])
        matches = router.match_working_memory("continuity 和 recurring anxiety 这条线索还在吗？", working_rows)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["candidate_type"], "dream_hypothesis")


if __name__ == "__main__":
    unittest.main()
