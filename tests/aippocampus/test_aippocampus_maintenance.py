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
                return 3, "", "index writer locked"
            self.fail(f"unexpected text command: {cmd}")

        with (
            mock.patch.object(maintenance, "run_json_checked", side_effect=fake_json),
            mock.patch.object(maintenance, "run_text_checked", side_effect=fake_text),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = maintenance.main(
                [
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
        health_calls = [{"ok": True, "recommended_actions": []}, {"ok": True, "recommended_actions": []}]

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
        self.assertEqual(payload["mode"], "applied")
        self.assertFalse(payload["read_only"])
        self.assertEqual(payload["failure_count"], 0)
        self.assertNotIn("health_final", payload)
        self.assertEqual(payload["full_audit_flag"], "--json")
        self.assertEqual(payload["plan_first_command"], "aippocampus maintenance --plan --summary-json")

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
        self.assertEqual(payload["apply_command"], "aippocampus maintenance --summary-json")

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
                maintenance.main(["--cwd", ".", "--fail-fast", "--json"])

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
            code = maintenance.main(["--cwd", ".", "--json"])

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
