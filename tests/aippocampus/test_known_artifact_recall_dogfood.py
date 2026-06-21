from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_TOOLS = REPO_ROOT / "tools" / "aippocampus" / "smoke"

import known_artifact_recall_dogfood as dogfood


class KnownArtifactRecallDogfoodTests(unittest.TestCase):
    def test_default_cases_record_metrics_and_owner_failures(self) -> None:
        report = dogfood.evaluate_known_artifact_recall(repo_root=REPO_ROOT)
        by_id = {case["case_id"]: case for case in report["cases"]}

        self.assertEqual(report["kind"], "aippocampus_known_artifact_recall_dogfood")
        self.assertEqual(report["case_count"], 3)
        self.assertTrue(by_id["compatibility_inventory_natural_cue"]["metrics"]["known_artifact_found"])
        self.assertTrue(by_id["discussion_2127_natural_cue"]["metrics"]["known_artifact_found"])
        self.assertEqual(
            by_id["discussion_2127_natural_cue"]["evidence"]["pointer"]["url"],
            "https://github.com/Sapientropic/AIppocampus/discussions/2127",
        )
        self.assertIn("registry_search_phrase_coverage", report["failing_owners"])
        self.assertFalse(report["privacy_boundary"]["discussion_bodies_serialized"])

    def test_observations_classify_manual_and_wrong_route_drag(self) -> None:
        report = dogfood.evaluate_known_artifact_recall(
            repo_root=REPO_ROOT,
            observations=[
                {
                    "case_id": "discussion_2127_natural_cue",
                    "status": "refine_only",
                    "next_action": "run discussion atlas pointer query",
                },
                {
                    "case_id": "discussion_2127_exact_public_phrase",
                    "status": "wrong_route",
                    "metrics": {"known_artifact_found": False},
                },
            ],
        )
        by_id = {case["case_id"]: case for case in report["cases"]}

        self.assertTrue(by_id["discussion_2127_natural_cue"]["metrics"]["manual_search_fallback"])
        self.assertTrue(by_id["discussion_2127_natural_cue"]["metrics"]["usable_next_action"])
        self.assertTrue(by_id["discussion_2127_exact_public_phrase"]["metrics"]["wrong_route_drag"])
        self.assertIn("registry_search_phrase_coverage", report["failing_owners"])

    def test_cli_json_is_machine_readable_even_when_quality_fails(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(SMOKE_TOOLS / "known_artifact_recall_dogfood.py"),
                "--repo-root",
                str(REPO_ROOT),
                "--json",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["failed_count"], 1)
        self.assertIn("registry_search_phrase_coverage", payload["failing_owners"])

if __name__ == "__main__":
    unittest.main()
