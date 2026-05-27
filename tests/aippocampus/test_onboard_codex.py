from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

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

import onboard_codex as onboard  # noqa: E402
import registry  # noqa: E402


class OnboardCodexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = self.root / "Project"
        self.cwd.mkdir()
        self.registry_dir = self.root / "registry"
        self.sessions = self.root / "sessions" / "2026" / "05" / "26"
        self.sessions.mkdir(parents=True)
        self.rollout = self.sessions / "rollout-test.jsonl"
        self._write_rollout()
        self.original_home = registry.codex_home
        registry.codex_home = lambda: self.root

    def tearDown(self) -> None:
        registry.codex_home = self.original_home
        self.tmp.cleanup()

    def _append(self, item: dict) -> None:
        with self.rollout.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _write_rollout(self) -> None:
        self._append(
            {
                "type": "session_meta",
                "payload": {
                    "id": "session-onboard",
                    "timestamp": "2026-05-26T03:00:00Z",
                    "cwd": str(self.cwd),
                    "originator": "Codex Desktop",
                },
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T03:00:01Z",
                "payload": {
                    "type": "user_message",
                    "message": "把全部 Codex 线程纳入 AIppocampus。",
                },
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T03:00:02Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "final_answer",
                    "message": "已注册为全局 clean-source 和索引。",
                },
            }
        )

    def test_dry_run_returns_agent_native_plan_without_writing(self) -> None:
        result = onboard.run_onboarding(
            cwd=self.cwd,
            registry_dir=self.registry_dir,
            dry_run=True,
            build_index=True,
            refresh_current=False,
            build_timeline=True,
            build_cognitive_map=True,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["dry_run"])
        self.assertEqual(result["data"]["plan"]["would_register_count"], 1)
        self.assertFalse((self.registry_dir / "threads.json").exists())
        self.assertIn("next", result)

    def test_onboarding_registers_indexes_and_returns_compact_stats(self) -> None:
        result = onboard.run_onboarding(
            cwd=self.cwd,
            registry_dir=self.registry_dir,
            dry_run=False,
            build_index=True,
            refresh_current=False,
            build_timeline=True,
            build_cognitive_map=True,
        )

        self.assertTrue(result["ok"])
        stats = result["data"]["stats_after"]
        self.assertEqual(stats["thread_count"], 1)
        self.assertEqual(stats["clean_source_count"], 1)
        self.assertEqual(stats["sqlite_index_count"], 1)
        self.assertEqual(stats["graph_json_count"], 1)
        self.assertEqual(result["data"]["actions"]["scan_sessions"]["registered_count"], 1)
        self.assertEqual(result["data"]["actions"]["cognitive_map"]["route_count"], 0)
        self.assertEqual(result["data"]["boundary"]["frontier"]["status"], "not_run")
        self.assertGreaterEqual(
            result["data"]["actions"]["project_timeline"]["life_label_count"], 1
        )
        self.assertTrue((self.registry_dir / "project_timeline.json").exists())

    def test_repair_detects_and_rebuilds_sqlite_stale_against_clean_source(self) -> None:
        initial = registry.register_rollout_thread(
            self.rollout,
            cwd=self.cwd,
            registry_dir=self.registry_dir,
            build_index=True,
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T03:00:03Z",
                "payload": {
                    "type": "user_message",
                    "message": "新增 clean-source 但旧 SQLite 还没有的 freshness marker。",
                },
            }
        )
        refreshed_clean_only = registry.register_rollout_thread(
            self.rollout,
            cwd=self.cwd,
            registry_dir=self.registry_dir,
            build_index=False,
        )
        self.assertEqual(
            initial["entry"]["paths"]["sqlite"], refreshed_clean_only["entry"]["paths"]["sqlite"]
        )

        stats = onboard.registry_stats(registry_dir=self.registry_dir)

        self.assertEqual(stats["stale_sqlite"], 1)
        self.assertIn("sqlite_index", stats["repair_artifacts"][0]["stale"])
        self.assertTrue(
            any(
                issue["code"] == "missing_clean_source_lines"
                for issue in stats["repair_artifacts"][0]["issues"]
            )
        )

        repair = onboard.repair_missing_artifacts(registry_dir=self.registry_dir, build_index=True)
        repaired_stats = onboard.registry_stats(registry_dir=self.registry_dir)

        self.assertEqual(repair["repaired_count"], 1)
        self.assertEqual(repaired_stats["stale_sqlite"], 0)

    def test_frontier_smoke_exposes_compact_sample_findings_and_infers_project(self) -> None:
        captured: dict[str, Any] = {}

        def fake_run_jobs(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {
                "job_count": 1,
                "successful_job_count": 1,
                "failure_count": 0,
                "finding_count": 3,
                "wrote": False,
                "jobs": [
                    {
                        "findings": [
                            {
                                "kind": "question_candidate",
                                "title": "Native CLI frontier",
                                "question_short": "native CLI frontier",
                                "question_text": "How should the onboarding command expose frontier smoke quality?",
                                "intent_orientation": "cli_design",
                                "phase_context": "pre-write smoke",
                                "confidence": 0.82,
                                "source_refs": [{"ref": "t0"}, {"ref": "o1"}],
                            },
                            {
                                "kind": "frontier_marker",
                                "title": "Long raw question gate",
                                "frontier_type": "scope_boundary",
                                "boundary_reason": "Overlong raw user excerpts should not be staged as question text.",
                                "confidence": 0.87,
                                "source_refs": [{"ref": "t1"}],
                            },
                            {
                                "kind": "frontier_marker",
                                "title": "Stale clean-source not automatically rewritten",
                                "frontier_type": "unresolved",
                                "boundary_reason": "旧 clean-source 注入块不会自动全量重写，除非跑 --refresh-registered。",
                                "confidence": 0.9,
                                "source_refs": [{"ref": "t2"}],
                            },
                        ]
                    }
                ],
            }

        old_run_jobs = onboard.run_jobs
        old_api_key = os.environ.get("DEEPSEEK_API_KEY")
        onboard.run_jobs = fake_run_jobs
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        try:
            result = onboard.run_onboarding(
                cwd=self.cwd,
                registry_dir=self.registry_dir,
                dry_run=False,
                build_index=True,
                refresh_current=False,
                build_timeline=True,
                build_cognitive_map=False,
                frontier_mode="smoke",
            )
        finally:
            onboard.run_jobs = old_run_jobs
            if old_api_key is None:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            else:
                os.environ["DEEPSEEK_API_KEY"] = old_api_key

        frontier = result["data"]["boundary"]["frontier"]
        self.assertEqual(captured["project"], "Project")
        self.assertEqual(frontier["project_scope"], "Project")
        self.assertEqual(frontier["sample_findings"][0]["kind"], "question_candidate")
        self.assertEqual(frontier["sample_findings"][0]["source_ref_count"], 2)
        self.assertNotIn("source_refs", frontier["sample_findings"][0])
        self.assertEqual(frontier["sample_findings"][1]["frontier_type"], "scope_boundary")
        self.assertEqual(frontier["raw_finding_count"], 3)
        self.assertEqual(frontier["finding_count"], 2)
        self.assertEqual(frontier["filtered_stale_count"], 1)
        self.assertNotIn(
            "refresh-registered", json.dumps(frontier["sample_findings"], ensure_ascii=False)
        )
        self.assertIn("Current onboarding state after maintenance", captured["objective"])
        self.assertIn("missing_clean=0", captured["objective"])

    def test_frontier_smoke_missing_deepseek_key_blocks_instead_of_skipping(self) -> None:
        old_api_key = os.environ.get("DEEPSEEK_API_KEY")
        os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            result = onboard.run_onboarding(
                cwd=self.cwd,
                registry_dir=self.registry_dir,
                dry_run=False,
                build_index=True,
                refresh_current=False,
                build_timeline=True,
                build_cognitive_map=False,
                frontier_mode="smoke",
            )
        finally:
            if old_api_key is None:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            else:
                os.environ["DEEPSEEK_API_KEY"] = old_api_key

        self.assertEqual(result["ok"], "partial")
        self.assertEqual(
            result["data"]["boundary"]["frontier"]["status"], "blocked_missing_api_key"
        )


if __name__ == "__main__":
    unittest.main()
