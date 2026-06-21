from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

REPO_ROOT = Path(__file__).resolve().parents[2]

benchmark = import_benchmark_module("benchmark_map_rot_lifecycle_debt")
from aippocampus_runtime.ops import map_rot_maintenance as maintenance


class MapRotMaintenanceTests(unittest.TestCase):
    def test_planner_turns_lifecycle_rows_into_bounded_actions(self) -> None:
        report = maintenance.plan_map_rot_maintenance(
            benchmark.fixture_map_rot_cases(),
            run_at="2026-06-11T00:00:00Z",
        )
        by_id = {item["case_id"]: item for item in report["actions"]}

        self.assertEqual(report["kind"], "aippocampus_map_rot_maintenance_plan")
        self.assertEqual(report["write_mode"], "no_write_plan_only")
        self.assertIn("refresh_source", report["bounded_maintenance_actions"])
        self.assertEqual(
            report["metrics"]["action_counts"],
            {
                "dead_letter_compact": 1,
                "keep_current": 1,
                "needs_review": 2,
                "prune_or_decay": 1,
                "refresh_source": 2,
                "suppress_until_source_changes": 2,
            },
        )
        self.assertEqual(report["metrics"]["hot_surface_removal_count"], 8)
        self.assertEqual(report["metrics"]["review_queue_count"], 2)
        self.assertEqual(report["metrics"]["reactivation_after_source_refresh_count"], 2)
        self.assertEqual(report["metrics"]["oldest_challenged_age_days"], 45)
        self.assertEqual(
            report["hard_red_lines"],
            {
                "deleted_no_recall_emit_count": 0,
                "masked_source_resurrection_count": 0,
                "quarantined_route_emit_count": 0,
                "stale_as_current_count": 0,
                "superseded_route_emit_count": 0,
                "wrong_route_revival_count": 0,
            },
        )
        self.assertEqual(by_id["stale_current_pointer_refresh"]["action"], "refresh_source")
        self.assertEqual(
            by_id["stale_current_pointer_refresh"]["maintenance_action"]["write_scope"],
            "no_write_plan_only",
        )
        self.assertEqual(by_id["challenged_conflict_backlog"]["action"], "needs_review")
        self.assertEqual(
            by_id["quarantined_masked_route_silent"]["action"],
            "suppress_until_source_changes",
        )
        self.assertEqual(by_id["superseded_route_uses_successor"]["action"], "refresh_source")
        self.assertEqual(by_id["pathlet_missing_middle_warning"]["action"], "needs_review")
        self.assertEqual(by_id["deleted_no_recall_object_silent"]["action"], "prune_or_decay")
        self.assertEqual(by_id["dead_lettered_cache_row_ignored"]["action"], "dead_letter_compact")
        self.assertEqual(
            by_id["repeated_wrong_route_suppressed"]["action"],
            "suppress_until_source_changes",
        )
        self.assertEqual(by_id["current_reopenable_route_allowed"]["action"], "keep_current")

    def test_planner_handles_single_pass_iterables_without_losing_red_lines(self) -> None:
        leaky_rows = (
            {
                **case,
                "emitted_route": True,
            }
            for case in benchmark.fixture_map_rot_cases()
            if case["case_id"] == "stale_current_pointer_refresh"
        )

        report = maintenance.plan_map_rot_maintenance(leaky_rows)

        self.assertFalse(report["ok"])
        self.assertEqual(report["metrics"]["case_count"], 1)
        self.assertEqual(report["hard_red_lines"]["stale_as_current_count"], 1)

    def test_topology_shapes_become_bounded_actions_without_new_action_types(self) -> None:
        rows = [
            {
                **benchmark.fixture_map_rot_cases()[-1],
                "case_id": "cycle_shape",
                "topology_shape": "repeated_failed_route_cycle",
            },
            {
                **benchmark.fixture_map_rot_cases()[-1],
                "case_id": "handoff_shape",
                "topology_shape": "orphaned_handoff",
            },
            {
                **benchmark.fixture_map_rot_cases()[-1],
                "case_id": "stale_knot_shape",
                "topology_shape": "stale_knot",
            },
        ]

        report = maintenance.plan_map_rot_maintenance(rows)
        by_id = {item["case_id"]: item for item in report["actions"]}

        self.assertEqual(
            by_id["cycle_shape"]["action"],
            "suppress_until_source_changes",
        )
        self.assertEqual(by_id["handoff_shape"]["action"], "needs_review")
        self.assertEqual(by_id["stale_knot_shape"]["action"], "refresh_source")
        self.assertEqual(
            set(report["metrics"]["action_counts"]),
            set(report["bounded_maintenance_actions"]),
        )

    def test_cli_report_is_public_safe_and_does_not_echo_input_path_or_private_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "private-map-rot-cases.json"
            rows = [
                {
                    **benchmark.fixture_map_rot_cases()[0],
                    "source_text": "PRIVATE source text must not leave the planner",
                    "local_path": str(root / "private-rollout.jsonl"),
                    "thread_id": "private-thread-id",
                }
            ]
            input_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.ops.map_rot_maintenance",
                    "--input",
                    str(input_path),
                    "--json",
                ],
                check=False,
                text=True,
                capture_output=True,
                cwd=REPO_ROOT,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertEqual(payload["kind"], "aippocampus_map_rot_maintenance_plan")
        self.assertFalse(payload["privacy_boundary"]["raw_source_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["local_paths_emitted"])
        self.assertNotIn(str(root), encoded)
        self.assertNotIn("PRIVATE source text", encoded)
        self.assertNotIn("private-thread-id", encoded)

if __name__ == "__main__":
    unittest.main()
