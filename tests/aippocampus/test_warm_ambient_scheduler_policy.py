from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ambient_warm_scheduler as warm_scheduler  # noqa: E402
from aippocampus_runtime.warm_ambient import scout_profiles  # noqa: E402


class WarmAmbientSchedulerPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_foreground_tiers_are_cache_only_and_model_free(self) -> None:
        tier0 = scout_profiles.scheduler_tier_policy("tier0_foreground")
        tier1 = scout_profiles.scheduler_tier_policy("tier1_foreground_warm_read")

        self.assertFalse(tier0["fresh_model_calls_allowed"])
        self.assertFalse(tier1["fresh_model_calls_allowed"])
        self.assertEqual(
            scout_profiles.select_scheduler_scouts(
                tier="tier0_foreground",
                task_profile="coding",
            ),
            (),
        )
        self.assertEqual(
            scout_profiles.select_scheduler_scouts(
                tier="tier1_foreground_warm_read",
                task_profile="personal",
            ),
            (),
        )

    def test_background_profiles_select_bounded_task_specific_scouts(self) -> None:
        coding = scout_profiles.select_scheduler_scouts(
            tier="tier2_background",
            task_profile="coding",
        )
        personal = scout_profiles.select_scheduler_scouts(
            tier="tier2_background",
            task_profile="personal",
        )
        high_risk = scout_profiles.select_scheduler_scouts(
            tier="tier2_background",
            task_profile="high_risk",
        )

        for selected in (coding, personal, high_risk):
            self.assertGreater(len(selected), 0)
            self.assertLess(len(selected), len(scout_profiles.DEFAULT_SCOUTS))
            self.assertEqual(len(selected), len(set(selected)))

        self.assertIn("intent_mode_classifier:direct", coding)
        self.assertIn("key_line_hunter:direct", coding)
        self.assertIn("trajectory_matcher:direct", coding)
        self.assertIn("evidence_gap_sentinel:skeptic_window", coding)
        self.assertIn("privacy_boundary_guard:direct", personal)
        self.assertIn("deep_theme_matcher:direct", personal)
        self.assertIn("user_style_preference:direct", personal)
        self.assertIn("privacy_boundary_guard:skeptic_window", high_risk)
        self.assertIn("evidence_gap_sentinel:skeptic_window", high_risk)
        self.assertNotIn("nudge_writer:direct", high_risk)

    def test_diagnostic_tier_keeps_full_scout_matrix_available(self) -> None:
        self.assertEqual(
            scout_profiles.select_scheduler_scouts(
                tier="tier3_diagnostic",
                task_profile="coding",
            ),
            scout_profiles.DEFAULT_SCOUTS,
        )

    def test_scheduler_defaults_to_bounded_background_subset(self) -> None:
        result = warm_scheduler.schedule_warm_ambient_recall(
            "继续 warm ambient scheduler policy",
            cwd=self.workspace,
            thread_id="thread-a",
            job_dir=self.root / "warm-jobs",
            enabled=True,
            spawn=False,
            scheduler_tier="tier2_background",
            task_profile="coding",
        )
        job = json.loads(Path(result["job_path"]).read_text(encoding="utf-8"))

        self.assertEqual(result["scheduler_tier"], "tier2_background")
        self.assertEqual(result["task_profile"], "coding")
        self.assertGreater(len(job["scouts"]), 0)
        self.assertLess(len(job["scouts"]), len(scout_profiles.DEFAULT_SCOUTS))
        self.assertEqual(job["scheduler"]["tier"], "tier2_background")
        self.assertTrue(job["scheduler"]["fresh_model_calls_allowed"])
        self.assertEqual(job["scheduler"]["task_profile"], "coding")

    def test_foreground_scheduler_tier_does_not_write_empty_full_sweep_job(self) -> None:
        result = warm_scheduler.schedule_warm_ambient_recall(
            "继续 warm ambient foreground policy",
            cwd=self.workspace,
            thread_id="thread-a",
            job_dir=self.root / "warm-jobs",
            enabled=True,
            spawn=False,
            scheduler_tier="tier0_foreground",
            task_profile="coding",
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["scheduler_tier"], "tier0_foreground")
        self.assertNotIn("job_path", result)

    def test_guard_lanes_do_not_retire_only_because_they_are_quiet(self) -> None:
        quiet_roi = {
            "classification": "watch",
            "scout_count": 12,
            "useful_result_count": 0,
            "card_candidate_count": 0,
            "accepted_card_count": 0,
            "evidence_candidate_count": 0,
            "accepted_evidence_count": 0,
        }

        self.assertEqual(
            scout_profiles.scheduler_lifecycle_status(
                "privacy_boundary_guard:direct",
                quiet_roi,
            ),
            "guard_required",
        )
        self.assertEqual(
            scout_profiles.scheduler_lifecycle_status("semantic_expander:direct", quiet_roi),
            "retire_candidate",
        )

    def test_nudge_visibility_requires_privacy_and_evidence_guards(self) -> None:
        self.assertFalse(
            scout_profiles.foreground_visibility_allowed(
                "nudge_writer:direct",
                privacy_guard_resolved=False,
                evidence_guard_clear=True,
                source_ref_count=1,
            )
        )
        self.assertFalse(
            scout_profiles.foreground_visibility_allowed(
                "nudge_writer:direct",
                privacy_guard_resolved=True,
                evidence_guard_clear=True,
                source_ref_count=0,
            )
        )
        self.assertTrue(
            scout_profiles.foreground_visibility_allowed(
                "nudge_writer:direct",
                privacy_guard_resolved=True,
                evidence_guard_clear=True,
                source_ref_count=1,
            )
        )


if __name__ == "__main__":
    unittest.main()
