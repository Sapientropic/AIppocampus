from __future__ import annotations

import json
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

import dream_natural_prompt_eval as natural_eval  # noqa: E402


def source_ref(thread_key: str, message_id: str, line: int) -> dict[str, object]:
    return {
        "thread_key": thread_key,
        "message_id": message_id,
        "line": line,
        "project_label": "AIppocampus",
    }


def fixture_rows() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    job_rows = [
        {
            "kind": "aippocampus_subconscious_job_finding",
            "finding_kind": "question_candidate",
            "fingerprint": "sf_q_continuity",
            "title": "Continuity after compaction",
            "question_text": "How can continuity survive compaction?",
            "question_short": "continuity after compaction",
            "summary": "A question about continuity and compaction.",
            "concepts": ["continuity", "compaction", "source refs"],
            "source_refs": [source_ref("session:a", "msg-a", 10)],
            "confidence": 0.88,
        },
        {
            "kind": "aippocampus_subconscious_job_finding",
            "finding_kind": "frontier_marker",
            "fingerprint": "sf_f_boundary",
            "title": "Source refs across thread changes",
            "summary": "A frontier about source refs surviving thread changes.",
            "boundary_reason": "Resume only after source refs survive the boundary.",
            "frontier_type": "blocked",
            "concepts": ["continuity", "source refs", "boundary"],
            "source_refs": [source_ref("session:b", "msg-b", 20)],
            "confidence": 0.84,
        },
    ]
    working_rows = [
        {
            "kind": "aippocampus_working_memory",
            "status": "active",
            "route": "use_with_source",
            "candidate_key": "wm_continuity",
            "candidate_type": "project_memory",
            "title": "Continuity source refs",
            "summary": "Source refs must stay attached during continuity work.",
            "trigger_terms": ["continuity", "source refs"],
            "concepts": ["continuity", "source refs"],
            "source_refs": [source_ref("session:d", "msg-d", 40)],
            "confidence": 0.76,
            "project_label": "AIppocampus",
        }
    ]
    return job_rows, working_rows


class DreamNaturalPromptEvalTests(unittest.TestCase):
    def test_eval_reports_manual_reminder_reduction_and_noise_gates(self) -> None:
        job_rows, working_rows = fixture_rows()

        payload = natural_eval.run_dream_natural_prompt_eval(
            job_rows=job_rows,
            working_memory_rows=working_rows,
            baseline_working_memory_rows=[],
            max_packs=4,
            natural_templates=(
                "{term} 这条线下一步怎么收？",
                "{term} 这里还有什么没接上的边？",
            ),
        )

        self.assertEqual(payload["kind"], "aippocampus_dream_natural_prompt_eval")
        self.assertEqual(payload["claim_level"], "large_sample_natural_prompt_route_eval")
        self.assertGreaterEqual(payload["metrics"]["sample"]["natural_prompt_count"], 2)
        self.assertGreater(payload["metrics"]["manual_reminder"]["reduction_count"], 0)
        self.assertEqual(payload["metrics"]["noise"]["negative_dream_match_count"], 0)
        self.assertEqual(
            payload["metrics"]["strong_claims"]["strong_claim_reopen_rate"],
            1.0,
        )
        self.assertFalse(payload["private_text_emitted"])
        self.assertIn("real_user_behavior_without_live_ab_test", payload["cannot_claim"])

    def test_eval_output_is_sanitized(self) -> None:
        job_rows, working_rows = fixture_rows()

        payload = natural_eval.run_dream_natural_prompt_eval(
            job_rows=job_rows,
            working_memory_rows=working_rows,
            baseline_working_memory_rows=[],
            max_packs=4,
        )
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("message_id", encoded)
        self.assertNotIn("thread_key", encoded)
        self.assertNotIn("session:a", encoded)
        self.assertNotIn("How can continuity survive", encoded)


if __name__ == "__main__":
    unittest.main()
