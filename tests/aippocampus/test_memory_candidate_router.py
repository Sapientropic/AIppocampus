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
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

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

    def test_activation_cues_drive_working_memory_trigger_terms(self) -> None:
        self.write_finding()
        self.write_jsonl(
            self.candidates,
            [
                self.base_candidate(
                    title="Reviewed semantic hook",
                    summary="A source-backed hook that should be activated by model-authored cues.",
                    recommendation="Use the subconscious cue surface rather than summary prose.",
                    activation_cues=[
                        "最近让我很烦",
                        "recent personal friction",
                        "что меня раздражало недавно",
                    ],
                )
            ],
        )

        row = router.route_candidates(self.candidates, self.jobs)["rows"][0]
        matched = router.match_working_memory(
            "最近让我很烦的那个点后来怎么处理来着？",
            [row],
            project_label="T-Sense",
        )

        self.assertIn("最近让我很烦", row["trigger_terms"])
        self.assertNotIn("source-backed hook", " ".join(row["trigger_terms"]).casefold())
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["matched_terms"], ["最近让我很烦"])

    def test_working_memory_ignores_generic_app_term(self) -> None:
        self.write_finding()
        self.write_jsonl(
            self.candidates,
            [
                self.base_candidate(
                    title="Mini App tunnel persistence",
                    summary="Cloudflare tunnel auto-restart for a production Mini App.",
                    recommendation="Use health-check auto-restart.",
                )
            ],
        )
        row = router.route_candidates(self.candidates, self.jobs)["rows"][0]

        matched = router.match_working_memory(
            "Rappelle-moi d'acheter du lait demain.",
            [row],
            project_label="T-Sense",
        )

        self.assertEqual(matched, [])

    def test_dream_hypothesis_match_carries_foreground_gate_and_skips_blocked_rows(self) -> None:
        dream_row = {
            "kind": "aippocampus_working_memory",
            "status": "active",
            "route": router.USE_WITH_SOURCE,
            "candidate_type": "dream_hypothesis",
            "title": "Continuity dream bridge",
            "summary": "A dream hypothesis about continuity and source refs.",
            "recommendation": "Use quietly; reopen source before strong claims.",
            "confidence": 0.66,
            "trigger_terms": ["continuity", "source refs"],
            "source_refs": [{"thread_key": "session:dream", "message_id": "msg-d", "line": 12}],
            "truth_boundary": "adjudicated_dream_hypothesis_not_fact",
            "review_state": "agent_adjudicated",
            "foreground_use": {
                "default_action": "quiet_substrate",
                "strong_claim_requires_source_reopen": True,
            },
            "sensitive_use_gate": {"state": "allowed"},
        }
        blocked = {
            **dream_row,
            "title": "Sensitive dream bridge",
            "sensitive_use_gate": {"state": "blocked"},
        }

        matched = router.match_working_memory(
            "continuity source refs 这条线索还在吗？",
            [dream_row, blocked],
        )

        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["candidate_type"], "dream_hypothesis")
        self.assertEqual(matched[0]["dream_hypothesis_use"]["action"], "use_quietly")
        self.assertEqual(
            matched[0]["dream_hypothesis_use"]["truth_boundary"],
            "adjudicated_dream_hypothesis_not_fact",
        )


if __name__ == "__main__":
    unittest.main()
