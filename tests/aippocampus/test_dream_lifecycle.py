from __future__ import annotations

import contextlib
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from aippocampus_runtime.dream import frontdoor, lifecycle
from aippocampus_runtime.dream import working_memory as wm


def source_ref(thread_key: str, message_id: str, line: int) -> dict[str, object]:
    return {
        "thread_key": thread_key,
        "message_id": message_id,
        "line": line,
        "project_label": "AIppocampus",
    }


def bridge_claim(refs: list[dict[str, object]]) -> dict[str, object]:
    return {"claim": "This hypothesis has source refs.", "source_refs": refs}


def dream_finding(**overrides: object) -> dict[str, object]:
    refs = [source_ref("session:a", "msg-a", 10), source_ref("session:b", "msg-b", 20)]
    row: dict[str, object] = {
        "finding_kind": "dream_synthesized",
        "dream_function": "amplification",
        "candidate_kind": "cross_thread_resonance",
        "review_state": "needs_review",
        "title": "RAW PRIVATE TITLE SHOULD NOT LEAK",
        "summary": "RAW PRIVATE SUMMARY SHOULD NOT LEAK",
        "confidence": 0.66,
        "source_refs": refs,
        "bridge_claims": [bridge_claim(refs)],
        "worker_validation": {"status": "passed", "failed_checks": []},
        "source_ref_audit": {
            "status": "model_candidate_source_ref_validated",
            "source_ref_count": 2,
            "source_thread_count": 2,
        },
        "truth_boundary": "dream_synthesized_candidate_not_fact",
    }
    row.update(overrides)
    return row


class DreamLifecycleTests(unittest.TestCase):
    def test_parked_source_ref_failure_has_reason_and_status_summary_stays_safe(self) -> None:
        parked = wm.background_adjudicate_dream_finding(
            dream_finding(source_refs=[], bridge_claims=[])
        )
        encoded_parked = json.dumps(parked, ensure_ascii=False)

        self.assertEqual(parked["adjudication_result"]["status"], "parked")
        self.assertEqual(parked["dream_lifecycle"]["state"], "parked_with_reason")
        self.assertIn("source_refs_present", parked["dream_lifecycle"]["reason_code"])
        self.assertIn("source", parked["dream_lifecycle"]["readable_reason"])
        self.assertEqual(
            parked["dream_lifecycle"]["next_review_or_cleanup"]["path"],
            "review_source_refs_or_cleanup_if_unreachable",
        )
        self.assertFalse(parked["dream_lifecycle"]["fact_claim_allowed"])
        self.assertIn("RAW PRIVATE TITLE SHOULD NOT LEAK", encoded_parked)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            findings = root / "dream_findings.jsonl"
            findings.write_text(json.dumps(parked, ensure_ascii=False) + "\n", encoding="utf-8")
            payload = frontdoor.dream_status_payload(
                registry_dir=root,
                findings_jsonl=findings,
                working_memory_jsonl=root / "missing_working_memory.jsonl",
            )

        report = payload["dream_lifecycle_report"]
        encoded_report = json.dumps(report, ensure_ascii=False)

        self.assertEqual(report["counts"]["parked_with_reason"], 1)
        self.assertEqual(report["examples"][0]["state"], "parked_with_reason")
        self.assertIn("source refs", report["examples"][0]["example_safe_summary"])
        self.assertNotIn("RAW PRIVATE TITLE SHOULD NOT LEAK", encoded_report)
        self.assertNotIn("RAW PRIVATE SUMMARY SHOULD NOT LEAK", encoded_report)
        self.assertTrue(report["privacy"]["example_summaries_omit_raw_text"])

    def test_speculative_navigation_only_survivor_reports_without_truth_upgrade(self) -> None:
        speculative = dream_finding()

        record = lifecycle.dream_lifecycle_record(speculative)
        surface = lifecycle.navigation_surface_for_finding(speculative)
        report = lifecycle.dream_lifecycle_report([speculative])
        working_rows = wm.adjudicated_dream_findings_to_working_memory([speculative])

        self.assertEqual(record["state"], "speculative_navigation_hypothesis")
        self.assertEqual(surface["surface_kind"], "dream_navigation_hypothesis")
        self.assertEqual(surface["claim_boundary"], "navigation_only_until_source_adjudicated")
        self.assertFalse(surface["fact_claim_allowed"])
        self.assertFalse(surface["foreground_eligible"])
        self.assertEqual(report["counts"]["speculative_navigation_hypothesis"], 1)
        self.assertEqual(report["examples"][0]["state"], "speculative_navigation_hypothesis")
        self.assertEqual(working_rows, [])

    def test_operator_json_flag_emits_parseable_full_status_json_without_json_flag(self) -> None:
        parked = wm.background_adjudicate_dream_finding(
            dream_finding(source_refs=[], bridge_claims=[])
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            findings = root / "dream_findings.jsonl"
            findings.write_text(json.dumps(parked, ensure_ascii=False) + "\n", encoding="utf-8")

            stdout = StringIO()
            with contextlib.redirect_stdout(stdout):
                code = frontdoor.main(
                    [
                        "dream",
                        "status",
                        "--registry-dir",
                        str(root),
                        "--findings-jsonl",
                        str(findings),
                        "--working-memory-jsonl",
                        str(root / "missing_working_memory.jsonl"),
                        "--operator-json",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["kind"], "aippocampus_dream_status")
        self.assertIn("dream_lifecycle_report", payload)
        self.assertIn("privacy_boundary", payload)
        self.assertIn("write_contract", payload)


if __name__ == "__main__":
    unittest.main()
