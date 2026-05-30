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

import dream_real_history_eval as dream_eval  # noqa: E402


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
        {
            "kind": "aippocampus_subconscious_job_finding",
            "finding_kind": "question_candidate",
            "fingerprint": "sf_single",
            "title": "Single thread implementation detail",
            "question_text": "How should this CLI flag be named?",
            "concepts": ["cli"],
            "source_refs": [source_ref("session:c", "msg-c", 30)],
            "confidence": 0.9,
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


class DreamRealHistoryEvalTests(unittest.TestCase):
    def test_select_real_history_packs_requires_cross_thread_source_pattern(self) -> None:
        job_rows, working_rows = fixture_rows()

        packs = dream_eval.select_real_history_packs(
            job_rows=job_rows,
            working_memory_rows=working_rows,
            max_packs=3,
        )

        self.assertEqual(len(packs), 1)
        pack = packs[0]
        self.assertEqual(pack["kind"], "aippocampus_dream_input_pack")
        self.assertEqual(pack["status"], "ready_for_dream_worker")
        self.assertEqual(pack["source_ref_audit"]["source_thread_count"], 3)
        self.assertEqual(pack["selection"]["resonance_term"], "continuity")
        self.assertIn("question_candidate", pack["source_seed_kinds"])
        self.assertIn("frontier_marker", pack["source_seed_kinds"])
        self.assertIn("working_memory", pack["source_seed_kinds"])
        self.assertNotIn("cli", pack["themes"])

    def test_small_worker_emits_adjudicated_compensatory_and_amplification_rows(self) -> None:
        job_rows, working_rows = fixture_rows()
        pack = dream_eval.select_real_history_packs(job_rows=job_rows, working_memory_rows=working_rows)[0]

        worker = dream_eval.run_pack_dream_worker(pack)

        self.assertEqual(worker["status"], "candidate_emitted")
        self.assertEqual(
            [finding["dream_function"] for finding in worker["findings"]],
            ["compensatory", "amplification"],
        )
        self.assertEqual(len(worker["adjudicated_findings"]), 2)
        self.assertEqual(
            {finding["review_state"] for finding in worker["adjudicated_findings"]},
            {"agent_adjudicated"},
        )
        self.assertEqual(len(worker["dream_working_memory_rows"]), 2)
        self.assertTrue(
            all(not row["human_review_required"] for row in worker["dream_working_memory_rows"])
        )
        self.assertTrue(
            all(row["candidate_type"] == "dream_hypothesis" for row in worker["dream_working_memory_rows"])
        )

    def test_eval_quantifies_recall_and_reflection_lift_against_plain_rows(self) -> None:
        job_rows, working_rows = fixture_rows()

        payload = dream_eval.run_dream_real_history_eval(
            job_rows=job_rows,
            working_memory_rows=working_rows,
            max_packs=2,
            min_packs=1,
        )

        self.assertEqual(payload["kind"], "aippocampus_dream_real_history_eval")
        self.assertEqual(payload["status"], "lift_observed")
        self.assertEqual(payload["claim_level"], "selected_real_history_structural_eval")
        self.assertEqual(payload["metrics"]["pack_count"], 1)
        self.assertEqual(payload["metrics"]["dream_working_memory_count"], 2)
        self.assertGreater(payload["metrics"]["lift"]["source_thread_coverage_delta"], 0)
        self.assertGreater(payload["metrics"]["lift"]["reflection_ready_delta"], 0)
        self.assertGreaterEqual(payload["metrics"]["augmented"]["prompt_hit_rate"], payload["metrics"]["plain"]["prompt_hit_rate"])
        self.assertIn("private_real_history_dream_quality", payload["cannot_claim"])
        self.assertFalse(payload["private_text_emitted"])
        self.assertEqual(payload["packs"][0]["source_ref_audit"]["source_thread_count"], 3)
        self.assertNotIn("source_threads", payload["packs"][0]["source_ref_audit"])
        self.assertNotIn("question_text", payload["packs"][0])
        self.assertEqual(payload["packs"][0]["themes"], ["continuity"])


if __name__ == "__main__":
    unittest.main()
