from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.contracts import executable_command_violations  # noqa: E402
from aippocampus_runtime.recall import agent_continuity, agent_continuity_cli_support  # noqa: E402


class AgentRecallApwFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.clean = self.root / ".aippocampus" / "clean-source"
        self.clean.mkdir(parents=True)
        self.registry = self.root / "registry"
        self.registry.mkdir()
        message = {
            "message_id": "msg-apw",
            "turn_id": "turn-apw",
            "turn_index": 4,
            "source_id": "src-apw",
            "source_line": 12,
            "role": "assistant",
            "phase": "final_answer",
            "is_final": True,
            "text": "Runtime notes: associative path walker can reopen a guarded source route.",
        }
        with (self.clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(message, ensure_ascii=False) + "\n")
        with (self.clean / "turns.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    {
                        "turn_id": "turn-apw",
                        "turn_index": 4,
                        "message_ids": ["msg-apw"],
                        "assistant_phase": "final_answer",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_jsonl(self, name: str, rows: list[dict[str, object]]) -> None:
        path = self.root / ".aippocampus" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _write_apw_sidecars(self, *, with_source_refs: bool = True) -> None:
        refs = (
            [
                {
                    "source_id": "src-apw",
                    "message_id": "msg-apw",
                    "turn_id": "turn-apw",
                    "turn_index": 4,
                }
            ]
            if with_source_refs
            else []
        )
        self._write_jsonl(
            "semantic-bridges.jsonl",
            [
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["黏菌", "联想回忆"],
                    "to_terms": ["associative path walker"],
                    "source_refs": refs,
                    "scope_bucket": "project",
                }
            ],
        )
        self._write_jsonl(
            "navigation-potential.jsonl",
            [
                {
                    "route_id": "route:apw",
                    "candidate_id": "bridge:apw",
                    "route_terms": ["associative path walker"],
                    "source_refs": refs,
                    "scope_bucket": "project",
                }
            ],
        )

    def _recall(self, *, include_apw: bool) -> dict[str, object]:
        return agent_continuity.recall(
            "黏菌 联想回忆 探索算法",
            cwd=self.root,
            clean_source_dir=self.clean,
            registry_dir=self.registry,
            include_associative_fallback=include_apw,
            associative_path_sidecar_dir=self.root / ".aippocampus",
        )

    def test_apw_fallback_is_gated_off_by_default(self) -> None:
        self._write_apw_sidecars()

        payload = self._recall(include_apw=False)

        self.assertEqual(payload["status"], "no_routes")
        self.assertIsNone(payload.get("associative_path_fallback"))
        self.assertEqual(payload["deepen_requests"], [])

    def test_opt_in_apw_fallback_becomes_request_index_source_reopen_action(self) -> None:
        self._write_apw_sidecars()

        payload = self._recall(include_apw=True)

        self.assertEqual(payload["status"], "no_routes")
        fallback = payload["associative_path_fallback"]
        self.assertIsInstance(fallback, dict)
        self.assertEqual(fallback["status"], "route_candidate")
        self.assertEqual(fallback["request_index"], 1)
        self.assertEqual(len(payload["deepen_requests"]), 1)

        cache_path = self.root / "last-recall.json"
        cache_written = agent_continuity_cli_support.write_last_recall_cache(
            payload["deepen_requests"],
            query="黏菌 联想回忆 探索算法",
            cwd=self.root,
            clean_source_dir=self.clean,
            registry_dir=self.registry,
            macro_state_path=None,
            project="AIppocampus",
            max_matches=5,
            schema_version=agent_continuity.SCHEMA_VERSION,
            path=cache_path,
        )
        selector_id = agent_continuity_cli_support.write_recall_selector_snapshot(cache_path)
        payload["last_recall_cache_available"] = cache_written
        payload["recall_selector_id"] = selector_id

        public = agent_continuity_cli_support.public_recall_projection(
            payload,
            query="黏菌 联想回忆 探索算法",
        )
        encoded = json.dumps(public, ensure_ascii=False, sort_keys=True)

        self.assertEqual(public["foreground_action"]["id"], "deepen_associative_path_fallback")
        self.assertEqual(public["foreground_action"]["tool_name"], "agent_deepen")
        self.assertEqual(public["foreground_action"]["arguments"]["request_index"], 1)
        self.assertEqual(public["foreground_action"]["arguments"]["recall_selector"], selector_id)
        self.assertIn("--recall-selector", public["foreground_action"]["command"])
        self.assertIn("associative_path_opt_in_fallback", public["foreground_action"]["route_choice_posture"])
        self.assertIn("search_registry_sources_for_original_cue_anchors", encoded)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("msg-apw", encoded)
        self.assertEqual(executable_command_violations(public), [])

        handle, _context = agent_continuity_cli_support.handle_from_last_recall_cache(
            request_index=1,
            path=cache_path,
        )
        deepened = agent_continuity.deepen(
            handle,
            cwd=self.root,
            clean_source_dir=self.clean,
            registry_dir=self.registry,
        )
        self.assertEqual(deepened["status"], "ok")
        self.assertGreater(deepened["result"]["source_window"]["message_count"], 0)

    def test_cli_apw_fallback_flag_returns_compact_action(self) -> None:
        self._write_apw_sidecars()
        env = {
            **os.environ,
            agent_continuity.LAST_RECALL_CACHE_ENV: str(self.root / "cli-last-recall.json"),
        }

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "黏菌 联想回忆 探索算法",
                "--cwd",
                str(self.root),
                "--clean-source-dir",
                str(self.clean),
                "--registry-dir",
                str(self.registry),
                "--apw-fallback",
                "--apw-sidecar-dir",
                str(self.root / ".aippocampus"),
                "--json",
            ],
            cwd=SCRIPTS,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertEqual(payload["foreground_action"]["id"], "deepen_associative_path_fallback")
        self.assertEqual(payload["associative_path_fallback"]["status"], "route_candidate")
        self.assertNotIn("source_refs", encoded)
        self.assertEqual(executable_command_violations(payload), [])

    def test_source_free_apw_bridge_abstains_instead_of_emitting_fake_action(self) -> None:
        self._write_apw_sidecars(with_source_refs=False)

        payload = self._recall(include_apw=True)

        fallback = payload["associative_path_fallback"]
        self.assertIsInstance(fallback, dict)
        self.assertEqual(fallback["status"], "abstained")
        self.assertIn("apw_no_route_candidate", fallback["reason_codes"])
        self.assertIn("source_free_candidates_will_evaporate", fallback["reason_codes"])
        self.assertEqual(payload["deepen_requests"], [])


if __name__ == "__main__":
    unittest.main()
