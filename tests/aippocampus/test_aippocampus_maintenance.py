from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import maintenance as maintenance  # noqa: E402


class AippocampusMaintenanceTests(unittest.TestCase):
    def test_activation_payload_compaction_delegation_is_explicit_dry_run_and_path_sanitized(
        self,
    ) -> None:
        health_calls = [
            {"ok": True, "recommended_actions": []},
            {"ok": True, "recommended_actions": []},
        ]
        seen_compaction_cmds: list[list[str]] = []

        def module_for(cmd: list[str]) -> str:
            return cmd[2] if len(cmd) > 2 and cmd[1] == "-m" else Path(cmd[1]).stem

        def fake_json(cmd: list[str]) -> tuple[int, dict | None, str, str]:
            module = module_for(cmd)
            if module == "aippocampus_runtime.health":
                return 0, health_calls.pop(0), "{}", ""
            if module == "aippocampus_runtime.ops.activation_payload_compaction":
                seen_compaction_cmds.append(cmd)
                self.assertIn("--dead-letter-manifest", cmd)
                self.assertIn("--ambient-cache", cmd)
                self.assertIn("--working-memory", cmd)
                self.assertIn("--semantic-triggers", cmd)
                self.assertIn("--active-recall-locks", cmd)
                self.assertNotIn("--apply", cmd)
                return (
                    0,
                    {
                        "kind": "aippocampus_activation_payload_compaction_run",
                        "status": "no_changes",
                        "write_mode": "no_write_dry_run",
                        "metrics": {"payload_compacted_count": 0},
                        "privacy_boundary": {
                            "local_paths_serialized": False,
                            "raw_activation_payload_serialized": False,
                            "source_refs_serialized": False,
                        },
                    },
                    "{}",
                    "",
                )
            self.fail(f"unexpected JSON command: {cmd}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "dead-letter-manifest.json"
            ambient = root / "ambient-cache.json"
            working = root / "working_memory.jsonl"
            semantic = root / "semantic_triggers.jsonl"
            active_locks = root / "active_recall_locks.json"
            with (
                mock.patch.object(maintenance, "run_json_checked", side_effect=fake_json),
                mock.patch("sys.stdout", new=StringIO()) as stdout,
            ):
                code = maintenance.main(
                    [
                        "apply",
                        "--cwd",
                        ".",
                        "--no-refresh-cognitive-map",
                        "--no-refresh-graphify",
                        "--activation-dead-letter-manifest",
                        str(manifest),
                        "--activation-ambient-cache",
                        str(ambient),
                        "--activation-working-memory",
                        str(working),
                        "--activation-semantic-triggers",
                        str(semantic),
                        "--activation-active-recall-locks",
                        str(active_locks),
                        "--json",
                    ]
                )

            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(len(seen_compaction_cmds), 1)
        action = next(
            item for item in payload["action_results"] if item["id"] == "activation_payload_compaction"
        )
        self.assertEqual(action["result"]["write_mode"], "no_write_dry_run")
        serialized_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(str(root), serialized_payload)
        self.assertFalse(action["result"]["privacy_boundary"]["local_paths_serialized"])

    def test_activation_payload_compaction_apply_requires_explicit_apply_flag(self) -> None:
        health_calls = [
            {"ok": True, "recommended_actions": []},
            {"ok": True, "recommended_actions": []},
        ]
        seen_compaction_cmds: list[list[str]] = []

        def module_for(cmd: list[str]) -> str:
            return cmd[2] if len(cmd) > 2 and cmd[1] == "-m" else Path(cmd[1]).stem

        def fake_json(cmd: list[str]) -> tuple[int, dict | None, str, str]:
            module = module_for(cmd)
            if module == "aippocampus_runtime.health":
                return 0, health_calls.pop(0), "{}", ""
            if module == "aippocampus_runtime.ops.activation_payload_compaction":
                seen_compaction_cmds.append(cmd)
                self.assertIn("--apply", cmd)
                return (
                    0,
                    {
                        "kind": "aippocampus_activation_payload_compaction_run",
                        "status": "compacted",
                        "write_mode": "apply_owner_payload_compaction",
                        "metrics": {"payload_compacted_count": 1},
                        "privacy_boundary": {"local_paths_serialized": False},
                    },
                    "{}",
                    "",
                )
            self.fail(f"unexpected JSON command: {cmd}")

        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "dead-letter-manifest.json"
            with (
                mock.patch.object(maintenance, "run_json_checked", side_effect=fake_json),
                mock.patch("sys.stdout", new=StringIO()) as stdout,
            ):
                code = maintenance.main(
                    [
                        "apply",
                        "--cwd",
                        ".",
                        "--no-refresh-cognitive-map",
                        "--no-refresh-graphify",
                        "--activation-dead-letter-manifest",
                        str(manifest),
                        "--apply-activation-payload-compaction",
                        "--json",
                    ]
                )

            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(len(seen_compaction_cmds), 1)
        action = next(
            item for item in payload["action_results"] if item["id"] == "activation_payload_compaction"
        )
        self.assertEqual(action["result"]["write_mode"], "apply_owner_payload_compaction")

    def test_degraded_report_records_failed_action_and_keeps_independent_refresh(self) -> None:
        health_calls = [
            {
                "ok": False,
                "recommended_actions": [
                    {"id": "build_index", "severity": "warning", "reason": "stale"},
                    {
                        "id": "prepare_graphify_corpus",
                        "severity": "info",
                        "reason": "index stale",
                    },
                ],
            },
            {
                "ok": False,
                "recommended_actions": [
                    {"id": "build_index", "severity": "warning", "reason": "still stale"},
                ],
            },
            {
                "ok": False,
                "recommended_actions": [
                    {"id": "build_index", "severity": "warning", "reason": "still stale"},
                ],
            },
        ]

        def module_for(cmd: list[str]) -> str:
            return cmd[2] if len(cmd) > 2 and cmd[1] == "-m" else Path(cmd[1]).stem

        def fake_json(cmd: list[str]) -> tuple[int, dict | None, str, str]:
            module = module_for(cmd)
            if module == "aippocampus_runtime.health":
                return 0, health_calls.pop(0), "{}", ""
            if module == "aippocampus_runtime.navigation.cognitive_map":
                return 0, {"ok": True}, "{}", ""
            self.fail(f"unexpected JSON command: {cmd}")

        def fake_text(cmd: list[str]) -> tuple[int, str, str]:
            if module_for(cmd) == "aippocampus_runtime.recall.index_builder":
                return 3, "", r"index writer locked at E:\private\registry\threads\x\.index-publish.lock"
            self.fail(f"unexpected text command: {cmd}")

        with (
            mock.patch.object(maintenance, "run_json_checked", side_effect=fake_json),
            mock.patch.object(maintenance, "run_text_checked", side_effect=fake_text),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = maintenance.main(
                [
                    "apply",
                    "--cwd",
                    ".",
                    "--no-refresh-graphify",
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["maintenance_status"], "degraded")
        self.assertEqual(payload["cwd"], "<local-path-redacted>")
        self.assertEqual(payload["action_failures"][0]["id"], "build_index")
        self.assertIn("index writer locked", payload["action_failures"][0]["message"])
        self.assertIn("<local-path-redacted>", payload["action_failures"][0]["message"])
        self.assertNotIn("E:\\private", json.dumps(payload, ensure_ascii=False))
        self.assertIn(
            "build_cognitive_map",
            [item["id"] for item in payload["action_results"]],
        )
        self.assertEqual(
            payload["remaining_recommended_actions"],
            [{"id": "build_index", "severity": "warning", "reason": "still stale"}],
        )

    def test_maintenance_runs_clean_source_before_index_when_health_recommends_it(self) -> None:
        health_calls = [
            {
                "ok": False,
                "recommended_actions": [
                    {
                        "id": "build_clean_source",
                        "severity": "warning",
                        "reason": "latest visible gap",
                    }
                ],
            },
            {
                "ok": False,
                "recommended_actions": [
                    {"id": "build_index", "severity": "warning", "reason": "index stale"}
                ],
            },
            {"ok": True, "recommended_actions": []},
            {"ok": True, "recommended_actions": []},
        ]
        seen_modules: list[str] = []

        def module_for(cmd: list[str]) -> str:
            return cmd[2] if len(cmd) > 2 and cmd[1] == "-m" else Path(cmd[1]).stem

        def fake_json(cmd: list[str]) -> tuple[int, dict | None, str, str]:
            module = module_for(cmd)
            seen_modules.append(module)
            if module == "aippocampus_runtime.health":
                return 0, health_calls.pop(0), "{}", ""
            if module == "aippocampus_runtime.source.clean_source":
                return 0, {"kind": "aippocampus_clean_source", "message_count": 24}, "{}", ""
            self.fail(f"unexpected JSON command: {cmd}")

        def fake_text(cmd: list[str]) -> tuple[int, str, str]:
            module = module_for(cmd)
            seen_modules.append(module)
            if module == "aippocampus_runtime.recall.index_builder":
                return 0, "indexed", ""
            self.fail(f"unexpected text command: {cmd}")

        with (
            mock.patch.object(maintenance, "run_json_checked", side_effect=fake_json),
            mock.patch.object(maintenance, "run_text_checked", side_effect=fake_text),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = maintenance.main(
                [
                    "apply",
                    "--cwd",
                    ".",
                    "--no-refresh-cognitive-map",
                    "--no-refresh-graphify",
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["maintenance_status"], "ok")
        self.assertEqual(
            [item["id"] for item in payload["action_results"]],
            ["health_initial", "build_clean_source", "build_index"],
        )
        self.assertEqual(payload["remaining_recommended_actions"], [])
        self.assertEqual(
            seen_modules,
            [
                "aippocampus_runtime.health",
                "aippocampus_runtime.source.clean_source",
                "aippocampus_runtime.health",
                "aippocampus_runtime.recall.index_builder",
                "aippocampus_runtime.health",
                "aippocampus_runtime.health",
            ],
        )

    def test_maintenance_final_index_catchup_prevents_immediate_repeat_prompt(self) -> None:
        health_calls = [
            {
                "ok": False,
                "recommended_actions": [
                    {"id": "build_index", "severity": "warning", "reason": "stale"},
                    {
                        "id": "prepare_graphify_corpus",
                        "severity": "info",
                        "reason": "index stale",
                    },
                ],
            },
            {
                "ok": True,
                "recommended_actions": [
                    {
                        "id": "prepare_graphify_corpus",
                        "severity": "info",
                        "reason": "graphify stale",
                    }
                ],
            },
            {
                "ok": False,
                "recommended_actions": [
                    {"id": "build_index", "severity": "warning", "reason": "maintenance live delta"},
                    {
                        "id": "prepare_graphify_corpus",
                        "severity": "info",
                        "reason": "index stale",
                    },
                ],
            },
            {
                "ok": False,
                "recommended_actions": [
                    {"id": "build_index", "severity": "warning", "reason": "maintenance live delta"},
                    {
                        "id": "prepare_graphify_corpus",
                        "severity": "info",
                        "reason": "index stale",
                    },
                ],
            },
            {
                "ok": True,
                "recommended_actions": [
                    {
                        "id": "prepare_graphify_corpus",
                        "severity": "info",
                        "reason": "graphify stale after final index",
                    }
                ],
            },
            {"ok": True, "recommended_actions": []},
        ]
        seen_modules: list[str] = []

        def module_for(cmd: list[str]) -> str:
            return cmd[2] if len(cmd) > 2 and cmd[1] == "-m" else Path(cmd[1]).stem

        def fake_json(cmd: list[str]) -> tuple[int, dict | None, str, str]:
            module = module_for(cmd)
            seen_modules.append(module)
            if module == "aippocampus_runtime.health":
                return 0, health_calls.pop(0), "{}", ""
            if module == "aippocampus_runtime.ops.graphify_corpus":
                return 0, {"kind": "graphify_corpus", "ok": True}, "{}", ""
            self.fail(f"unexpected JSON command: {cmd}")

        def fake_text(cmd: list[str]) -> tuple[int, str, str]:
            module = module_for(cmd)
            seen_modules.append(module)
            if module == "aippocampus_runtime.recall.index_builder":
                return 0, "indexed", ""
            self.fail(f"unexpected text command: {cmd}")

        with (
            mock.patch.object(maintenance, "run_json_checked", side_effect=fake_json),
            mock.patch.object(maintenance, "run_text_checked", side_effect=fake_text),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = maintenance.main(
                [
                    "apply",
                    "--cwd",
                    ".",
                    "--no-refresh-cognitive-map",
                    "--summary-json",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["maintenance_status"], "ok")
        self.assertEqual(payload["remaining_recommended_action_count"], 0)
        self.assertIn("build_index_final_catchup", payload["action_ids"])
        self.assertIn("prepare_graphify_corpus_final_catchup", payload["action_ids"])
        self.assertEqual(
            seen_modules,
            [
                "aippocampus_runtime.health",
                "aippocampus_runtime.recall.index_builder",
                "aippocampus_runtime.health",
                "aippocampus_runtime.ops.graphify_corpus",
                "aippocampus_runtime.health",
                "aippocampus_runtime.health",
                "aippocampus_runtime.recall.index_builder",
                "aippocampus_runtime.health",
                "aippocampus_runtime.ops.graphify_corpus",
                "aippocampus_runtime.health",
            ],
        )

    def test_summary_json_is_bounded_and_omits_full_health_audit(self) -> None:
        health_calls = [{"ok": True, "status": "ok", "recommended_actions": []}]

        def fake_json(cmd: list[str]) -> tuple[int, dict | None, str, str]:
            if len(cmd) > 2 and cmd[2] == "aippocampus_runtime.health":
                return 0, health_calls.pop(0), "{}", ""
            self.fail(f"unexpected JSON command: {cmd}")

        with (
            mock.patch.object(maintenance, "run_json_checked", side_effect=fake_json),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = maintenance.main(
                [
                    "--cwd",
                    ".",
                    "--no-refresh-cognitive-map",
                    "--no-refresh-graphify",
                    "--summary-json",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "aippocampus_maintenance_summary")
        self.assertEqual(payload["cwd"], "<local-path-redacted>")
        self.assertEqual(payload["maintenance_status"], "ok")
        self.assertEqual(payload["mode"], "summary")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["command_ok"])
        self.assertTrue(payload["maintenance_ok"])
        self.assertNotIn("health_final", payload)
        self.assertEqual(payload["full_audit_flag"], "--json")
        self.assertEqual(payload["apply_command"], "aippocampus maintenance apply --summary-json")
        self.assertEqual(health_calls, [])

    def test_plan_is_read_only_and_does_not_run_maintenance_actions(self) -> None:
        seen_modules: list[str] = []

        def fake_json(cmd: list[str]) -> tuple[int, dict | None, str, str]:
            seen_modules.append(cmd[2])
            if cmd[2] == "aippocampus_runtime.health":
                return (
                    0,
                    {
                        "ok": False,
                        "recommended_actions": [
                            {"id": "build_clean_source", "severity": "warning"},
                            {"id": "build_index", "severity": "warning"},
                        ],
                    },
                    "{}",
                    "",
                )
            self.fail(f"unexpected JSON command: {cmd}")

        with (
            mock.patch.object(maintenance, "run_json_checked", side_effect=fake_json),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = maintenance.main(
                [
                    "--cwd",
                    ".",
                    "--no-refresh-cognitive-map",
                    "--no-refresh-graphify",
                    "--plan",
                    "--summary-json",
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(seen_modules, ["aippocampus_runtime.health"])
        self.assertEqual(payload["kind"], "aippocampus_maintenance_plan")
        self.assertTrue(payload["read_only"])
        self.assertEqual(
            payload["would_run_action_ids"],
            ["build_clean_source", "build_index"],
        )
        self.assertEqual(payload["apply_command"], "aippocampus maintenance apply --summary-json")
        self.assertTrue(payload["command_ok"])
        self.assertTrue(payload["plan_generated"])
        self.assertEqual(payload["maintenance_status"], "attention_needed")
        self.assertNotIn("health_error", payload)

    def test_plan_projects_health_state_without_nested_health_error_or_duplicate_actions(self) -> None:
        def fake_json(cmd: list[str]) -> tuple[int, dict | None, str, str]:
            if len(cmd) > 2 and cmd[2] == "aippocampus_runtime.health":
                return (
                    0,
                    {
                        "ok": False,
                        "status": "attention_needed",
                        "product_readiness": {"ready": False, "status": "needs_clean_source"},
                        "recommended_actions": [
                            {
                                "id": "build_clean_source",
                                "severity": "critical",
                                "reason": "clean-source manifest missing",
                            },
                            {
                                "id": "prepare_graphify_corpus",
                                "severity": "info",
                                "reason": "graphify stale",
                            },
                        ],
                    },
                    json.dumps({"ok": False, "status": "attention_needed"}),
                    "",
                )
            self.fail(f"unexpected JSON command: {cmd}")

        with (
            mock.patch.object(maintenance, "run_json_checked", side_effect=fake_json),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = maintenance.main(["--cwd", ".", "--plan", "--summary-json"])

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["command_ok"])
        self.assertFalse(payload["maintenance_ok"])
        self.assertEqual(payload["maintenance_status"], "attention_needed")
        self.assertEqual(
            payload["would_run_action_ids"],
            ["build_clean_source", "prepare_graphify_corpus", "build_cognitive_map"],
        )
        self.assertNotIn("health_error", payload)
        self.assertNotIn("health_returncode", payload)
        self.assertEqual(payload["best_next_action"]["id"], "build_clean_source")
        self.assertEqual(payload["user_impact"]["recall_usable"], "degraded")

    def test_natural_status_subcommand_is_read_only_summary_card(self) -> None:
        seen_modules: list[str] = []

        def fake_json(cmd: list[str]) -> tuple[int, dict | None, str, str]:
            seen_modules.append(cmd[2])
            if cmd[2] == "aippocampus_runtime.health":
                return (
                    0,
                    {
                        "ok": True,
                        "product_readiness": {
                            "ready": True,
                            "ordinary_first_recall_usable": True,
                            "freshness_degraded": True,
                            "latest_current_thread_may_be_missing": True,
                            "maintenance_recommended": True,
                            "maintenance_required_before_recall": False,
                            "status": "ready_with_freshness_degraded",
                        },
                        "recommended_actions": [
                            {"id": "build_index", "severity": "warning", "reason": "index stale"}
                        ],
                    },
                    "{}",
                    "",
                )
            self.fail(f"unexpected JSON command: {cmd}")

        with (
            mock.patch.object(maintenance, "run_json_checked", side_effect=fake_json),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = maintenance.main(["status", "--cwd", ".", "--json"])

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(seen_modules, ["aippocampus_runtime.health"])
        self.assertEqual(payload["mode"], "status")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["maintenance_ok"])
        self.assertEqual(payload["maintenance_status"], "degraded")
        self.assertTrue(payload["user_impact"]["can_continue_normally"])
        self.assertEqual(payload["user_impact"]["recall_usable"], "yes_latest_may_be_missing")
        self.assertEqual(payload["would_run_action_ids"], ["build_index", "build_cognitive_map"])
        self.assertEqual(payload["apply_command"], "aippocampus maintenance apply --summary-json")

    def test_fail_fast_preserves_legacy_raise_on_failed_action(self) -> None:
        with (
            mock.patch.object(
                maintenance,
                "run_json",
                return_value={
                    "ok": False,
                    "recommended_actions": [
                        {"id": "build_index", "severity": "warning", "reason": "stale"}
                    ],
                },
            ),
            mock.patch.object(maintenance, "run_text", side_effect=RuntimeError("boom")),
        ):
            with self.assertRaises(RuntimeError):
                maintenance.main(["apply", "--cwd", ".", "--fail-fast", "--json"])

    def test_graphify_refresh_is_skipped_when_index_rebuild_fails(self) -> None:
        stale_health = {
            "ok": False,
            "recommended_actions": [
                {"id": "build_index", "severity": "warning", "reason": "stale"},
                {
                    "id": "prepare_graphify_corpus",
                    "severity": "info",
                    "reason": "index stale",
                },
            ],
        }
        health_calls = [stale_health, stale_health, stale_health]

        def module_for(cmd: list[str]) -> str:
            return cmd[2] if len(cmd) > 2 and cmd[1] == "-m" else Path(cmd[1]).stem

        def fake_json(cmd: list[str]) -> tuple[int, dict | None, str, str]:
            module = module_for(cmd)
            if module == "aippocampus_runtime.health":
                return 0, health_calls.pop(0), "{}", ""
            if module == "aippocampus_runtime.navigation.cognitive_map":
                return 0, {"ok": True}, "{}", ""
            if module == "aippocampus_runtime.ops.graphify_corpus":
                self.fail("Graphify refresh should wait for a successful index rebuild")
            self.fail(f"unexpected JSON command: {cmd}")

        with (
            mock.patch.object(maintenance, "run_json_checked", side_effect=fake_json),
            mock.patch.object(
                maintenance,
                "run_text_checked",
                return_value=(2, "", "index writer locked"),
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = maintenance.main(["apply", "--cwd", ".", "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(payload["maintenance_status"], "blocked")
        self.assertEqual(
            payload["skipped_due_to_failure"],
            [
                {
                    "id": "prepare_graphify_corpus",
                    "reason": "depends_on_failed_build_index",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
