from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from aippocampus_runtime import health, health_stages
from tests.aippocampus.health_fixtures import health_workspace
from tests.aippocampus.health_report_fixtures import (
    write_current_artifacts,
    write_rollout,
)


class AippocampusHealthStorageHostTests(unittest.TestCase):
    def test_registry_cache_pressure_report_uses_storage_governance_metrics(self) -> None:
        with mock.patch(
            "aippocampus_runtime.ops.storage_governance.build_plan",
            return_value={
                "metrics": {
                    "reclaimable_rebuildable_bytes": 2 * 1024 * 1024 * 1024,
                    "reclaimable_rebuildable_human": "2.0 GB",
                    "protected_source_bytes": 128 * 1024 * 1024,
                    "protected_source_human": "128.0 MB",
                    "generated_index_amplification_ratio": 16.0,
                    "eviction_candidate_count": 140,
                }
            },
        ) as build_plan:
            report = health.registry_cache_pressure_report(
                Path("workspace"),
                Path("registry"),
            )

        build_plan.assert_called_once()
        self.assertTrue(report["available"])
        self.assertTrue(report["pressure"])
        self.assertEqual(report["status"], "pressure")
        self.assertIn("reclaimable_rebuildable_cache_bytes_high", report["reasons"])
        self.assertEqual(
            report["dry_run_command"],
            "aippocampus storage gc --dry-run --json --top 1 --cwd .",
        )
        self.assertEqual(
            report["summary_command"],
            "aippocampus storage gc --dry-run --summary-json --cwd .",
        )
        self.assertEqual(
            report["repair_command"],
            "aippocampus storage gc --apply --class rebuildable --include-active --summary-json --cwd .",
        )
        self.assertTrue(report["source_history_protected"])
        self.assertFalse(report["privacy_boundary"]["paths_included"])

    def test_health_surfaces_generated_cache_pressure_as_safe_repair_action(self) -> None:
        with health_workspace() as (root, workspace):
            rollout = workspace / "rollout.jsonl"
            write_rollout(rollout, workspace)
            paths = write_current_artifacts(root, workspace, rollout)
            registry_dir = root / "registry"
            registry_dir.mkdir()
            (registry_dir / "threads.json").write_text('{"threads":[]}', encoding="utf-8")

            pressure = {
                "available": True,
                "status": "pressure",
                "pressure": True,
                "reasons": ["reclaimable_rebuildable_cache_bytes_high"],
                "metrics": {
                    "reclaimable_rebuildable_human": "2.0 GB",
                    "generated_index_amplification_ratio": 16.0,
                },
                "dry_run_command": "aippocampus storage gc --dry-run --json --top 1 --cwd .",
                "summary_command": "aippocampus storage gc --dry-run --summary-json --cwd .",
                "repair_command": "aippocampus storage gc --apply --class rebuildable --include-active --summary-json --cwd .",
                "source_history_protected": True,
                "foreground_blocking": False,
            }
            with (
                mock.patch.object(health_stages, "locate_rollout", return_value=rollout),
                mock.patch.object(
                    health,
                    "registry_cache_pressure_report",
                    return_value=pressure,
                ),
            ):
                payload = health.build_health_report(
                    health.HealthOptions(
                        cwd=workspace,
                        registry_dir=registry_dir,
                        include_operator_diagnostics=True,
                        include_expensive_diagnostics=True,
                        **paths,
                    )
                )

        action_ids = [item["id"] for item in payload["recommended_actions"]]
        self.assertIn("storage_gc_rebuildable_cache", action_ids)
        action = next(
            item
            for item in payload["recommended_actions"]
            if item["id"] == "storage_gc_rebuildable_cache"
        )
        self.assertEqual(action["severity"], "warning")
        self.assertEqual(
            action["command"],
            "aippocampus storage gc --dry-run --json --top 1 --cwd .",
        )
        self.assertEqual(payload["storage_pressure"], pressure)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["product_readiness"]["ordinary_first_recall_usable"])
        self.assertFalse(payload["product_readiness"]["maintenance_required_before_recall"])
        self.assertTrue(payload["product_readiness"]["storage_pressure_cleanup_recommended"])

    def test_health_reports_codex_host_state_confounds_without_paths_or_ids(self) -> None:
        with health_workspace() as (root, workspace):
            rollout = workspace / "rollout.jsonl"
            write_rollout(rollout, workspace)
            paths = write_current_artifacts(root, workspace, rollout)
            registry_dir = root / "registry"
            registry_dir.mkdir()
            (registry_dir / "threads.json").write_text('{"threads":[]}', encoding="utf-8")
            codex = root / "codex-home"
            (codex / "logs").mkdir(parents=True)
            (codex / "sessions" / "private-session-id").mkdir(parents=True)
            (codex / "logs" / "state.sqlite").write_bytes(b"x" * 128)
            (codex / "logs" / "state.sqlite-wal").write_bytes(b"y" * 64)
            (codex / "sessions" / "private-session-id" / "rollout.jsonl").write_bytes(b"z" * 256)
            (codex / "threads.json").write_text(
                '{"threads":[{"id":"private-thread-id"}]}',
                encoding="utf-8",
            )

            with (
                mock.patch.object(health_stages, "codex_home", return_value=codex),
                mock.patch.object(health_stages, "locate_rollout", return_value=rollout),
            ):
                payload = health.build_health_report(
                    health.HealthOptions(
                        cwd=workspace,
                        registry_dir=registry_dir,
                        include_operator_diagnostics=True,
                        **paths,
                    )
                )

        confounds = payload["host_state_confounds"]
        encoded = json.dumps(confounds, ensure_ascii=False)

        self.assertTrue(confounds["available"])
        self.assertEqual(confounds["artifact_scope"], "codex_host_state_not_aippocampus_registry")
        self.assertGreater(confounds["logs_db_wal"]["total_bytes"], 0)
        self.assertGreater(confounds["session_store"]["total_bytes"], 0)
        self.assertTrue(confounds["thread_list"]["available"])
        self.assertFalse(confounds["privacy_boundary"]["paths_included"])
        self.assertNotIn(str(root), encoded)
        self.assertNotIn("private-session-id", encoded)
        self.assertNotIn("private-thread-id", encoded)


if __name__ == "__main__":
    unittest.main()
