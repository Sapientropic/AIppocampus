from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"


class ContinuityDomainCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aippocampus_runtime.cli.facade", *args],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def write_registry(
        self,
        root: Path,
        *,
        thread_count: int,
    ) -> Path:
        registry_dir = root / "registry"
        registry_dir.mkdir()
        threads = []
        for index in range(thread_count):
            clean = root / f"clean-source-{index}"
            clean.mkdir()
            rows = [
                {
                    "message_id": f"msg-{index}-{line}",
                    "turn_id": f"turn-{index}-{line}",
                    "turn_index": line,
                    "source_line": line,
                    "phase": "final_answer",
                    "text": (
                        "provider orchestration continuity route needs "
                        "source-backed operator review before append publish"
                    ),
                }
                for line in (1, 2)
            ]
            (clean / "messages.jsonl").write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )
            threads.append(
                {
                    "thread_key": f"session:{index}",
                    "title": "provider orchestration continuity route",
                    "summary": "provider orchestration continuity route",
                    "project_label": "AIppocampus",
                    "paths": {"clean_source_dir": str(clean)},
                }
            )
        (registry_dir / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "updated_at": "2026-06-16T00:00:00Z",
                    "threads": threads,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return registry_dir

    def test_default_produce_json_is_bounded_preview_equivalent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_dir = self.write_registry(Path(tmp), thread_count=12)
            proc = self.run_cli(
                "continuity-domain",
                "--registry-dir",
                str(registry_dir),
                "produce",
                "--json",
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["detail"], "agent_preview")
        self.assertEqual(
            payload["preview_scan_policy"]["mode"],
            "foreground_bounded_default",
        )
        self.assertEqual(payload["metrics"]["registered_thread_count"], 12)
        self.assertEqual(payload["metrics"]["considered_thread_count"], 8)
        self.assertEqual(payload["metrics"]["scanned_thread_count"], 8)
        self.assertTrue(payload["metrics"]["scan_partial"])
        self.assertTrue(payload["candidate_previews"])
        self.assertIn("preview_boundary", payload)
        self.assertNotIn("candidate_events", payload)
        self.assertEqual(payload["mode"], "dry_run")

    def test_explicit_produce_scan_options_keep_operator_backfill_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir = self.write_registry(root, thread_count=12)
            events_path = root / "continuity-domain-events.jsonl"
            broad = self.run_cli(
                "continuity-domain",
                "--registry-dir",
                str(registry_dir),
                "produce",
                "--broad-scan",
                "--json",
            )
            bounded = self.run_cli(
                "continuity-domain",
                "--registry-dir",
                str(registry_dir),
                "produce",
                "--max-threads",
                "3",
                "--json",
            )
            append = self.run_cli(
                "continuity-domain",
                "--registry-dir",
                str(registry_dir),
                "produce",
                "--append",
                "--events-path",
                str(events_path),
                "--json",
            )

        self.assertEqual(broad.returncode, 0, broad.stderr)
        broad_payload = json.loads(broad.stdout)
        self.assertEqual(broad_payload["metrics"]["considered_thread_count"], 12)
        self.assertFalse(broad_payload["metrics"]["scan_partial"])
        self.assertNotIn("candidate_events", broad_payload)

        self.assertEqual(bounded.returncode, 0, bounded.stderr)
        bounded_payload = json.loads(bounded.stdout)
        self.assertEqual(bounded_payload["metrics"]["considered_thread_count"], 3)
        self.assertTrue(bounded_payload["metrics"]["scan_partial"])
        self.assertEqual(bounded_payload["scan_policy"]["max_threads"], 3)
        self.assertNotIn("candidate_events", bounded_payload)

        self.assertEqual(append.returncode, 0, append.stderr)
        append_payload = json.loads(append.stdout)
        self.assertEqual(append_payload["mode"], "append")
        self.assertEqual(append_payload["metrics"]["considered_thread_count"], 12)
        self.assertFalse(append_payload["metrics"]["scan_partial"])
        self.assertGreater(append_payload["write_report"]["appended_event_count"], 0)


if __name__ == "__main__":
    unittest.main()
