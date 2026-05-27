from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import memory_candidate_router as router  # noqa: E402


class MemoryCandidateRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.candidates = self.root / "promotion_candidates.jsonl"
        self.jobs = self.root / "subconscious_jobs.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_jsonl(self, path: Path, rows: list[dict]) -> None:
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def base_candidate(self, **overrides) -> dict:
        data = {
            "kind": "aippocampus_promotion_candidate",
            "created_at": "2026-05-26T00:00:00Z",
            "batch_id": "batch",
            "candidate_type": "project_memory",
            "title": "Jackie consent gate",
            "summary": "Jackie tool bridge mutations need explicit user consent before Review card writes.",
            "recommendation": "Use explicit consent gate before mutation.",
            "confidence": 0.9,
            "source_finding_ids": ["sf_gate"],
            "source_refs": [{"thread_key": "session:app", "title": "T-Sense-App", "line": 149}],
        }
        data.update(overrides)
        return data

    def write_finding(self) -> None:
        self.write_jsonl(
            self.jobs,
            [
                {
                    "kind": "aippocampus_subconscious_job_finding",
                    "fingerprint": "sf_gate",
                    "source_refs": [
                        {
                            "thread_key": "session:app",
                            "title": "T-Sense-App",
                            "project_label": "T-Sense",
                            "assistant_line": 149,
                        },
                        {
                            "thread_key": "session:core",
                            "title": "T-Sense core",
                            "project_label": "T-Sense",
                            "assistant_line": 222,
                        },
                    ],
                    "concepts": ["Jackie", "consent gate", "Review card mutation"],
                }
            ],
        )

    def test_project_memory_routes_to_use_with_source(self) -> None:
        self.write_finding()
        self.write_jsonl(self.candidates, [self.base_candidate()])

        result = router.route_candidates(self.candidates, self.jobs)
        row = result["rows"][0]

        self.assertEqual(row["route"], router.USE_WITH_SOURCE)
        self.assertEqual(row["project_label"], "T-Sense")
        self.assertEqual(row["status"], "active")
        terms = "\n".join(row["trigger_terms"]).casefold()
        self.assertIn("consent", terms)
        self.assertIn("gate", terms)

    def test_preference_with_limited_evidence_confirms_when_relevant(self) -> None:
        self.write_finding()
        self.write_jsonl(
            self.candidates,
            [
                self.base_candidate(
                    candidate_type="preference_review",
                    title="Prefer incremental rewrites",
                    summary="User prefers bounded partial rewrites over full rewrites.",
                    confidence=0.72,
                )
            ],
        )

        row = router.route_candidates(self.candidates, self.jobs)["rows"][0]

        self.assertEqual(row["route"], router.CONFIRM_WHEN_RELEVANT)
        self.assertIn("ask_only_when_current_action", row["ask_policy"])

    def test_low_confidence_candidate_is_parked(self) -> None:
        self.write_finding()
        self.write_jsonl(self.candidates, [self.base_candidate(confidence=0.3)])

        row = router.route_candidates(self.candidates, self.jobs)["rows"][0]

        self.assertEqual(row["route"], router.PARK)
        self.assertEqual(row["status"], "parked")

    def test_working_memory_match_requires_project_scope_and_concrete_term(self) -> None:
        self.write_finding()
        self.write_jsonl(self.candidates, [self.base_candidate()])
        row = router.route_candidates(self.candidates, self.jobs)["rows"][0]

        matched = router.match_working_memory(
            "Jackie mutation flow 现在怎么处理？",
            [row],
            project_label="T-Sense",
        )
        wrong_project = router.match_working_memory(
            "Jackie mutation flow 现在怎么处理？",
            [row],
            project_label="Other",
        )
        broad_only = router.match_working_memory("T-Sense 怎么办？", [row], project_label="T-Sense")

        self.assertEqual(len(matched), 1)
        self.assertEqual(wrong_project, [])
        self.assertEqual(broad_only, [])


if __name__ == "__main__":
    unittest.main()
