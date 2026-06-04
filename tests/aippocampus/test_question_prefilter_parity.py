from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke"
sys.path.insert(0, str(SMOKE))

import smoke_question_prefilter_parity as parity  # noqa: E402


def source_ref(suffix: str) -> dict[str, Any]:
    return {
        "thread_key": f"session:private-{suffix}",
        "message_id": f"msg-private-{suffix}",
        "turn_id": f"turn-private-{suffix}",
        "source_line": int(suffix) * 10,
    }


def question_row(index: int, group: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "aippocampus_subconscious_job_finding",
        "created_at": f"2026-05-0{index}T00:00:00Z",
        "job": "question_extraction",
        "finding_kind": "question_candidate",
        "fingerprint": f"sf_private_question_{index}",
        "title": f"Private {group} title should not be emitted",
        "summary": "Private raw summary should not be emitted.",
        "confidence": 0.88,
        "source_refs": [source_ref(str(index))],
        "question_text": f"How should {group} preserve private source refs?",
        "question_short": f"{group} source refs",
        "intent_orientation": "implementation",
        "what_features": [group, "source refs", "question tracking"],
        "where_context": ["AIppocampus private fixture"],
        "phase_context": "prefilter_parity_fixture",
        "collaboration_context": ["Codex"],
        "concepts": [group, "source refs"],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


class QuestionPrefilterParitySmokeTests(unittest.TestCase):
    def test_smoke_reports_structural_parity_without_private_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs_path = root / "subconscious_jobs.jsonl"
            write_jsonl(
                jobs_path,
                [
                    question_row(1, "context continuity"),
                    question_row(2, "context continuity"),
                    question_row(3, "handoff calibration"),
                ],
            )

            payload = parity.run_question_prefilter_parity_smoke(
                jobs_path=jobs_path,
                min_candidates=2,
            )
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_question_prefilter_parity_smoke")
        self.assertEqual(payload["claim_level"], "selected_registry_structural_parity")
        self.assertGreater(payload["metrics"]["baseline_strong_pair_count"], 0)
        self.assertEqual(payload["parity"]["baseline_strong_pair_coverage"], 1.0)
        self.assertTrue(payload["parity"]["source_ref_join_survived"])
        self.assertTrue(payload["parity"]["source_ref_key_join_survived"])
        self.assertFalse(payload["default_prefilter"]["enabled"])
        self.assertFalse(payload["default_prefilter"]["recommended"])
        self.assertIn("answer_quality", payload["cannot_claim"])
        self.assertNotIn("How should context continuity", rendered)
        self.assertNotIn("Private raw summary", rendered)
        self.assertNotIn("msg-private", rendered)
        self.assertNotIn("session:private", rendered)
        self.assertNotIn(str(root), rendered)

    def test_smoke_surfaces_coverage_gap_as_not_default_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jobs_path = Path(tmp) / "subconscious_jobs.jsonl"
            write_jsonl(
                jobs_path,
                [
                    question_row(1, "context continuity"),
                    question_row(2, "context continuity"),
                ],
            )

            payload = parity.run_question_prefilter_parity_smoke(
                jobs_path=jobs_path,
                max_pairs=0,
                min_candidates=2,
            )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "structural_parity_gap")
        self.assertIn("sidecar_candidate_coverage_gap", payload["warnings"])
        self.assertEqual(payload["parity"]["baseline_strong_pair_coverage"], 0.0)
        self.assertFalse(payload["default_prefilter"]["enabled"])
        self.assertFalse(payload["default_prefilter"]["recommended"])


if __name__ == "__main__":
    unittest.main()
