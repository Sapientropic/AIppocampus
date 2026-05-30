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

import memory_candidate_router as router  # noqa: E402


class RoutingBoundaryTests(unittest.TestCase):
    def route(
        self,
        *,
        candidate_type: str,
        confidence: float,
        ref_count: int,
        thread_count: int = 1,
        score: float = 0.55,
    ) -> str:
        route, _risk, _reason = router.route_candidate(
            {"candidate_type": candidate_type, "confidence": confidence},
            {
                "score": score,
                "source_ref_count": ref_count,
                "source_thread_count": thread_count,
            },
        )
        return route

    def test_candidate_route_thresholds_are_explicit(self) -> None:
        cases = [
            ("project_memory", 0.75, 1, 1, router.USE_WITH_SOURCE),
            ("project_memory", 0.60, 1, 1, router.CONFIRM_WHEN_RELEVANT),
            ("project_memory", 0.59, 1, 1, router.PARK),
            ("preference_review", 0.85, 3, 2, router.USE_WITH_SOURCE),
            ("preference_review", 0.65, 1, 1, router.CONFIRM_WHEN_RELEVANT),
            ("preference_review", 0.64, 3, 2, router.PARK),
            ("hook_trigger", 0.70, 1, 1, router.USE_SILENTLY),
            ("hook_trigger", 0.69, 1, 1, router.PARK),
            ("question_candidate", 0.55, 1, 1, router.USE_SILENTLY),
            ("question_link", 0.65, 2, 2, router.USE_WITH_SOURCE),
            ("question_link", 0.55, 1, 1, router.USE_SILENTLY),
            ("frontier_marker", 0.60, 1, 1, router.USE_SILENTLY),
            ("theme_candidate", 0.55, 1, 1, router.USE_SILENTLY),
        ]
        for candidate_type, confidence, ref_count, thread_count, expected in cases:
            with self.subTest(
                candidate_type=candidate_type,
                confidence=confidence,
                ref_count=ref_count,
                thread_count=thread_count,
            ):
                self.assertEqual(
                    self.route(
                        candidate_type=candidate_type,
                        confidence=confidence,
                        ref_count=ref_count,
                        thread_count=thread_count,
                    ),
                    expected,
                )

    def test_missing_source_refs_always_parks_candidate(self) -> None:
        self.assertEqual(
            self.route(candidate_type="project_memory", confidence=0.99, ref_count=0),
            router.PARK,
        )

    def test_working_memory_match_rejects_broad_project_only_prompt(self) -> None:
        row = {
            "status": "active",
            "route": router.CONFIRM_WHEN_RELEVANT,
            "candidate_type": "project_memory",
            "title": "Jackie mutation consent gate",
            "summary": "Jackie mutations require explicit consent before writes.",
            "confidence": 0.75,
            "project_label": "T-Sense",
            "trigger_terms": ["Jackie", "mutation", "consent gate"],
        }

        matched = router.match_working_memory(
            "Jackie mutation flow 现在怎么处理？",
            [row],
            project_label="T-Sense",
        )
        broad_only = router.match_working_memory("T-Sense 怎么办？", [row], project_label="T-Sense")
        wrong_project = router.match_working_memory(
            "Jackie mutation flow 现在怎么处理？",
            [row],
            project_label="Other",
        )

        self.assertEqual(len(matched), 1)
        self.assertEqual(broad_only, [])
        self.assertEqual(wrong_project, [])

    def test_working_memory_match_rejects_single_generic_action_term(self) -> None:
        row = {
            "status": "active",
            "route": router.CONFIRM_WHEN_RELEVANT,
            "candidate_type": "contradiction_review",
            "title": "Jackie mutation consent gate",
            "summary": "Jackie mutations require explicit consent before writes.",
            "confidence": 0.7,
            "project_label": "AIppocampus",
            "trigger_terms": ["Jackie", "mutation", "consent gate", "Review card"],
        }

        self.assertEqual(
            router.match_working_memory(
                "ParkedSecret mutation flow 现在怎么处理？",
                [row],
                project_label="AIppocampus",
            ),
            [],
        )

    def test_working_memory_match_rejects_partial_multiword_phrase(self) -> None:
        row = {
            "status": "active",
            "route": router.CONFIRM_WHEN_RELEVANT,
            "candidate_type": "contradiction_review",
            "title": "Jackie mutation consent gate",
            "summary": "Jackie mutations require explicit consent before writes.",
            "confidence": 0.7,
            "project_label": "AIppocampus",
            "trigger_terms": ["Jackie", "mutation", "consent gate", "Review card"],
        }

        self.assertEqual(
            router.match_working_memory(
                "这个 recall gate 能不能 stay project-scoped?",
                [row],
                project_label="AIppocampus",
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
