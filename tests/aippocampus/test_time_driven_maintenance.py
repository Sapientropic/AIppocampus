from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

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

from aippocampus_runtime.subconscious import time_maintenance  # noqa: E402


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


class TimeDrivenMaintenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = self.root / "workspace"
        self.cwd.mkdir()
        self.registry = self.root / "threads.json"
        self.registry.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippo",
                            "project_label": "AIppocampus",
                            "workspace_name": "AIppocampus",
                            "clean_turn_count": 8,
                            "clean_message_count": 16,
                            "updated_at": "2026-06-01T00:00:00Z",
                            "paths": {"workspace": str(self.cwd)},
                            "health": {
                                "recommended_actions": [
                                    {
                                        "id": "build_index",
                                        "severity": "info",
                                        "reason": "RAW_PRIVATE_SENTINEL health reason",
                                    }
                                ]
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def source_ref(self, suffix: str = "1") -> dict[str, object]:
        return {
            "thread_key": "session:aippo",
            "message_id": f"msg-{suffix}",
            "source_line": int(suffix),
            "timestamp": "2026-04-01T00:00:00Z",
        }

    def write_due_sidecars(self) -> None:
        write_jsonl(
            self.root / "scheduled_revisits.jsonl",
            [
                {
                    "kind": "aippocampus_agency_ticket",
                    "ticket_id": "ticket-revisit",
                    "project_label": "AIppocampus",
                    "why_now": {"trigger": "scheduled_revisit"},
                    "scheduled_for": "2026-06-06T00:00:00Z",
                    "summary": "RAW_PRIVATE_SENTINEL revisit summary",
                    "source_refs": [self.source_ref("1")],
                }
            ],
        )
        write_jsonl(
            self.root / "journeys.jsonl",
            [
                {
                    "kind": "aippocampus_journey",
                    "journey_id": "jr-camped",
                    "project_label": "AIppocampus",
                    "status": "camped",
                    "last_seen": "2026-04-01T00:00:00Z",
                    "current_frontier": "RAW_PRIVATE_SENTINEL frontier",
                    "current_frontier_source_refs": [self.source_ref("2")],
                },
                {
                    "kind": "aippocampus_journey",
                    "journey_id": "jr-stale-frontier",
                    "project_label": "AIppocampus",
                    "status": "traveling",
                    "last_seen": "2026-05-01T00:00:00Z",
                    "current_frontier": "RAW_PRIVATE_SENTINEL stale frontier",
                    "current_frontier_source_refs": [self.source_ref("3")],
                },
            ],
        )
        write_jsonl(
            self.root / "subconscious_jobs.jsonl",
            [
                {
                    "schema_version": 1,
                    "kind": "aippocampus_subconscious_job_finding",
                    "created_at": "2026-04-01T00:00:00Z",
                    "finding_kind": "question_link",
                    "fingerprint": "sf_link_dormant",
                    "question_cluster_id": "ql_dormant",
                    "linked_question_short": "RAW_PRIVATE_SENTINEL dormant question",
                    "question_count": 1,
                    "link_type": "recurring",
                    "first_seen": "2026-04-01T00:00:00Z",
                    "last_seen": "2026-04-01T00:00:00Z",
                    "source_refs": [self.source_ref("4")],
                    "linked_questions": [
                        {
                            "question_id": "q_dormant",
                            "source_finding_id": "sf_question_dormant",
                        }
                    ],
                },
                {
                    "schema_version": 1,
                    "kind": "aippocampus_subconscious_job_finding",
                    "created_at": "2026-04-01T00:00:00Z",
                    "finding_kind": "frontier_marker",
                    "fingerprint": "sf_frontier_marker",
                    "project_label": "AIppocampus",
                    "frontier_type": "blocked",
                    "boundary_reason": "RAW_PRIVATE_SENTINEL boundary",
                    "source_refs": [self.source_ref("5")],
                },
            ],
        )
        (self.root / "associations.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "updated_at": "2026-04-01T00:00:00Z",
                    "terms": {"RAW_PRIVATE_SENTINEL": ["should not leak"]},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def reason_codes(self, payload: dict[str, object]) -> set[str]:
        return {str(item["reason_code"]) for item in payload.get("candidates", [])}

    def candidate_key(self, item: dict[str, object]) -> tuple[str, str, str]:
        return (
            str(item["reason_code"]),
            str(item["subject"]["kind"]),
            str(item["subject"]["id"]),
        )

    def test_dry_run_discovers_due_metadata_without_raw_text(self) -> None:
        self.write_due_sidecars()

        payload = time_maintenance.run_time_maintenance(
            registry_dir=self.root,
            cwd=self.cwd,
            now="2026-06-07T00:00:00Z",
            dry_run=True,
        )

        self.assertTrue(payload["dry_run"])
        self.assertEqual(
            self.reason_codes(payload),
            {
                "scheduled_revisit",
                "camped_journey_due",
                "stale_frontier",
                "dormant_question_due",
                "stale_association_cache",
                "health_preemptive_due",
            },
        )
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("RAW_PRIVATE_SENTINEL", encoded)
        self.assertNotIn(str(self.cwd), encoded)
        self.assertFalse((self.root / time_maintenance.CANDIDATES_FILE_NAME).exists())

    def test_cli_default_dry_run_emits_public_reason_codes(self) -> None:
        self.write_due_sidecars()

        with patch("sys.stdout", new=StringIO()) as stdout:
            code = time_maintenance.main(
                [
                    "--registry-dir",
                    str(self.root),
                    "--cwd",
                    str(self.cwd),
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertEqual(code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertIn("scheduled_revisit", payload["reason_codes"])
        self.assertNotIn("candidates", payload)
        self.assertNotIn("RAW_PRIVATE_SENTINEL", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_write_mode_materializes_same_bounded_candidates_and_cooldown_blocks_repeat(
        self,
    ) -> None:
        self.write_due_sidecars()

        dry_run = time_maintenance.run_time_maintenance(
            registry_dir=self.root,
            cwd=self.cwd,
            now="2026-06-07T00:00:00Z",
            dry_run=True,
        )
        written = time_maintenance.run_time_maintenance(
            registry_dir=self.root,
            cwd=self.cwd,
            now="2026-06-07T00:00:00Z",
            dry_run=False,
            cooldown_seconds=3600,
        )
        repeated = time_maintenance.run_time_maintenance(
            registry_dir=self.root,
            cwd=self.cwd,
            now="2026-06-07T00:10:00Z",
            dry_run=False,
            cooldown_seconds=3600,
        )

        rows = [
            json.loads(line)
            for line in (self.root / time_maintenance.CANDIDATES_FILE_NAME)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(written["written_count"], len(dry_run["candidates"]))
        self.assertEqual(
            {self.candidate_key(item) for item in rows},
            {self.candidate_key(item) for item in dry_run["candidates"]},
        )
        self.assertEqual(repeated["skipped"], "enqueue_cooldown")
        self.assertEqual(repeated["written_count"], 0)
        self.assertEqual(
            len(rows),
            len(
                (self.root / time_maintenance.CANDIDATES_FILE_NAME)
                .read_text(encoding="utf-8")
                .splitlines()
            ),
        )

    def test_active_scheduler_lease_blocks_time_driven_write(self) -> None:
        self.write_due_sidecars()
        state_file = self.root / "subconscious_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "projects": {
                        "AIppocampus": {
                            "lease_until_ts": 9_999_999_999,
                            "lease_id": "lease-existing",
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        payload = time_maintenance.run_time_maintenance(
            registry_dir=self.root,
            state_file=state_file,
            cwd=self.cwd,
            now="2026-06-07T00:00:00Z",
            dry_run=False,
        )

        self.assertEqual(payload["skipped"], "leased_projects")
        self.assertEqual(payload["written_count"], 0)
        self.assertFalse((self.root / time_maintenance.CANDIDATES_FILE_NAME).exists())

    def test_noop_healthy_workspace_stays_quiet_and_writes_nothing(self) -> None:
        self.registry.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:healthy",
                            "project_label": "Healthy",
                            "workspace_name": "Healthy",
                            "clean_turn_count": 1,
                            "clean_message_count": 2,
                            "updated_at": "2026-06-07T00:00:00Z",
                            "paths": {"workspace": str(self.cwd)},
                            "health": {"recommended_actions": []},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        payload = time_maintenance.run_time_maintenance(
            registry_dir=self.root,
            cwd=self.cwd,
            now="2026-06-07T00:00:00Z",
            dry_run=False,
        )

        self.assertEqual(payload["skipped"], "no_due_projects")
        self.assertEqual(payload["candidates"], [])
        self.assertFalse((self.root / time_maintenance.CANDIDATES_FILE_NAME).exists())

    def test_worker_task_queue_requires_enabled_cognitive_worker_mode(self) -> None:
        self.write_due_sidecars()

        with patch.dict(os.environ, {}, clear=True):
            disabled = time_maintenance.run_time_maintenance(
                registry_dir=self.root,
                cwd=self.cwd,
                now="2026-06-07T00:00:00Z",
                dry_run=False,
                enqueue_worker=True,
                state_file=self.root / "disabled-state.json",
            )

        queue_path = self.root / "agent_fallback_tasks.jsonl"
        self.assertEqual(disabled["cognitive_worker"]["resolved_mode"], "deterministic_only")
        self.assertEqual(disabled["agent_fallback_task_count"], 0)
        self.assertFalse(queue_path.exists())

        with patch.dict(os.environ, {"AIPPOCAMPUS_AGENT_FALLBACK_AVAILABLE": "1"}, clear=True):
            enabled = time_maintenance.run_time_maintenance(
                registry_dir=self.root,
                cwd=self.cwd,
                now="2026-06-07T01:00:00Z",
                dry_run=False,
                enqueue_worker=True,
                state_file=self.root / "enabled-state.json",
            )

        queued = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(enabled["cognitive_worker"]["resolved_mode"], "agent_fallback")
        self.assertGreater(enabled["agent_fallback_task_count"], 0)
        self.assertEqual(queued[0]["kind"], "agent_fallback_time_maintenance_task")
        self.assertNotIn("RAW_PRIVATE_SENTINEL", json.dumps(queued, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
