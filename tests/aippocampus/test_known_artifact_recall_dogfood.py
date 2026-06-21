from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import (
    REPO_ROOT,
    SMOKE_TOOLS,
    import_smoke_module,
)

dogfood = import_smoke_module("known_artifact_recall_dogfood")


def runner_with_targets(targets: dict[str, dict[str, object]]):
    def run(argv: list[str], cwd: Path) -> dict[str, object]:
        del cwd
        command = " ".join(argv)
        for marker, payload in targets.items():
            if marker in command:
                return {"returncode": 0, "payload": payload}
        return {"returncode": 1, "payload": {"status": "no_routes"}}

    return run


class KnownArtifactRecallDogfoodTests(unittest.TestCase):
    def test_default_cases_record_metrics_and_owner_failures(self) -> None:
        report = dogfood.evaluate_known_artifact_recall(
            repo_root=REPO_ROOT,
            command_runner=runner_with_targets(
                {
                    "compatibility historical fields": {
                        "status": "ok",
                        "foreground_action": {
                            "id": "open_repo_familiarity_source",
                            "command": "python -c ...",
                            "arguments": {
                                "path": (
                                    "docs/architecture/ops/compatibility-shim-inventory.md"
                                )
                            },
                        },
                    },
                    "discussion 2127 source-backed": {
                        "status": "ok",
                        "foreground_action": {
                            "id": "open_discussion_pointer",
                            "command": "open discussion 2127",
                        },
                        "url": "https://github.com/Sapientropic/AIppocampus/discussions/2127",
                    },
                }
            ),
        )
        by_id = {case["case_id"]: case for case in report["cases"]}

        self.assertEqual(report["kind"], "aippocampus_known_artifact_recall_dogfood")
        self.assertEqual(report["case_count"], 3)
        self.assertTrue(by_id["compatibility_inventory_natural_cue"]["metrics"]["known_artifact_found"])
        self.assertTrue(by_id["compatibility_inventory_natural_cue"]["metrics"]["artifact_exists"])
        self.assertTrue(by_id["compatibility_inventory_natural_cue"]["metrics"]["live_recall_found"])
        self.assertTrue(
            by_id["compatibility_inventory_natural_cue"]["metrics"]["usable_foreground_action"]
        )
        self.assertTrue(by_id["discussion_2127_natural_cue"]["metrics"]["known_artifact_found"])
        self.assertEqual(
            by_id["discussion_2127_natural_cue"]["evidence"]["pointer"]["url"],
            "https://github.com/Sapientropic/AIppocampus/discussions/2127",
        )
        self.assertEqual(report["failing_owners"], [])
        self.assertFalse(report["privacy_boundary"]["discussion_bodies_serialized"])

    def test_observations_classify_manual_and_wrong_route_drag(self) -> None:
        report = dogfood.evaluate_known_artifact_recall(
            repo_root=REPO_ROOT,
            command_runner=None,
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

    def test_static_repo_doc_existence_does_not_pass_without_live_route(self) -> None:
        report = dogfood.evaluate_known_artifact_recall(
            repo_root=REPO_ROOT,
            command_runner=runner_with_targets({}),
            cases=(dogfood.DEFAULT_CASES[0],),
        )
        case = report["cases"][0]

        self.assertTrue(case["artifact_exists"])
        self.assertFalse(case["metrics"]["live_recall_found"])
        self.assertFalse(case["metrics"]["live_search_found"])
        self.assertFalse(case["metrics"]["usable_foreground_action"])
        self.assertFalse(case["ok"])
        self.assertIn("recall_fallback", report["failing_owners"])

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

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["failed_count"], 0)
        self.assertEqual(payload["failing_owners"], [])
        compat = {
            case["case_id"]: case for case in payload["cases"]
        }["compatibility_inventory_natural_cue"]
        self.assertIn("artifact_exists", compat)
        self.assertIn("live_recall_found", compat)
        self.assertIn("live_search_found", compat)
        self.assertIn("usable_foreground_action", compat)

if __name__ == "__main__":
    unittest.main()
